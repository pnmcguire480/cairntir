"""Consolidation, forgetting curve, and contradiction detection — v0.3.

The round table committed v0.3 to three disciplines, all built on top of the
verbatim floor:

1. **Consolidate** — cluster recent drawers in a room and emit a single
   derived drawer one layer up (``on_demand → essential``). The verbatim
   sources stay put. Nothing is rewritten; the derived drawer cites every
   source id in its metadata.
2. **Forget** — drawers untouched for N days drift from a warm layer to a
   cold one (``on_demand → deep``). Never deletion. The store's
   ``last_accessed_at`` column is the replay signal.
3. **Contradict** — when two drawers make the same claim but commit to
   different predicted or observed outcomes, flag them. Never average,
   never silently pick a winner. The human (or a downstream Reason pass)
   decides.

All three functions are pure over the store — they take it as an argument,
read via its public surface, and write via the two mutating methods v0.3
added (``update_layer`` for demotion and ``add`` for derived drawers). No
global state, no background threads.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from cairntir.memory.taxonomy import Drawer, Layer

if TYPE_CHECKING:
    from cairntir.memory.store import DrawerStore

_DERIVED_SOURCE: str = "consolidate"


@dataclass(frozen=True)
class Contradiction:
    """A pair of drawers whose claims agree but whose outcomes diverge.

    Attributes:
        claim: The normalized claim the two drawers share.
        first_id: The older drawer's id.
        second_id: The newer drawer's id.
        field: Which outcome field diverged — ``"predicted_outcome"`` or
            ``"observed_outcome"``.
        first_value: The older drawer's value for that field.
        second_value: The newer drawer's value for that field.
    """

    claim: str
    first_id: int
    second_id: int
    field: str
    first_value: str
    second_value: str


def demote_stale(
    store: DrawerStore,
    *,
    cold_after_days: int,
    wing: str | None = None,
    now: datetime | None = None,
) -> list[int]:
    """Drift ``on_demand`` drawers untouched for ``cold_after_days`` to ``deep``.

    Demotion only, never deletion. Returns the ids that were demoted so
    callers can log or audit the pass. Idempotent: a second run immediately
    after returns an empty list because the demoted drawers are no longer
    in the ``on_demand`` layer.
    """
    if cold_after_days < 0:
        raise ValueError(f"cold_after_days must be >= 0, got {cold_after_days}")
    reference = now or datetime.now(UTC)
    cutoff = reference - timedelta(days=cold_after_days)
    stale = store.stale_ids(older_than=cutoff, layer=Layer.ON_DEMAND, wing=wing)
    for drawer_id in stale:
        store.update_layer(drawer_id, Layer.DEEP)
    return stale


def detect_contradictions(
    store: DrawerStore,
    *,
    wing: str | None = None,
    limit: int = 1000,
) -> list[Contradiction]:
    """Flag drawers that agree on ``claim`` but diverge on outcome.

    Never mutates. Never averages. Never picks a winner. The return value
    is a list of :class:`Contradiction` records the caller is expected to
    surface to a human or a Reason pass. Claims are normalized
    case-insensitively with whitespace collapsed so trivial formatting
    drift does not mask a real contradiction.
    """
    drawers = store.list_by(wing=wing, limit=limit)
    # Keep only drawers that actually assert a claim. Preserve insertion
    # order by id ascending so "first" is deterministic.
    with_claim = sorted(
        (d for d in drawers if d.claim and d.id is not None),
        key=lambda d: d.id or 0,
    )
    by_claim: dict[str, list[Drawer]] = {}
    for drawer in with_claim:
        key = _normalize_claim(drawer.claim or "")
        by_claim.setdefault(key, []).append(drawer)

    contradictions: list[Contradiction] = []
    for group in by_claim.values():
        if len(group) < 2:
            continue
        # Compare each drawer to the first one in the group. This catches
        # every pair where the first asserts X and a later one asserts
        # not-X, without exploding to O(n^2) for large clusters.
        anchor = group[0]
        for other in group[1:]:
            for field in ("predicted_outcome", "observed_outcome"):
                a = getattr(anchor, field)
                b = getattr(other, field)
                if a is None or b is None:
                    continue
                if _normalize_claim(a) == _normalize_claim(b):
                    continue
                contradictions.append(
                    Contradiction(
                        claim=anchor.claim or "",
                        first_id=anchor.id or 0,
                        second_id=other.id or 0,
                        field=field,
                        first_value=a,
                        second_value=b,
                    )
                )
    return contradictions


def consolidate_room(
    store: DrawerStore,
    *,
    wing: str,
    room: str,
    min_cluster: int = 3,
) -> Drawer | None:
    """Cluster a room's ``on_demand`` drawers and emit a derived ``essential``.

    The derived drawer is a verbatim concatenation of the source contents
    with source ids listed both inline and in ``metadata.derived_from``.
    Nothing is rewritten. The source drawers stay at ``on_demand``; only
    the derived drawer is written, at ``essential``. If an essential drawer
    already exists in the room with the same set of source ids, this is a
    no-op and returns ``None``.

    Returns the new derived drawer (with id) or ``None`` if there was
    nothing new to consolidate.
    """
    if min_cluster < 2:
        raise ValueError(f"min_cluster must be >= 2, got {min_cluster}")
    sources = [
        d
        for d in store.list_by(wing=wing, room=room, layer=Layer.ON_DEMAND, limit=1000)
        if d.id is not None
    ]
    if len(sources) < min_cluster:
        return None
    sources.sort(key=lambda d: d.id or 0)
    source_ids = [d.id for d in sources if d.id is not None]

    # Have we already consolidated this exact set? If an essential drawer
    # in this room lists the same derived_from, skip — consolidation is
    # idempotent and append-only.
    for existing in store.list_by(wing=wing, room=room, layer=Layer.ESSENTIAL, limit=200):
        prior = existing.metadata.get("derived_from")
        if isinstance(prior, list) and prior == source_ids:
            return None

    header = f"Consolidated from {len(sources)} drawers: {source_ids}"
    body = "\n\n".join(f"[#{d.id}] {d.content}" for d in sources if d.id is not None)
    derived_content = f"{header}\n\n{body}"

    derived = Drawer(
        wing=wing,
        room=room,
        content=derived_content,
        layer=Layer.ESSENTIAL,
        metadata={
            "source": _DERIVED_SOURCE,
            "derived_from": source_ids,
        },
    )
    return store.add(derived)


def _normalize_claim(value: str) -> str:
    """Case-fold and collapse whitespace so trivial drift does not mask a match."""
    return " ".join(value.casefold().split())
