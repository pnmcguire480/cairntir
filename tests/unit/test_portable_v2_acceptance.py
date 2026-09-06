"""Independent portable-evidence contract; implementations must not edit this file."""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
from collections.abc import Iterator
from contextlib import ExitStack, closing
from datetime import UTC, datetime
from pathlib import Path
from queue import Queue
from threading import Thread
from typing import Any
from uuid import UUID

import pytest
import sqlite_vec

import cairntir.portable as portable
from cairntir.errors import CairntirError, EmbeddingError
from cairntir.hotfix import HotfixAction, HotfixCommand, HotfixCoordinator
from cairntir.learning import list_discoveries, propose_multi_episode_discoveries
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer, Layer
from cairntir.provenance import Sensitivity, TrustLevel, Visibility, WriteProvenance

ROOT = Path(__file__).resolve().parents[2]
V6 = ROOT / "plans/portable-v2-v6.fixture"
V6_SHA256 = "ae20b045d2557e58ab5c072e5673b59ede94697aa5ce3f63710bd8fe48f50206"
STAMP = datetime(2025, 3, 4, 5, 6, 7, tzinfo=UTC)
KEY = b"independent-portable-test-key"


def _api() -> None:
    for owner, names in (
        (portable, ("export_bundle", "import_bundle")),
        (DrawerStore, ("portable_identity", "portable_source", "portable_relations")),
    ):
        for name in names:
            if not callable(getattr(owner, name, None)):
                pytest.fail(f"PORTABLE_V2_MISSING: {owner.__name__}.{name}", pytrace=False)


@pytest.fixture()
def stores(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path / "isolated-home"))
    with ExitStack() as stack:

        def open_store(name: str, embedder: Any = None) -> DrawerStore:
            return stack.enter_context(
                DrawerStore(
                    tmp_path / f"{name}.db",
                    embedder or HashEmbeddingProvider(dimension=16),
                    provenance=WriteProvenance.create(
                        host="independent-fixture",
                        capture_path="portable.acceptance",
                        trust=TrustLevel.USER_ASSERTED,
                    ),
                )
            )

        yield open_store


def _add(store: DrawerStore, content: str, **kwargs: Any) -> Drawer:
    return store.add(
        Drawer(
            wing=kwargs.pop("wing", "portable"),
            room=kwargs.pop("room", "archive"),
            content=content,
            created_at=STAMP,
            **kwargs,
        )
    )


def _canonical(payload: Any) -> bytes:
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _seal(bundle: dict[str, Any], key: bytes | None = None) -> dict[str, Any]:
    bundle["records"] = sorted(bundle["records"], key=lambda item: item["identity"])
    payload = _canonical({"format_version": 2, "records": bundle["records"]})
    bundle["bundle_hash"] = "sha256:" + hashlib.sha256(payload).hexdigest()
    bundle["signature"] = (
        "hmac-sha256:" + hmac.new(key, payload, hashlib.sha256).hexdigest() if key else None
    )
    return bundle


def _write(path: Path, bundle: dict[str, Any]) -> None:
    path.write_bytes(_canonical(bundle) + b"\n")


def _export(store: DrawerStore, path: Path, **kwargs: Any) -> dict[str, Any]:
    result = portable.export_bundle(store, path, **kwargs)
    bundle = json.loads(path.read_text(encoding="utf-8"))
    assert bundle["format_version"] == 2
    assert result["complete"] is True
    assert result["count"] == len(bundle["records"])
    expected = _seal(copy.deepcopy(bundle), kwargs.get("signing_key"))
    assert bundle["bundle_hash"] == expected["bundle_hash"]
    assert bundle["signature"] == expected["signature"]
    assert result["bundle_hash"] == bundle["bundle_hash"]
    return bundle


def _import(store: DrawerStore, path: Path, **kwargs: Any) -> dict[str, Any]:
    result = portable.import_bundle(store, path, **kwargs)
    assert result["count"] == result["imported"] + result["existing"]
    assert result["count"] == len(result["identity_map"])
    for identity, local_id in result["identity_map"].items():
        assert str(UUID(identity)) == identity
        assert store.portable_identity(local_id) == identity
    return result


def _snapshot(path: Path, *, receipts: bool = False) -> dict[str, Any]:
    with closing(sqlite3.connect(path)) as conn:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        names = [
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        ]
        return {
            name: sorted(
                conn.execute('SELECT * FROM "' + name.replace('"', '""') + '"').fetchall(),  # noqa: S608
                key=repr,
            )
            for name in sorted(names)
            if receipts or name != "workflow_runs"
        }


def _success_receipts(store: DrawerStore) -> list[Any]:
    return store._conn.execute(
        "SELECT * FROM workflow_runs WHERE state='committed' ORDER BY idempotency_key"
    ).fetchall()


def _records(bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {record["identity"]: record for record in bundle["records"]}


def test_frozen_fixture_is_genuine_v6_with_existing_evidence() -> None:
    assert hashlib.sha256(V6.read_bytes()).hexdigest() == V6_SHA256
    with closing(sqlite3.connect(f"{V6.as_uri()}?mode=ro&immutable=1", uri=True)) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 6
        assert conn.execute("SELECT COUNT(*) FROM drawers").fetchone()[0] == 3
        assert conn.execute("SELECT supersedes_id FROM drawers WHERE id=2").fetchone()[0] == 1
        assert conn.execute("SELECT state FROM workflow_runs").fetchone()[0] == "committed"


def test_v6_migration_preserves_every_existing_column_vector_and_receipt(tmp_path: Path) -> None:
    _api()
    path = tmp_path / "legacy.db"
    shutil.copyfile(V6, path)
    before = _snapshot(path, receipts=True)
    with closing(sqlite3.connect(path)) as conn:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        columns = {
            name: [row[1] for row in conn.execute('PRAGMA table_info("' + name + '")')]
            for name in ("drawers", "workflow_runs", "store_metadata", "vec_drawers")
        }
    with DrawerStore(path, HashEmbeddingProvider(dimension=16)) as store:
        identities = [store.portable_identity(item) for item in (1, 2, 3)]
        assert len(set(identities)) == 3
        for identity in identities:
            assert str(UUID(identity)) == identity
        for name, names in columns.items():
            selected = ",".join('"' + value + '"' for value in names)
            query = f'SELECT {selected} FROM "{name}"'  # noqa: S608
            after = sorted(map(tuple, store._conn.execute(query).fetchall()), key=repr)
            prior = before[name]
            if name == "store_metadata":
                assert set(prior).issubset(set(map(tuple, after)))
            else:
                assert list(map(tuple, after)) == prior
    with DrawerStore(path, HashEmbeddingProvider(dimension=16)) as reopened:
        assert [reopened.portable_identity(item) for item in (1, 2, 3)] == identities
    assert hashlib.sha256(V6.read_bytes()).hexdigest() == V6_SHA256


def test_identity_survives_local_mutation_restart_and_clone_without_new_collisions(
    stores: Any, tmp_path: Path
) -> None:
    _api()
    source, other = stores("source"), stores("other")
    first, second = _add(source, "identical text"), _add(other, "identical text")
    identity = source.portable_identity(first.id)
    assert identity != other.portable_identity(second.id)
    original = source.portable_source(first.id)
    source.update_layer(first.id, Layer.DEEP)
    source.reinforce(first.id)
    source.add_anchors(first.id, [{"path": "src/example.py"}])
    source.get(first.id)
    assert source.portable_identity(first.id) == identity
    assert source.portable_source(first.id) == original
    with closing(sqlite3.connect(tmp_path / "clone.db")) as conn:
        source._conn.backup(conn)
    clone = stores("clone")
    assert clone.portable_identity(first.id) == identity
    left, right = _add(source, "new after clone"), _add(clone, "new after clone")
    assert source.portable_identity(left.id) != clone.portable_identity(right.id)


def test_three_store_roundtrip_preserves_original_envelopes_and_numeric_source_references(
    stores: Any, tmp_path: Path
) -> None:
    _api()
    first, second, third = stores("first"), stores("second"), stores("third")
    original = _add(first, "Original evidence.")
    linked = _add(
        first,
        f"Exact reference cairntir://drawer/{original.id}; count 1 is not a reference.",
        supersedes_id=original.id,
        metadata={"evidence_drawer_ids": [original.id], "ordinary_count": 1},
    )
    for store in (second, third):
        for index in range(4):
            _add(store, f"Destination-only collision {index}.")
    source_bundle = _export(first, tmp_path / "a.json")
    imported = _import(second, tmp_path / "a.json")
    relay_bundle = _export(
        second, tmp_path / "b.json", drawer_ids=list(imported["identity_map"].values())
    )
    assert _records(relay_bundle) == _records(source_bundle)
    final = _import(third, tmp_path / "b.json")
    for identity, record in _records(source_bundle).items():
        local_id = final["identity_map"][identity]
        assert third.portable_source(local_id) == record
        assert third.get(local_id).content == record["drawer"]["content"]
        assert third.get_provenance(local_id).trust is TrustLevel.UNTRUSTED
    identity = first.portable_identity(linked.id)
    local = third.get(final["identity_map"][identity])
    assert local.supersedes_id == final["identity_map"][first.portable_identity(original.id)]
    assert local.content == linked.content
    assert third.get(1).content.startswith("Destination-only collision")


def test_reference_map_names_typed_paths_without_rewriting_specialized_metadata(
    stores: Any, tmp_path: Path
) -> None:
    _api()
    source, target = stores("source"), stores("target")
    evidence = _add(source, "Evidence for the source maps.")
    linked = _add(
        source,
        f"Source cairntir://drawer/{evidence.id} stays exact.",
        metadata={
            "evidence_drawer_ids": [evidence.id],
            "counterexample_drawer_ids": [evidence.id],
            "walkthrough_id": evidence.id,
            "derived_from": [evidence.id],
            "payload": {"evidence_ids": [evidence.id], "parent_drawer_id": evidence.id},
            "ordinary_count": evidence.id,
        },
    )
    bundle = _export(source, tmp_path / "references.json", drawer_ids=[linked.id])
    record = _records(bundle)[source.portable_identity(linked.id)]
    refs = record["references"]
    paths = {item["path"] for item in refs}
    assert {
        "/content",
        "/metadata/evidence_drawer_ids/0",
        "/metadata/counterexample_drawer_ids/0",
        "/metadata/walkthrough_id",
        "/metadata/derived_from/0",
        "/metadata/payload/evidence_ids/0",
        "/metadata/payload/parent_drawer_id",
    } <= paths
    assert "/metadata/ordinary_count" not in paths
    for item in refs:
        assert item["kind"] in {"source", "evidence", "counterexample", "supersedes"}
        assert item["source_target_id"] == evidence.id
        assert item["target_identity"] == source.portable_identity(evidence.id)
    result = _import(target, tmp_path / "references.json")
    relations = target.portable_relations(result["identity_map"][record["identity"]])
    assert len(relations) == len(refs)
    for item in relations:
        assert item["target_drawer_id"] == result["identity_map"][item["target_identity"]]
    assert (
        target.portable_source(result["identity_map"][record["identity"]])["drawer"]["metadata"]
        == linked.metadata
    )


def test_new_local_reference_to_imported_evidence_keeps_referring_origin_namespace(
    stores: Any, tmp_path: Path
) -> None:
    _api()
    first, second, third = stores("first"), stores("second"), stores("third")
    evidence = _add(first, "Evidence originally authored in store A.")
    for index in range(4):
        _add(second, f"B-local collision {index}.")
    _export(first, tmp_path / "a.json")
    imported = _import(second, tmp_path / "a.json")
    identity = first.portable_identity(evidence.id)
    second_id = imported["identity_map"][identity]
    assert second_id != evidence.id
    authored = _add(second, f"New B-local reference cairntir://drawer/{second_id}.")
    bundle = _export(second, tmp_path / "b.json", drawer_ids=[authored.id])
    record = _records(bundle)[second.portable_identity(authored.id)]
    reference = next(item for item in record["references"] if item["path"] == "/content")
    assert record["source_store_id"] != first.portable_source(evidence.id)["source_store_id"]
    assert reference["source_target_id"] == second_id
    assert reference["target_identity"] == identity
    result = _import(third, tmp_path / "b.json")
    local_id = result["identity_map"][record["identity"]]
    assert third.get(local_id).content == authored.content
    assert third.portable_source(local_id) == record
    assert (
        third.portable_relations(local_id)[0]["target_drawer_id"]
        == result["identity_map"][identity]
    )


def test_competing_successors_remain_two_branches_after_import(stores: Any, tmp_path: Path) -> None:
    _api()
    source, target = stores("source"), stores("target")
    root = _add(source, "Initial claim.")
    left = _add(source, "Left correction.", supersedes_id=root.id)
    right = _add(source, "Right correction.", supersedes_id=root.id)
    _export(source, tmp_path / "branches.json")
    result = _import(target, tmp_path / "branches.json")
    mapping = result["identity_map"]
    root_id = mapping[source.portable_identity(root.id)]
    assert {item.id for item in target.list_by(limit=None) if item.supersedes_id == root_id} == {
        mapping[source.portable_identity(left.id)],
        mapping[source.portable_identity(right.id)],
    }


def test_hash_binds_identity_provenance_and_reference_mapping(stores: Any, tmp_path: Path) -> None:
    _api()
    source, target = stores("source"), stores("target")
    first = _add(source, "Hash-bound original.")
    _add(source, "Hash-bound successor.", supersedes_id=first.id)
    path = tmp_path / "hash.json"
    original = _export(source, path)
    before = _snapshot(tmp_path / "target.db")
    for field in ("identity", "provenance", "references"):
        changed = copy.deepcopy(original)
        record = next(item for item in changed["records"] if item["references"])
        if field == "identity":
            record[field] = "00000000-0000-4000-8000-000000000001"
        elif field == "provenance":
            record[field]["host"] = "forged-origin"
        else:
            record[field][0]["target_identity"] = record["identity"]
        _write(path, changed)
        with pytest.raises(CairntirError):
            portable.import_bundle(target, path)
        assert _snapshot(tmp_path / "target.db") == before
        assert _success_receipts(target) == []


def test_existing_identity_conflict_rolls_back_new_records(stores: Any, tmp_path: Path) -> None:
    _api()
    source, target = stores("source"), stores("target")
    old = _add(source, "Original immutable evidence.")
    path = tmp_path / "conflict.json"
    _export(source, path)
    _import(target, path)
    _add(source, "New record must not partially commit.")
    bundle = _export(source, path)
    _records(bundle)[source.portable_identity(old.id)]["drawer"]["content"] = (
        "Altered historical claim."
    )
    _write(path, _seal(bundle))
    before, receipts = _snapshot(tmp_path / "target.db"), _success_receipts(target)
    with pytest.raises(CairntirError):
        portable.import_bundle(target, path)
    assert _snapshot(tmp_path / "target.db") == before
    assert _success_receipts(target) == receipts


def test_conflicting_duplicate_identity_inside_bundle_is_rejected(
    stores: Any, tmp_path: Path
) -> None:
    _api()
    source, target = stores("source"), stores("target")
    _add(source, "One identity.")
    path = tmp_path / "duplicate.json"
    bundle = _export(source, path)
    duplicate = copy.deepcopy(bundle["records"][0])
    duplicate["drawer"]["content"] = "Different evidence under the same identity."
    bundle["records"].append(duplicate)
    _write(path, _seal(bundle))
    before = _snapshot(tmp_path / "target.db")
    with pytest.raises(CairntirError):
        portable.import_bundle(target, path)
    assert _snapshot(tmp_path / "target.db") == before
    assert _success_receipts(target) == []


def test_dangling_required_relation_rejects_entire_import(stores: Any, tmp_path: Path) -> None:
    _api()
    source, target = stores("source"), stores("target")
    first = _add(source, "Required target.")
    _add(source, "Dependent record.", supersedes_id=first.id)
    path = tmp_path / "dangling.json"
    bundle = _export(source, path)
    bundle["records"] = [
        item for item in bundle["records"] if item["identity"] != source.portable_identity(first.id)
    ]
    _write(path, _seal(bundle))
    before = _snapshot(tmp_path / "target.db")
    with pytest.raises(CairntirError):
        portable.import_bundle(target, path)
    assert _snapshot(tmp_path / "target.db") == before
    assert _success_receipts(target) == []


def test_numeric_reference_cannot_be_rebound_by_a_validly_rehashed_map(
    stores: Any, tmp_path: Path
) -> None:
    _api()
    source, target = stores("source"), stores("target")
    first = _add(source, "Intended reference.")
    other = _add(source, "Unrelated reference.")
    linked = _add(source, f"cairntir://drawer/{first.id}", supersedes_id=first.id)
    path = tmp_path / "rebound.json"
    bundle = _export(source, path)
    record = _records(bundle)[source.portable_identity(linked.id)]
    for ref in record["references"]:
        ref["target_identity"] = source.portable_identity(other.id)
    _write(path, _seal(bundle))
    before = _snapshot(tmp_path / "target.db")
    with pytest.raises(CairntirError):
        portable.import_bundle(target, path)
    assert _snapshot(tmp_path / "target.db") == before


def test_unmapped_numeric_uri_is_not_silently_bound_to_destination(
    stores: Any, tmp_path: Path
) -> None:
    _api()
    source, target = stores("source"), stores("target")
    first = _add(source, "Source evidence.")
    linked = _add(source, f"A source-local URI cairntir://drawer/{first.id}.")
    _add(target, "Destination collision.")
    path = tmp_path / "unmapped.json"
    bundle = _export(source, path)
    _records(bundle)[source.portable_identity(linked.id)]["references"] = []
    _write(path, _seal(bundle))
    before = _snapshot(tmp_path / "target.db")
    with pytest.raises(CairntirError):
        portable.import_bundle(target, path)
    assert _snapshot(tmp_path / "target.db") == before


def test_import_failures_roll_back_graph_vectors_maps_and_committed_receipt_then_retry(
    stores: Any, tmp_path: Path
) -> None:
    _api()

    class FailingHash(HashEmbeddingProvider):
        fail = True

        def embed(self, texts: Any) -> Any:
            if self.fail:
                raise EmbeddingError("injected embedding failure")
            return super().embed(texts)

    source = stores("source")
    first = _add(source, "Atomic first.")
    _add(source, "Atomic second.", supersedes_id=first.id)
    path = tmp_path / "atomic.json"
    _export(source, path)
    embedder = FailingHash(dimension=16)
    target = stores("target", embedder)
    before = _snapshot(tmp_path / "target.db")
    with pytest.raises(CairntirError, match="injected embedding failure"):
        portable.import_bundle(target, path, idempotency_key="atomic-retry")
    assert _snapshot(tmp_path / "target.db") == before
    assert _success_receipts(target) == []
    embedder.fail = False
    target._conn.execute(
        "CREATE TRIGGER acceptance_failure BEFORE INSERT ON drawers "
        "WHEN (SELECT COUNT(*) FROM drawers) = 1 "
        "BEGIN SELECT RAISE(ABORT, 'injected second row failure'); END"
    )
    with pytest.raises(CairntirError, match="injected second row failure"):
        portable.import_bundle(target, path, idempotency_key="atomic-retry")
    assert _snapshot(tmp_path / "target.db") == before
    assert _success_receipts(target) == []
    target._conn.execute("DROP TRIGGER acceptance_failure")
    result = _import(target, path, idempotency_key="atomic-retry")
    assert result["imported"] == 2
    assert len(target.list_by(limit=None)) == 2
    assert target._conn.execute("SELECT COUNT(*) FROM vec_drawers").fetchone()[0] == 2
    receipt = target.workflow_receipt("atomic-retry")
    assert receipt is not None and receipt.state.value == "committed"


def test_separate_process_concurrent_imports_preserve_one_graph_and_receipt(
    stores: Any, tmp_path: Path
) -> None:
    _api()
    source = stores("source")
    first = _add(source, "Concurrent original.")
    for index in range(8):
        _add(source, f"Concurrent descendant {index}.", supersedes_id=first.id)
    path = tmp_path / "concurrent.json"
    _export(source, path)
    database = tmp_path / "target.db"
    with DrawerStore(database, HashEmbeddingProvider(dimension=16)):
        pass
    script = """
import json,sys
from pathlib import Path
from cairntir.memory.store import DrawerStore
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.portable import import_bundle
with DrawerStore(Path(sys.argv[1]),HashEmbeddingProvider(dimension=16)) as store:
    print('READY',flush=True)
    assert sys.stdin.readline().strip()=='GO'
    print(json.dumps(import_bundle(store,Path(sys.argv[2]),idempotency_key='concurrent-import')),flush=True)
"""
    processes: list[subprocess.Popen[str]] = []
    ready: Queue[str] = Queue()
    try:
        for _ in range(2):
            processes.append(
                subprocess.Popen(  # noqa: S603
                    [sys.executable, "-c", script, str(database), str(path)],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=ROOT,
                    env={**os.environ, "CAIRNTIR_HOME": str(tmp_path / "child-home")},
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            )
        for process in processes:
            Thread(
                target=lambda stream: ready.put(stream.readline().strip()),
                args=(process.stdout,),
                daemon=True,
            ).start()
        for _ in processes:
            assert ready.get(timeout=30) == "READY"
        for process in processes:
            process.stdin.write("GO\n")
            process.stdin.flush()
        results = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=60)
            assert process.returncode == 0, stderr
            results.append(json.loads(stdout))
        assert results[0]["identity_map"] == results[1]["identity_map"]
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=10)
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
    with DrawerStore(database, HashEmbeddingProvider(dimension=16)) as target:
        assert len(target.list_by(limit=None)) == 9
        assert target._conn.execute("SELECT COUNT(*) FROM vec_drawers").fetchone()[0] == 9
        assert len(_success_receipts(target)) == 1
        assert len({target.portable_identity(item.id) for item in target.list_by(limit=None)}) == 9


def test_overlapping_reordered_bundles_deduplicate_by_identity_not_file_hash(
    stores: Any, tmp_path: Path
) -> None:
    _api()
    source, target = stores("source"), stores("target")
    first = _add(source, "Overlapping first.")
    path = tmp_path / "overlap.json"
    _export(source, path)
    one = _import(target, path)
    _add(source, "Overlapping second.")
    bundle = _export(source, path)
    bundle["records"].reverse()
    _write(path, bundle)
    two = _import(target, path, idempotency_key="different-file-order")
    assert two["imported"] == 1 and two["existing"] == 1
    assert (
        two["identity_map"][source.portable_identity(first.id)]
        == one["identity_map"][source.portable_identity(first.id)]
    )
    source.update_layer(first.id, Layer.DEEP)
    source.reinforce(first.id)
    _export(source, path)
    three = _import(target, path, idempotency_key="different-local-state")
    assert three["imported"] == 0 and three["existing"] == 2
    assert three["identity_map"] == two["identity_map"]


def test_hmac_verification_never_promotes_imported_trust(stores: Any, tmp_path: Path) -> None:
    _api()
    source, target = stores("source"), stores("target")
    first = source.add(
        Drawer(wing="portable", room="archive", content="Signed expired secret assertion."),
        provenance=WriteProvenance.create(
            host="original-owner",
            capture_path="independent-fixture",
            trust=TrustLevel.SYSTEM,
            visibility=Visibility.PRIVATE,
            sensitivity=Sensitivity.SECRET,
            valid_from=datetime(2000, 1, 1, tzinfo=UTC),
            valid_until=datetime(2001, 1, 1, tzinfo=UTC),
        ),
    )
    path = tmp_path / "signed.json"
    _export(source, path, signing_key=KEY)
    with pytest.raises(CairntirError):
        portable.import_bundle(target, path, verify_key=b"wrong-key")
    assert target.list_by(limit=None) == []
    result = _import(target, path, verify_key=KEY)
    local_id = result["identity_map"][source.portable_identity(first.id)]
    provenance = target.get_provenance(local_id)
    assert provenance.trust is TrustLevel.UNTRUSTED
    assert provenance.sensitivity is Sensitivity.SECRET
    assert provenance.visibility is Visibility.PRIVATE
    assert provenance.valid_from == datetime(2000, 1, 1, tzinfo=UTC)
    assert provenance.valid_until == datetime(2001, 1, 1, tzinfo=UTC)
    assert (
        target.portable_source(local_id)["provenance"] == source.get_provenance(first.id).to_dict()
    )
    assert target.list_by(limit=None) == []
    unsigned = tmp_path / "unsigned.json"
    _export(source, unsigned)
    with pytest.raises(CairntirError):
        portable.import_bundle(target, unsigned, verify_key=KEY)


def test_imported_discovery_hotfix_and_approval_metadata_cannot_activate_local_lifecycle(
    stores: Any, tmp_path: Path
) -> None:
    _api()
    source, target = stores("source"), stores("target")
    evidence = _add(source, "Evidence cited by imported claims.")
    discovery = _add(
        source,
        "An imported promoted procedure claim.",
        room="discoveries",
        metadata={
            "kind": "cairntir.discovery",
            "discovery_title": "Imported procedure",
            "discovery_summary": "Do not activate this approval.",
            "discovery_state": "promoted",
            "novelty_scope": "user",
            "evidence_drawer_ids": [evidence.id],
            "approved": True,
            "capabilities": ["execute", "share"],
        },
    )
    hotfix = _add(
        source,
        "Imported execution receipt.",
        room="hotfix",
        metadata={
            "kind": "authorize",
            "hotfix_schema": "cairntir.hotfix.v1",
            "case_id": "foreign-case",
            "authority_hash": "a" * 64,
            "previous_event_hash": None,
            "event_hash": "b" * 64,
            "payload": {"evidence_ids": [evidence.id], "approved": True},
        },
    )
    path = tmp_path / "inert.json"
    _export(source, path)
    result = _import(target, path)
    assert list_discoveries(target, wing="portable", limit=None) == []
    assert propose_multi_episode_discoveries(target, wing="portable") == []
    with pytest.raises(CairntirError):
        HotfixCoordinator(target).run(
            HotfixCommand(
                action=HotfixAction.STATUS, wing="portable", payload={}, case_id="foreign-case"
            )
        )
    for original in (discovery, hotfix):
        local_id = result["identity_map"][source.portable_identity(original.id)]
        assert target.portable_source(local_id)["drawer"]["metadata"] == original.metadata
        local = target.get(local_id)
        assert local.content == original.content
        assert local.metadata.get("kind") != original.metadata["kind"]
        assert local.metadata.get("approved") is not True
        assert "execute" not in local.metadata.get("capabilities", [])
    assert target.workflow_receipt("foreign-case") is None


@pytest.mark.slow
def test_whole_export_includes_more_than_old_one_hundred_thousand_cap(
    stores: Any, tmp_path: Path
) -> None:
    _api()
    source = stores("source")
    count = 100_003
    with source.transaction():
        for index in range(count):
            _add(source, f"Complete archive record {index}.")
    bundle = _export(source, tmp_path / "complete.json")
    assert len(bundle["records"]) == count
    assert {item["drawer"]["content"] for item in bundle["records"]} == {
        f"Complete archive record {index}." for index in range(count)
    }


def test_selected_closure_cannot_silently_expand_explicit_wing_or_room_scope(
    stores: Any, tmp_path: Path
) -> None:
    _api()
    source = stores("source")
    target = _add(source, "Dependency outside requested scope.", wing="elsewhere", room="private")
    selected = _add(source, "Selected with scoped dependency.", supersedes_id=target.id)
    path = tmp_path / "scope.json"
    for scope in ({"wing": "portable"}, {"room": "archive"}):
        with pytest.raises(CairntirError):
            portable.export_bundle(source, path, drawer_ids=[selected.id], **scope)
        assert not path.exists()
    complete = _export(source, path, drawer_ids=[selected.id])
    assert len(complete["records"]) == 2


def test_failed_export_preserves_existing_destination_without_partial_temp_files(
    stores: Any, tmp_path: Path
) -> None:
    _api()
    source = stores("source")
    _add(source, "First exportable record.")
    _add(source, "Unresolved reference cairntir://drawer/987654321.")
    output = tmp_path / "output"
    output.mkdir()
    path = output / "archive.json"
    previous = b"Existing archive bytes.\n"
    path.write_bytes(previous)
    with pytest.raises(CairntirError):
        portable.export_bundle(source, path)
    assert path.read_bytes() == previous
    assert list(output.iterdir()) == [path]


def test_v2_preserves_external_urls_without_network_while_v1_still_rejects(
    stores: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _api()
    calls: list[Any] = []

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        calls.append((args, kwargs))
        raise AssertionError("portable evidence attempted network I/O")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    source, target = stores("source"), stores("target")
    text = (
        "Source https://example.org/paper?q=a&b=two#section\nfile:///source/original.txt is inert."
    )
    original = _add(source, text, metadata={"source_url": "https://example.org/metadata"})
    with pytest.raises(CairntirError):
        portable.encode_drawer(original)
    path = tmp_path / "url.json"
    _export(source, path)
    result = _import(target, path)
    local_id = result["identity_map"][source.portable_identity(original.id)]
    assert target.get(local_id).content == text
    assert target.portable_source(local_id)["drawer"]["metadata"] == original.metadata
    assert calls == []


def test_malformed_input_has_typed_errors_and_no_committed_partial_state(
    stores: Any, tmp_path: Path
) -> None:
    _api()
    source, target = stores("source"), stores("target")
    _add(source, "Valid shape.")
    path = tmp_path / "invalid.json"
    bundle = _export(source, path)
    before = _snapshot(tmp_path / "target.db")
    wrong_version = copy.deepcopy(bundle)
    wrong_version["format_version"] = True
    missing_origin = copy.deepcopy(bundle)
    del missing_origin["records"][0]["source_store_id"]
    _seal(missing_origin)
    for raw in (
        b"\xff",
        b'{"truncated":',
        b"[]",
        _canonical(wrong_version),
        _canonical(missing_origin),
    ):
        path.write_bytes(raw)
        with pytest.raises(CairntirError):
            portable.import_bundle(target, path)
        assert _snapshot(tmp_path / "target.db") == before
        assert _success_receipts(target) == []


def test_identity_source_relation_reads_and_export_preserve_all_persisted_state(
    stores: Any, tmp_path: Path
) -> None:
    _api()
    source = stores("source")
    first = _add(source, "Read-only first.")
    second = _add(source, "Read-only successor.", supersedes_id=first.id)
    before = _snapshot(tmp_path / "source.db", receipts=True)
    for _ in range(2):
        for drawer in (first, second):
            identity = source.portable_identity(drawer.id)
            record = source.portable_source(drawer.id)
            assert record["identity"] == identity
            assert str(UUID(record["source_store_id"])) == record["source_store_id"]
            assert record["source_drawer_id"] == drawer.id
            source.portable_relations(drawer.id)
        _export(source, tmp_path / "read-only.json")
    assert _snapshot(tmp_path / "source.db", receipts=True) == before


def test_idempotency_key_cannot_be_reused_for_different_bundle(stores: Any, tmp_path: Path) -> None:
    _api()
    source, target = stores("source"), stores("target")
    _add(source, "Initial import.")
    path = tmp_path / "retry.json"
    _export(source, path)
    first = _import(target, path, idempotency_key="fixed-key")
    replay = _import(target, path, idempotency_key="fixed-key")
    assert replay["identity_map"] == first["identity_map"]
    _add(source, "Different requested import.")
    _export(source, path)
    before, receipts = _snapshot(tmp_path / "target.db"), _success_receipts(target)
    with pytest.raises(CairntirError):
        portable.import_bundle(target, path, idempotency_key="fixed-key")
    assert _snapshot(tmp_path / "target.db") == before
    assert _success_receipts(target) == receipts
