"""Unit tests for v0.3 consolidation, forgetting, and contradiction."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cairntir.memory.consolidate import (
    consolidate_room,
    demote_stale,
    detect_contradictions,
)
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer, Layer


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[DrawerStore]:
    with DrawerStore(tmp_path / "consolidate.db", HashEmbeddingProvider(dimension=32)) as s:
        yield s


# --------- demote_stale --------------------------------------------------


def test_demote_stale_moves_untouched_on_demand_to_deep(store: DrawerStore) -> None:
    old = datetime.now(UTC) - timedelta(days=30)
    recent = datetime.now(UTC) - timedelta(hours=1)
    stale_drawer = store.add(
        Drawer(wing="cairntir", room="room-a", content="stale", created_at=old)
    )
    fresh_drawer = store.add(
        Drawer(wing="cairntir", room="room-a", content="fresh", created_at=recent)
    )
    assert stale_drawer.id is not None and fresh_drawer.id is not None

    demoted = demote_stale(store, cold_after_days=7)
    assert demoted == [stale_drawer.id]

    # Fetching changes last_accessed_at; list_by by layer is side-effect free.
    cold = store.list_by(wing="cairntir", layer=Layer.DEEP)
    warm = store.list_by(wing="cairntir", layer=Layer.ON_DEMAND)
    assert [d.content for d in cold] == ["stale"]
    assert [d.content for d in warm] == ["fresh"]


def test_demote_stale_is_idempotent(store: DrawerStore) -> None:
    old = datetime.now(UTC) - timedelta(days=30)
    store.add(Drawer(wing="cairntir", room="room-a", content="x", created_at=old))
    first = demote_stale(store, cold_after_days=7)
    second = demote_stale(store, cold_after_days=7)
    assert len(first) == 1
    assert second == []


def test_demote_stale_rejects_negative_days(store: DrawerStore) -> None:
    with pytest.raises(ValueError, match="cold_after_days"):
        demote_stale(store, cold_after_days=-1)


def test_touch_preserves_drawer_from_demotion(store: DrawerStore) -> None:
    old = datetime.now(UTC) - timedelta(days=30)
    saved = store.add(Drawer(wing="cairntir", room="room-a", content="touched", created_at=old))
    assert saved.id is not None
    # A successful get() bumps last_accessed_at to now — the drawer is
    # no longer stale and must survive the forgetting curve.
    assert store.get(saved.id) is not None
    demoted = demote_stale(store, cold_after_days=7)
    assert demoted == []


# --------- detect_contradictions -----------------------------------------


def test_contradictions_flag_divergent_predicted_outcomes(store: DrawerStore) -> None:
    store.add(
        Drawer(
            wing="cairntir",
            room="predictions",
            content="a",
            claim="the cache is write-through",
            predicted_outcome="writes land in postgres synchronously",
        )
    )
    store.add(
        Drawer(
            wing="cairntir",
            room="predictions",
            content="b",
            claim="  The cache is write-through  ",  # whitespace/case drift
            predicted_outcome="writes are async and may lose data on crash",
        )
    )
    contradictions = detect_contradictions(store, wing="cairntir")
    assert len(contradictions) == 1
    c = contradictions[0]
    assert c.field == "predicted_outcome"
    assert c.first_value.startswith("writes land")
    assert c.second_value.startswith("writes are async")


def test_contradictions_ignore_agreement(store: DrawerStore) -> None:
    for _ in range(2):
        store.add(
            Drawer(
                wing="cairntir",
                room="room-p",
                content="x",
                claim="sqlite-vec is embedded",
                predicted_outcome="no network calls",
            )
        )
    assert detect_contradictions(store, wing="cairntir") == []


def test_contradictions_ignore_missing_outcomes(store: DrawerStore) -> None:
    # One drawer has a claim but no predicted outcome — nothing to contradict.
    store.add(
        Drawer(
            wing="cairntir",
            room="room-p",
            content="x",
            claim="the daemon polls every second",
        )
    )
    store.add(
        Drawer(
            wing="cairntir",
            room="room-p",
            content="y",
            claim="the daemon polls every second",
            predicted_outcome="latency under 2s end-to-end",
        )
    )
    assert detect_contradictions(store, wing="cairntir") == []


# --------- consolidate_room ---------------------------------------------


def test_consolidate_room_emits_derived_essential_drawer(store: DrawerStore) -> None:
    ids: list[int] = []
    for i in range(3):
        d = store.add(Drawer(wing="cairntir", room="phase-3", content=f"fact {i}"))
        assert d.id is not None
        ids.append(d.id)

    derived = consolidate_room(store, wing="cairntir", room="phase-3", min_cluster=3)
    assert derived is not None
    assert derived.layer == Layer.ESSENTIAL
    assert derived.metadata["source"] == "consolidate"
    assert derived.metadata["derived_from"] == ids
    # Source drawers are untouched — still on_demand, still verbatim.
    on_demand = store.list_by(wing="cairntir", room="phase-3", layer=Layer.ON_DEMAND)
    assert {d.content for d in on_demand} == {"fact 0", "fact 1", "fact 2"}
    # Derived content cites every source id verbatim.
    for drawer_id in ids:
        assert f"[#{drawer_id}]" in derived.content


def test_consolidate_room_below_min_cluster_returns_none(store: DrawerStore) -> None:
    store.add(Drawer(wing="cairntir", room="tiny", content="only one"))
    assert consolidate_room(store, wing="cairntir", room="tiny", min_cluster=3) is None


def test_consolidate_room_is_idempotent_for_same_source_set(store: DrawerStore) -> None:
    for i in range(3):
        store.add(Drawer(wing="cairntir", room="repeat", content=f"f{i}"))
    first = consolidate_room(store, wing="cairntir", room="repeat", min_cluster=3)
    second = consolidate_room(store, wing="cairntir", room="repeat", min_cluster=3)
    assert first is not None
    assert second is None


def test_consolidate_room_rejects_invalid_min_cluster(store: DrawerStore) -> None:
    with pytest.raises(ValueError, match="min_cluster"):
        consolidate_room(store, wing="cairntir", room="room-a", min_cluster=1)
