"""What Cairntir costs the context window it is trying to protect.

This closes **P5**, the only one of the twelve primitives BrainStormer's
2026-04-03 harness audit scored MISSING, at risk HIGH, deferred with the
words *"until cost becomes a real concern."* That condition is now met
three separate ways: token usage reportedly explains ~80% of performance
variance on agent evaluations; context rot degrades accuracy as the
window grows even when nothing relevant is missing; and Cairntir's own
fixed session cost was measured at ~10,000 tokens for roughly 6%
utilisation.

The objective this serves is Patrick's, stated verbatim on 2026-08-02:
Cairntir exists to *"help get more out of the $20 models, us poor folks
can afford."* That is **budget-constrained maximisation**, not cost
minimisation. Minimising tokens says "send less." Maximising work under a
fixed cap says **"never spend a token on something that carries no
information"** — a much harsher test, and the one this report scores.

Scope, deliberately narrow
--------------------------

This measures **Cairntir's own payload** and nothing else. It is not a
general token dashboard and must not grow into one: Tokalator already
does live budget monitoring across a whole session, and Headroom already
does reversible compression of tool output, both better than anything
Cairntir would build. Cairntir's uncontested job is deciding *what to
send from persistent memory in the first place*, which is upstream of
both. Measuring that is in scope; measuring anything else is not.

Why this is a CLI command and not an MCP tool
---------------------------------------------

Adding a nineteenth read-path tool would enlarge the very tool catalog
this report exists to hold accountable — every tool definition is paid
for in every session in every host, whether or not it is ever called.
The number belongs to the maintainer, not the agent, so it lives on the
command line.

Estimates, labelled as such
---------------------------

Token figures are characters ÷ 4. Cairntir does not ship a tokenizer and
will not add one as a dependency to produce an advisory number. The same
divisor is used everywhere, so the figures are comparable to each other
and to those in ``plans/research-2026-08-02-upgrade-candidates.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from cairntir.handoff import CHARS_PER_TOKEN, DEFAULT_BUDGET_CHARS

if TYPE_CHECKING:
    from cairntir.memory.store import DrawerStore

EMBEDDER_TOKEN_LIMIT = 512
"""Hard input window of the default embedder, ``all-MiniLM-L6-v2``.

Anything past this is never vectorised. The drawer is stored whole — the
verbatim floor is not at risk — but the part beyond the window is
invisible to semantic search, which is a silent retrieval defect rather
than a storage one.
"""

EMBEDDER_CHAR_WINDOW = EMBEDDER_TOKEN_LIMIT * CHARS_PER_TOKEN
"""Approximate character equivalent of the embedder window (~2,048)."""

_SCAN_LIMIT = 10_000


def estimate_tokens(chars: int) -> int:
    """Estimate tokens from a character count. See the module docstring."""
    return chars // CHARS_PER_TOKEN


@dataclass(frozen=True)
class Measurement:
    """The cost of one Cairntir surface, in characters and estimated tokens."""

    name: str
    chars: int
    note: str

    @property
    def tokens(self) -> int:
        """Estimated tokens. Characters ÷ 4."""
        return estimate_tokens(self.chars)


@dataclass(frozen=True)
class CorpusStats:
    """Shape of a wing's drawers, and how much of it the embedder can read."""

    drawers: int
    median_chars: int
    p75_chars: int
    p90_chars: int
    max_chars: int
    over_window: int
    worst_embedded_pct: int

    @property
    def over_window_pct(self) -> int:
        """Share of drawers the embedder cannot read in full."""
        if not self.drawers:
            return 0
        return self.over_window * 100 // self.drawers


@dataclass(frozen=True)
class CostReport:
    """Everything ``cairntir cost`` knows about one wing."""

    wing: str
    measurements: list[Measurement]
    corpus: CorpusStats


def _percentile(values: list[int], pct: int) -> int:
    """Nearest-rank percentile. Exact, no interpolation, no numpy."""
    if not values:
        return 0
    rank = max(1, (pct * len(values) + 99) // 100)
    return values[min(rank, len(values)) - 1]


def corpus_stats(store: DrawerStore, *, wing: str | None = None) -> CorpusStats:
    """Measure drawer sizes against the embedder's input window."""
    lengths = sorted(len(d.content) for d in store.list_by(wing=wing, limit=_SCAN_LIMIT))
    if not lengths:
        return CorpusStats(0, 0, 0, 0, 0, 0, 100)
    longest = lengths[-1]
    over = sum(1 for n in lengths if n > EMBEDDER_CHAR_WINDOW)
    worst = min(100, EMBEDDER_CHAR_WINDOW * 100 // longest) if longest else 100
    return CorpusStats(
        drawers=len(lengths),
        median_chars=_percentile(lengths, 50),
        p75_chars=_percentile(lengths, 75),
        p90_chars=_percentile(lengths, 90),
        max_chars=longest,
        over_window=over,
        worst_embedded_pct=worst,
    )


def measure(
    store: DrawerStore,
    *,
    wing: str,
    budget_chars: int = DEFAULT_BUDGET_CHARS,
) -> CostReport:
    """Measure what Cairntir's read path costs for one wing.

    Only pure-SQL surfaces are exercised, so this never triggers the
    embedder and never writes. Running the report must not change what
    it measures.
    """
    from cairntir.mcp.backend import CairntirBackend
    from cairntir.mcp.server import _tool_specs

    backend = CairntirBackend(store)

    catalog = sum(
        len(spec.name) + len(spec.description or "") + len(str(spec.inputSchema))
        for spec in _tool_specs()
    )
    measurements = [
        Measurement(
            name=f"tool catalog ({len(_tool_specs())} tools)",
            chars=catalog,
            note="paid in every session, in every host, called or not",
        ),
        Measurement(
            name="session_start",
            chars=len(backend.session_start(wing=wing)),
            note="every identity + essential drawer, truncated to 100-char stubs",
        ),
        Measurement(
            name=f"handoff (budget {budget_chars:,})",
            chars=len(backend.handoff(wing=wing, budget_chars=budget_chars)),
            note="whole drawers under a ceiling; omissions named, never cut",
        ),
    ]
    return CostReport(
        wing=wing,
        measurements=measurements,
        corpus=corpus_stats(store, wing=wing),
    )


def render(report: CostReport) -> str:
    """Render a cost report as plain text for the terminal."""
    lines = [
        f"Cairntir cost — wing={report.wing!r}",
        "",
        f"  {'surface':<34} {'chars':>9} {'~tokens':>9}",
        f"  {'-' * 34} {'-' * 9} {'-' * 9}",
    ]
    for m in report.measurements:
        lines.append(f"  {m.name:<34} {m.chars:>9,} {m.tokens:>9,}")
        lines.append(f"  {'':<34} {m.note}")

    session = next((m for m in report.measurements if m.name == "session_start"), None)
    handoff = next((m for m in report.measurements if m.name.startswith("handoff")), None)
    if session and handoff and session.tokens:
        saved = session.tokens - handoff.tokens
        pct = saved * 100 // session.tokens
        verb = "cheaper" if saved > 0 else "more expensive"
        lines += [
            "",
            f"  handoff is {abs(saved):,} tokens {verb} than session_start ({abs(pct)}%),",
            "  and returns whole drawers rather than stubs that cannot answer anything.",
        ]

    c = report.corpus
    lines += [
        "",
        f"Corpus — {c.drawers} drawer(s)",
        f"  median {c.median_chars:,} · p75 {c.p75_chars:,} · "
        f"p90 {c.p90_chars:,} · longest {c.max_chars:,} chars",
    ]
    if c.over_window:
        lines += [
            f"  {c.over_window} of {c.drawers} ({c.over_window_pct}%) exceed the embedder's "
            f"~{EMBEDDER_CHAR_WINDOW:,}-char window.",
            f"  The longest drawer has ~{c.worst_embedded_pct}% of its content embedded; "
            "the rest is",
            "  stored verbatim but invisible to semantic search. Drawers stay whole —",
            "  this is a retrieval defect, not a storage one.",
        ]
    else:
        lines.append("  every drawer fits the embedder's input window.")
    return "\n".join(lines) + "\n"
