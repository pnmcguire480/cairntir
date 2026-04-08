"""Four-layer retrieval loader.

When a Cairntir session starts, :class:`Retriever` assembles the context
window from four disjoint layers:

1. **IDENTITY** — always loaded, cross-wing user/agent identity.
2. **ESSENTIAL** — always loaded for the active wing.
3. **ON_DEMAND** — semantic-search results for the current query.
4. **DEEP** — skipped unless explicitly requested.

The result is a :class:`RetrievalResult` that callers render into prompts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer, Layer


@dataclass(frozen=True)
class RetrievalResult:
    """Layered retrieval result.

    Each field holds drawers from exactly one layer. ``on_demand`` preserves
    semantic-search order (closest first); the other layers are most-recent
    first.
    """

    identity: list[Drawer] = field(default_factory=list)
    essential: list[Drawer] = field(default_factory=list)
    on_demand: list[Drawer] = field(default_factory=list)
    deep: list[Drawer] = field(default_factory=list)

    def all(self) -> list[Drawer]:
        """Flatten all layers in canonical order."""
        return [*self.identity, *self.essential, *self.on_demand, *self.deep]

    def __len__(self) -> int:
        """Total drawers across all layers."""
        return len(self.identity) + len(self.essential) + len(self.on_demand) + len(self.deep)


class Retriever:
    """Assemble a :class:`RetrievalResult` from a :class:`DrawerStore`."""

    def __init__(
        self,
        store: DrawerStore,
        *,
        identity_limit: int = 20,
        essential_limit: int = 40,
        on_demand_limit: int = 10,
        deep_limit: int = 20,
    ) -> None:
        """Configure per-layer budgets."""
        self._store = store
        self._identity_limit = identity_limit
        self._essential_limit = essential_limit
        self._on_demand_limit = on_demand_limit
        self._deep_limit = deep_limit

    def load(
        self,
        *,
        wing: str,
        query: str | None = None,
        include_deep: bool = False,
    ) -> RetrievalResult:
        """Load the four-layer context for ``wing``.

        Args:
            wing: The active wing.
            query: Optional query; if provided, populates the on-demand layer
                via semantic search scoped to ``wing``.
            include_deep: If ``True``, also populate the deep archive layer.
        """
        identity = self._store.list_by(layer=Layer.IDENTITY, limit=self._identity_limit)
        essential = self._store.list_by(
            wing=wing, layer=Layer.ESSENTIAL, limit=self._essential_limit
        )
        on_demand: list[Drawer] = []
        if query:
            hits = self._store.search(query, wing=wing, limit=self._on_demand_limit)
            on_demand = [drawer for drawer, _distance in hits if drawer.layer is Layer.ON_DEMAND]
        deep: list[Drawer] = []
        if include_deep:
            deep = self._store.list_by(wing=wing, layer=Layer.DEEP, limit=self._deep_limit)
        return RetrievalResult(
            identity=identity,
            essential=essential,
            on_demand=on_demand,
            deep=deep,
        )
