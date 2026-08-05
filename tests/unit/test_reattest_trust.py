"""Unit tests for retiring the v6-migration 'untrusted' trust stamp."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer, Layer
from cairntir.provenance import TrustLevel, WriteProvenance, legacy_provenance


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[DrawerStore]:
    with DrawerStore(tmp_path / "cairntir.db", HashEmbeddingProvider(dimension=32)) as s:
        yield s


def _drawer(content: str, *, wing: str = "cairntir", room: str = "phase-1") -> Drawer:
    return Drawer(wing=wing, room=room, content=content, layer=Layer.ON_DEMAND)


def _drawer_trust(store: DrawerStore, drawer_id: int) -> str:
    row = store._conn.execute("SELECT trust FROM drawers WHERE id = ?", (drawer_id,)).fetchone()
    return str(row["trust"])


def _vec_trust(store: DrawerStore, drawer_id: int) -> str:
    row = store._conn.execute(
        "SELECT trust FROM vec_drawers WHERE drawer_id = ?", (drawer_id,)
    ).fetchone()
    return str(row["trust"])


def _receipt(store: DrawerStore, drawer_id: int) -> WriteProvenance:
    row = store._conn.execute(
        "SELECT provenance FROM drawers WHERE id = ?", (drawer_id,)
    ).fetchone()
    return WriteProvenance.from_json(str(row["provenance"]))


def test_legacy_migration_drawers_are_identified(store: DrawerStore) -> None:
    legacy = store.add(_drawer("migrated from a predecessor"), provenance=legacy_provenance())
    normal = store.add(_drawer("written through the normal path"))
    assert store.legacy_migration_drawer_ids() == [legacy.id]
    assert normal.id not in store.legacy_migration_drawer_ids()


def test_reattest_moves_only_legacy_migration_drawers(store: DrawerStore) -> None:
    legacy = store.add(_drawer("migrated drawer"), provenance=legacy_provenance())
    normal = store.add(_drawer("normal drawer"))
    assert store.reattest_legacy_trust() == [legacy.id]
    assert _drawer_trust(store, legacy.id) == TrustLevel.LEGACY_MIGRATED.value
    assert _drawer_trust(store, normal.id) == TrustLevel.UNTRUSTED.value


def test_reattest_keeps_all_three_trust_copies_consistent(store: DrawerStore) -> None:
    legacy = store.add(_drawer("migrated drawer"), provenance=legacy_provenance())
    store.reattest_legacy_trust()
    assert _drawer_trust(store, legacy.id) == TrustLevel.LEGACY_MIGRATED.value
    assert _vec_trust(store, legacy.id) == TrustLevel.LEGACY_MIGRATED.value
    assert _receipt(store, legacy.id).trust is TrustLevel.LEGACY_MIGRATED


def test_reattest_preserves_content_and_migration_receipt(store: DrawerStore) -> None:
    legacy = store.add(_drawer("verbatim, never summarized"), provenance=legacy_provenance())
    store.reattest_legacy_trust()
    fetched = store.get(legacy.id)
    assert fetched is not None
    assert fetched.content == "verbatim, never summarized"
    receipt = _receipt(store, legacy.id)
    assert receipt.host == "legacy"
    assert receipt.capture_path == "pre-v6-migration"


def test_reattest_is_idempotent(store: DrawerStore) -> None:
    store.add(_drawer("migrated drawer"), provenance=legacy_provenance())
    assert len(store.reattest_legacy_trust()) == 1
    assert store.reattest_legacy_trust() == []
    assert store.legacy_migration_drawer_ids() == []
