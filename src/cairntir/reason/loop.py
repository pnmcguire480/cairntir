"""The Reason loop itself — v0.6.

:class:`ReasonLoop` is the orchestration. It composes four ports —
proposer, runner, beliefs, memory — and exposes one method:
:meth:`ReasonLoop.step`. Everything inside is stdlib and pure.

The step shape:

1. Propose a hypothesis for the question.
2. Write a **prediction drawer** to memory (v0.2 contract: nothing
   leaves the loop without a falsifiable commitment).
3. Ask the runner to carry out the experiment.
4. Write an **observation drawer** that ``supersedes`` the prediction,
   carrying the observed outcome and — if the prediction failed — a
   non-empty ``delta`` surprise note.
5. Nudge the belief store: reinforce on success, weaken on failure.
6. Return a :class:`BeliefUpdate` describing what just changed.

The loop writes two drawers per step, always, even when the runner
fails. Verbatim is the floor; a failed step is not a skipped step.
"""

from __future__ import annotations

from cairntir.memory.taxonomy import Drawer, Layer
from cairntir.reason.model import BeliefUpdate, Hypothesis, Outcome
from cairntir.reason.ports import (
    BeliefStore,
    ExperimentRunner,
    HypothesisProposer,
    MemoryGateway,
)


class ReasonLoop:
    """A transport-free reasoning loop over four ports."""

    def __init__(
        self,
        *,
        proposer: HypothesisProposer,
        runner: ExperimentRunner,
        beliefs: BeliefStore,
        memory: MemoryGateway,
    ) -> None:
        """Bind the four adapters this loop will drive."""
        self._proposer = proposer
        self._runner = runner
        self._beliefs = beliefs
        self._memory = memory

    def step(self, *, question: str, wing: str, room: str) -> BeliefUpdate:
        """Run one full predict → observe → update cycle.

        Returns a :class:`BeliefUpdate` describing the drawers written
        and the belief mass change. Raises whatever the adapters raise
        — the loop does not swallow errors. If a proposer returns an
        empty ``predicted_outcome`` it is a programming mistake in the
        adapter and the loop surfaces it immediately.
        """
        hypothesis = self._proposer.propose(question=question, wing=wing, room=room)
        if not hypothesis.predicted_outcome.strip():
            raise ValueError(
                "HypothesisProposer returned an empty predicted_outcome; "
                "the v0.2 contract requires a falsifiable prediction"
            )

        prediction_id = self._memory.remember(
            _build_prediction_drawer(hypothesis, question=question)
        )

        outcome = self._runner.run(hypothesis)

        delta = _compute_delta(hypothesis, outcome)
        observation_id = self._memory.remember(
            _build_observation_drawer(
                hypothesis,
                outcome,
                delta=delta,
                supersedes_id=prediction_id,
            )
        )

        mass_change = self._update_beliefs(prediction_id, outcome)

        return BeliefUpdate(
            prediction_id=prediction_id,
            observation_id=observation_id,
            mass_change=mass_change,
            delta=delta,
        )

    def _update_beliefs(self, drawer_id: int, outcome: Outcome) -> float:
        """Nudge belief mass and return the signed mass change the loop intended.

        We return the *intended* change (+1.0 on success, -1.0 on
        failure), not the raw mass after clamping. A caller that cares
        about the actual post-clamp mass can query the belief store
        directly; what the loop logs is the reasoning-step verdict.
        """
        if outcome.success:
            self._beliefs.reinforce(drawer_id, amount=1.0)
            return 1.0
        self._beliefs.weaken(drawer_id, amount=1.0)
        return -1.0


def _build_prediction_drawer(hypothesis: Hypothesis, *, question: str) -> Drawer:
    return Drawer(
        wing=hypothesis.wing,
        room=hypothesis.room,
        content=(
            f"Q: {question}\nClaim: {hypothesis.claim}\nPredicted: {hypothesis.predicted_outcome}"
        ),
        layer=Layer.ON_DEMAND,
        metadata={"source": "reason.predict"},
        claim=hypothesis.claim,
        predicted_outcome=hypothesis.predicted_outcome,
    )


def _build_observation_drawer(
    hypothesis: Hypothesis,
    outcome: Outcome,
    *,
    delta: str,
    supersedes_id: int,
) -> Drawer:
    return Drawer(
        wing=hypothesis.wing,
        room=hypothesis.room,
        content=(
            f"Claim: {hypothesis.claim}\n"
            f"Predicted: {hypothesis.predicted_outcome}\n"
            f"Observed:  {outcome.observed}\n"
            f"Success:   {outcome.success}"
        ),
        layer=Layer.ON_DEMAND,
        metadata={"source": "reason.observe", "success": outcome.success},
        claim=hypothesis.claim,
        predicted_outcome=hypothesis.predicted_outcome,
        observed_outcome=outcome.observed,
        delta=delta or None,
        supersedes_id=supersedes_id,
    )


def _compute_delta(hypothesis: Hypothesis, outcome: Outcome) -> str:
    """Return a surprise note iff the observation diverged from the prediction.

    Empty string means "no surprise" — the loop passes that through as
    ``None`` into the observation drawer so the store's ``delta``
    column stays null in the unsurprising case.
    """
    if outcome.success:
        return ""
    return f"predicted {hypothesis.predicted_outcome!r}, observed {outcome.observed!r}"
