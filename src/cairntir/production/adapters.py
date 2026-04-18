"""Non-LLM production adapters — store-backed memory, beliefs, a null runner, a manual proposer.

All four adapters are stdlib-only (beyond :mod:`cairntir`). They never
reach for a network, a subprocess, or an LLM. Running the Reason loop
with :class:`ManualProposer` + :class:`NullRunner` +
:class:`StoreBackedMemory` + :class:`StoreBackedBeliefs` is enough to
write prediction-bound drawers and log belief adjustments with zero
runtime dependencies beyond what Cairntir already requires.

A future local-AI proposer (Gemma 4 via llama.cpp or similar) can
implement :class:`~cairntir.reason.HypothesisProposer` and drop in
without a change to this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from cairntir.reason.model import Experiment, Hypothesis, Outcome

if TYPE_CHECKING:
    from cairntir.contracts import Store
    from cairntir.memory.taxonomy import Drawer


@dataclass
class StoreBackedMemory:
    """Implement :class:`~cairntir.reason.MemoryGateway` over a :class:`~cairntir.Store`.

    The loop never sees the underlying store directly — everything it
    needs (remember a drawer, recall drawers relevant to a question)
    is expressed through this narrow gateway.
    """

    store: Store

    def remember(self, drawer: Drawer) -> int:
        """Persist the drawer and return its newly assigned id."""
        saved = self.store.add(drawer)
        if saved.id is None:
            # The Store protocol requires add() to return a drawer with an id.
            # Any impl that skips this has violated its own contract.
            from cairntir.errors import MemoryStoreError

            raise MemoryStoreError("store.add returned a drawer without an id")
        return saved.id

    def recall(
        self,
        query: str,
        *,
        wing: str,
        room: str | None = None,
        limit: int = 5,
    ) -> list[Drawer]:
        """Return drawers relevant to ``query`` in ``wing``, belief-reranked by default."""
        hits = self.store.search(query, wing=wing, room=room, limit=limit)
        return [drawer for drawer, _distance in hits]


@dataclass
class StoreBackedBeliefs:
    """Implement :class:`~cairntir.reason.BeliefStore` over a :class:`~cairntir.Store`.

    Thin pass-through to ``store.reinforce`` / ``store.weaken``, which
    already have the shape the protocol requires.
    """

    store: Store

    def reinforce(self, drawer_id: int, *, amount: float) -> float:
        """Raise belief mass and return the new mass."""
        return self.store.reinforce(drawer_id, amount=amount)

    def weaken(self, drawer_id: int, *, amount: float) -> float:
        """Lower belief mass (clamped at zero) and return the new mass."""
        return self.store.weaken(drawer_id, amount=amount)


class NullRunner:
    """An :class:`~cairntir.reason.ExperimentRunner` that records a caller-supplied verdict.

    No experiment is executed. The verdict — success-or-not plus a
    human-readable observation string — is either passed at
    construction time or via :meth:`set_verdict` before the next
    :meth:`run` call. Useful for recipes where the "experiment" is a
    human reading the proposer's output and judging whether the
    prediction held.

    If :meth:`run` is called without a verdict set, it raises
    :class:`RuntimeError` immediately. The loop expects outcomes; a
    silent fallback would be a footgun.
    """

    def __init__(self, *, observed: str = "", success: bool | None = None) -> None:
        """Initialize with an optional starting verdict.

        Leaving both arguments at their defaults means the first call
        to :meth:`run` will fail until :meth:`set_verdict` is called
        — enforcing the "experiment needs a verdict" contract.
        """
        self._observed = observed
        self._success = success

    def set_verdict(self, *, observed: str, success: bool) -> None:
        """Record the verdict for the next :meth:`run` call.

        After :meth:`run` consumes a verdict it is *not* reset; the
        same verdict would apply to a subsequent call. Re-calling
        :meth:`set_verdict` between loop steps is the intended pattern
        when running multiple steps in one session.
        """
        self._observed = observed
        self._success = success

    def run(self, hypothesis: Hypothesis) -> Outcome:
        """Return an :class:`Outcome` built from the stored verdict."""
        if self._success is None:
            raise RuntimeError(
                "NullRunner.run called without a verdict — "
                "call set_verdict(observed=..., success=...) first"
            )
        experiment = Experiment(
            hypothesis=hypothesis,
            description="null runner — verdict supplied by caller",
        )
        return Outcome(
            experiment=experiment,
            observed=self._observed,
            success=self._success,
        )


class ManualProposer:
    """A :class:`~cairntir.reason.HypothesisProposer` that returns a caller-supplied hypothesis.

    Cairntir does not do inference. The Reason loop is a *discipline*
    for committing falsifiable predictions; where the claim and
    predicted outcome come from is the caller's problem. This adapter
    is the simplest wiring: the caller hands in a fully-formed
    :class:`~cairntir.reason.Hypothesis` (or the pieces of one), and
    the proposer returns it when the loop asks.

    Typical callers:

    * The ``cairntir reason`` CLI, which collects ``--claim`` and
      ``--predicted`` from flags or an interactive prompt.
    * A recipe that receives claim/predicted as declared inputs.
    * A future local-AI proposer — though a proposer that actually
      does inference will usually want its own class, not this
      pass-through.

    Two constructor shapes are supported: pass a
    :class:`Hypothesis` directly, or pass ``claim`` and
    ``predicted_outcome`` as strings and let this class build the
    hypothesis at :meth:`propose` time.
    """

    def __init__(
        self,
        hypothesis: Hypothesis | None = None,
        *,
        claim: str | None = None,
        predicted_outcome: str | None = None,
    ) -> None:
        """Accept a prebuilt hypothesis or the raw strings to build one later.

        If ``hypothesis`` is supplied it is returned verbatim on every
        :meth:`propose` call (the wing/room on the hypothesis wins,
        regardless of what the loop passes). If ``claim`` and
        ``predicted_outcome`` are supplied instead, the hypothesis is
        constructed per-call with the loop's wing/room so the same
        proposer works across multiple contexts.
        """
        if hypothesis is None and (claim is None or predicted_outcome is None):
            raise ValueError(
                "ManualProposer requires either a prebuilt hypothesis or both "
                "claim and predicted_outcome strings"
            )
        self._hypothesis = hypothesis
        self._claim = claim
        self._predicted_outcome = predicted_outcome

    def propose(self, *, question: str, wing: str, room: str) -> Hypothesis:
        """Return the caller-supplied hypothesis.

        ``question`` is accepted to satisfy the protocol but is not
        used — the hypothesis was already formed by the caller. If
        :meth:`__init__` received raw strings, the returned hypothesis
        is built here with the loop's wing/room.
        """
        _ = question
        if self._hypothesis is not None:
            return self._hypothesis
        # __init__ guarantees both strings are non-None in this branch,
        # but narrow for mypy without using assert (banned under -O).
        claim = self._claim or ""
        predicted = self._predicted_outcome or ""
        return Hypothesis(
            claim=claim,
            predicted_outcome=predicted,
            wing=wing,
            room=room,
        )
