"""Belief-as-distribution: surprise and replay-weighted ranking — v0.4.

The round table converged on this: in a verbatim-only system with no
training pipeline, **the retrieval distribution itself is the belief**.
You do not need weights. You need:

1. A scalar mass per drawer that goes up when a retrieval proves useful
   and down when it proves dead weight (``Drawer.belief_mass``).
2. A surprise signal — the ``delta`` field from v0.2 — that boosts a
   drawer's mass when it records something the system did not expect.
3. A scorer that combines both with raw vector distance so semantic
   closeness still matters first, but replay + surprise bend the ranking.

This module is the scorer. It is pure over :class:`Drawer` values: no
database, no side effects, no global state. :meth:`DrawerStore.search`
composes it when the caller asks for belief-aware ranking (on by
default). Callers that want raw vector distance can opt out.

The math is deliberately blunt. Cairntir's ethos is "verbatim first";
belief is a steering wheel, not an engine. When in doubt the semantic
distance wins. We'd rather under-rerank than overfit.
"""

from __future__ import annotations

from cairntir.memory.taxonomy import Drawer

DEFAULT_DELTA_BOOST: float = 0.25
"""Fractional boost applied when a drawer carries a non-empty ``delta``.

A drawer with a recorded surprise is treated as 25% more retrievable
than an otherwise identical drawer. Tuned to nudge, not dominate — if
two drawers are close in semantic distance, the one with a real
observed-minus-predicted record should win the tiebreak.
"""

DEFAULT_MASS_FLOOR: float = 0.1
"""Lower clamp on ``belief_mass`` during scoring.

A drawer at mass zero would have infinite effective distance, which
silently removes it from search even though the store still holds the
verbatim content. The floor keeps weakened drawers retrievable at
degraded rank — punishment without deletion, which is the Cairntir
ethos for every piece of remembered state.
"""


def effective_distance(
    drawer: Drawer,
    raw_distance: float,
    *,
    delta_boost: float = DEFAULT_DELTA_BOOST,
    mass_floor: float = DEFAULT_MASS_FLOOR,
) -> float:
    """Return the belief-adjusted distance for one search result.

    Smaller is better, same as the raw vector distance it replaces.
    The adjustment is::

        effective = raw_distance / (mass * (1 + delta_boost_if_surprise))

    ``mass`` is clamped at ``mass_floor`` so a weakened drawer never
    disappears from results entirely — punishment without deletion.
    A drawer carrying a non-empty ``delta`` is boosted by ``delta_boost``
    because surprise is the load-bearing signal when there are no
    weights to train.
    """
    mass = max(drawer.belief_mass, mass_floor)
    boost = 1.0 + (delta_boost if drawer.delta else 0.0)
    return raw_distance / (mass * boost)


def rerank_results(
    results: list[tuple[Drawer, float]],
    *,
    delta_boost: float = DEFAULT_DELTA_BOOST,
    mass_floor: float = DEFAULT_MASS_FLOOR,
) -> list[tuple[Drawer, float]]:
    """Rerank ``(drawer, raw_distance)`` pairs in place of a new list.

    The returned tuples keep their **raw** distance so the caller can
    still inspect vector closeness; only the ordering changes. Sort is
    stable on equal effective distances so ties fall back to input order
    (which is vector distance order coming out of the store).
    """
    return sorted(
        results,
        key=lambda pair: effective_distance(
            pair[0],
            pair[1],
            delta_boost=delta_boost,
            mass_floor=mass_floor,
        ),
    )
