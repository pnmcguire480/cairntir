"""Portable origin and explicit derivation integrity on temporary stores."""

from __future__ import annotations

import hashlib
import json
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from cairntir import derivation, origin
from cairntir.access import bind_grant, issue_grant, revoke_grant
from cairntir.errors import CairntirError
from cairntir.mcp.backend import CairntirBackend
from cairntir.memory.consolidate import consolidate_room
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer, Layer
from cairntir.obsidian_bridge import sync_workspace
from cairntir.portable import export_bundle, import_bundle
from cairntir.provenance import Sensitivity, WriteProvenance

WING = "origin-derivation-test"
OLD = "Decision: use Postgres for the main datastore. Reason: team already runs it."
NEW = "Decision REVERSED: use SQLite for the main datastore. Reason: single-user local app."


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def evidence_contents(output):
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        records = []
        for line in output.splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                records.append(item)
    else:
        records = payload.get("evidence", [])
    return [record["content"] for record in records if isinstance(record.get("content"), str)]


@pytest.fixture
def stores(tmp_path, monkeypatch):
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path / "isolated-home"))
    with ExitStack() as stack:

        def create(name):
            return stack.enter_context(
                DrawerStore(tmp_path / f"{name}.db", HashEmbeddingProvider(dimension=32))
            )

        yield create


def add(store, content, *, room="database", metadata=None, layer=Layer.ON_DEMAND, **kwargs):
    return store.add(
        Drawer(
            wing=WING, room=room, content=content, metadata=metadata or {}, layer=layer, **kwargs
        )
    )


def api():
    return origin, derivation


def snapshot(store):
    tables = [
        row[0] for row in store._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    ]
    return {
        name: sorted(
            map(
                tuple,
                store._conn.execute('SELECT * FROM "' + name.replace('"', '""') + '"').fetchall(),  # noqa: S608 — quoted sqlite_master identifier
            ),
            key=repr,
        )
        for name in tables
    }


def correct(store, source, *, content=NEW, key=None):
    return json.loads(
        CairntirBackend(store).correct(
            wing=WING,
            source_drawer_id=source.id,
            source_identity=store.portable_identity(source.id),
            source_sha256=digest(source.content),
            content=content,
            idempotency_key=key or str(uuid4()),
        )
    )


def consolidated(store):
    source = add(store, OLD)
    add(store, "The local app has one user.")
    add(store, "The datastore must work offline.")
    derived = consolidate_room(store, wing=WING, room="database", min_cluster=3)
    assert derived is not None
    return source, derived


@pytest.mark.parametrize("wrong", ["identity", "source_store_id", "content_sha256"])
def test_guarded_get_refuses_foreign_expectation_before_disclosure_or_touch(stores, wrong):
    origin, _ = api()
    work, home = stores("work"), stores("home")
    foreign, local = add(work, "WORK PRIVATE CANARY"), add(home, "HOME PRIVATE CANARY")
    assert foreign.id == local.id
    ref = origin.origin_reference(home, local.id)
    good = json.loads(
        CairntirBackend(home).get(
            drawer_id=local.id,
            expected_identity=ref["identity"],
            expected_source_store_id=ref["source_store_id"],
            expected_content_sha256=ref["content_sha256"],
        )
    )
    assert good["content"] == local.content and good["origin_reference"] == ref
    bad = {**ref, wrong: origin.origin_reference(work, foreign.id)[wrong]}
    before = snapshot(home)
    with pytest.raises(CairntirError) as error:
        CairntirBackend(home).get(
            drawer_id=local.id,
            expected_identity=bad["identity"],
            expected_source_store_id=bad["source_store_id"],
            expected_content_sha256=bad["content_sha256"],
        )
    assert "HOME PRIVATE CANARY" not in str(error.value)
    assert "WORK PRIVATE CANARY" not in str(error.value)
    assert snapshot(home) == before


def test_portable_origin_resolves_remapped_import_and_numeric_only_never_falls_back(
    stores, tmp_path
):
    origin, _ = api()
    work, home = stores("work"), stores("home")
    source = add(work, "WORK DATABASE CANARY")
    collision = add(home, "HOME DATABASE CANARY")
    ref = origin.origin_reference(work, source.id)
    assert set(ref) == {"source_store_id", "source_drawer_id", "identity", "content_sha256"}
    assert ref["content_sha256"] == digest(source.content)
    assert origin.resolve_reference(home, {"source_drawer_id": source.id}) == {
        "status": "unresolved"
    }
    assert origin.resolve_reference(home, ref) == {"status": "unresolved"}
    linked = add(work, f"Historical citation cairntir://drawer/{source.id}", room="links")
    path = tmp_path / "bundle.json"
    export_bundle(work, path, drawer_ids=[linked.id])
    receipt = import_bundle(home, path)
    local_id = receipt["identity_map"][ref["identity"]]
    assert local_id != collision.id
    assert origin.resolve_reference(home, ref) == {
        "status": "resolved",
        "drawer_id": local_id,
        "reference": ref,
    }
    local_link = receipt["identity_map"][work.portable_identity(linked.id)]
    assert home.get(local_link).content == linked.content
    assert home.portable_relations(local_link)[0]["target_drawer_id"] == local_id
    assert home.portable_source(local_id) == work.portable_source(source.id)
    before_count = len(home.list_by(limit=None, include_expired=True))
    replay = import_bundle(home, path)
    assert replay["identity_map"] == receipt["identity_map"]
    assert len(home.list_by(limit=None, include_expired=True)) == before_count
    for changed in (
        {"identity": str(uuid4())},
        {"source_store_id": str(uuid4())},
        {"content_sha256": "0" * 64},
    ):
        assert origin.resolve_reference(home, {**ref, **changed}) == {"status": "unresolved"}


def test_known_foreign_uri_capture_is_atomic_refusal_and_same_origin_preserves_text(stores):
    origin, _ = api()
    work, home = stores("work"), stores("home")
    foreign, local = add(work, "WORK"), add(home, "HOME")
    text = f"Work handoff quotes cairntir://drawer/{foreign.id}."
    before = snapshot(home)
    with pytest.raises(CairntirError, match=r"(?i)portable.*import|import.*portable"):
        CairntirBackend(home).remember(
            wing=WING,
            room="capture",
            content=text,
            reference_origin=origin.origin_reference(work, foreign.id)["source_store_id"],
        )
    assert snapshot(home) == before
    local_text = f"Home-authored reference cairntir://drawer/{local.id}."
    CairntirBackend(home).remember(
        wing=WING,
        room="capture",
        content=local_text,
        reference_origin=home.portable_store_identity(),
    )
    saved = home.list_by(wing=WING, room="capture", limit=None)[0]
    assert saved.content == local_text
    assert home.portable_relations(saved.id)[0]["target_drawer_id"] == local.id


def test_corrected_consolidation_withheld_from_working_views_but_history_preserved(stores):
    _, derivation = api()
    store = stores("corrected")
    source, derived = consolidated(store)
    backend = CairntirBackend(store)
    original = store.portable_source(derived.id)
    assert derivation.derivation_status(store, derived.id)["status"] == "current"
    assert derived.content in evidence_contents(backend.handoff(wing=WING, budget_chars=40000))
    key = str(uuid4())
    receipt = correct(store, source, key=key)
    replay = correct(store, source, key=key)
    assert replay["replayed"] and replay["correction_drawer_id"] == receipt["correction_drawer_id"]
    historical = json.loads(backend.get(drawer_id=derived.id))
    assert historical["content"] == derived.content
    assert historical["derivation"]["status"] == "needs_review"
    assert "source_superseded" in historical["derivation"]["reasons"]
    assert store.portable_source(derived.id) == original
    assert store.get(source.id).content == OLD
    outputs = [
        backend.handoff(wing=WING, budget_chars=40000),
        backend.handoff(wing=WING, task="main datastore", budget_chars=40000),
        backend.recall(
            query="main datastore", wing=WING, limit=20, full_content=20, budget_chars=40000
        ),
        backend.recall_bounded(
            query="main datastore", wing=WING, limit=20, full_content=20, budget_chars=40000
        ),
    ]
    for output in outputs:
        assert derived.content not in output
        assert "Consolidated from 3 drawers:" not in output
        assert NEW in output


def test_explicit_transitive_dependency_propagates_but_generic_citation_does_not(stores):
    _, derivation = api()
    store = stores("transitive")
    source = add(store, OLD)
    first = add(
        store, "FIRST DERIVED CANARY", metadata={"derived_from": [source.id]}, layer=Layer.ESSENTIAL
    )
    second = add(
        store, "SECOND DERIVED CANARY", metadata={"derived_from": [first.id]}, layer=Layer.ESSENTIAL
    )
    citation = add(
        store,
        "CITATION REMAINS ELIGIBLE",
        metadata={"evidence_ids": [source.id]},
        layer=Layer.ESSENTIAL,
    )
    correct(store, source)
    assert derivation.derivation_status(store, first.id)["status"] == "needs_review"
    assert derivation.derivation_status(store, second.id)["status"] == "needs_review"
    assert derivation.derivation_status(store, citation.id)["status"] == "not_derived"
    view = CairntirBackend(store).handoff(wing=WING, budget_chars=40000)
    assert first.content not in view and second.content not in view and citation.content in view


def test_imported_explicit_derivation_uses_uuid_map_not_colliding_source_integer(stores, tmp_path):
    _, derivation = api()
    work, home = stores("work"), stores("home")
    source = add(work, OLD)
    derived = add(
        work, "WORK DERIVED CANARY", metadata={"derived_from": [source.id]}, layer=Layer.ESSENTIAL
    )
    collision = add(home, "HOME COLLISION REMAINS CURRENT")
    path = tmp_path / "derived.json"
    export_bundle(work, path, drawer_ids=[derived.id])
    receipt = import_bundle(home, path)
    mapped_source = receipt["identity_map"][work.portable_identity(source.id)]
    mapped_derived = receipt["identity_map"][work.portable_identity(derived.id)]
    assert home.portable_source(mapped_derived)["drawer"]["metadata"]["derived_from"] == [source.id]
    assert mapped_source != collision.id
    add(home, NEW, supersedes_id=mapped_source)
    state = derivation.derivation_status(home, mapped_derived)
    assert state["status"] == "needs_review" and "source_superseded" in state["reasons"]
    assert derivation.derivation_status(home, collision.id)["status"] == "not_derived"
    assert home.get(collision.id).content == collision.content


def test_missing_and_hidden_dependency_are_unknown_without_disclosure(stores):
    origin, derivation = api()
    store = stores("visibility")
    hidden = add(store, "HIDDEN SOURCE CANARY", room="secret")
    visible = add(
        store,
        "VISIBLE DERIVATION",
        room="public",
        metadata={"derived_from": [hidden.id]},
        layer=Layer.ESSENTIAL,
    )
    missing = add(
        store,
        "MISSING DERIVATION",
        room="public",
        metadata={"derived_from": [999999]},
        layer=Layer.ESSENTIAL,
    )
    token = issue_grant(store, scopes=[{"wing": WING, "rooms": ["public"]}], capabilities=["read"])
    scoped = bind_grant(store, token)
    for target, reader in ((visible, scoped), (missing, store)):
        before = snapshot(store)
        state = derivation.derivation_status(reader, target.id)
        assert state == {"status": "unknown", "reasons": ["source_unavailable"], "sources": []}
        assert snapshot(store) == before
        assert "HIDDEN SOURCE CANARY" not in json.dumps(state)
        assert store.portable_identity(hidden.id) not in json.dumps(state)
    ref = origin.origin_reference(store, hidden.id)
    assert origin.resolve_reference(scoped, ref) == {"status": "unresolved"}
    assert visible.content not in CairntirBackend(scoped).handoff(wing=WING, budget_chars=40000)
    revoke_grant(store, token)
    assert origin.resolve_reference(scoped, ref) == {"status": "unresolved"}
    cyclic_store = stores("self-derivation")
    cyclic = add(
        cyclic_store,
        "CYCLIC DERIVATION CANARY",
        metadata={"derived_from": [1]},
        layer=Layer.ESSENTIAL,
    )
    assert cyclic.id == 1
    references = cyclic_store.portable_relations(cyclic.id)
    assert len(references) == 1
    assert references[0]["path"] == "/metadata/derived_from/0"
    assert references[0]["target_drawer_id"] == cyclic.id
    assert references[0]["target_identity"] == cyclic_store.portable_identity(cyclic.id)
    assert derivation.derivation_status(cyclic_store, cyclic.id)["status"] == "unknown"


def test_forked_and_expired_dependencies_never_become_current(stores):
    _, derivation = api()
    store = stores("conflict")
    source = add(store, OLD)
    derived = add(
        store, "FORK DERIVED CANARY", metadata={"derived_from": [source.id]}, layer=Layer.ESSENTIAL
    )
    add(store, NEW, supersedes_id=source.id)
    add(store, "Decision: use DuckDB for the main datastore.", supersedes_id=source.id)
    state = derivation.derivation_status(store, derived.id)
    assert state["status"] == "needs_review" and "source_conflict" in state["reasons"]
    expired = store.add(
        Drawer(wing=WING, room="expired", content="EXPIRED SOURCE"),
        provenance=WriteProvenance.create(
            host="fixture",
            capture_path="acceptance",
            valid_until=datetime.now(UTC) - timedelta(days=1),
        ),
    )
    expired_derived = add(
        store,
        "EXPIRED DERIVED CANARY",
        metadata={"derived_from": [expired.id]},
        layer=Layer.ESSENTIAL,
    )
    assert derivation.derivation_status(store, expired_derived.id)["status"] == "unknown"


def test_origin_and_derivation_reads_are_read_only_and_secret_inputs_unavailable(stores):
    origin, derivation = api()
    store = stores("read-only")
    source, derived = consolidated(store)
    secret = store.add(
        Drawer(wing=WING, room="secret", content="SECRET CONTENT CANARY"),
        provenance=WriteProvenance.create(
            host="fixture", capture_path="acceptance", sensitivity=Sensitivity.SECRET
        ),
    )
    protected = add(
        store,
        "PUBLIC DERIVED SECRET",
        metadata={"derived_from": [secret.id]},
        layer=Layer.ESSENTIAL,
    )
    before = snapshot(store)
    ref = origin.origin_reference(store, source.id)
    assert origin.resolve_reference(store, ref)["status"] == "resolved"
    assert derivation.derivation_status(store, derived.id)["status"] == "current"
    state = derivation.derivation_status(store, protected.id)
    assert state == {"status": "unknown", "reasons": ["source_unavailable"], "sources": []}
    assert snapshot(store) == before


def test_owned_obsidian_view_marks_derivation_review_and_preserves_human_text(stores, tmp_path):
    store = stores("obsidian")
    source, derived = consolidated(store)
    citation = add(
        store,
        "INDEPENDENT CITATION",
        room="notes",
        metadata={"evidence_ids": [source.id]},
        layer=Layer.ESSENTIAL,
    )
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    assert sync_workspace(store, vault=vault, wing=WING)["projection"]["status"] == "complete"
    note = vault / "cairntir-sync" / "memory" / f"drawer-{derived.id}.md"
    human = "\nHUMAN NOTES CANARY: keep this exact text.\n"
    with note.open("a", encoding="utf-8") as stream:
        stream.write(human)
    original = store.portable_source(derived.id)
    receipt = correct(store, source)
    assert sync_workspace(store, vault=vault, wing=WING)["projection"]["status"] == "complete"
    text = note.read_text(encoding="utf-8")
    assert text.endswith(human) and derived.content in text
    assert "Derivation: needs_review" in text and "Status: Historical or inactive" in text
    assert f"drawer-{source.id}" in text and f"drawer-{receipt['correction_drawer_id']}" in text
    workspace = json.loads((vault / "cairntir-sync" / "workspace.json").read_text(encoding="utf-8"))
    entries = {entry["drawer_id"]: entry for entry in workspace["drawers"]}
    assert (
        not entries[derived.id]["current"]
        and entries[derived.id]["derivation"]["status"] == "needs_review"
    )
    assert entries[citation.id]["current"]
    assert store.portable_source(derived.id) == original
