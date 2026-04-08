"""Unit tests for the 4-layer retriever."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.retrieval import Retriever
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer, Layer


@pytest.fixture()
def populated_store(tmp_path: Path) -> Iterator[DrawerStore]:
    with DrawerStore(tmp_path / "db.sqlite", HashEmbeddingProvider(dimension=32)) as s:
        s.add(
            Drawer(
                wing="cairntir",
                room="identity",
                content="Patrick owns cairntir",
                layer=Layer.IDENTITY,
            )
        )
        s.add(
            Drawer(
                wing="cairntir", room="state", content="phase 1 in progress", layer=Layer.ESSENTIAL
            )
        )
        s.add(
            Drawer(
                wing="cairntir",
                room="notes",
                content="kill cross chat amnesia",
                layer=Layer.ON_DEMAND,
            )
        )
        s.add(Drawer(wing="cairntir", room="archive", content="old decision log", layer=Layer.DEEP))
        s.add(
            Drawer(wing="other", room="state", content="unrelated essential", layer=Layer.ESSENTIAL)
        )
        yield s


def test_load_without_query_skips_on_demand_and_deep(populated_store: DrawerStore) -> None:
    r = Retriever(populated_store).load(wing="cairntir")
    assert [d.content for d in r.identity] == ["Patrick owns cairntir"]
    assert [d.content for d in r.essential] == ["phase 1 in progress"]
    assert r.on_demand == []
    assert r.deep == []


def test_load_with_query_populates_on_demand(populated_store: DrawerStore) -> None:
    r = Retriever(populated_store).load(wing="cairntir", query="kill cross chat amnesia")
    assert any("amnesia" in d.content for d in r.on_demand)


def test_include_deep_loads_deep_layer(populated_store: DrawerStore) -> None:
    r = Retriever(populated_store).load(wing="cairntir", include_deep=True)
    assert [d.content for d in r.deep] == ["old decision log"]


def test_essential_is_wing_scoped(populated_store: DrawerStore) -> None:
    r = Retriever(populated_store).load(wing="cairntir")
    assert all(d.wing == "cairntir" for d in r.essential)


def test_retrieval_result_all_and_len(populated_store: DrawerStore) -> None:
    r = Retriever(populated_store).load(wing="cairntir", query="amnesia", include_deep=True)
    assert len(r) == len(r.all())
    assert len(r) >= 3
