from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from test_recovery_outcomes import TEXT, add, child, contents

from cairntir.errors import MemoryStoreError
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import (
    DrawerStore,
    backup_database,
    inspect_database_integrity,
    inspect_embedding_space,
    reindex_database,
)


@pytest.mark.parametrize("boundary", ["replace", "sidecar-cleanup"])
def test_reindex_filesystem_failure_preserves_source_and_can_be_retried(
    seeded, monkeypatch, boundary
):
    database, _, _ = seeded
    before = contents(database)
    unlink = Path.unlink

    def failed_replace(*args):
        raise OSError("candidate installation denied")

    def failed_cleanup(path, *args, **kwargs):
        if ".reindex-" in path.name and path.name.endswith("-wal"):
            raise OSError("candidate sidecar removal denied")
        return unlink(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        if boundary == "replace":
            patch.setattr(os, "replace", failed_replace)
        else:
            patch.setattr(Path, "unlink", failed_cleanup)
        with pytest.raises(MemoryStoreError, match="denied"):
            reindex_database(database, HashEmbeddingProvider(dimension=32))
    assert contents(database) == before
    result = reindex_database(database, HashEmbeddingProvider(dimension=32))
    assert result.drawer_count == 3
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        assert store.search(TEXT, wing="recovery", room="evidence", limit=1)[0][0].content == TEXT


@pytest.mark.parametrize(
    "operation", [backup_database, reindex_database, inspect_database_integrity]
)
def test_missing_database_is_never_created_by_recovery_or_inspection(tmp_path, operation):
    path = tmp_path / "absent.db"
    args = (
        (path, tmp_path / "backup.db")
        if operation is backup_database
        else (
            (path, HashEmbeddingProvider(dimension=32))
            if operation is reindex_database
            else (path,)
        )
    )
    with pytest.raises(MemoryStoreError, match=r"missing|does not exist"):
        operation(*args)
    assert list(tmp_path.iterdir()) == []


def test_existing_manual_backup_and_source_are_never_overwritten(seeded, tmp_path):
    database, _, _ = seeded
    destination = tmp_path / "existing.db"
    destination.write_bytes(b"previous recovery point")
    before = contents(database)
    for target in (database, destination):
        with pytest.raises(MemoryStoreError, match=r"differ|overwrite"):
            backup_database(database, target)
    assert destination.read_bytes() == b"previous recovery point"
    assert contents(database) == before


@pytest.mark.parametrize("version", [0, 999])
def test_inspection_reports_missing_schema_or_future_version_without_migration(tmp_path, version):
    database = tmp_path / "unknown.db"
    with closing(sqlite3.connect(database)) as connection:
        connection.execute(f"PRAGMA user_version={version}")
    before = database.read_bytes()
    status = inspect_embedding_space(database, HashEmbeddingProvider(dimension=32))
    assert not status.verified
    assert status.state == ("corrupt" if version == 0 else "future_schema")
    assert database.read_bytes() == before


@pytest.mark.parametrize("damage", ["no-vector-table", "wrong-dimension", "no-filter-columns"])
def test_inspection_explains_broken_vector_schema_without_rebuilding_it(seeded, damage):
    database, _, _ = seeded
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        if damage == "wrong-dimension":
            store._conn.execute(
                "UPDATE store_metadata SET value='64' WHERE key='embedding_dimension'"
            )
        else:
            store._conn.execute("DROP TABLE vec_drawers")
            if damage == "no-filter-columns":
                store._conn.execute(
                    "CREATE VIRTUAL TABLE vec_drawers USING vec0("
                    "drawer_id INTEGER PRIMARY KEY, embedding FLOAT[32])"
                )
        store._conn.commit()
    before = contents(database)
    status = inspect_embedding_space(database, HashEmbeddingProvider(dimension=32))
    assert status.state == "corrupt" and not status.verified
    required = {
        "no-vector-table": "missing",
        "wrong-dimension": "does not match",
        "no-filter-columns": "prefilter columns",
    }[damage]
    assert required in status.detail
    assert contents(database) == before


def test_vector_read_failure_does_not_masquerade_as_no_relevant_evidence(seeded):
    database, _, _ = seeded
    before = contents(database)
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        store._conn.set_authorizer(
            lambda action, table, field, *_: (
                sqlite3.SQLITE_DENY
                if action == sqlite3.SQLITE_READ and table == "vec_drawers" and field == "embedding"
                else sqlite3.SQLITE_OK
            )
        )
        try:
            with pytest.raises(MemoryStoreError, match="context vector read failed"):
                store.context_similarities(TEXT, [1])
        finally:
            store._conn.set_authorizer(None)
        assert contents(database) == before
        assert store.context_similarities(TEXT, [1])[1] == pytest.approx(1)


def test_held_reader_prevents_checkpoint_but_committed_wal_data_survives(seeded, tmp_path):
    database, _, _ = seeded
    ready = tmp_path / "reader-ready"
    code = """
import pathlib, sqlite3, sys
connection = sqlite3.connect(sys.argv[1])
connection.execute('BEGIN')
connection.execute('SELECT COUNT(*) FROM drawers').fetchone()
pathlib.Path(sys.argv[2]).write_text('ready')
sys.stdin.readline()
"""
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        with child(code, database, ready):
            saved = add(store, "committed while an older reader remains")
            store._conn.execute("PRAGMA busy_timeout=50")
            before = contents(database)
            with pytest.raises(MemoryStoreError, match="checkpoint is busy"):
                store.checkpoint()
            assert contents(database) == before
        store.checkpoint()
        assert store.get(saved.id).content == "committed while an older reader remains"
    assert contents(database)
