"""Independent cache-invalidating SQLite TEMP DDL and savepoint rollback probes."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from cairntir.errors import EmbeddingSpaceError
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer


def _add(store: DrawerStore, text: str) -> Drawer:
    return store.add(Drawer(wing="bulk-review", room="evidence", content=text))


class _OtherSpace(HashEmbeddingProvider):
    @property
    def embedding_space_id(self) -> str:
        return "bulk-review/negated-vectors-v1"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[-value for value in vector] for vector in super().embed(texts)]


def test_temp_trigger_cannot_hide_corrupt_index_from_the_next_append(tmp_path: Path) -> None:
    with (
        DrawerStore(tmp_path / "temp-trigger.db", HashEmbeddingProvider(dimension=16)) as store,
        store.transaction(),
    ):
        first = _add(store, "original verified index entry")
        assert first.id == 1
        store._conn.execute(
            "CREATE TEMP TRIGGER remove_original_vector AFTER INSERT ON main.drawers "
            "BEGIN DELETE FROM vec_drawers WHERE drawer_id=1; END"
        )
        _add(store, "trigger executes while the paired append completes")
        assert store.embedding_status().state == "corrupt"
        before = len(store.list_by(limit=None))
        with pytest.raises(EmbeddingSpaceError):
            _add(store, "must not reuse a verified status over trigger corruption")
        assert len(store.list_by(limit=None)) == before


def test_savepoint_rollback_revalidates_restored_embedding_metadata(tmp_path: Path) -> None:
    with (
        DrawerStore(tmp_path / "savepoint.db", HashEmbeddingProvider(dimension=16)) as store,
        store.transaction(),
    ):
        original = _add(store, "original provider evidence")
        with (
            pytest.raises(RuntimeError, match="deliberate savepoint rollback"),
            store.transaction(),
        ):
            store._embedder = _OtherSpace(dimension=16)
            store.reindex_embeddings()
            _add(store, "verified append in the temporary replacement space")
            raise RuntimeError("deliberate savepoint rollback")
        assert {drawer.id for drawer in store.list_by(limit=None)} == {original.id}
        assert store.embedding_status().state == "mismatch"
        with pytest.raises(EmbeddingSpaceError):
            _add(store, "new provider cannot append into restored original vectors")
        assert {drawer.id for drawer in store.list_by(limit=None)} == {original.id}
