"""Unit tests for the v1.1 temporal walk over the supersedes chain."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cairntir.errors import MemoryStoreError
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer, Layer
from cairntir.memory.temporal import as_of, walk_supersedes


def _build_chain(store: DrawerStore, *, wing: str, room: str) -> tuple[int, int, int]:
    """Write a three-drawer supersedes chain and return (root, mid, leaf) ids."""
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    t1 = t0 + timedelta(days=1)
    t2 = t0 + timedelta(days=2)

    root = store.add(
        Drawer(
            wing=wing,
            room=room,
            content="root — first prediction",
            layer=Layer.ON_DEMAND,
            claim="c",
            predicted_outcome="p-v1",
            created_at=t0,
        )
    )
    assert root.id is not None
    mid = store.add(
        Drawer(
            wing=wing,
            room=room,
            content="mid — revised prediction",
            layer=Layer.ON_DEMAND,
            claim="c",
            predicted_outcome="p-v2",
            supersedes_id=root.id,
            created_at=t1,
        )
    )
    assert mid.id is not None
    leaf = store.add(
        Drawer(
            wing=wing,
            room=room,
            content="leaf — observation",
            layer=Layer.ON_DEMAND,
            claim="c",
            predicted_outcome="p-v2",
            observed_outcome="matched",
            supersedes_id=mid.id,
            created_at=t2,
        )
    )
    assert leaf.id is not None
    return root.id, mid.id, leaf.id


@pytest.fixture()
def store(tmp_path: Path) -> DrawerStore:
    return DrawerStore(tmp_path / "t.db", HashEmbeddingProvider(dimension=32))


def test_walk_supersedes_from_leaf_returns_root_to_leaf(store: DrawerStore) -> None:
    root, mid, leaf = _build_chain(store, wing="cairntir", room="predictions")
    chain = walk_supersedes(store, leaf)
    assert [d.id for d in chain] == [root, mid, leaf]


def test_walk_supersedes_from_middle_returns_full_chain(store: DrawerStore) -> None:
    root, mid, leaf = _build_chain(store, wing="cairntir", room="predictions")
    chain = walk_supersedes(store, mid)
    assert [d.id for d in chain] == [root, mid, leaf]


def test_walk_supersedes_from_root_returns_full_chain(store: DrawerStore) -> None:
    root, mid, leaf = _build_chain(store, wing="cairntir", room="predictions")
    chain = walk_supersedes(store, root)
    assert [d.id for d in chain] == [root, mid, leaf]


def test_walk_supersedes_singleton(store: DrawerStore) -> None:
    saved = store.add(
        Drawer(
            wing="cairntir",
            room="solo",
            content="standalone drawer, no chain",
        )
    )
    assert saved.id is not None
    chain = walk_supersedes(store, saved.id)
    assert len(chain) == 1
    assert chain[0].id == saved.id


def test_walk_supersedes_missing_raises(store: DrawerStore) -> None:
    with pytest.raises(MemoryStoreError, match="no drawer with id 9999"):
        walk_supersedes(store, 9999)


def test_as_of_returns_leaf_at_that_time(store: DrawerStore) -> None:
    root, mid, leaf = _build_chain(store, wing="cairntir", room="predictions")

    # Before mid was written — root should be the leaf.
    when = datetime(2026, 1, 1, 12, tzinfo=UTC)
    result = as_of(store, leaf, when)
    assert result.id == root

    # After mid but before leaf — mid should be the answer.
    when = datetime(2026, 1, 2, 12, tzinfo=UTC)
    result = as_of(store, leaf, when)
    assert result.id == mid

    # After leaf was written — leaf is the answer.
    when = datetime(2026, 1, 3, 12, tzinfo=UTC)
    result = as_of(store, leaf, when)
    assert result.id == leaf


def test_as_of_before_root_returns_root(store: DrawerStore) -> None:
    root, _mid, leaf = _build_chain(store, wing="cairntir", room="predictions")
    when = datetime(2025, 12, 1, tzinfo=UTC)
    result = as_of(store, leaf, when)
    assert result.id == root


def test_walk_supersedes_dangling_pointer_returns_current(store: DrawerStore) -> None:
    """If the supersedes_id points at a deleted drawer, return what exists."""
    saved = store.add(
        Drawer(
            wing="cairntir",
            room="orphans",
            content="dangling",
            supersedes_id=42,  # never existed
        )
    )
    assert saved.id is not None
    chain = walk_supersedes(store, saved.id)
    assert len(chain) == 1
    assert chain[0].id == saved.id
