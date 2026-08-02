"""One call, one composed brief, one hard budget.

``cairntir_handoff(wing)`` exists to replace a ``HANDOFF.md`` file. The
goal Patrick set, and the bar to judge this module against: *carry a chat
across sessions without a handoff file, light, fast, and cheap on tokens.*

Why this is not ``session_start``
---------------------------------

``session_start`` answers "what is in this wing?" by returning every
identity and essential drawer as a 100-character stub. Measured on
2026-08-02: ~7,700 tokens, 51 drawers, **3 used**. Every stub is
truncated, so the payload cannot answer anything — it is pure routing,
and the caller still has to spend two more round trips on ``recall`` and
``get`` to read anything.

This module answers a different question: "what do I need to start
working?" That is a **composition problem, not a retrieval problem**,
which is why no ranking is involved and why ranking quality is not on
its critical path.

The rule
--------

**Never return a token the model cannot use.**

The consequence is the single load-bearing invariant here: a drawer is
included **whole, or not at all.** Truncation is the anti-pattern — it
pays the full token cost *and* destroys the information, which is the
worst of both. When a drawer does not fit the budget it is listed by id,
room and length so the caller can spend one ``cairntir_get`` on exactly
the thing it wants. An honest index of what was left out is cheap and
actionable; a truncated body is neither.

This is the founding invariant of the lineage, restored. BabyTIEROS
separated material into always-load / load-when-relevant / never-load
before any vector store existed. The 2026-07-27 evolution audit found
that the policy survived into Cairntir and the **budget did not**, and
wrote the fix into the "restore in the v1.2 core" list. v1.2 shipped
without it. See ``plans/research-2026-08-02-upgrade-candidates.md``.

Scoping, and the measured reason for it
---------------------------------------

Handoff scopes the identity layer **to the wing**. ``session_start``
deliberately loads identity across every wing, on the theory that
identity is cross-cutting. In practice a ``cairntir`` session was paying
for identity drawers from ``larder``, ``quietpdf``, ``win10legacy`` and
``common-table``. For the question "what do I need to start working *in
this wing*", those tokens carry no information. That is the difference,
and it is deliberate.

What the budget does and does not cover
--------------------------------------

``budget_chars`` bounds **drawer content**, not the rendered response.
Every drawer is returned inside the poisoned-memory evidence envelope,
which carries provenance — host, model, session, trust — that the
security boundary depends on and which must not be dropped to make a
number look better.

Measured on a copy of the live store, wing ``cairntir``, at the default
budget: 11,922 characters of content rendered to 17,045 characters
total, so the envelope costs roughly 43% on top. Stated here because a
budget whose real cost is somewhere else is exactly the kind of quiet
drift this project exists to oppose.

Measured against what it replaces
---------------------------------

Same store, same day, ``session_start`` versus ``handoff``:

===============  =============  =========  ========
wing             call           ~tokens    change
===============  =============  =========  ========
cairntir         session_start  7,737
cairntir         handoff        4,261      **-44%**
detroit-clone    session_start  8,201
detroit-clone    handoff        3,880      **-52%**
===============  =============  =========  ========

The token saving is the less interesting half. ``session_start`` spent
its 7,737 tokens on 51 stubs that could not answer anything; ``handoff``
spends 4,261 on 9 whole drawers that can. Cheaper *and* usable is the
only version of cheaper worth having.

Determinism
-----------

No ranking, no embeddings, no semantic search. Given the same store the
output is byte-identical — verified against the live store, not assumed
— which keeps it friendly to prompt caching, since the ecosystem's 90%
read discount only applies to a prefix that does not move.
:func:`compose` is pure with respect to the store.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from cairntir.memory.anchors import recall_for_change
from cairntir.memory.taxonomy import Drawer, Layer

if TYPE_CHECKING:
    from collections.abc import Sequence

    from cairntir.memory.store import DrawerStore

DEFAULT_BUDGET_CHARS = 12_000
"""Default hard ceiling on composed content, in characters.

Roughly 3,000 tokens — deliberately smaller than the ~7,700 tokens
``session_start`` was measured spending on stubs that answered nothing.
The point is not that 12,000 is a magic number; it is that a number
exists at all and the caller can see it.
"""

CHARS_PER_TOKEN = 4
"""Divisor for the character-to-token estimate.

An estimate, and labelled as one everywhere it surfaces. Cairntir does
not ship a tokenizer and will not add one as a dependency to produce a
number that is advisory. Four characters per token is the common English
approximation and is the same divisor used for every measurement in
``plans/research-2026-08-02-upgrade-candidates.md``, so the figures are
comparable to each other.
"""

_SCAN_LIMIT = 500
"""Upper bound on drawers examined per section before budgeting."""


def estimate_tokens(text: str) -> int:
    """Estimate token count from character length.

    Deliberately crude. See :data:`CHARS_PER_TOKEN`.
    """
    return len(text) // CHARS_PER_TOKEN


@dataclass(frozen=True)
class Omission:
    """One drawer that did not fit the budget.

    Carries exactly enough for the caller to decide whether to spend a
    ``cairntir_get`` on it: what it is, where it lives, and what it would
    cost. Never carries content — a partial body is the thing this module
    exists to refuse.
    """

    drawer_id: int
    room: str
    layer: Layer
    chars: int

    @property
    def tokens(self) -> int:
        """Estimated cost of fetching this drawer in full."""
        return self.chars // CHARS_PER_TOKEN


@dataclass(frozen=True)
class Section:
    """One titled part of the brief, with what fit and what did not."""

    key: str
    title: str
    why: str
    included: list[Drawer] = field(default_factory=list)
    omitted: list[Omission] = field(default_factory=list)

    @property
    def chars(self) -> int:
        """Total characters of included drawer content."""
        return sum(len(d.content) for d in self.included)


@dataclass(frozen=True)
class Handoff:
    """A composed brief for one wing, and the receipt for what it cost."""

    wing: str
    sections: list[Section]
    budget_chars: int
    wing_total: int = 0
    """How many drawers the wing holds in total, briefed or not.

    Carried so an empty brief can tell the caller *which* kind of empty it
    is. "No drawers at all" means the store may be new or misconfigured
    and is worth alarming about; "drawers exist but none are in briefing
    scope" is ordinary and calls for ``cairntir_recall`` instead. Reporting
    the second as the first sends people to debug a healthy store.
    """

    @property
    def used_chars(self) -> int:
        """Characters of drawer content actually included."""
        return sum(s.chars for s in self.sections)

    @property
    def used_tokens(self) -> int:
        """Estimated tokens of drawer content actually included."""
        return self.used_chars // CHARS_PER_TOKEN

    @property
    def included_count(self) -> int:
        """Number of drawers returned whole."""
        return sum(len(s.included) for s in self.sections)

    @property
    def omitted_count(self) -> int:
        """Number of drawers named but not returned."""
        return sum(len(s.omitted) for s in self.sections)

    @property
    def is_empty(self) -> bool:
        """True when nothing was composed, for either reason."""
        return self.included_count == 0 and self.omitted_count == 0

    @property
    def wing_is_unknown(self) -> bool:
        """True when the wing holds no drawers at all — the alarming case."""
        return self.wing_total == 0

    def all_drawers(self) -> list[Drawer]:
        """Flatten every included drawer in section order."""
        return [d for s in self.sections for d in s.included]


# --------------------------------------------------------------- composition

# Section order is the load policy, most load-bearing first. A section
# earlier in this tuple gets its reserve before a later one, and takes
# priority when leftover budget is redistributed.
_SECTION_SPECS: tuple[tuple[str, str, str, float], ...] = (
    (
        "protocol",
        "Operating protocol and identity",
        "How to work here, and what has already been decided. Wing-scoped on purpose.",
        0.30,
    ),
    (
        "deltas",
        "Recent session deltas",
        "What happened last, newest first, in full text.",
        0.45,
    ),
    (
        "open_questions",
        "Open questions",
        "Decisions with no recorded outcome yet. These are what a session should close.",
        0.15,
    ),
    (
        "anchored",
        "Anchored to the files in play",
        "Memory attached to the code this change touches.",
        0.10,
    ),
)


def compose(
    store: DrawerStore,
    *,
    wing: str,
    budget_chars: int = DEFAULT_BUDGET_CHARS,
    files: Sequence[str] | None = None,
    max_deltas: int = 8,
) -> Handoff:
    """Compose one bounded brief for ``wing``.

    Args:
        store: The drawer store to read from. Never written to.
        wing: The wing to brief on.
        budget_chars: Hard ceiling on included drawer content. Whole
            drawers are dropped to stay under it; none is ever cut.
        files: Optional paths in play. When given, adds the drawers
            structurally anchored to them.
        max_deltas: How many recent session drawers to consider.

    Returns:
        A :class:`Handoff`. Never raises on an empty or unknown wing —
        an empty brief is a truthful answer, and the caller needs to be
        able to tell "nothing recorded" apart from "lookup failed".
    """
    if budget_chars <= 0:
        raise ValueError(f"budget_chars must be positive, got {budget_chars}")

    candidates = _gather(store, wing=wing, files=files, max_deltas=max_deltas)
    wing_total = len(store.list_by(wing=wing, limit=_SCAN_LIMIT))
    return _fit(
        wing=wing,
        candidates=candidates,
        budget_chars=budget_chars,
        wing_total=wing_total,
    )


def _gather(
    store: DrawerStore,
    *,
    wing: str,
    files: Sequence[str] | None,
    max_deltas: int,
) -> dict[str, list[Drawer]]:
    """Collect candidate drawers per section, before any budgeting.

    Deduplicated across sections by drawer id: a drawer that is both
    identity and an open question is paid for once, in the earlier
    section. Without this the budget silently buys the same tokens twice.
    """
    seen: set[int] = set()

    def _fresh(drawers: list[Drawer]) -> list[Drawer]:
        out: list[Drawer] = []
        for d in drawers:
            if d.id is None or d.id in seen:
                continue
            seen.add(d.id)
            out.append(d)
        return out

    protocol = _fresh(store.list_by(wing=wing, layer=Layer.IDENTITY, limit=_SCAN_LIMIT))
    deltas = _fresh(store.list_by(wing=wing, layer=Layer.ESSENTIAL, limit=max_deltas))
    questions = _fresh(_open_questions(store, wing=wing))
    anchored = _fresh(_anchored(store, wing=wing, files=files))

    return {
        "protocol": protocol,
        "deltas": deltas,
        "open_questions": questions,
        "anchored": anchored,
    }


def _open_questions(store: DrawerStore, *, wing: str) -> list[Drawer]:
    """Drawers holding a question this wing has not answered yet.

    Two shapes count, and both are exact matches rather than guesses:

    * a **prediction-bound drawer** whose ``predicted_outcome`` is set and
      whose ``observed_outcome`` is not — the loop is open by definition;
    * a drawer whose metadata carries an explicit ``open_question`` key.

    Nothing is inferred from prose. A question nobody recorded as one is
    not surfaced here, which is the honest behaviour.
    """
    out: list[Drawer] = []
    for drawer in store.list_by(wing=wing, limit=_SCAN_LIMIT):
        unresolved_prediction = (
            drawer.predicted_outcome is not None and drawer.observed_outcome is None
        )
        flagged = bool(drawer.metadata.get("open_question"))
        if unresolved_prediction or flagged:
            out.append(drawer)
    return out


def _anchored(
    store: DrawerStore,
    *,
    wing: str,
    files: Sequence[str] | None,
) -> list[Drawer]:
    """Drawers structurally anchored to ``files``, or none when no files given.

    Malformed anchors are ignored here rather than warned about. The
    handoff is a briefing surface, not a repair surface, and
    ``cairntir_recall_for_change`` already reports malformed drawers
    loudly to the caller who can act on them.
    """
    if not files:
        return []
    paths = [f for f in files if f.strip()]
    if not paths:
        return []
    result = recall_for_change(store, paths, wing=wing, limit=_SCAN_LIMIT)
    return [m.drawer for m in result.matches]


def _fit(
    *,
    wing: str,
    candidates: dict[str, list[Drawer]],
    budget_chars: int,
    wing_total: int,
) -> Handoff:
    """Fit candidates into the budget, whole drawers only.

    Two passes, so that no section can starve another:

    1. Each section spends up to its own reserved share.
    2. Whatever is left over is offered back to the sections in priority
       order, so an empty section funds a full one instead of the budget
       going unspent.

    A drawer larger than the entire remaining budget is omitted, not cut.
    It still appears by id and size, so an oversized drawer is visible
    rather than silently missing.
    """
    remaining_pool = budget_chars
    staged: dict[str, tuple[list[Drawer], list[Drawer]]] = {}

    # Pass 1 — each section inside its own reserve.
    for key, _title, _why, reserve in _SECTION_SPECS:
        allowance = min(int(budget_chars * reserve), remaining_pool)
        taken, left = _take_while_fits(candidates.get(key, []), allowance)
        staged[key] = (taken, left)
        remaining_pool -= sum(len(d.content) for d in taken)

    # Pass 2 — redistribute the unspent remainder in priority order.
    for key, _title, _why, _reserve in _SECTION_SPECS:
        taken, left = staged[key]
        if not left or remaining_pool <= 0:
            continue
        extra, still_left = _take_while_fits(left, remaining_pool)
        remaining_pool -= sum(len(d.content) for d in extra)
        staged[key] = ([*taken, *extra], still_left)

    sections = [
        Section(
            key=key,
            title=title,
            why=why,
            included=staged[key][0],
            omitted=[_omission(d) for d in staged[key][1]],
        )
        for key, title, why, _reserve in _SECTION_SPECS
    ]
    return Handoff(
        wing=wing,
        sections=sections,
        budget_chars=budget_chars,
        wing_total=wing_total,
    )


def _take_while_fits(drawers: list[Drawer], allowance: int) -> tuple[list[Drawer], list[Drawer]]:
    """Split ``drawers`` into what fits in ``allowance`` and what does not.

    **Order is preserved and never re-sorted by size.** Sorting the
    candidates so more of them fit would quietly reorder the brief by
    length instead of by importance, which is the failure the caller
    cannot see. Everything included stays in canonical order — newest
    first for deltas, store order elsewhere.

    **Gaps are allowed, and every gap is named.** An earlier attempt
    stopped at the first drawer that did not fit, on the theory that a
    brief with holes in it misleads. It does the opposite: one oversized
    newest drawer blanked the entire section, so the caller got nothing
    instead of most things. Because each omission is printed in the same
    section with its id and size, a gap is explicit rather than silent —
    which is the property that actually matters.
    """
    taken: list[Drawer] = []
    left: list[Drawer] = []
    spent = 0
    for drawer in drawers:
        cost = len(drawer.content)
        if spent + cost > allowance:
            left.append(drawer)
            continue
        taken.append(drawer)
        spent += cost
    return taken, left


def _omission(drawer: Drawer) -> Omission:
    if drawer.id is None:
        raise ValueError("cannot record an omission for an unsaved drawer")
    return Omission(
        drawer_id=drawer.id,
        room=drawer.room,
        layer=drawer.layer,
        chars=len(drawer.content),
    )
