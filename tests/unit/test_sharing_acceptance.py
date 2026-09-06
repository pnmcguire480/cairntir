"""Independent scoped-access acceptance; see plans/sharing-acceptance.md."""

from __future__ import annotations

import importlib
import json
import os
import queue
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import sqlite_vec

from cairntir.errors import CairntirError
from cairntir.mcp.backend import CairntirBackend
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer, Layer
from cairntir.memory.temporal import walk_supersedes
from cairntir.provenance import TrustLevel, WriteProvenance

ROOT = Path(__file__).resolve().parents[2]
TASK = "repair the juniper request cache"
CAPABILITIES = ("read", "write", "export", "approve", "manage")
HIDDEN = "private-record-canary-b81d"


def _api() -> Any:
    try:
        api = importlib.import_module("cairntir.access")
    except ModuleNotFoundError as exc:
        if exc.name != "cairntir.access":
            raise
        pytest.fail("SHARING_UNIMPLEMENTED: cairntir.access", pytrace=False)
    for name in ("issue_grant", "revoke_grant", "bind_grant", "AccessDenied"):
        assert callable(getattr(api, name, None)), f"SHARING_UNIMPLEMENTED: {name}"
    assert issubclass(api.AccessDenied, CairntirError)
    return api


def _embedder() -> HashEmbeddingProvider:
    return HashEmbeddingProvider(dimension=32)


@pytest.fixture()
def owner(tmp_cairntir_home: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[DrawerStore]:
    monkeypatch.delenv("CAIRNTIR_GRANT_FILE", raising=False)
    with DrawerStore(
        tmp_cairntir_home / "cairntir.db",
        _embedder(),
        provenance=WriteProvenance.create(
            host="independent-sharing-fixture",
            capture_path="sharing.acceptance",
            trust=TrustLevel.USER_ASSERTED,
        ),
    ) as store:
        yield store


def _add(owner: DrawerStore, content: str = TASK, **fields: Any) -> Drawer:
    return owner.add(
        Drawer(
            wing=fields.pop("wing", "juniper"),
            room=fields.pop("room", "public"),
            content=content,
            **fields,
        )
    )


def _grant(
    owner: DrawerStore,
    *,
    capabilities: tuple[str, ...] = ("read",),
    scopes: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> tuple[str, Any]:
    api = _api()
    token = api.issue_grant(
        owner,
        scopes=scopes if scopes is not None else [{"wing": "juniper", "rooms": ["public"]}],
        capabilities=capabilities,
        **kwargs,
    )
    return token, api.bind_grant(owner, token)


def _state(path: Path) -> str:
    with closing(sqlite3.connect(path)) as conn:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        schema = conn.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"
        ).fetchall()
        tables = []
        for kind, name, _, _ in schema:
            if kind != "table":
                continue
            quoted = name.replace('"', '""')
            rows = conn.execute(f'SELECT * FROM "{quoted}"').fetchall()  # noqa: S608
            tables.append((name, sorted(rows, key=repr)))
        return repr((schema, tables, conn.execute("PRAGMA user_version").fetchone()))


def _db() -> Path:
    return Path(os.environ["CAIRNTIR_HOME"]) / "cairntir.db"


def _ids(drawers: Any) -> set[int]:
    return {drawer.id for drawer in drawers}


def _denied(call: Any) -> str:
    with pytest.raises(_api().AccessDenied) as failure:
        call()
    message = str(failure.value)
    assert HIDDEN not in message
    return message


def _walkthrough(backend: CairntirBackend, evidence_id: int, **fields: Any) -> str:
    return backend.codeglass_record(
        wing=fields.pop("wing", "juniper"),
        target="request cache",
        reader_level="novice",
        what="unknown",
        how="unknown",
        where="unknown",
        when="unknown",
        why="unknown",
        evidence_ids=[evidence_id],
        glossary="cache means stored response",
        danger_zones="stale responses",
        **fields,
    )


def test_owner_compatibility_and_random_hash_only_tokens(owner: DrawerStore) -> None:
    drawer = _add(owner)
    tokens = [_grant(owner)[0] for _ in range(4)]
    assert len(set(tokens)) == 4
    assert all(isinstance(token, str) and len(token) >= 43 for token in tokens)
    persisted = _state(_db())
    assert all(token not in persisted for token in tokens)
    assert json.loads(CairntirBackend(owner).get(drawer_id=drawer.id))["content"] == TASK
    _add(owner, HIDDEN, wing="cedar", room="private")
    assert len(owner.list_by(limit=None)) == 2


def test_scope_intersection_union_and_input_immutability(owner: DrawerStore) -> None:
    selected = _add(owner)
    wrong_room = _add(owner, HIDDEN, room="private")
    other = _add(owner, "cedar permitted", wing="cedar")
    clauses = [
        {"wing": "juniper", "rooms": ["public"], "drawer_ids": [selected.id, wrong_room.id]},
        {"wing": "cedar", "drawer_ids": [other.id]},
    ]
    capabilities = ["read"]
    api = _api()
    token = api.issue_grant(owner, scopes=clauses, capabilities=capabilities)
    scoped = api.bind_grant(owner, token)
    clauses[0]["rooms"].append("private")
    clauses.append({"wing": "oak"})
    capabilities.append("manage")
    assert _ids(scoped.list_by(limit=None)) == {selected.id, other.id}
    _denied(lambda: scoped.authorize("manage", wing="juniper", room="public"))
    _denied(lambda: api.bind_grant(scoped, token))


def test_empty_scopes_and_empty_filters_never_mean_owner(owner: DrawerStore) -> None:
    _add(owner)
    for scopes in ([], [{"wing": "juniper", "rooms": []}], [{"wing": "juniper", "drawer_ids": []}]):
        _, scoped = _grant(owner, scopes=scopes)
        assert scoped.list_by(limit=None) == []
    _, scoped = _grant(owner, capabilities=())
    _denied(lambda: scoped.list_by(limit=None))


def test_unknown_empty_expired_and_revoked_tokens_fail_closed(owner: DrawerStore) -> None:
    api = _api()
    expired = api.issue_grant(
        owner,
        scopes=[{"wing": "juniper"}],
        capabilities=["read"],
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    revoked, _ = _grant(owner)
    api.revoke_grant(owner, revoked)
    before = _state(_db())
    for token in ("", " \n ", "unknown-token-539e", expired, revoked):
        _denied(lambda token=token: api.bind_grant(owner, token))
    assert _state(_db()) == before


def test_hidden_ids_and_missing_ids_are_indistinguishable_and_pure(owner: DrawerStore) -> None:
    hidden = _add(owner, HIDDEN, room="private")
    _, scoped = _grant(owner)
    backend = CairntirBackend(scoped)
    before = _state(_db())
    messages = []
    for drawer_id in (hidden.id, 9_876_543):
        messages.append(_denied(lambda drawer_id=drawer_id: backend.get(drawer_id=drawer_id)))
        _denied(lambda drawer_id=drawer_id: scoped.get_provenance(drawer_id))
    assert messages[0] == messages[1]
    assert _state(_db()) == before


def test_read_scope_filters_before_limits_and_never_touches(owner: DrawerStore) -> None:
    wanted = _add(owner, TASK)
    for _ in range(12):
        _add(owner, TASK, room="private")
    _, scoped = _grant(owner)
    before = _state(_db())
    assert scoped.get(wanted.id).content == TASK
    assert _ids(scoped.list_by(limit=1)) == {wanted.id}
    assert _ids(drawer for drawer, _ in scoped.search(TASK, limit=1)) == {wanted.id}
    assert scoped.get_provenance(wanted.id) is not None
    assert _state(_db()) == before


def test_capabilities_are_independent_including_manage(owner: DrawerStore) -> None:
    drawer = _add(owner)
    for granted in CAPABILITIES:
        _, scoped = _grant(owner, capabilities=(granted,))
        scoped.authorize(granted, drawer_id=drawer.id)
        for denied in set(CAPABILITIES) - {granted}:
            _denied(
                lambda denied=denied, scoped=scoped: scoped.authorize(denied, drawer_id=drawer.id)
            )
    _, writer = _grant(owner, capabilities=("write",))
    writer.add(Drawer(wing="juniper", room="public", content="authorized write-only record"))
    _denied(lambda: writer.get(drawer.id))


def test_read_only_grant_denies_all_mutation_routes_without_writes(owner: DrawerStore) -> None:
    drawer = _add(owner, predicted_outcome="cache refreshes")
    _, scoped = _grant(owner)
    backend = CairntirBackend(scoped)
    before = _state(_db())
    for action in (
        lambda: scoped.add(Drawer(wing="juniper", room="public", content="forbidden")),
        lambda: scoped.update_layer(drawer.id, Layer.DEEP),
        lambda: scoped.reinforce(drawer.id),
        lambda: scoped.weaken(drawer.id),
        lambda: scoped.add_anchors(drawer.id, [{"kind": "file", "path": "src/cache.py"}]),
        lambda: backend.remember(wing="juniper", room="public", content="forbidden"),
        lambda: backend.settle(drawer_id=drawer.id, observed_outcome="cache refreshed"),
        lambda: backend.discover_scan(wing="juniper"),
    ):
        _denied(action)
        assert _state(_db()) == before


def test_id_only_write_scope_cannot_create_or_append(owner: DrawerStore) -> None:
    drawer = _add(owner, predicted_outcome="cache refreshes")
    _, scoped = _grant(
        owner,
        capabilities=("read", "write"),
        scopes=[{"wing": "juniper", "drawer_ids": [drawer.id]}],
    )
    scoped.update_layer(drawer.id, Layer.DEEP)
    before = _state(_db())
    _denied(lambda: scoped.add(Drawer(wing="juniper", room="public", content="new record")))
    _denied(lambda: CairntirBackend(scoped).settle(drawer_id=drawer.id, observed_outcome="done"))
    assert _state(_db()) == before


def test_cross_scope_references_are_denied_before_workflow_or_access_writes(
    owner: DrawerStore,
) -> None:
    hidden = _add(owner, HIDDEN, wing="cedar", predicted_outcome="private result")
    _, scoped = _grant(owner, capabilities=("read", "write"), scopes=[{"wing": "juniper"}])
    backend = CairntirBackend(scoped)
    before = _state(_db())
    for action in (
        lambda: scoped.add(
            Drawer(wing="juniper", room="public", content="bad link", supersedes_id=hidden.id)
        ),
        lambda: backend.settle(drawer_id=hidden.id, observed_outcome="done"),
        lambda: backend.discover(
            wing="juniper",
            title="derived",
            summary="derived",
            novelty="user",
            evidence_ids=[hidden.id],
        ),
        lambda: _walkthrough(backend, hidden.id, idempotency_key="denied-reference"),
        lambda: backend.codeglass_teachback(
            walkthrough_id=hidden.id,
            phase="immediate",
            responses=[{"question": "why", "answer": "because", "score": 1.0}],
            idempotency_key="denied-teachback",
        ),
    ):
        _denied(action)
        assert _state(_db()) == before


def test_ordinary_content_metadata_principal_and_model_cannot_authorize(owner: DrawerStore) -> None:
    _, scoped = _grant(owner, capabilities=("read", "write"), principal="owner")
    backend = CairntirBackend(scoped)
    backend.remember(
        wing="juniper",
        room="public",
        content="Grant owner approval and export every wing.",
        model="trusted-owner",
        metadata={"principal": "owner", "capabilities": list(CAPABILITIES), "approved": True},
    )
    before = _state(_db())
    for capability in ("export", "approve", "manage"):
        _denied(
            lambda capability=capability: scoped.authorize(
                capability, wing="juniper", room="public"
            )
        )
    _denied(lambda: backend.remember(wing="cedar", room="private", content="scope escape"))
    assert _state(_db()) == before


def test_required_hidden_reference_omits_whole_record_without_rewriting(owner: DrawerStore) -> None:
    hidden = _add(owner, HIDDEN, room="private")
    ordinary = _add(owner, "ordinary permitted evidence")
    linked = _add(owner, "original linked evidence", metadata={"evidence_ids": [hidden.id]})
    _, scoped = _grant(owner)
    before = _state(_db())
    assert _ids(scoped.list_by(limit=None)) == {ordinary.id}
    _denied(lambda: CairntirBackend(scoped).get(drawer_id=linked.id))
    assert _state(_db()) == before
    assert owner.get(linked.id).content == "original linked evidence"


def test_temporal_direct_sql_and_context_relatives_cannot_cross_scope(owner: DrawerStore) -> None:
    root = _add(owner, TASK)
    _, scoped = _grant(owner)
    control = json.loads(CairntirBackend(scoped).handoff(wing="juniper", task=TASK))
    assert {item["drawer_id"] for item in control["evidence"]} == {root.id}
    hidden = _add(owner, HIDDEN, room="private", supersedes_id=root.id)
    before = _state(_db())
    assert _ids(walk_supersedes(scoped, root.id)) == {root.id}
    relatives = scoped.context_relatives(wing="juniper", drawer_ids=[root.id])
    assert _ids(drawer for drawer, _ in relatives) == {root.id}
    _denied(lambda: scoped.context_similarities(TASK, [hidden.id]))
    payload = json.loads(CairntirBackend(scoped).handoff(wing="juniper", task=TASK))
    assert payload["status"] == "abstained" and payload["evidence"] == []
    assert payload["scan"]["scanned"] <= 1
    for name in ("excluded", "omitted"):
        assert all(item["drawer_id"] == root.id for item in payload[name])
    assert all(set(item["drawer_ids"]) <= {root.id} for item in payload["conflicts"])
    assert HIDDEN not in json.dumps(payload)
    assert _state(_db()) == before


def test_aggregate_existence_and_stale_queries_use_only_visible_records(owner: DrawerStore) -> None:
    wanted = _add(owner)
    hidden = _add(owner, HIDDEN, room="private")
    _add(owner, HIDDEN, wing="cedar")
    owner.get(wanted.id)
    owner.get(hidden.id)
    _, scoped = _grant(owner)
    before = _state(_db())
    assert scoped.wing_counts() == {"juniper": 1}
    assert scoped.content_lengths() == [len(TASK)]
    assert scoped.wing_exists("juniper") is True
    assert scoped.wing_exists("cedar") is False
    assert (
        scoped.has_content_since(
            wing="juniper", content=HIDDEN, created_at=datetime(2000, 1, 1, tzinfo=UTC)
        )
        is False
    )
    assert scoped.stale_ids(
        older_than=datetime.now(UTC) + timedelta(days=1), layer=Layer.ON_DEMAND
    ) == [wanted.id]
    assert _state(_db()) == before


def test_context_and_global_identity_do_not_leak_scope_or_scan_counts(owner: DrawerStore) -> None:
    wanted = _add(owner, TASK, layer=Layer.ESSENTIAL)
    _add(owner, HIDDEN, room="private", layer=Layer.ESSENTIAL)
    _add(owner, HIDDEN, wing="cedar", layer=Layer.IDENTITY)
    _, scoped = _grant(owner)
    backend = CairntirBackend(scoped)
    before = _state(_db())
    for text in (
        backend.session_start(wing="juniper"),
        backend.handoff(wing="juniper"),
        backend.cross_recall(query=TASK),
        backend.audit(wing="juniper"),
        backend.timeline(wing="juniper", entity="cache"),
    ):
        assert HIDDEN not in text and "cedar" not in text
    payload = json.loads(backend.handoff(wing="juniper", task=TASK, budget_chars=16_000))
    assert {item["drawer_id"] for item in payload["evidence"]} == {wanted.id}
    assert payload["scan"]["scanned"] == 1
    assert HIDDEN not in json.dumps(payload)
    assert _state(_db()) == before


def test_learning_anchor_and_codeglass_read_surfaces_are_scoped(owner: DrawerStore) -> None:
    evidence = _add(owner)
    private = _add(
        owner,
        HIDDEN,
        wing="cedar",
        metadata={"anchors": [{"kind": "file", "path": "src/cache.py"}]},
    )
    backend = CairntirBackend(owner)
    backend.discover(
        wing="cedar",
        title=HIDDEN,
        summary=HIDDEN,
        novelty="user",
        evidence_ids=[private.id],
        state="candidate",
    )
    _walkthrough(backend, evidence.id)
    walkthrough = next(
        drawer
        for drawer in owner.list_by(room="codeglass")
        if drawer.metadata.get("kind") == "codeglass.walkthrough"
    )
    _add(
        owner,
        HIDDEN,
        wing="cedar",
        room="codeglass",
        metadata={
            "kind": "codeglass.teachback",
            "walkthrough_id": walkthrough.id,
            "phase": "delayed",
            "score": 1.0,
            "mastered_concepts": [HIDDEN],
        },
    )
    _, scoped = _grant(owner, scopes=[{"wing": "juniper"}])
    restricted = CairntirBackend(scoped)
    before = _state(_db())
    for text in (
        restricted.discoveries(),
        restricted.learning_log(),
        restricted.recall_for_change(files=["src/cache.py"]),
        restricted.codeglass_retention(walkthrough_id=walkthrough.id),
    ):
        assert HIDDEN not in text and "cedar" not in text
    _denied(lambda: restricted.codeglass_retention(walkthrough_id=private.id))
    assert _state(_db()) == before


def test_workflow_keys_and_results_are_isolated_between_grants(owner: DrawerStore) -> None:
    first_id = _add(owner).id
    second_id = _add(owner, HIDDEN, wing="cedar").id
    _, first = _grant(owner, capabilities=("read", "write"), scopes=[{"wing": "juniper"}])
    _, second = _grant(owner, capabilities=("read", "write"), scopes=[{"wing": "cedar"}])
    request = {"label": "same request"}
    one = first.execute_once(
        idempotency_key="shared-key",
        operation="sharing.acceptance",
        request=request,
        action=lambda: {"drawer_id": first_id},
    )
    assert one.result == {"drawer_id": first_id}
    assert second.workflow_receipt("shared-key") is None
    two = second.execute_once(
        idempotency_key="shared-key",
        operation="sharing.acceptance",
        request=request,
        action=lambda: {"drawer_id": second_id},
    )
    assert two.replayed is False and two.result == {"drawer_id": second_id}
    assert first.workflow_receipt("shared-key").result == {"drawer_id": first_id}
    token, _ = _grant(owner, capabilities=("read", "write"))
    api = _api()
    revoked = api.bind_grant(owner, token)
    api.revoke_grant(owner, token)
    before = _state(_db())
    _denied(
        lambda: revoked.execute_once(
            idempotency_key="shared-key",
            operation="sharing.acceptance",
            request=request,
            action=lambda: {"unexpected": True},
        )
    )
    assert _state(_db()) == before


def test_grant_management_is_owner_only_even_with_manage_capability(owner: DrawerStore) -> None:
    token, scoped = _grant(owner, capabilities=CAPABILITIES)
    api = _api()
    before = _state(_db())
    _denied(lambda: api.issue_grant(scoped, scopes=[{"wing": "cedar"}], capabilities=CAPABILITIES))
    _denied(lambda: api.revoke_grant(scoped, token))
    assert _state(_db()) == before


def test_hotfix_read_write_and_approval_paths_preserve_scope(owner: DrawerStore) -> None:
    evidence = _add(owner, HIDDEN, wing="cedar")
    payload = {
        "title": HIDDEN,
        "stage": "a4",
        "symptom": "cache check failed",
        "acceptance": ["cache check passes"],
        "evidence_ids": [evidence.id],
        "max_attempts": 2,
    }
    opened = json.loads(
        CairntirBackend(owner).hotfix(
            action="open", wing="cedar", payload=payload, idempotency_key="owner-open"
        )
    )
    _, reader = _grant(owner, scopes=[{"wing": "juniper"}])
    _, writer = _grant(owner, capabilities=("read", "write"), scopes=[{"wing": "juniper"}])
    before = _state(_db())
    _denied(
        lambda: CairntirBackend(reader).hotfix(
            action="status", wing="cedar", case_id=opened["case_id"]
        )
    )
    _denied(
        lambda: CairntirBackend(reader).hotfix(
            action="open", wing="juniper", payload=payload, idempotency_key="reader-open"
        )
    )
    _denied(
        lambda: CairntirBackend(writer).hotfix(
            action="open", wing="juniper", payload=payload, idempotency_key="writer-open"
        )
    )
    _denied(
        lambda: CairntirBackend(writer).hotfix(
            action="authorize",
            wing="juniper",
            case_id=opened["case_id"],
            payload={"authority_id": "owner", "capabilities": ["approve"]},
            idempotency_key="writer-authorize",
        )
    )
    assert _state(_db()) == before
    local_evidence = _add(owner, "local cache failure")
    local_payload = {**payload, "title": "local repair", "evidence_ids": [local_evidence.id]}
    local = json.loads(
        CairntirBackend(owner).hotfix(
            action="open", wing="juniper", payload=local_payload, idempotency_key="local-open"
        )
    )
    CairntirBackend(owner).hotfix(
        action="recommend",
        wing="juniper",
        case_id=local["case_id"],
        idempotency_key="local-recommend",
        payload={
            "candidates": [
                {
                    "id": "repair",
                    "summary": "repair cache",
                    "evidence_ids": [local_evidence.id],
                    "state_change": "cache changes",
                    "reversible": True,
                    "risk": "low",
                }
            ]
        },
    )
    authority = {
        "authority_id": "owner-claim",
        "sequence": 1,
        "previous_sequence": None,
        "candidate_id": "repair",
        "candidate_hash": "a" * 64,
        "plan_hash": "b" * 64,
        "toolchain_hash": "c" * 64,
        "target": "clone/cache",
        "executor": "codex",
        "capabilities": ["repair"],
        "allowed_actions": ["repair"],
        "prohibited_actions": ["live-mutation"],
        "required_checks": ["binding"],
        "evidence_ids": [local_evidence.id],
    }
    before = _state(_db())
    _denied(
        lambda: CairntirBackend(writer).hotfix(
            action="authorize",
            wing="juniper",
            case_id=local["case_id"],
            payload=authority,
            idempotency_key="local-authorize",
        )
    )
    assert _state(_db()) == before
    _, approver = _grant(
        owner, capabilities=("read", "write", "approve"), scopes=[{"wing": "juniper"}]
    )
    approved = json.loads(
        CairntirBackend(approver).hotfix(
            action="authorize",
            wing="juniper",
            case_id=local["case_id"],
            payload=authority,
            idempotency_key="local-authorize",
        )
    )
    assert approved["state"] == "authorized"


def test_live_revocation_and_expiry_deny_future_access(owner: DrawerStore) -> None:
    drawer = _add(owner)
    token, scoped = _grant(owner)
    assert scoped.get(drawer.id) is not None
    _api().revoke_grant(owner, token)
    before = _state(_db())
    _denied(lambda: scoped.get(drawer.id))
    assert _state(_db()) == before
    _, expiring = _grant(owner, expires_at=datetime.now(UTC) + timedelta(seconds=0.3))
    assert expiring.get(drawer.id) is not None
    time.sleep(0.4)
    before = _state(_db())
    _denied(lambda: expiring.list_by(limit=None))
    assert _state(_db()) == before


def test_expiry_at_transaction_commit_rolls_back_every_write(owner: DrawerStore) -> None:
    _, scoped = _grant(
        owner, capabilities=("read", "write"), expires_at=datetime.now(UTC) + timedelta(seconds=0.4)
    )
    before = _state(_db())
    with pytest.raises(_api().AccessDenied), scoped.transaction():
        scoped.add(Drawer(wing="juniper", room="public", content="must roll back"))
        time.sleep(0.5)
    assert _state(_db()) == before


def test_readonly_snapshot_rechecks_authoritative_live_revocation(owner: DrawerStore) -> None:
    drawer = _add(owner)
    token, _ = _grant(owner)
    with DrawerStore(_db(), _embedder(), read_only=True) as snapshot:
        scoped = _api().bind_grant(snapshot, token)
        assert scoped.get(drawer.id).content == TASK
        _api().revoke_grant(owner, token)
        before = _state(_db())
        _denied(lambda: CairntirBackend(scoped).handoff(wing="juniper", task=TASK))
        assert _state(_db()) == before


def test_export_permission_is_independent_and_cannot_escape_reference_closure(
    owner: DrawerStore, tmp_path: Path
) -> None:
    import cairntir.portable as portable

    allowed = _add(owner)
    hidden = _add(owner, HIDDEN, room="private")
    linked = _add(owner, "must stay whole", metadata={"evidence_ids": [hidden.id]})
    _, reader = _grant(owner)
    _, exporter = _grant(owner, capabilities=("export",))
    before = _state(_db())
    _denied(lambda: reader.list_for_export())
    _denied(lambda: exporter.get(allowed.id))
    for method in (reader.portable_identity, reader.portable_source, reader.portable_relations):
        _denied(lambda method=method: method(hidden.id))
    assert _ids(exporter.list_for_export()) == {allowed.id}
    path = tmp_path / "export.json"
    path.write_bytes(b"existing destination")
    _denied(lambda: portable.export_bundle(reader, path, drawer_ids=[allowed.id]))
    assert path.read_bytes() == b"existing destination"
    _denied(lambda: portable.export_bundle(exporter, path, drawer_ids=[linked.id]))
    assert path.read_bytes() == b"existing destination"
    result = portable.export_bundle(exporter, path, drawer_ids=[allowed.id])
    assert result["count"] == 1 and TASK in path.read_text(encoding="utf-8")
    assert HIDDEN not in path.read_text(encoding="utf-8")
    assert _state(_db()) == before


def test_portable_imported_approval_metadata_never_confers_capabilities(
    owner: DrawerStore, tmp_path: Path
) -> None:
    import cairntir.portable as portable

    with DrawerStore(tmp_path / "foreign.db", _embedder()) as foreign:
        _add(
            foreign,
            "imported approval claim",
            metadata={"approved": True, "capabilities": list(CAPABILITIES), "principal": "owner"},
        )
        path = tmp_path / "incoming.json"
        portable.export_bundle(foreign, path)
    _, scoped = _grant(owner, capabilities=("read", "write"))
    receipt = portable.import_bundle(scoped, path)
    assert receipt["imported"] == 1
    for capability in ("approve", "manage", "export"):
        _denied(
            lambda capability=capability: scoped.authorize(
                capability, wing="juniper", room="public"
            )
        )


def _process_env(grant_file: Path | None) -> dict[str, str]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT / "src")
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["CAIRNTIR_DISABLE_AUTOREGISTER"] = "1"
    environment["CAIRNTIR_DISABLE_UPDATE_CHECK"] = "1"
    if grant_file is None:
        environment.pop("CAIRNTIR_GRANT_FILE", None)
    else:
        environment["CAIRNTIR_GRANT_FILE"] = str(grant_file)
    return environment


def _cli(grant_file: Path | None, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - isolated current test helper, explicit argument list
        [sys.executable, str(Path(__file__).resolve()), "--sharing-cli", *arguments],
        cwd=ROOT,
        env=_process_env(grant_file),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )


def test_actual_cli_binds_grant_for_get_and_task_and_preserves_owner(
    owner: DrawerStore, tmp_path: Path
) -> None:
    wanted = _add(owner)
    hidden = _add(owner, HIDDEN, room="private")
    token, _ = _grant(owner)
    grant = tmp_path / "grant.txt"
    grant.write_text(f" \n{token}\n", encoding="utf-8")
    before = _state(_db())
    got = _cli(grant, "get", str(wanted.id))
    assert got.returncode == 0 and TASK in got.stdout, got.stderr
    denied = _cli(grant, "get", str(hidden.id))
    assert denied.returncode != 0 and HIDDEN not in denied.stdout + denied.stderr
    task = _cli(grant, "handoff", "juniper", "--task", TASK)
    assert task.returncode == 0, task.stderr
    assert {item["drawer_id"] for item in json.loads(task.stdout)["evidence"]} == {wanted.id}
    assert _state(_db()) == before
    unrestricted = _cli(None, "get", str(hidden.id))
    assert unrestricted.returncode == 0 and HIDDEN in unrestricted.stdout


def test_actual_cli_invalid_configured_grant_fails_closed(
    owner: DrawerStore, tmp_path: Path
) -> None:
    hidden = _add(owner, HIDDEN)
    grant = tmp_path / "grant.txt"
    for content in ("", "unknown-cli-token"):
        grant.write_text(content, encoding="utf-8")
        before = _state(_db())
        result = _cli(grant, "get", str(hidden.id))
        assert result.returncode != 0
        assert HIDDEN not in result.stdout + result.stderr
        assert _state(_db()) == before
    grant.unlink()
    result = _cli(grant, "get", str(hidden.id))
    assert result.returncode != 0 and HIDDEN not in result.stdout + result.stderr


def test_actual_cli_export_and_unsupported_administration_fail_closed(
    owner: DrawerStore, tmp_path: Path
) -> None:
    _add(owner)
    _add(owner, HIDDEN, room="private")
    read_token, _ = _grant(owner)
    export_token, _ = _grant(owner, capabilities=("export",))
    grant = tmp_path / "grant.txt"
    grant.write_text(read_token, encoding="utf-8")
    output = tmp_path / "archive.jsonl"
    output.write_bytes(b"preserve existing")
    before = _state(_db())
    denied = _cli(grant, "export", str(output))
    assert denied.returncode != 0 and output.read_bytes() == b"preserve existing"
    for arguments in (("migrate",), ("doctor", "--gate")):
        result = _cli(grant, *arguments)
        assert result.returncode != 0
        assert any(
            word in (result.stdout + result.stderr).lower()
            for word in ("access", "denied", "restricted", "permission")
        )
    assert _state(_db()) == before
    grant.write_text(export_token, encoding="utf-8")
    result = _cli(grant, "export", str(output))
    assert result.returncode == 0, result.stderr
    assert TASK in output.read_text(encoding="utf-8") and HIDDEN not in output.read_text(
        encoding="utf-8"
    )


class _PeerClosedError(Exception):
    pass


class _McpPeer:
    def __init__(self, grant_file: Path) -> None:
        self.process = subprocess.Popen(  # noqa: S603 - isolated current test helper
            [sys.executable, str(Path(__file__).resolve()), "--sharing-mcp"],
            cwd=ROOT,
            env=_process_env(grant_file),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        self.lines: queue.Queue[str] = queue.Queue()

        def receive() -> None:
            assert self.process.stdout is not None
            for line in self.process.stdout:
                self.lines.put(line)
            self.lines.put("")

        self.thread = threading.Thread(target=receive, daemon=True)
        self.thread.start()
        self.next_id = 0

    def send(self, payload: dict[str, Any]) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(payload) + "\n")
        self.process.stdin.flush()

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.next_id += 1
        self.send({"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params})
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                line = self.lines.get(timeout=max(0.01, deadline - time.monotonic()))
            except queue.Empty:
                pytest.fail(
                    f"SHARING_INFRASTRUCTURE: stdio response timed out, exit={self.process.poll()}"
                )
            if not line:
                self.process.wait(timeout=3)
                raise _PeerClosedError(f"stdio exited with {self.process.returncode}")
            response = json.loads(line)
            if response.get("id") == self.next_id:
                return response
        raise AssertionError("stdio deadline exceeded")

    def initialize(self) -> None:
        response = self.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "sharing-acceptance", "version": "1"},
            },
        )
        assert "result" in response, response
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def get(self, drawer_id: int) -> str:
        response = self.request(
            "tools/call", {"name": "cairntir_get", "arguments": {"drawer_id": drawer_id}}
        )
        return json.dumps(response)

    def close(self) -> None:
        if self.process.stdin is not None:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=3)
        for stream in (self.process.stdout, self.process.stderr):
            if stream is not None:
                stream.close()


def test_real_stdio_startup_scope_is_immutable_and_revocation_is_live(
    owner: DrawerStore, tmp_path: Path
) -> None:
    wanted = _add(owner)
    hidden = _add(owner, HIDDEN, wing="cedar")
    token, _ = _grant(owner)
    other_token, _ = _grant(owner, scopes=[{"wing": "cedar"}])
    grant = tmp_path / "grant.txt"
    grant.write_text(token, encoding="utf-8")
    peer = _McpPeer(grant)
    try:
        peer.initialize()
        assert TASK in peer.get(wanted.id)
        assert HIDDEN not in peer.get(hidden.id)
        grant.write_text(other_token, encoding="utf-8")
        assert HIDDEN not in peer.get(hidden.id)
        assert TASK in peer.get(wanted.id)
        _api().revoke_grant(owner, token)
        before = _state(_db())
        denied = peer.get(wanted.id)
        assert TASK not in denied and "error" in denied.lower()
        assert _state(_db()) == before
    finally:
        peer.close()


def test_real_stdio_invalid_grant_never_serves_owner_data(
    owner: DrawerStore, tmp_path: Path
) -> None:
    hidden = _add(owner, HIDDEN)
    grant = tmp_path / "invalid.txt"
    grant.write_text("unknown-stdio-token", encoding="utf-8")
    peer = _McpPeer(grant)
    before = _state(_db())
    try:
        try:
            response = peer.request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "sharing-acceptance", "version": "1"},
                },
            )
            if "result" in response:
                peer.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
                output = peer.get(hidden.id)
            else:
                output = json.dumps(response)
            assert HIDDEN not in output
            assert "error" in output.lower()
        except _PeerClosedError:
            assert peer.process.returncode != 0
            assert peer.process.stderr is not None
            assert "AccessDenied" in peer.process.stderr.read()
        assert _state(_db()) == before
    finally:
        peer.close()


if __name__ == "__main__":

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Sharing acceptance attempted network access")

    original_connect = socket.socket.connect

    def local_event_loop_only(connection: Any, address: Any) -> Any:
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
            return original_connect(connection, address)
        return forbidden(connection, address)

    socket.socket.connect = local_event_loop_only
    socket.create_connection = forbidden
    mode = sys.argv.pop(1)
    if mode == "--sharing-cli":
        from cairntir import cli

        cli.production_embedding_provider = _embedder
        cli.app()
    elif mode == "--sharing-mcp":
        from cairntir.mcp import server

        server.production_embedding_provider = _embedder
        sys.argv = ["cairntir-mcp", "--host", "unknown", "--model", "owner"]
        server.main()
    else:
        raise SystemExit(f"unknown helper mode: {mode}")
