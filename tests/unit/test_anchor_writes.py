"""Unit tests for retroactive anchoring — DrawerStore.add_anchors."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from cairntir.errors import MemoryStoreError
from cairntir.memory.anchors import parse_anchors, recall_for_change
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer, Layer


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[DrawerStore]:
    with DrawerStore(tmp_path / "anchor-writes.db", HashEmbeddingProvider(dimension=32)) as s:
        yield s


def _drawer(store: DrawerStore, **kwargs: object) -> int:
    saved = store.add(
        Drawer(wing="cairntir", room="architecture", content="the cold-start arc", **kwargs)  # type: ignore[arg-type]
    )
    assert saved.id is not None
    return saved.id


def test_add_anchors_makes_an_existing_drawer_recallable(store: DrawerStore) -> None:
    """The whole point: a corpus written before anchors existed can participate."""
    drawer_id = _drawer(store)
    assert recall_for_change(store, ["src/cairntir/memory/embeddings.py"]).matches == ()

    store.add_anchors(drawer_id, [{"path": "src/cairntir/memory/embeddings.py"}])

    result = recall_for_change(store, ["src/cairntir/memory/embeddings.py"])
    assert [m.drawer.id for m in result.matches] == [drawer_id]


def test_add_anchors_preserves_existing_anchors(store: DrawerStore) -> None:
    drawer_id = _drawer(store, metadata={"anchors": [{"path": "src/cairntir/cli.py"}]})

    merged = store.add_anchors(drawer_id, [{"path": "src/cairntir/memory/store.py"}])

    assert [a["path"] for a in merged] == [
        "src/cairntir/cli.py",
        "src/cairntir/memory/store.py",
    ]


def test_add_anchors_preserves_unrelated_metadata(store: DrawerStore) -> None:
    drawer_id = _drawer(store, metadata={"topic": "release", "related_drawers": [94, 95]})

    store.add_anchors(drawer_id, [{"path": "src/cairntir/cli.py"}])

    stored = store.get(drawer_id)
    assert stored is not None
    assert stored.metadata["topic"] == "release"
    assert stored.metadata["related_drawers"] == [94, 95]


def test_add_anchors_never_touches_content_or_layer(store: DrawerStore) -> None:
    """Controlled mutation: retrieval routing changes, the verbatim floor does not."""
    drawer_id = _drawer(store, layer=Layer.ESSENTIAL)
    before = store.get(drawer_id)
    assert before is not None

    store.add_anchors(drawer_id, [{"path": "src/cairntir/cli.py"}])

    after = store.get(drawer_id)
    assert after is not None
    assert after.content == before.content
    assert after.layer == before.layer
    assert after.belief_mass == before.belief_mass
    assert after.created_at == before.created_at


def test_add_anchors_collapses_duplicates(store: DrawerStore) -> None:
    drawer_id = _drawer(store, metadata={"anchors": [{"path": "src/cairntir/cli.py"}]})

    merged = store.add_anchors(
        drawer_id,
        [{"path": "src/cairntir/cli.py"}, {"path": "src/cairntir/cli.py"}],
    )

    assert len(merged) == 1


def test_add_anchors_treats_same_path_different_symbol_as_distinct(store: DrawerStore) -> None:
    drawer_id = _drawer(store)

    merged = store.add_anchors(
        drawer_id,
        [
            {"path": "src/cairntir/cli.py", "symbol": "recall"},
            {"path": "src/cairntir/cli.py", "symbol": "anchor_cmd"},
        ],
    )

    assert len(merged) == 2


def test_add_anchors_is_idempotent(store: DrawerStore) -> None:
    drawer_id = _drawer(store)
    entry = [{"path": "src/cairntir/cli.py", "symbol": "recall"}]

    first = store.add_anchors(drawer_id, entry)
    second = store.add_anchors(drawer_id, entry)

    assert first == second
    assert len(second) == 1


def test_add_anchors_result_parses_back(store: DrawerStore) -> None:
    drawer_id = _drawer(store)
    store.add_anchors(
        drawer_id,
        [{"path": "src\\cairntir\\cli.py", "symbol": "recall", "symbol_source_hash": "abc123"}],
    )

    stored = store.get(drawer_id)
    assert stored is not None
    parsed = parse_anchors(stored.metadata)
    assert parsed[0].path == "src/cairntir/cli.py"
    assert parsed[0].symbol == "recall"
    assert parsed[0].symbol_source_hash == "abc123"


def test_add_anchors_rejects_missing_drawer(store: DrawerStore) -> None:
    with pytest.raises(MemoryStoreError, match="no drawer with id"):
        store.add_anchors(9999, [{"path": "src/cairntir/cli.py"}])


@pytest.mark.parametrize(
    "entries",
    [
        [{"symbol": "no path"}],
        [{"path": ""}],
        [{"path": "   "}],
        ["src/cairntir/cli.py"],
    ],
)
def test_add_anchors_rejects_malformed(store: DrawerStore, entries: list[object]) -> None:
    drawer_id = _drawer(store)
    with pytest.raises(MemoryStoreError):
        store.add_anchors(drawer_id, entries)  # type: ignore[arg-type]


def test_add_anchors_rejects_malformed_without_partial_write(store: DrawerStore) -> None:
    """A rejected batch must leave the drawer exactly as it was."""
    drawer_id = _drawer(store, metadata={"anchors": [{"path": "src/cairntir/cli.py"}]})

    with pytest.raises(MemoryStoreError):
        store.add_anchors(
            drawer_id,
            [{"path": "src/cairntir/memory/store.py"}, {"symbol": "bad"}],
        )

    stored = store.get(drawer_id)
    assert stored is not None
    assert stored.metadata["anchors"] == [{"path": "src/cairntir/cli.py"}]
