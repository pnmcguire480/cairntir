"""Unit tests for v0.4 belief-as-distribution scoring and reinforce/weaken."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from cairntir.errors import MemoryStoreError
from cairntir.memory.belief import (
    DEFAULT_DELTA_BOOST,
    DEFAULT_MASS_FLOOR,
    effective_distance,
    rerank_results,
)
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[DrawerStore]:
    with DrawerStore(tmp_path / "belief.db", HashEmbeddingProvider(dimension=32)) as s:
        yield s


# --------- effective_distance ------------------------------------------


def test_neutral_mass_leaves_distance_unchanged() -> None:
    d = Drawer(wing="cairntir", room="r1", content="x")
    assert effective_distance(d, 0.5) == pytest.approx(0.5)


def test_higher_mass_shrinks_effective_distance() -> None:
    light = Drawer(wing="cairntir", room="r1", content="x", belief_mass=1.0)
    heavy = Drawer(wing="cairntir", room="r1", content="x", belief_mass=4.0)
    assert effective_distance(heavy, 0.5) < effective_distance(light, 0.5)


def test_delta_boost_shrinks_effective_distance() -> None:
    plain = Drawer(wing="cairntir", room="r1", content="x")
    surprised = Drawer(
        wing="cairntir",
        room="r1",
        content="x",
        delta="observed outcome diverged from prediction",
    )
    assert effective_distance(surprised, 0.5) < effective_distance(plain, 0.5)
    # Exact math: 0.5 / (1.0 * (1 + DEFAULT_DELTA_BOOST)).
    expected = 0.5 / (1.0 * (1.0 + DEFAULT_DELTA_BOOST))
    assert effective_distance(surprised, 0.5) == pytest.approx(expected)


def test_mass_floor_prevents_infinite_distance() -> None:
    zero = Drawer(wing="cairntir", room="r1", content="x", belief_mass=0.0)
    assert effective_distance(zero, 1.0) == pytest.approx(1.0 / DEFAULT_MASS_FLOOR)


# --------- rerank_results -----------------------------------------------


def test_rerank_moves_reinforced_drawer_ahead_of_a_slightly_closer_one() -> None:
    close_but_dead = Drawer(wing="cairntir", room="r1", content="dead", belief_mass=0.25)
    farther_but_trusted = Drawer(wing="cairntir", room="r1", content="trusted", belief_mass=4.0)
    results = [(close_but_dead, 0.30), (farther_but_trusted, 0.40)]
    reranked = rerank_results(results)
    assert [d.content for d, _ in reranked] == ["trusted", "dead"]
    # Raw distances survive for inspection.
    assert reranked[0][1] == pytest.approx(0.40)


def test_rerank_is_stable_on_ties() -> None:
    a = Drawer(wing="cairntir", room="r1", content="a")
    b = Drawer(wing="cairntir", room="r1", content="b")
    reranked = rerank_results([(a, 0.5), (b, 0.5)])
    assert [d.content for d, _ in reranked] == ["a", "b"]


# --------- store.reinforce / store.weaken -------------------------------


def test_reinforce_raises_belief_mass_and_persists(store: DrawerStore) -> None:
    saved = store.add(Drawer(wing="cairntir", room="beliefs", content="x"))
    assert saved.id is not None and saved.belief_mass == pytest.approx(1.0)
    new_mass = store.reinforce(saved.id, amount=2.5)
    assert new_mass == pytest.approx(3.5)
    fetched = store.get(saved.id)
    assert fetched is not None
    assert fetched.belief_mass == pytest.approx(3.5)


def test_weaken_clamps_at_zero(store: DrawerStore) -> None:
    saved = store.add(Drawer(wing="cairntir", room="beliefs", content="x"))
    assert saved.id is not None
    new_mass = store.weaken(saved.id, amount=10.0)
    assert new_mass == pytest.approx(0.0)
    fetched = store.get(saved.id)
    assert fetched is not None
    assert fetched.belief_mass == pytest.approx(0.0)


def test_reinforce_missing_drawer_raises(store: DrawerStore) -> None:
    with pytest.raises(MemoryStoreError, match="no drawer"):
        store.reinforce(9999)


def test_search_applies_belief_rerank_by_default(store: DrawerStore) -> None:
    # Two drawers with identical content will collide to zero distance;
    # use distinct content so the semantic distances differ and belief
    # mass has to do the work to reorder.
    dead = store.add(Drawer(wing="cairntir", room="search", content="close but dead weight"))
    trusted = store.add(Drawer(wing="cairntir", room="search", content="less close but trusted"))
    assert dead.id is not None and trusted.id is not None

    # Seed very different belief mass.
    store.weaken(dead.id, amount=0.9)  # mass -> 0.1
    store.reinforce(trusted.id, amount=5.0)  # mass -> 6.0

    # Neither content is the query verbatim — both get non-zero
    # distances — so belief mass actually has room to do work in the
    # rerank. Raw order depends on the hash embedder; grab it first,
    # then assert the rerank flips the top hit.
    raw = store.search(
        "weight trust signal",
        wing="cairntir",
        limit=2,
        rerank_by_belief=False,
    )
    raw_ids = [d.id for d, _ in raw]
    assert len(raw_ids) == 2

    reranked = store.search("weight trust signal", wing="cairntir", limit=2)
    # The trusted drawer (mass 6.0) must land at the top regardless of
    # which raw distance happened to be smaller.
    assert reranked[0][0].id == trusted.id
