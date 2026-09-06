"""Independent bulk-write recount and integrity boundaries."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
import sqlite_vec

from cairntir.errors import CairntirError
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer


def _add(store: DrawerStore, number: int = 0) -> Drawer:
    return store.add(
        Drawer(wing="bulk-proof", room="evidence", content=f"Exact evidence {number}.")
    )


def _counts(trace: list[str]) -> int:
    return sum("select count(*) from vec_drawers" in " ".join(sql.lower().split()) for sql in trace)


def test_fifty_adds_in_one_transaction_have_bounded_full_vector_recounts(tmp_path: Path) -> None:
    with DrawerStore(tmp_path / "memory.db", HashEmbeddingProvider(dimension=32)) as store:
        trace: list[str] = []
        store._conn.set_trace_callback(trace.append)
        with store.transaction():
            for number in range(50):
                _add(store, number)
        assert 1 <= _counts(trace) <= 3, "full-vector COUNT must not run once per addition"
        status = store.embedding_status()
        assert status.verified and status.drawer_count == status.vector_count == 50


def test_vector_corruption_is_freshly_visible_and_next_add_is_atomic(tmp_path: Path) -> None:
    with (
        DrawerStore(tmp_path / "memory.db", HashEmbeddingProvider(dimension=32)) as store,
        store.transaction(),
    ):
        saved = _add(store)
        assert store.embedding_status().verified
        store._conn.execute("DELETE FROM vec_drawers WHERE drawer_id=?", (saved.id,))
        status = store.embedding_status()
        assert not status.verified and status.drawer_count == 1 and status.vector_count == 0
        with pytest.raises(CairntirError):
            _add(store, 1)
        assert store._conn.execute("SELECT COUNT(*) FROM drawers").fetchone()[0] == 1
        assert store._conn.execute("SELECT COUNT(*) FROM vec_drawers").fetchone()[0] == 0


def test_intervening_embedding_identity_change_rejects_next_add(tmp_path: Path) -> None:
    with (
        DrawerStore(tmp_path / "memory.db", HashEmbeddingProvider(dimension=32)) as store,
        store.transaction(),
    ):
        _add(store)
        rows = store._conn.execute("SELECT key,value FROM store_metadata").fetchall()
        keys = [row[0] for row in rows if "embedding" in row[0] and "space" in row[0]]
        assert len(keys) == 1, "fixture must identify the actual persisted embedding identity"
        store._conn.execute(
            "UPDATE store_metadata SET value=? WHERE key=?", ("different-space", keys[0])
        )
        with pytest.raises(CairntirError):
            _add(store, 1)
        assert store._conn.execute("SELECT COUNT(*) FROM drawers").fetchone()[0] == 1
        assert store._conn.execute("SELECT COUNT(*) FROM vec_drawers").fetchone()[0] == 1


def test_schema_change_forces_fresh_integrity_verification(tmp_path: Path) -> None:
    with DrawerStore(tmp_path / "memory.db", HashEmbeddingProvider(dimension=32)) as store:
        trace: list[str] = []
        store._conn.set_trace_callback(trace.append)
        with store.transaction():
            _add(store)
            before = _counts(trace)
            store._conn.execute("CREATE TABLE independent_schema_change (value TEXT)")
            _add(store, 1)
            assert _counts(trace) > before, "schema changes must invalidate bulk verification"
        assert store.embedding_status().verified


def test_rollback_new_transaction_and_external_writer_invalidate_bulk_cache(tmp_path: Path) -> None:
    path = tmp_path / "memory.db"
    with DrawerStore(path, HashEmbeddingProvider(dimension=32)) as store:
        saved = _add(store)
        with pytest.raises(RuntimeError, match="rollback fixture"), store.transaction():
            _add(store, 1)
            raise RuntimeError("rollback fixture")
        assert len(store.list_by(limit=None)) == 1
        trace: list[str] = []
        store._conn.set_trace_callback(trace.append)
        with store.transaction():
            _add(store, 2)
        assert _counts(trace) >= 1, "a new transaction must verify again after rollback"
        with closing(sqlite3.connect(path)) as external:
            external.enable_load_extension(True)
            sqlite_vec.load(external)
            external.enable_load_extension(False)
            external.execute("DELETE FROM vec_drawers WHERE drawer_id=?", (saved.id,))
            external.commit()
        with store.transaction(), pytest.raises(CairntirError):
            _add(store, 3)
        assert store._conn.execute("SELECT COUNT(*) FROM drawers").fetchone()[0] == 2
        assert store._conn.execute("SELECT COUNT(*) FROM vec_drawers").fetchone()[0] == 1


def test_cached_verification_never_bypasses_per_write_vector_length(tmp_path: Path) -> None:
    class TruncatedProvider(HashEmbeddingProvider):
        def __init__(self) -> None:
            super().__init__(dimension=32)
            self.truncate = False

        def embed(self, texts: list[str]) -> list[list[float]]:
            vectors = super().embed(texts)
            return [vector[:-1] for vector in vectors] if self.truncate else vectors

    provider = TruncatedProvider()
    with DrawerStore(tmp_path / "memory.db", provider) as store, store.transaction():
        _add(store)
        provider.truncate = True
        with pytest.raises(CairntirError):
            _add(store, 1)
        assert store._conn.execute("SELECT COUNT(*) FROM drawers").fetchone()[0] == 1
        assert store._conn.execute("SELECT COUNT(*) FROM vec_drawers").fetchone()[0] == 1
