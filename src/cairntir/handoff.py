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

Open predictions
----------------

The first thing the brief says is what this wing claimed and never
settled. ``claim`` / ``predicted_outcome`` / ``observed_outcome`` have
existed on every drawer since v0.2 and were, on 2026-08-04, populated on
**2 of 278** rows — a fully-built epistemic mechanism with no wire to it.
The write side of that wire is being run separately; this is the read
side. A prediction nobody is ever reminded of is not a prediction, it is
a note.

The section is deliberately small and deliberately first. "3 open
predictions in this wing" is the honest opening line of a session,
because closing one is worth more than making another. A wing with none
— which is nearly every wing today — renders no header and spends no
characters.

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

    deep_total: int = 0
    """How many of ``wing_total`` sit in the DEEP layer.

    DEEP is the one layer this composer legitimately never loads. When it
    accounts for the whole wing, an empty brief is correct — and the
    message has to *say so* rather than assert that nothing is wrong.
    Carried so the renderer can name the reason without a second query.
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
    def open_prediction_count(self) -> int:
        """How many predictions this wing has left unsettled.

        Counts the ones that did not fit the budget as well as the ones
        that did, because an undercount is the failure mode that
        matters: "2 open" when three more were omitted reads like the
        loop is nearly closed. The omitted ones are named by id in the
        section itself, so the number and the list agree.

        Zero for the overwhelming majority of wings, and that is a
        truthful answer rather than a missing one.
        """
        for section in self.sections:
            if section.key == OPEN_PREDICTIONS:
                return len(section.included) + len(section.omitted)
        return 0

    @property
    def wing_is_unknown(self) -> bool:
        """True when the wing holds no drawers at all — the alarming case."""
        return self.wing_total == 0

    def all_drawers(self) -> list[Drawer]:
        """Flatten every included drawer in section order."""
        return [d for s in self.sections for d in s.included]


# --------------------------------------------------------------- composition

OPEN_PREDICTIONS = "open_predictions"
"""Key of the section holding predictions this wing never settled."""

RECENT_ACTIVITY = "recent_activity"
"""Key of the fallback section holding recent ``on_demand`` drawers.

Exists because ``cairntir_remember`` **defaults** to ``on_demand``, and
this composer runs no query. Reading the layer taxonomy as permission to
drop the default write layer meant a user who followed the documented
policy and took the defaults got an empty brief back — the exact
cross-chat amnesia Cairntir exists to kill, reproduced by its own
defaults. Measured 2026-08-10 on a clean install; see drawer #409.

The section carries a **zero reserve on purpose**. It is skipped
entirely in pass 1 and can only ever be filled from budget that no
higher-priority section wanted, so it cannot outbid identity or
essential material. Leftover budget spent on a real decision beats
leftover budget returned unspent; that is the whole of the fix.
"""

# Section order is the load policy, most load-bearing first. A section
# earlier in this tuple gets its reserve before a later one, and takes
# priority when leftover budget is redistributed.
#
# Open predictions lead. They are the cheapest section — nearly always
# empty, and capped at a tenth of the budget when it is not — and they
# are the one thing a session should see before it starts deciding
# things, because a claim already on the record beats a fresh guess.
# Its 10% comes out of the old 15% reserved for open questions, which
# used to carry both shapes; the reserves still sum to 1.00, so nothing
# else was quietly made smaller to pay for it.
_SECTION_SPECS: tuple[tuple[str, str, str, float], ...] = (
    (
        OPEN_PREDICTIONS,
        "Open predictions",
        "Claims made here and never settled. Closing one is worth more than making another.",
        0.10,
    ),
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
        "Questions flagged as unanswered. These are what a session should close.",
        0.05,
    ),
    (
        "anchored",
        "Anchored to the files in play",
        "Memory attached to the code this change touches.",
        0.10,
    ),
    (
        RECENT_ACTIVITY,
        "Recent activity",
        "Default-layer drawers written here lately. Shown because budget was left over.",
        0.00,
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
    wing_drawers = store.list_by(wing=wing, limit=_SCAN_LIMIT)
    return _fit(
        wing=wing,
        candidates=candidates,
        budget_chars=budget_chars,
        wing_total=len(wing_drawers),
        deep_total=sum(1 for d in wing_drawers if d.layer is Layer.DEEP),
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

    The wing is scanned once and the same list feeds every section that
    needs it, so two sections can never disagree about what the store
    holds or about what order it is in.
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

    wing_drawers = store.list_by(wing=wing, limit=_SCAN_LIMIT)

    predictions = _fresh(_open_predictions(wing_drawers))
    protocol = _fresh(store.list_by(wing=wing, layer=Layer.IDENTITY, limit=_SCAN_LIMIT))
    deltas = _fresh(store.list_by(wing=wing, layer=Layer.ESSENTIAL, limit=max_deltas))
    questions = _fresh(_open_questions(wing_drawers))
    anchored = _fresh(_anchored(store, wing=wing, files=files))
    # Gathered last so _fresh() has already claimed every drawer another
    # section wants: this is a fallback, never a competitor. DEEP stays
    # out — "skipped unless explicitly requested" is a real decision,
    # unlike on_demand's exclusion, which was an accident of running no
    # query.
    recent = _fresh(store.list_by(wing=wing, layer=Layer.ON_DEMAND, limit=max_deltas))

    return {
        OPEN_PREDICTIONS: predictions,
        "protocol": protocol,
        "deltas": deltas,
        "open_questions": questions,
        "anchored": anchored,
        RECENT_ACTIVITY: recent,
    }


def is_open_prediction(drawer: Drawer) -> bool:
    """True when ``drawer`` holds a prediction nobody has settled.

    **The definition is the narrow, literal one:** a non-empty
    ``predicted_outcome`` and no ``observed_outcome``, both read off
    *this drawer*. Nothing else counts, and nothing is inferred.

    Scope of the predicate, and where the rest lives
    ------------------------------------------------

    A prediction can also be settled by a *second* drawer that supersedes
    it — the shape :meth:`cairntir.mcp.backend.CairntirBackend.settle` and
    :meth:`cairntir.reason.ReasonLoop.step` both write: a prediction
    drawer, then an observation drawer carrying ``supersedes_id`` and the
    ``observed_outcome``, with the original left untouched. Under the rule
    above the original still reads as open, and that is deliberate **at
    this level**: the predicate stays per-drawer so every drawer it names
    can be audited with one ``cairntir_get``.

    Settlement by supersession is accounted for one level up:
    :func:`compose` subtracts :func:`settled_prediction_ids` over the same
    single wing scan, so predictions settled that way drop out of the open
    count without a graph traversal, and the count still agrees with the
    ids printed beside it. The original drawer never changes — a store
    that rewrote its own predictions could not be used to check whether it
    had ever been right; see ``settle``. Only the reading of it moves.
    """
    predicted = (drawer.predicted_outcome or "").strip()
    observed = (drawer.observed_outcome or "").strip()
    return bool(predicted) and not observed


def settled_prediction_ids(scanned: Sequence[Drawer]) -> set[int]:
    """Prediction ids settled by exactly one observation within ``scanned``.

    A prediction counts as settled here when one — and only one — drawer in
    the scanned set supersedes it carrying a non-empty
    ``observed_outcome``. That is the shape
    :meth:`cairntir.mcp.backend.CairntirBackend.settle` writes and the
    shape :meth:`cairntir.reason.ReasonLoop.step` has written since v0.6,
    detected in one pass over drawers already in hand: no per-drawer graph
    traversal, no second query, nothing for determinism to hide in.

    Two limits, stated here so they are discovered in the docstring and not
    in a bug report:

    * **Contested settlements stay open.** When two or more observations
      supersede the same prediction they contradict each other, and this
      seam refuses to pick a winner — silently taking the lowest id is
      exactly the lineage defect the temporal walk has, and it hides a
      branch. Counting a contested prediction as open is the honest read
      until an adjudication exists.
    * **An observation drawer outside the scanned set will not clear its
      prediction** — one stored in another wing, beyond the scan limit, or
      back-dated behind the scan window. Sometimes stale beats never
      clears; the alternative is an unbounded walk, and the count would
      stop agreeing with the ids printed beside it.
    """
    observations: dict[int, int] = {}
    for drawer in scanned:
        target = drawer.supersedes_id
        if target is None or not (drawer.observed_outcome or "").strip():
            continue
        observations[target] = observations.get(target, 0) + 1
    return {prediction_id for prediction_id, count in observations.items() if count == 1}


def _open_predictions(wing_drawers: list[Drawer]) -> list[Drawer]:
    """The unsettled predictions in a wing, in store order.

    Open means :func:`is_open_prediction` **and** not settled by a
    superseding observation in the same scan — see
    :func:`settled_prediction_ids`. The two halves are computed together
    here because testing them separately is exactly how the seam between
    them shipped green on both sides while disagreeing in the middle.
    """
    settled = settled_prediction_ids(wing_drawers)
    return [d for d in wing_drawers if is_open_prediction(d) and d.id not in settled]


def _open_questions(wing_drawers: list[Drawer]) -> list[Drawer]:
    """Drawers explicitly flagged as an unanswered question.

    One shape counts, and it is an exact match rather than a guess: a
    drawer whose metadata carries a truthy ``open_question`` key.

    Unsettled predictions used to land here too. They now have their own
    section, ahead of this one, because a prediction is a stronger thing
    than a question — it is falsifiable — and burying it among questions
    lost that. See :func:`is_open_prediction`.

    Nothing is inferred from prose. A question nobody recorded as one is
    not surfaced here, which is the honest behaviour.
    """
    return [d for d in wing_drawers if bool(d.metadata.get("open_question"))]


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
    deep_total: int = 0,
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
            why=_rationale(key, why, len(staged[key][0]) + len(staged[key][1])),
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
        deep_total=deep_total,
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


def _rationale(key: str, base: str, total: int) -> str:
    """Lead the open-predictions rationale with its honest total.

    The rendered section header can only show what fit; this line shows
    what exists. ``total`` therefore counts the omitted ones too, and the
    line reads the same whether or not the budget was tight.

    An empty section returns ``base`` untouched and is dropped by the
    renderer, so a wing with no predictions pays nothing — no header, no
    count, no line saying zero. Depends only on the drawers, never on the
    clock, so repeat calls stay byte-identical.
    """
    if key != OPEN_PREDICTIONS or total == 0:
        return base
    plural = "" if total == 1 else "s"
    return f"{total} open prediction{plural} in this wing. {base}"


def _omission(drawer: Drawer) -> Omission:
    if drawer.id is None:
        raise ValueError("cannot record an omission for an unsaved drawer")
    return Omission(
        drawer_id=drawer.id,
        room=drawer.room,
        layer=drawer.layer,
        chars=len(drawer.content),
    )
