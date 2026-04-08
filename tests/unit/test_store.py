"""Unit tests for the sqlite-vec drawer store."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer, Layer


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[DrawerStore]:
    with DrawerStore(tmp_path / "cairntir.db", HashEmbeddingProvider(dimension=32)) as s:
        yield s


def _drawer(
    content: str, *, wing: str = "cairntir", room: str = "phase-1", layer: Layer = Layer.ON_DEMAND
) -> Drawer:
    return Drawer(wing=wing, room=room, content=content, layer=layer)


def test_add_assigns_id_and_roundtrips(store: DrawerStore) -> None:
    saved = store.add(_drawer("the cairn sees across time"))
    assert saved.id is not None and saved.id > 0
    fetched = store.get(saved.id)
    assert fetched is not None
    assert fetched.content == "the cairn sees across time"
    assert fetched.wing == "cairntir"


def test_get_returns_none_when_missing(store: DrawerStore) -> None:
    assert store.get(9999) is None


def test_list_by_filters_wing_room_layer(store: DrawerStore) -> None:
    store.add(_drawer("a", layer=Layer.IDENTITY))
    store.add(_drawer("b", layer=Layer.ESSENTIAL))
    store.add(_drawer("c", layer=Layer.ON_DEMAND))
    store.add(_drawer("d", wing="other", layer=Layer.ON_DEMAND))

    essentials = store.list_by(wing="cairntir", layer=Layer.ESSENTIAL)
    assert [d.content for d in essentials] == ["b"]

    on_demand = store.list_by(layer=Layer.ON_DEMAND)
    assert {d.content for d in on_demand} == {"c", "d"}


def test_search_returns_exact_match_first(store: DrawerStore) -> None:
    store.add(_drawer("kill cross-chat amnesia"))
    store.add(_drawer("3d printing post scarcity"))
    store.add(_drawer("sqlite vec backend"))

    results = store.search("kill cross-chat amnesia", limit=3)
    assert len(results) >= 1
    top_drawer, _distance = results[0]
    assert top_drawer.content == "kill cross-chat amnesia"


def test_search_scopes_to_wing(store: DrawerStore) -> None:
    store.add(_drawer("memory spike", wing="cairntir"))
    store.add(_drawer("memory spike", wing="other"))
    results = store.search("memory spike", wing="cairntir", limit=5)
    assert all(d.wing == "cairntir" for d, _ in results)
    assert len(results) == 1


def test_metadata_is_preserved(store: DrawerStore) -> None:
    d = Drawer(
        wing="cairntir",
        room="phase-1",
        content="with meta",
        metadata={"k": "v", "n": 3},
    )
    saved = store.add(d)
    assert saved.id is not None
    fetched = store.get(saved.id)
    assert fetched is not None
    assert fetched.metadata == {"k": "v", "n": 3}
