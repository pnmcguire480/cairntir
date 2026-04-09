"""Protocol contracts — the public library surface for v1.0.

This module defines the *shapes* Cairntir promises to keep stable. A
future concrete impl can change radically; as long as it continues to
satisfy :class:`Store`, every downstream tool that imports ``cairntir``
and depends on the protocol keeps working.

The rule, enforced by ``tests/unit/test_public_api.py``, is that
``cairntir.__init__`` re-exports *only*:

* Protocols defined here.
* Frozen value types (:class:`~cairntir.memory.taxonomy.Drawer`,
  :class:`~cairntir.memory.taxonomy.Layer`) and reason-loop dataclasses.
* Typed exceptions from :mod:`cairntir.errors`.
* ``__version__``.

Concrete implementations live under ``cairntir.impl.*`` and reserve
the right to change. Calling them directly is fine for now, but the
stable seam is this protocol module.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from cairntir.memory.taxonomy import Drawer, Layer


@runtime_checkable
class Store(Protocol):
    """The minimum surface every drawer store must provide.

    A store persists :class:`Drawer` values verbatim, supports
    wing/room/layer-filtered listing, semantic search with optional
    belief reranking, and exposes the forgetting-curve and belief
    adjustment primitives the v0.3/v0.4 passes depend on. Every
    method raises a :class:`~cairntir.errors.MemoryStoreError` (or a
    subclass) on failure — silent swallowing is banned.

    The default concrete impl is
    :class:`cairntir.impl.DrawerStore`. A contract test suite
    (``tests/contract/test_store_contract.py``) asserts the shape
    of this protocol against any implementation factory.
    """

    def add(self, drawer: Drawer) -> Drawer:
        """Insert a drawer. Return a copy with its assigned id."""
        ...

    def get(self, drawer_id: int) -> Drawer | None:
        """Return a drawer by id, or ``None`` if missing. Touches access tracking."""
        ...

    def list_by(
        self,
        *,
        wing: str | None = None,
        room: str | None = None,
        layer: Layer | None = None,
        limit: int = 100,
    ) -> list[Drawer]:
        """Return drawers filtered by wing/room/layer, most recent first."""
        ...

    def search(
        self,
        query: str,
        *,
        wing: str | None = None,
        room: str | None = None,
        limit: int = 10,
        rerank_by_belief: bool = True,
    ) -> list[tuple[Drawer, float]]:
        """Semantic-search drawers. Returns ``(drawer, raw_distance)`` pairs."""
        ...

    def update_layer(self, drawer_id: int, layer: Layer) -> None:
        """Move a drawer to a new retrieval layer. Never deletes."""
        ...

    def reinforce(self, drawer_id: int, *, amount: float = 1.0) -> float:
        """Raise a drawer's belief mass. Return the new mass."""
        ...

    def weaken(self, drawer_id: int, *, amount: float = 1.0) -> float:
        """Lower a drawer's belief mass (clamped at 0). Return the new mass."""
        ...

    def stale_ids(
        self,
        *,
        older_than: datetime,
        layer: Layer,
        wing: str | None = None,
    ) -> list[int]:
        """Return ids of drawers in ``layer`` untouched since ``older_than``."""
        ...

    def close(self) -> None:
        """Release any underlying resources."""
        ...
