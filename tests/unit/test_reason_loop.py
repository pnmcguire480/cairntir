"""Unit tests for the v0.6 Reason loop. No sqlite, no LLMs, no networks."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from cairntir.memory.taxonomy import Drawer
from cairntir.reason import (
    BeliefStore,
    BeliefUpdate,
    ExperimentRunner,
    Hypothesis,
    HypothesisProposer,
    MemoryGateway,
    Outcome,
    ReasonLoop,
)

# --------- fakes --------------------------------------------------------


@dataclass
class FakeProposer:
    """Returns a canned hypothesis per question."""

    hypothesis: Hypothesis
    seen: list[str] = field(default_factory=list)

    def propose(self, *, question: str, wing: str, room: str) -> Hypothesis:
        self.seen.append(question)
        return self.hypothesis


@dataclass
class FakeRunner:
    """Returns a canned outcome for any hypothesis."""

    observed: str
    success: bool

    def run(self, hypothesis: Hypothesis) -> Outcome:
        from cairntir.reason.model import Experiment

        experiment = Experiment(
            hypothesis=hypothesis,
            description="fake experiment",
        )
        return Outcome(
            experiment=experiment,
            observed=self.observed,
            success=self.success,
        )


@dataclass
class FakeBeliefStore:
    """Counter-backed belief store with mass clamped at zero."""

    masses: dict[int, float] = field(default_factory=dict)

    def reinforce(self, drawer_id: int, *, amount: float) -> float:
        new = self.masses.get(drawer_id, 1.0) + amount
        self.masses[drawer_id] = new
        return new

    def weaken(self, drawer_id: int, *, amount: float) -> float:
        new = max(0.0, self.masses.get(drawer_id, 1.0) - amount)
        self.masses[drawer_id] = new
        return new


@dataclass
class FakeMemoryGateway:
    """Dict-backed memory with auto-incrementing ids."""

    next_id: int = 1
    drawers: dict[int, Drawer] = field(default_factory=dict)

    def remember(self, drawer: Drawer) -> int:
        drawer_id = self.next_id
        self.next_id += 1
        self.drawers[drawer_id] = drawer.model_copy(update={"id": drawer_id})
        return drawer_id

    def recall(
        self,
        query: str,
        *,
        wing: str,
        room: str | None = None,
        limit: int = 5,
    ) -> list[Drawer]:
        return [d for d in self.drawers.values() if d.wing == wing][:limit]


# --------- protocol conformance ----------------------------------------


def test_fakes_satisfy_protocols() -> None:
    # runtime_checkable protocols let us assert shape without inheritance.
    assert isinstance(
        FakeProposer(hypothesis=Hypothesis(claim="x", predicted_outcome="y", wing="w", room="r1")),
        HypothesisProposer,
    )
    assert isinstance(FakeRunner(observed="z", success=True), ExperimentRunner)
    assert isinstance(FakeBeliefStore(), BeliefStore)
    assert isinstance(FakeMemoryGateway(), MemoryGateway)


# --------- successful step ---------------------------------------------


def test_successful_step_writes_prediction_and_observation_drawers() -> None:
    hypothesis = Hypothesis(
        claim="sqlite-vec is embedded",
        predicted_outcome="no network calls during search",
        wing="cairntir",
        room="phase-6",
    )
    proposer = FakeProposer(hypothesis=hypothesis)
    runner = FakeRunner(observed="no network calls during search", success=True)
    beliefs = FakeBeliefStore()
    memory = FakeMemoryGateway()

    loop = ReasonLoop(proposer=proposer, runner=runner, beliefs=beliefs, memory=memory)
    update = loop.step(
        question="does search hit the network?",
        wing="cairntir",
        room="phase-6",
    )

    assert isinstance(update, BeliefUpdate)
    assert update.mass_change == pytest.approx(1.0)
    assert update.delta == ""

    prediction = memory.drawers[update.prediction_id]
    observation = memory.drawers[update.observation_id]
    assert prediction.claim == "sqlite-vec is embedded"
    assert prediction.predicted_outcome == "no network calls during search"
    assert prediction.observed_outcome is None
    assert prediction.metadata["source"] == "reason.predict"

    assert observation.supersedes_id == update.prediction_id
    assert observation.observed_outcome == "no network calls during search"
    assert observation.delta is None  # success → no surprise
    assert observation.metadata["source"] == "reason.observe"
    assert observation.metadata["success"] is True

    assert beliefs.masses[update.prediction_id] == pytest.approx(2.0)


# --------- failing step -------------------------------------------------


def test_failing_step_records_delta_and_weakens_belief() -> None:
    hypothesis = Hypothesis(
        claim="the cache is write-through",
        predicted_outcome="writes land in postgres synchronously",
        wing="cairntir",
        room="predictions",
    )
    proposer = FakeProposer(hypothesis=hypothesis)
    runner = FakeRunner(
        observed="writes are asynchronous and may lose data on crash",
        success=False,
    )
    beliefs = FakeBeliefStore()
    memory = FakeMemoryGateway()

    loop = ReasonLoop(proposer=proposer, runner=runner, beliefs=beliefs, memory=memory)
    update = loop.step(
        question="is the cache write-through?",
        wing="cairntir",
        room="predictions",
    )

    assert update.mass_change == pytest.approx(-1.0)
    assert "predicted" in update.delta and "observed" in update.delta

    observation = memory.drawers[update.observation_id]
    assert observation.delta is not None
    assert "writes land in postgres" in observation.delta
    assert observation.metadata["success"] is False

    # Weaken from default-initialised mass (1.0) by 1.0 → 0.0. Clamped.
    assert beliefs.masses[update.prediction_id] == pytest.approx(0.0)


# --------- contract enforcement ----------------------------------------


def test_empty_predicted_outcome_is_rejected() -> None:
    hypothesis = Hypothesis(
        claim="something",
        predicted_outcome="   ",  # whitespace only
        wing="cairntir",
        room="room-a",
    )
    loop = ReasonLoop(
        proposer=FakeProposer(hypothesis=hypothesis),
        runner=FakeRunner(observed="doesn't matter", success=True),
        beliefs=FakeBeliefStore(),
        memory=FakeMemoryGateway(),
    )
    with pytest.raises(ValueError, match="falsifiable prediction"):
        loop.step(question="q", wing="cairntir", room="room-a")


def test_loop_never_swallows_runner_errors() -> None:
    class BrokenRunner:
        def run(self, hypothesis: Hypothesis) -> Outcome:
            raise RuntimeError("hardware on fire")

    hypothesis = Hypothesis(claim="x", predicted_outcome="y", wing="cairntir", room="room-a")
    loop = ReasonLoop(
        proposer=FakeProposer(hypothesis=hypothesis),
        runner=BrokenRunner(),  # type: ignore[arg-type]
        beliefs=FakeBeliefStore(),
        memory=FakeMemoryGateway(),
    )
    with pytest.raises(RuntimeError, match="hardware on fire"):
        loop.step(question="q", wing="cairntir", room="room-a")


def test_two_steps_in_a_row_accumulate_mass_on_repeated_success() -> None:
    hypothesis = Hypothesis(
        claim="claim",
        predicted_outcome="outcome",
        wing="cairntir",
        room="room-a",
    )
    beliefs = FakeBeliefStore()
    memory = FakeMemoryGateway()
    loop = ReasonLoop(
        proposer=FakeProposer(hypothesis=hypothesis),
        runner=FakeRunner(observed="outcome", success=True),
        beliefs=beliefs,
        memory=memory,
    )
    first = loop.step(question="q1", wing="cairntir", room="room-a")
    second = loop.step(question="q2", wing="cairntir", room="room-a")
    assert first.prediction_id != second.prediction_id
    assert beliefs.masses[first.prediction_id] == pytest.approx(2.0)
    assert beliefs.masses[second.prediction_id] == pytest.approx(2.0)
