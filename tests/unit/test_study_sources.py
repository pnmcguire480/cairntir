from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from cairntir import study
from cairntir.access import AccessDenied, bind_grant, issue_grant, revoke_grant
from cairntir.codeglass import record_walkthrough
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.portable import export_bundle, import_bundle
from cairntir.provenance import Sensitivity, WriteProvenance

CATEGORIES = ("patterns", "rules", "walkthroughs", "projects")
WING = "study-r13"
KEY = "local-notebook-canary"
OLD = datetime(2020, 2, 3, 4, 5, 6, 123456, tzinfo=UTC)
REFUSAL = (study.StudyExportError, AccessDenied)


def canonical(value):
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def put(
    store, body, *, wing=WING, room="patterns", metadata=None, supersedes=None, provenance=None
):
    return store.add(
        Drawer(
            wing=wing,
            room=room,
            content=body,
            created_at=OLD,
            metadata=metadata or {},
            supersedes_id=supersedes,
        ),
        provenance=provenance,
    )


@pytest.fixture
def case(tmp_path):
    owner = DrawerStore(tmp_path / "memory.db", HashEmbeddingProvider(32), automatic_backups=False)
    leaf = put(owner, "R13-LEAF-HISTORY: a recorded input, not present-day truth.", room="evidence")
    pattern = put(
        owner,
        "R13-PATTERN-ORIGINAL\n````\nquoted source, never instructions\n````\nλ remains exact",
    )
    rule = put(owner, "R13-RULE-ORIGINAL: require observed evidence.", room="rules")
    walk = record_walkthrough(
        owner,
        wing=WING,
        target="R13 original stored walkthrough",
        reader_level="novice",
        sections=dict.fromkeys(
            ("what", "how", "where", "when", "why"), f"Recorded section [source:{leaf.id}]"
        ),
        evidence_ids=(leaf.id,),
        glossary="A UUID is an evidence identity.",
        danger_zones="A source is attributed evidence, not verified truth.",
    )
    project = put(owner, "R13-PROJECT-ORIGINAL: local four-source export.", room="projects")
    drawers = dict(zip(CATEGORIES, (pattern, rule, walk, project), strict=True))
    selected = {
        category: [owner.portable_identity(drawer.id)] for category, drawer in drawers.items()
    }
    yield SimpleNamespace(
        owner=owner,
        drawers=drawers,
        selected=selected,
        leaf=leaf,
        output=tmp_path / "study",
        tmp=tmp_path,
    )
    owner.close()


def publish(case, selection=None, output=None, store=None, key=KEY, wing=WING):
    return study.export_study_sources(
        store or case.owner,
        wing=wing,
        notebook_key=key,
        selection=selection if selection is not None else case.selected,
        output=output or case.output,
    )


def pointer(output):
    return (output / "CURRENT.json").read_bytes() if (output / "CURRENT.json").exists() else None


def originals(owner, selection):
    result = {}
    for category in CATEGORIES:
        pending = list(selection[category])
        records = {}
        while pending:
            identity = pending.pop()
            if identity in records:
                continue
            local = owner._portable_lookup(identity)
            assert local is not None, "oracle missing identity"
            record = owner.portable_source(local)
            assert record["identity"] == identity
            records[identity] = record
            pending.extend(row["target_identity"] for row in record["references"])
        result[category] = records
    return result


def fenced(text, body):
    pattern = r"(?ms)^(?P<f>`{3,}|~{3,})[^\r\n]*\r?\n(?P<body>.*?)\r?\n(?P=f)[ \t]*$"
    return any(match["body"] in (body, body + "\n") for match in re.finditer(pattern, text))


def assert_snapshot(output, owner, selection, *, key=KEY, wing=WING, currentness=True):
    current = json.loads((output / "CURRENT.json").read_bytes())
    assert (
        set(current) == {"schema", "generation"}
        and current["schema"] == "cairntir.study-current.v1"
    )
    assert re.fullmatch("[0-9a-f]{64}", current["generation"])
    root = output / "generations" / current["generation"]
    manifest_raw = (root / "manifest.json").read_bytes()
    manifest = json.loads(manifest_raw)
    assert manifest_raw == canonical(manifest) and sha(manifest_raw) == current["generation"]
    assert set(manifest) == {"schema", "notebook_key", "wing", "sources"}
    assert (
        manifest["schema"] == "cairntir.study-sources.v1"
        and manifest["notebook_key"] == key
        and manifest["wing"] == wing
    )
    assert [row["category"] for row in manifest["sources"]] == list(CATEGORIES)
    assert {p.name for p in root.iterdir()} == {
        "manifest.json",
        *(category + ".md" for category in CATEGORIES),
    }
    expected = originals(owner, selection)
    texts = {}
    for category, row in zip(CATEGORIES, manifest["sources"], strict=True):
        assert set(row) == {
            "category",
            "source_id",
            "revision",
            "bytes",
            "path",
            "selected",
            "cited",
        }
        assert row["source_id"] == sha(
            canonical(["cairntir.study-source.v1", key, wing, category])
        ), "wrong stable source identity"
        assert row["path"] == category + ".md" and row["selected"] == sorted(selection[category])
        records = expected[category]
        assert row["cited"] == sorted(set(records) - set(selection[category]))
        raw = (root / row["path"]).read_bytes()
        assert len(raw) == row["bytes"] and sha(raw) == row["revision"], "wrong exact-byte revision"
        text = raw.decode("utf-8")
        assert row["source_id"] in text and category in text and wing in text
        for identity, record in records.items():
            assert identity in text and record["source_store_id"] in text
            assert str(record["source_drawer_id"]) in text
            body = record["drawer"]["content"]
            assert text.count(body) == 1 and fenced(text, body), (
                "source body must be exact and unambiguously fenced"
            )
            assert record["drawer"]["created_at"] in text, "original source date replaced"
            for value in record["provenance"].values():
                if value is not None:
                    assert str(value) in text, "original provenance omitted"
            for reference in record["references"]:
                assert (
                    reference["target_identity"] in text
                    and reference["kind"] in text
                    and reference["path"] in text
                )
        if records:
            assert re.search(r"authored[^\n]{0,80}unknown|unknown[^\n]{0,80}authored", text, re.I)
        if row["cited"]:
            assert re.search(r"cited|histor", text, re.I)
        if currentness:
            for identity in selection[category]:
                assert owner.has_export_successor(owner._portable_lookup(identity)) is False, (
                    "selected source is superseded"
                )
        texts[category] = text
    return manifest, texts


def assert_receipt(receipt, output, manifest, changes):
    assert set(receipt) == {
        "schema",
        "status",
        "generation",
        "sources",
        "changes",
        "validated_at",
        "notebooklm",
    }
    assert receipt["schema"] == "cairntir.study-export-receipt.v1"
    assert receipt["status"] == (
        "UNCHANGED" if set(changes.values()) == {"unchanged"} else "PUBLISHED"
    )
    assert receipt["generation"] == sha(canonical(manifest)) and receipt["changes"] == changes
    assert receipt["notebooklm"] == {"status": "UNVERIFIED"}
    assert datetime.fromisoformat(receipt["validated_at"]).tzinfo is not None
    for source, row in zip(receipt["sources"], manifest["sources"], strict=True):
        expected = dict(
            row, path=str((output / "generations" / receipt["generation"] / row["path"]).resolve())
        )
        assert source == expected


def test_four_real_categories_dates_retry_and_readonly_source(case):
    changes_before = case.owner._conn.total_changes
    first = publish(case)
    manifest, text = assert_snapshot(case.output, case.owner, case.selected)
    assert_receipt(first, case.output, manifest, dict.fromkeys(CATEGORIES, "added"))
    assert first["validated_at"] not in "".join(text.values())
    before = {
        p.relative_to(case.output).as_posix(): p.read_bytes()
        for p in case.output.rglob("*")
        if p.is_file()
    }
    second = publish(case)
    assert_receipt(second, case.output, manifest, dict.fromkeys(CATEGORIES, "unchanged"))
    assert second["generation"] == first["generation"]
    assert before == {
        p.relative_to(case.output).as_posix(): p.read_bytes()
        for p in case.output.rglob("*")
        if p.is_file()
    }
    assert case.owner._conn.total_changes == changes_before
    read = study.read_study_sources(case.output)
    assert set(read) == {"manifest", "paths"} and read["manifest"] == manifest
    assert read["paths"] == {
        category: str(
            (case.output / "generations" / first["generation"] / (category + ".md")).resolve()
        )
        for category in CATEGORIES
    }


def test_successor_explicit_refresh_removal_and_preserved_generation(case):
    old_receipt = publish(case)
    old_pointer = pointer(case.output)
    old_generation = case.output / "generations" / old_receipt["generation"]
    old_files = {p.name: p.read_bytes() for p in old_generation.iterdir()}
    successor = put(case.owner, "R13-PATTERN-REPLACEMENT", supersedes=case.drawers["patterns"].id)
    with pytest.raises(REFUSAL):
        publish(case)
    assert pointer(case.output) == old_pointer
    selected = deepcopy(case.selected)
    selected["patterns"] = [case.owner.portable_identity(successor.id)]
    selected["projects"] = []
    receipt = publish(case, selected)
    manifest, text = assert_snapshot(case.output, case.owner, selected)
    assert_receipt(
        receipt,
        case.output,
        manifest,
        {
            "patterns": "updated",
            "rules": "unchanged",
            "walkthroughs": "unchanged",
            "projects": "updated",
        },
    )
    assert "R13-PROJECT-ORIGINAL" not in text["projects"]
    assert "R13-PATTERN-REPLACEMENT" in text["patterns"]
    assert {p.name: p.read_bytes() for p in old_generation.iterdir()} == old_files


def test_portable_import_keeps_original_uuid_date_body_and_source_id(case):
    bundle = case.tmp / "portable.json"
    export_bundle(case.owner, bundle, wing=WING)
    other = DrawerStore(case.tmp / "other.db", HashEmbeddingProvider(32), automatic_backups=False)
    try:
        for index in range(20):
            put(other, f"unrelated preexisting integer ID {index}", wing="other-wing")
        import_bundle(other, bundle)
        assert other._portable_lookup(case.selected["patterns"][0]) != case.drawers["patterns"].id
        first = publish(case)
        second = publish(case, output=case.tmp / "imported", store=other)
        assert first["generation"] == second["generation"]
        assert_snapshot(case.tmp / "imported", other, case.selected)
    finally:
        other.close()


def test_empty_categories_and_selection_order_are_deterministic(case):
    empty = dict.fromkeys(CATEGORIES, None)
    empty = {key: [] for key in empty}
    publish(case, empty)
    assert_snapshot(case.output, case.owner, empty)
    extra = put(case.owner, "R13-SECOND-PATTERN")
    selected = deepcopy(case.selected)
    selected["patterns"].append(case.owner.portable_identity(extra.id))
    a = publish(case, selected)
    selected["patterns"].reverse()
    b = publish(case, selected)
    assert a["generation"] == b["generation"]


def test_invalid_selections_never_publish(case):
    bad = []
    value = deepcopy(case.selected)
    value["patterns"] = ["not-a-uuid"]
    bad.append(value)
    value = deepcopy(case.selected)
    value["patterns"] = ["AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"]
    bad.append(value)
    value = deepcopy(case.selected)
    value["patterns"] *= 2
    bad.append(value)
    value = deepcopy(case.selected)
    value["rules"] = value["patterns"]
    bad.append(value)
    value = deepcopy(case.selected)
    value["extra"] = []
    bad.append(value)
    value = deepcopy(case.selected)
    value["projects"] = "not-a-list"
    bad.append(value)
    for index, selected in enumerate(bad):
        output = case.tmp / f"invalid-{index}"
        with pytest.raises(study.StudyExportError):
            publish(case, selected, output)
        assert pointer(output) is None


def test_unknown_identity_and_wrong_store_integer_reuse_refuse(case):
    selected = deepcopy(case.selected)
    selected["patterns"] = [str(uuid4())]
    with pytest.raises(REFUSAL):
        publish(case, selected)
    other = DrawerStore(
        case.tmp / "unrelated.db", HashEmbeddingProvider(32), automatic_backups=False
    )
    try:
        saved = put(other, "same integer, different immutable original")
        assert saved.id == case.leaf.id
        with pytest.raises(REFUSAL):
            publish(case, output=case.tmp / "wrong-store", store=other)
    finally:
        other.close()
    assert pointer(case.output) is None


def test_selected_secret_future_and_expired_sources_refuse(case):
    for index, changes in enumerate(
        (
            {"sensitivity": Sensitivity.SECRET},
            {"valid_from": datetime.now(UTC) + timedelta(days=1)},
            {"valid_until": datetime.now(UTC) - timedelta(days=1)},
        )
    ):
        provenance = WriteProvenance.create(
            host="r13-fixture", capture_path="independent-test", **changes
        )
        record = put(case.owner, f"R13-NOT-CURRENT-{index}", provenance=provenance)
        selected = deepcopy(case.selected)
        selected["patterns"] = [case.owner.portable_identity(record.id)]
        output = case.tmp / f"not-current-{index}"
        with pytest.raises(REFUSAL):
            publish(case, selected, output)
        assert pointer(output) is None


def test_hidden_future_and_expired_successors_still_block_selected_predecessor(case):
    for index, changes in enumerate(
        (
            {"valid_from": datetime.now(UTC) + timedelta(days=1)},
            {"valid_until": datetime.now(UTC) - timedelta(days=1)},
        )
    ):
        predecessor = put(case.owner, f"R13-PREDECESSOR-{index}")
        put(
            case.owner,
            f"R13-HIDDEN-SUCCESSOR-{index}",
            room="hidden",
            supersedes=predecessor.id,
            provenance=WriteProvenance.create(
                host="r13-fixture", capture_path="independent-test", **changes
            ),
        )
        token = issue_grant(
            case.owner, scopes=[{"wing": WING, "rooms": ["patterns"]}], capabilities=["export"]
        )
        scoped = bind_grant(case.owner, token)
        assert scoped.has_export_successor(predecessor.id) is True
        selection = {category: [] for category in CATEGORIES}
        selection["patterns"] = [case.owner.portable_identity(predecessor.id)]
        with pytest.raises(REFUSAL):
            publish(case, selection, case.tmp / f"hidden-{index}", scoped)


def test_secret_foreign_missing_and_unauthorized_dependencies_refuse(case):
    secret = put(
        case.owner,
        "R13-SECRET-DEPENDENCY",
        provenance=WriteProvenance.create(
            host="r13-fixture", capture_path="independent-test", sensitivity=Sensitivity.SECRET
        ),
    )
    foreign = put(case.owner, "R13-FOREIGN-DEPENDENCY", wing="foreign-wing")
    for index, target in enumerate((secret.id, foreign.id, 999999)):
        record = put(case.owner, f"R13-DEPENDENT-{index}", metadata={"evidence_ids": [target]})
        selected = {category: [] for category in CATEGORIES}
        selected["patterns"] = [case.owner.portable_identity(record.id)]
        with pytest.raises(REFUSAL):
            publish(case, selected, case.tmp / f"dependency-{index}")
    ids = [drawer.id for drawer in case.drawers.values()]
    scoped = bind_grant(
        case.owner,
        issue_grant(
            case.owner, scopes=[{"wing": WING, "drawer_ids": ids}], capabilities=["export"]
        ),
    )
    with pytest.raises(REFUSAL):
        publish(case, output=case.tmp / "forbidden-citation", store=scoped)


def test_export_only_capability_works_without_read_or_write(case):
    scoped = bind_grant(
        case.owner, issue_grant(case.owner, scopes=[{"wing": WING}], capabilities=["export"])
    )
    with pytest.raises(AccessDenied):
        scoped.get(case.drawers["patterns"].id)
    before = case.owner._conn.total_changes
    publish(case, store=scoped)
    assert_snapshot(case.output, case.owner, case.selected)
    assert case.owner._conn.total_changes == before


def test_read_only_revoked_and_expired_grants_do_not_export(case):
    read = bind_grant(
        case.owner, issue_grant(case.owner, scopes=[{"wing": WING}], capabilities=["read"])
    )
    with pytest.raises(REFUSAL):
        publish(case, store=read)
    token = issue_grant(case.owner, scopes=[{"wing": WING}], capabilities=["export"])
    revoked = bind_grant(case.owner, token)
    revoke_grant(case.owner, token)
    with pytest.raises(REFUSAL):
        publish(case, store=revoked)
    token = issue_grant(
        case.owner,
        scopes=[{"wing": WING}],
        capabilities=["export"],
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    with pytest.raises(AccessDenied):
        bind_grant(case.owner, token)
    assert pointer(case.output) is None


def test_revocation_at_final_successor_check_and_facade_postcheck(case, monkeypatch):
    token = issue_grant(case.owner, scopes=[{"wing": WING}], capabilities=["export"])
    scoped = bind_grant(case.owner, token)
    original = case.owner.has_export_successor
    calls = {}

    def revoke_on_second(key):
        calls[key] = calls.get(key, 0) + 1
        if calls[key] == 2:
            revoke_grant(case.owner, token)
        return original(key)

    monkeypatch.setattr(case.owner, "has_export_successor", revoke_on_second)
    with pytest.raises(REFUSAL):
        publish(case, store=scoped)
    assert max(calls.values()) >= 2 and pointer(case.output) is None
    monkeypatch.setattr(case.owner, "has_export_successor", original)
    token2 = issue_grant(case.owner, scopes=[{"wing": WING}], capabilities=["export"])
    scoped2 = bind_grant(case.owner, token2)

    def revoke_during_delegate(key):
        result = original(key)
        revoke_grant(case.owner, token2)
        return result

    monkeypatch.setattr(case.owner, "has_export_successor", revoke_during_delegate)
    with pytest.raises(AccessDenied):
        scoped2.has_export_successor(case.drawers["patterns"].id)


def test_source_bytes_change_between_reads_refuses_publication(case, monkeypatch):
    original = case.owner.portable_source
    calls = {}

    def changed(key):
        value = deepcopy(original(key))
        calls[key] = calls.get(key, 0) + 1
        if calls[key] > 1:
            value["drawer"]["content"] += "\nR13-RACED-SOURCE"
        return value

    monkeypatch.setattr(case.owner, "portable_source", changed)
    with pytest.raises(REFUSAL):
        publish(case)
    assert max(calls.values()) >= 2 and pointer(case.output) is None


def test_cycles_deduplicate_and_superseded_cited_evidence_is_allowed(case):
    cyclic = put(case.owner, "R13-SELF-CITED-EVIDENCE", metadata={"evidence_ids": [case.leaf.id]})
    record = case.owner.portable_source(cyclic.id)
    record["drawer"]["metadata"]["evidence_ids"] = [cyclic.id]
    record["references"][0]["source_target_id"] = cyclic.id
    record["references"][0]["target_identity"] = record["identity"]
    with case.owner.transaction():
        case.owner._portable_replace(cyclic.id, record["identity"], record)
    put(case.owner, "R13-LEAF-SUCCESSOR", room="hidden", supersedes=case.leaf.id)
    selected = deepcopy(case.selected)
    selected["patterns"] = [record["identity"]]
    publish(case, selected)
    manifest, _ = assert_snapshot(case.output, case.owner, selected)
    assert manifest["sources"][0]["cited"] == []
    assert case.owner.portable_identity(case.leaf.id) in manifest["sources"][2]["cited"]


def test_tampered_prior_generations_refuse_reader_and_refresh(case):
    for index, kind in enumerate(("payload", "missing", "manifest", "pointer")):
        output = case.tmp / f"tamper-{index}"
        receipt = publish(case, output=output)
        root = output / "generations" / receipt["generation"]
        if kind == "payload":
            (root / "patterns.md").write_bytes(b"R13-TAMPERED")
        elif kind == "missing":
            (root / "rules.md").unlink()
        elif kind == "manifest":
            (root / "manifest.json").write_bytes(b"{}")
        else:
            (output / "CURRENT.json").write_bytes(
                canonical({"schema": "cairntir.study-current.v1", "generation": "../escape"})
            )
        before = pointer(output)
        with pytest.raises(study.StudyExportError):
            study.read_study_sources(output)
        with pytest.raises(study.StudyExportError):
            publish(case, output=output)
        assert pointer(output) == before


def test_owned_output_collision_notebook_mismatch_and_actual_hardlinks(case):
    unowned = case.tmp / "unowned"
    unowned.mkdir()
    (unowned / "human.md").write_text("human-owned", encoding="utf-8")
    with pytest.raises(study.StudyExportError):
        publish(case, output=unowned)
    assert (unowned / "human.md").read_text() == "human-owned"
    publish(case)
    before = pointer(case.output)
    with pytest.raises(study.StudyExportError):
        publish(case, key="other-notebook")
    assert pointer(case.output) == before
    for filename in (
        case.output / "CURRENT.json",
        case.output / "generations" / json.loads(before)["generation"] / "patterns.md",
    ):
        alias = case.tmp / "actual-hardlink"
        os.link(filename, alias)
        original = filename.read_bytes()
        try:
            with pytest.raises(study.StudyExportError):
                study.read_study_sources(case.output)
            with pytest.raises(study.StudyExportError):
                publish(case)
            assert alias.read_bytes() == original
        finally:
            alias.unlink()


def test_simulated_reparse_detector_refuses_without_claiming_actual_symlink(case, monkeypatch):
    publish(case)
    before = pointer(case.output)
    original = Path.is_symlink
    original_stat, original_lstat = os.stat, os.lstat

    class LinkStat:
        def __init__(self, value):
            self.value = value
            self.st_mode = stat.S_IFLNK | stat.S_IMODE(value.st_mode)
            self.st_file_attributes = getattr(value, "st_file_attributes", 0) | 0x400

        def __getattr__(self, name):
            return getattr(self.value, name)

    def simulated(function):
        def inspect(path, *args, **kwargs):
            value = function(path, *args, **kwargs)
            return LinkStat(value) if os.fspath(path) == os.fspath(case.output) else value

        return inspect

    monkeypatch.setattr(
        Path, "is_symlink", lambda path: True if path == case.output else original(path)
    )
    monkeypatch.setattr(os, "stat", simulated(original_stat))
    monkeypatch.setattr(os, "lstat", simulated(original_lstat))
    with pytest.raises(study.StudyExportError):
        study.read_study_sources(case.output)
    with pytest.raises(study.StudyExportError):
        publish(case)
    assert pointer(case.output) == before


def test_pointer_swap_failure_and_keyboard_cancellation_preserve_previous(case, monkeypatch):
    publish(case)
    before = pointer(case.output)
    extra = put(case.owner, "R13-UNPUBLISHED-REFRESH")
    selected = deepcopy(case.selected)
    selected["projects"] = [case.owner.portable_identity(extra.id)]
    original = os.replace
    for exception, expected in (
        (OSError("R13 injected pointer failure"), study.StudyExportError),
        (KeyboardInterrupt(), KeyboardInterrupt),
    ):
        calls = []

        def interrupted(source, destination, *, calls=calls, exception=exception):
            if Path(destination) == case.output / "CURRENT.json":
                calls.append(True)
                raise exception
            return original(source, destination)

        with monkeypatch.context() as patch:
            patch.setattr(os, "replace", interrupted)
            with pytest.raises(expected):
                publish(case, selected)
        assert calls and pointer(case.output) == before
        assert_snapshot(case.output, case.owner, case.selected)


def test_concurrent_publication_is_refused_without_stealing_lock(case, monkeypatch):
    original = os.replace
    entered = []

    def nested(source, destination):
        if Path(destination) == case.output / "CURRENT.json" and not entered:
            entered.append(True)
            with pytest.raises(study.StudyExportError):
                publish(case)
        return original(source, destination)

    monkeypatch.setattr(os, "replace", nested)
    publish(case)
    assert entered
    assert_snapshot(case.output, case.owner, case.selected)


def test_real_selection_closure_and_markdown_limits_refuse_without_truncation(tmp_path):
    owner = DrawerStore(tmp_path / "limits.db", HashEmbeddingProvider(32), automatic_backups=False)
    try:
        with owner.transaction():
            leaves = [put(owner, f"R13-LIMIT-LEAF-{index}") for index in range(4000)]
        selections = {category: [] for category in CATEGORIES}
        selections["patterns"] = [owner.portable_identity(row.id) for row in leaves[:1001]]
        with pytest.raises(REFUSAL):
            study.export_study_sources(
                owner,
                wing=WING,
                notebook_key=KEY,
                selection=selections,
                output=tmp_path / "selected-limit",
            )
        root = put(owner, "R13-OVER-CLOSURE", metadata={"evidence_ids": [row.id for row in leaves]})
        selections["patterns"] = [owner.portable_identity(root.id)]
        with pytest.raises(REFUSAL):
            study.export_study_sources(
                owner,
                wing=WING,
                notebook_key=KEY,
                selection=selections,
                output=tmp_path / "closure-limit",
            )
        huge = put(owner, "X" * (8 * 1024**2 + 1))
        selections["patterns"] = [owner.portable_identity(huge.id)]
        with pytest.raises(REFUSAL):
            study.export_study_sources(
                owner,
                wing=WING,
                notebook_key=KEY,
                selection=selections,
                output=tmp_path / "bytes-limit",
            )
        assert not list(tmp_path.glob("*-limit/CURRENT.json"))
    finally:
        owner.close()


def test_cli_uses_actual_readonly_store_and_emits_receipt(case, monkeypatch):
    from typer.testing import CliRunner

    from cairntir import cli

    monkeypatch.setenv("CAIRNTIR_HOME", str(case.tmp / "home"))
    monkeypatch.setenv("CAIRNTIR_DISABLE_AUTOREGISTER", "1")
    monkeypatch.setenv("CAIRNTIR_DISABLE_UPDATE_CHECK", "1")
    monkeypatch.setattr(cli, "db_path", lambda **kwargs: case.tmp / "memory.db")
    monkeypatch.setattr(cli, "production_embedding_provider", lambda: HashEmbeddingProvider(32))
    real_open = cli._open_store
    calls = []

    def opened(*args, **kwargs):
        calls.append(kwargs.get("read_only"))
        return real_open(*args, **kwargs)

    monkeypatch.setattr(cli, "_open_store", opened)
    selection_file = case.tmp / "selection.json"
    selection_file.write_bytes(canonical(case.selected))
    before = case.owner._conn.total_changes
    result = CliRunner().invoke(
        cli.app,
        [
            "study-export",
            str(selection_file),
            "--wing",
            WING,
            "--notebook-key",
            KEY,
            "--output",
            str(case.output),
        ],
    )
    assert result.exit_code == 0, result.output
    receipt = json.loads(result.stdout)
    manifest, _ = assert_snapshot(case.output, case.owner, case.selected)
    assert_receipt(receipt, case.output, manifest, dict.fromkeys(CATEGORIES, "added"))
    assert calls and all(calls) and case.owner._conn.total_changes == before
    refresh = publish(case)
    assert_receipt(refresh, case.output, manifest, dict.fromkeys(CATEGORIES, "unchanged"))


def test_reader_snapshot_remains_valid_without_live_store_authority(case):
    token = issue_grant(case.owner, scopes=[{"wing": WING}], capabilities=["export"])
    publish(case, store=bind_grant(case.owner, token))
    before = pointer(case.output)
    revoke_grant(case.owner, token)
    assert study.read_study_sources(case.output)["manifest"]["wing"] == WING
    assert pointer(case.output) == before


def rewrite_generation(output, mutate):
    current = json.loads(pointer(output))
    root = output / "generations" / current["generation"]
    manifest = json.loads((root / "manifest.json").read_bytes())
    payload = {row["category"]: (root / row["path"]).read_bytes() for row in manifest["sources"]}
    mutate(manifest, payload)
    for row in manifest["sources"]:
        row["bytes"] = len(payload[row["category"]])
        row["revision"] = sha(payload[row["category"]])
    raw = canonical(manifest)
    generation = sha(raw)
    target = output / "generations" / generation
    target.mkdir(exist_ok=False)
    for row in manifest["sources"]:
        (target / row["path"]).write_bytes(payload[row["category"]])
    (target / "manifest.json").write_bytes(raw)
    (output / "CURRENT.json").write_bytes(
        canonical({"schema": "cairntir.study-current.v1", "generation": generation})
    )


def test_broken_control_wrong_stable_identity_is_detected(case):
    publish(case)
    rewrite_generation(
        case.output, lambda manifest, payload: manifest["sources"][0].update(source_id="0" * 64)
    )
    with pytest.raises(AssertionError, match="wrong stable source identity"):
        assert_snapshot(case.output, case.owner, case.selected)


def test_broken_control_export_date_substitution_is_detected(case):
    publish(case)
    date = case.owner.portable_source(case.drawers["patterns"].id)["drawer"]["created_at"]

    def wrong_date(manifest, payload):
        payload["patterns"] = payload["patterns"].replace(
            date.encode(), b"2099-01-01T00:00:00+00:00"
        )

    rewrite_generation(case.output, wrong_date)
    with pytest.raises(AssertionError, match="original source date replaced"):
        assert_snapshot(case.output, case.owner, case.selected)


def test_broken_control_stale_removed_member_bytes_are_detected(case):
    old = publish(case)
    old_bytes = (case.output / "generations" / old["generation"] / "projects.md").read_bytes()
    selected = deepcopy(case.selected)
    selected["projects"] = []
    publish(case, selected)
    rewrite_generation(case.output, lambda manifest, payload: payload.update(projects=old_bytes))
    _, text = assert_snapshot(case.output, case.owner, selected)
    with pytest.raises(AssertionError, match="stale removed content"):
        assert "R13-PROJECT-ORIGINAL" not in text["projects"], "stale removed content"


def test_broken_control_ignored_successor_is_detected(case, monkeypatch):
    put(case.owner, "R13-CURRENT-SUCCESSOR", supersedes=case.drawers["patterns"].id)
    with monkeypatch.context() as patch:
        patch.setattr(case.owner, "has_export_successor", lambda key: False)
        publish(case)
    with pytest.raises(AssertionError, match="selected source is superseded"):
        assert_snapshot(case.output, case.owner, case.selected)
