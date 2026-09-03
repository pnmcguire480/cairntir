"""The Reason loop itself — v0.6.

:class:`ReasonLoop` is the orchestration. It composes four ports —
proposer, runner, beliefs, memory — and exposes one method:
:meth:`ReasonLoop.step`. Everything inside is stdlib and pure.

The step shape:

1. Propose a hypothesis for the question.
2. Write a **prediction drawer** to memory (v0.2 contract: nothing
   leaves the loop without a falsifiable commitment).
3. Ask the runner to carry out the experiment.
4. Validate that the outcome describes the committed hypothesis, then write
   an **observation drawer** that ``supersedes`` the prediction and carries
   the experiment, observed outcome, verdict, and any surprise ``delta``.
5. Nudge the belief store: reinforce on success, weaken on failure.
6. Return a :class:`BeliefUpdate` describing what just changed.

Every completed step writes two drawers. A negative outcome is still a
completed experiment and records a delta. Runner exceptions propagate; a
durable gateway rolls their incomplete transaction back.
"""

from __future__ import annotations

from typing import Any

from cairntir.memory.taxonomy import Drawer, Layer
from cairntir.reason.model import BeliefUpdate, Experiment, Hypothesis, Outcome
from cairntir.reason.ports import (
    BeliefStore,
    DurableMemoryGateway,
    ExperimentRunner,
    HypothesisProposer,
    LearningMemoryGateway,
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

    def step(
        self,
        *,
        question: str,
        wing: str,
        room: str,
        supersedes_id: int | None = None,
        idempotency_key: str | None = None,
    ) -> BeliefUpdate:
        """Run one full predict → observe → update cycle.

        Returns a :class:`BeliefUpdate` describing the drawers written
        and the belief mass change. Raises whatever the adapters raise
        — the loop does not swallow errors. If a proposer returns an
        empty ``predicted_outcome`` it is a programming mistake in the
        adapter and the loop surfaces it immediately.

        ``supersedes_id`` extends an existing prediction-bound chain:
        when supplied, the prediction drawer this step writes carries
        that pointer. The Decision Replay recipe uses this to chain a
        new prediction onto the leaf of a past decision's history.
        Leave it ``None`` for a fresh chain (the v0.6 default).
        """
        _validate_invocation(
            question=question,
            wing=wing,
            room=room,
            supersedes_id=supersedes_id,
        )
        memory = self._memory
        if idempotency_key is not None and not isinstance(memory, DurableMemoryGateway):
            raise ValueError("idempotency_key requires a durable memory gateway")
        if isinstance(memory, DurableMemoryGateway):
            self._require_shared_store_when_visible()
            if idempotency_key is not None:
                execution = memory.execute_once(
                    idempotency_key=idempotency_key,
                    operation="reason.step",
                    request={
                        "question": question,
                        "wing": wing,
                        "room": room,
                        "supersedes_id": supersedes_id,
                    },
                    action=lambda: _belief_update_to_dict(
                        self._step_once(
                            question=question,
                            wing=wing,
                            room=room,
                            supersedes_id=supersedes_id,
                        )
                    ),
                )
                return _belief_update_from_dict(execution.result)
            with memory.atomic():
                return self._step_once(
                    question=question,
                    wing=wing,
                    room=room,
                    supersedes_id=supersedes_id,
                )
        return self._step_once(
            question=question,
            wing=wing,
            room=room,
            supersedes_id=supersedes_id,
        )

    def _step_once(
        self,
        *,
        question: str,
        wing: str,
        room: str,
        supersedes_id: int | None,
    ) -> BeliefUpdate:
        hypothesis = self._proposer.propose(question=question, wing=wing, room=room)
        _validate_hypothesis(hypothesis, wing=wing, room=room)

        prediction_id = self._memory.remember(
            _build_prediction_drawer(
                hypothesis,
                question=question,
                supersedes_id=supersedes_id,
            )
        )

        outcome = self._runner.run(hypothesis)
        _validate_outcome(outcome, hypothesis=hypothesis)

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
        if isinstance(self._memory, LearningMemoryGateway):
            self._memory.reflect(wing=wing)

        return BeliefUpdate(
            prediction_id=prediction_id,
            observation_id=observation_id,
            mass_change=mass_change,
            delta=delta,
        )

    def _require_shared_store_when_visible(self) -> None:
        memory_store = getattr(self._memory, "store", None)
        belief_store = getattr(self._beliefs, "store", None)
        if (
            memory_store is not None
            and belief_store is not None
            and memory_store is not belief_store
        ):
            raise ValueError(
                "durable Reason workflows require memory and beliefs to share one store"
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


def _build_prediction_drawer(
    hypothesis: Hypothesis,
    *,
    question: str,
    supersedes_id: int | None = None,
) -> Drawer:
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
        supersedes_id=supersedes_id,
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
            f"Experiment: {outcome.experiment.description.strip()}\n"
            f"Observed:  {outcome.observed}\n"
            f"Success:   {outcome.success}"
        ),
        layer=Layer.ON_DEMAND,
        metadata={
            "source": "reason.observe",
            "success": outcome.success,
            "experiment": outcome.experiment.description.strip(),
        },
        claim=hypothesis.claim,
        predicted_outcome=hypothesis.predicted_outcome,
        observed_outcome=outcome.observed,
        delta=delta or None,
        supersedes_id=supersedes_id,
    )


def _compute_delta(hypothesis: Hypothesis, outcome: Outcome) -> str:
    """Return explicit surprise or a deterministic failed-prediction fallback.

    Success and surprise are independent. Empty string means "no surprise";
    the loop passes that through as ``None`` into the observation drawer.
    """
    explicit = outcome.delta.strip()
    if explicit:
        return explicit
    if outcome.success:
        return ""
    return f"predicted {hypothesis.predicted_outcome!r}, observed {outcome.observed!r}"


def _validate_invocation(
    *,
    question: str,
    wing: str,
    room: str,
    supersedes_id: int | None,
) -> None:
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be non-empty")
    if not isinstance(wing, str) or not wing.strip():
        raise ValueError("wing must be non-empty")
    if not isinstance(room, str) or not room.strip():
        raise ValueError("room must be non-empty")
    if supersedes_id is not None and (
        isinstance(supersedes_id, bool) or not isinstance(supersedes_id, int) or supersedes_id < 1
    ):
        raise ValueError("supersedes_id must be a positive integer")


def _validate_hypothesis(hypothesis: Hypothesis, *, wing: str, room: str) -> None:
    if not isinstance(hypothesis, Hypothesis):
        raise TypeError("HypothesisProposer must return a Hypothesis")
    if not isinstance(hypothesis.claim, str) or not hypothesis.claim.strip():
        raise ValueError("HypothesisProposer returned an empty claim")
    if (
        not isinstance(hypothesis.predicted_outcome, str)
        or not hypothesis.predicted_outcome.strip()
    ):
        raise ValueError(
            "HypothesisProposer returned an empty predicted_outcome; "
            "the v0.2 contract requires a falsifiable prediction"
        )
    if hypothesis.wing != wing or hypothesis.room != room:
        raise ValueError(
            "HypothesisProposer scope mismatch: returned "
            f"{hypothesis.wing}/{hypothesis.room}, expected {wing}/{room}"
        )


def _validate_outcome(outcome: Outcome, *, hypothesis: Hypothesis) -> None:
    if not isinstance(outcome, Outcome):
        raise TypeError("ExperimentRunner must return an Outcome")
    if not isinstance(outcome.experiment, Experiment):
        raise TypeError("ExperimentRunner outcome must carry an Experiment")
    if outcome.experiment.hypothesis != hypothesis:
        raise ValueError("ExperimentRunner returned an outcome for a different hypothesis")
    if (
        not isinstance(outcome.experiment.description, str)
        or not outcome.experiment.description.strip()
    ):
        raise ValueError("ExperimentRunner returned an empty experiment description")
    if not isinstance(outcome.observed, str) or not outcome.observed.strip():
        raise ValueError("ExperimentRunner returned an empty observation")
    if not isinstance(outcome.success, bool):
        raise TypeError("ExperimentRunner returned a non-boolean verdict")
    if not isinstance(outcome.delta, str):
        raise TypeError("ExperimentRunner returned a non-string delta")


def _belief_update_to_dict(update: BeliefUpdate) -> dict[str, object]:
    return {
        "prediction_id": update.prediction_id,
        "observation_id": update.observation_id,
        "mass_change": update.mass_change,
        "delta": update.delta,
    }


def _belief_update_from_dict(payload: dict[str, Any]) -> BeliefUpdate:
    try:
        return BeliefUpdate(
            prediction_id=int(payload["prediction_id"]),
            observation_id=int(payload["observation_id"]),
            mass_change=float(payload["mass_change"]),
            delta=str(payload["delta"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid durable Reason result: {exc}") from exc
