from __future__ import annotations

import hashlib
import json
import sqlite3
from copy import deepcopy

import pytest
from test_recovery_outcomes import TEXT, contents

from cairntir.errors import MemoryStoreError, PortableFormatError
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.portable import export_bundle, import_bundle


@pytest.fixture()
def bundle(seeded, tmp_path):
    database, _, _ = seeded
    path = tmp_path / "bundle.json"
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        export_bundle(store, path)
    return path, json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("identity", 1),
        ("identity", "invalid"),
        ("identity", "AAAAAAAA-AAAA-4AAA-AAAA-AAAAAAAAAAAA"),
        ("source_store_id", None),
        ("source_drawer_id", True),
        ("source_drawer_id", 0),
        ("drawer", []),
        ("drawer", {}),
        ("drawer.content", None),
        ("drawer.belief_mass", "2"),
        ("provenance", []),
        ("provenance", {}),
        ("provenance.trust", "unknown"),
        ("references", {}),
        ("references", [None]),
        ("references", [{"target_identity": "bad"}]),
        (
            "references",
            [{"target_identity": "aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa", "source_target_id": "1"}],
        ),
        (
            "references",
            [
                {
                    "target_identity": "aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa",
                    "source_target_id": 1,
                    "kind": "source",
                    "path": "/invented",
                }
            ],
        ),
    ],
)
def test_invalid_portable_original_is_rejected_without_coercion_or_partial_import(
    seeded, bundle, tmp_path, field, value
):
    source, _, _ = seeded
    source_before = contents(source)
    database = tmp_path / "destination.db"
    path, valid = bundle
    damaged = deepcopy(valid)
    record = next(item for item in damaged["records"] if item["source_drawer_id"] == 1)
    parts = field.split(".")
    target = record
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = value
    raw = json.dumps(
        {
            "format_version": 2,
            "records": sorted(damaged["records"], key=lambda item: str(item["identity"])),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    damaged["bundle_hash"] = "sha256:" + hashlib.sha256(raw).hexdigest()
    path.write_text(json.dumps(damaged), encoding="utf-8")
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        before = contents(database)
        with pytest.raises(PortableFormatError):
            import_bundle(store, path)
        assert contents(database) == before
        path.write_text(json.dumps(valid), encoding="utf-8")
        result = import_bundle(store, path)
        assert result["imported"] == 3 and result["existing"] == 0
        imported = [store.portable_source(item.id) for item in store.list_by()]
        assert any(item["drawer"]["content"] == TEXT for item in imported)
    assert contents(source) == source_before


@pytest.mark.parametrize("raw", ["[]", "{}", '{"format_version":2,"records":{}}', "{", "null"])
def test_invalid_bundle_envelope_cannot_change_the_store(seeded, tmp_path, raw):
    database, _, _ = seeded
    path = tmp_path / "invalid.json"
    path.write_text(raw, encoding="utf-8")
    before = contents(database)
    with (
        DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store,
        pytest.raises(PortableFormatError),
    ):
        import_bundle(store, path)
    assert contents(database) == before


@pytest.mark.parametrize("operation", ["identity-lookup", "original-replacement", "supersession"])
def test_sql_failure_during_import_preserves_all_originals_and_retry_recovers(
    bundle, tmp_path, operation
):
    path, original = bundle
    destination = tmp_path / "destination.db"
    with DrawerStore(destination, HashEmbeddingProvider(dimension=32)) as store:
        baseline = store.list_by()

        def authorize(action, table, field, *_):
            denied = (
                (
                    operation == "identity-lookup"
                    and action == sqlite3.SQLITE_READ
                    and table == "portable_records"
                    and field == "identity"
                )
                or (
                    operation == "original-replacement"
                    and action == sqlite3.SQLITE_UPDATE
                    and table == "portable_records"
                    and field == "identity"
                )
                or (
                    operation == "supersession"
                    and action == sqlite3.SQLITE_UPDATE
                    and table == "drawers"
                    and field == "supersedes_id"
                )
            )
            return sqlite3.SQLITE_DENY if denied else sqlite3.SQLITE_OK

        store._conn.set_authorizer(authorize)
        try:
            with pytest.raises(MemoryStoreError, match=r"authorized|prohibited"):
                import_bundle(store, path, idempotency_key="import-retry")
        finally:
            store._conn.set_authorizer(None)
        assert store.list_by() == baseline == []
        for table in ("vec_drawers", "portable_records"):
            assert store._conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0  # noqa: S608
        failed = store.workflow_receipt("import-retry")
        assert failed is not None and failed.state.value == "failed"
        result = import_bundle(store, path, idempotency_key="import-retry")
        assert result["imported"] == 3 and result["existing"] == 0
        for record in original["records"]:
            local_id = result["identity_map"][record["identity"]]
            assert store.portable_source(local_id) == record
        after = contents(destination)
        assert import_bundle(store, path, idempotency_key="import-retry") == result
        assert contents(destination) == after
