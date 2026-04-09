"""Contract test suite for the :class:`cairntir.Store` protocol.

Every concrete store impl must pass this module. To run the suite
against a new backend, add an entry to the ``_store_factories`` list
below; each factory takes a ``tmp_path`` and returns an open store the
test will ``close()`` afterwards.

The tests assert only protocol-level invariants — the stuff the
library promises every store obeys — so they are deliberately blind
to backend-specific internals (sqlite pragmas, vec0 tables, etc).
If a test here needs to reach past the protocol, it belongs in the
backend's own unit tests, not in the contract suite.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cairntir import Drawer, Layer, MemoryStoreError, Store
from cairntir.impl import DrawerStore, HashEmbeddingProvider

StoreFactory = Callable[[Path], Store]


def _drawer_store(path: Path) -> Store:
    return DrawerStore(path / "contract.db", HashEmbeddingProvider(dimension=32))


_store_factories: list[tuple[str, StoreFactory]] = [
    ("DrawerStore", _drawer_store),
]


@pytest.fixture(params=_store_factories, ids=[name for name, _ in _store_factories])
def store(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Store]:
    _name, factory = request.param
    instance = factory(tmp_path)
    try:
        yield instance
    finally:
        instance.close()


def _d(
    content: str,
    *,
    wing: str = "cairntir",
    room: str = "contract",
    layer: Layer = Layer.ON_DEMAND,
) -> Drawer:
    return Drawer(wing=wing, room=room, content=content, layer=layer)


# --------- protocol conformance ----------------------------------------


def test_store_satisfies_protocol(store: Store) -> None:
    assert isinstance(store, Store)


# --------- add / get ---------------------------------------------------


def test_add_assigns_id_and_get_returns_it(store: Store) -> None:
    saved = store.add(_d("contract says add+get round-trips"))
    assert saved.id is not None and saved.id > 0
    fetched = store.get(saved.id)
    assert fetched is not None
    assert fetched.content == "contract says add+get round-trips"


def test_get_missing_returns_none(store: Store) -> None:
    assert store.get(9999) is None


def test_add_preserves_prediction_bound_fields(store: Store) -> None:
    drawer = Drawer(
        wing="cairntir",
        room="contract",
        content="prediction drawer",
        claim="v1.0 is stable",
        predicted_outcome="protocols do not drift",
        belief_mass=2.0,
    )
    saved = store.add(drawer)
    assert saved.id is not None
    got = store.get(saved.id)
    assert got is not None
    assert got.claim == "v1.0 is stable"
    assert got.predicted_outcome == "protocols do not drift"
    assert got.belief_mass == pytest.approx(2.0)


# --------- list_by filtering -------------------------------------------


def test_list_by_filters_wing_room_layer(store: Store) -> None:
    store.add(_d("a", layer=Layer.IDENTITY))
    store.add(_d("b", layer=Layer.ESSENTIAL))
    store.add(_d("c", layer=Layer.ON_DEMAND))
    store.add(_d("d", wing="other-wing"))

    assert {d.content for d in store.list_by(layer=Layer.ESSENTIAL)} == {"b"}
    assert {d.content for d in store.list_by(wing="other-wing")} == {"d"}
    assert len(store.list_by(wing="cairntir")) == 3


# --------- search ranking ----------------------------------------------


def test_search_returns_hits_for_exact_content(store: Store) -> None:
    store.add(_d("belief mass steers rank"))
    store.add(_d("an unrelated fact"))
    results = store.search("belief mass steers rank", wing="cairntir", limit=2)
    assert results
    assert results[0][0].content == "belief mass steers rank"


def test_search_respects_wing_scope(store: Store) -> None:
    store.add(_d("shared text", wing="cairntir"))
    store.add(_d("shared text", wing="other-wing"))
    results = store.search("shared text", wing="cairntir")
    assert all(d.wing == "cairntir" for d, _ in results)


# --------- layer mutation + forgetting curve ---------------------------


def test_update_layer_moves_drawer(store: Store) -> None:
    saved = store.add(_d("demote me"))
    assert saved.id is not None
    store.update_layer(saved.id, Layer.DEEP)
    got = store.get(saved.id)
    assert got is not None and got.layer == Layer.DEEP


def test_update_layer_raises_for_missing_drawer(store: Store) -> None:
    with pytest.raises(MemoryStoreError):
        store.update_layer(9999, Layer.DEEP)


def test_stale_ids_reports_untouched_drawers(store: Store) -> None:
    old = datetime.now(UTC) - timedelta(days=30)
    saved = store.add(Drawer(wing="cairntir", room="contract", content="stale", created_at=old))
    assert saved.id is not None
    cutoff = datetime.now(UTC) - timedelta(days=7)
    stale = store.stale_ids(older_than=cutoff, layer=Layer.ON_DEMAND)
    assert saved.id in stale


# --------- belief-mass primitives --------------------------------------


def test_reinforce_raises_mass(store: Store) -> None:
    saved = store.add(_d("reinforce me"))
    assert saved.id is not None
    new_mass = store.reinforce(saved.id, amount=2.0)
    assert new_mass == pytest.approx(3.0)


def test_weaken_clamps_at_zero(store: Store) -> None:
    saved = store.add(_d("weaken me"))
    assert saved.id is not None
    new_mass = store.weaken(saved.id, amount=10.0)
    assert new_mass == pytest.approx(0.0)


def test_reinforce_missing_drawer_raises(store: Store) -> None:
    with pytest.raises(MemoryStoreError):
        store.reinforce(9999)
