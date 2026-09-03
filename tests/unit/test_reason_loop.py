"""Unit tests for the v0.6 Reason loop. No sqlite, no LLMs, no networks."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from cairntir.memory.taxonomy import Drawer
from cairntir.reason import (
    BeliefStore,
    BeliefUpdate,
    Experiment,
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

    def list_by(
        self,
        *,
        wing: str | None = None,
        room: str | None = None,
        limit: int = 10,
    ) -> list[Drawer]:
        result = [
            d
            for d in self.drawers.values()
            if (wing is None or d.wing == wing) and (room is None or d.room == room)
        ]
        # Most-recent-first by drawer id (the fake assigns monotonic ids).
        result.sort(key=lambda d: d.id or 0, reverse=True)
        return result[:limit]


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


def test_blank_claim_is_rejected_before_writing() -> None:
    memory = FakeMemoryGateway()
    loop = ReasonLoop(
        proposer=FakeProposer(
            hypothesis=Hypothesis(
                claim="   ",
                predicted_outcome="something observable happens",
                wing="cairntir",
                room="room-a",
            )
        ),
        runner=FakeRunner(observed="something observable happens", success=True),
        beliefs=FakeBeliefStore(),
        memory=memory,
    )

    with pytest.raises(ValueError, match="empty claim"):
        loop.step(question="q", wing="cairntir", room="room-a")

    assert memory.drawers == {}


def test_reason_loop_rejects_cross_scope_hypothesis_before_writing() -> None:
    memory = FakeMemoryGateway()
    loop = ReasonLoop(
        proposer=FakeProposer(
            hypothesis=Hypothesis(
                claim="scope stays bound",
                predicted_outcome="the requested wing receives the record",
                wing="other-wing",
                room="other-room",
            )
        ),
        runner=FakeRunner(observed="unused", success=True),
        beliefs=FakeBeliefStore(),
        memory=memory,
    )

    with pytest.raises(ValueError, match="scope mismatch"):
        loop.step(question="where does this land?", wing="cairntir", room="reason")

    assert memory.drawers == {}


def test_reason_loop_rejects_outcome_for_a_different_hypothesis() -> None:
    hypothesis = Hypothesis(
        claim="the committed hypothesis is tested",
        predicted_outcome="the same hypothesis returns in the outcome",
        wing="cairntir",
        room="reason",
    )
    different = Hypothesis(
        claim="different claim",
        predicted_outcome="different outcome",
        wing="cairntir",
        room="reason",
    )

    class MismatchedRunner:
        def run(self, proposed: Hypothesis) -> Outcome:
            _ = proposed
            return Outcome(
                experiment=Experiment(hypothesis=different, description="wrong experiment"),
                observed="different outcome",
                success=True,
            )

    memory = FakeMemoryGateway()
    beliefs = FakeBeliefStore()
    loop = ReasonLoop(
        proposer=FakeProposer(hypothesis=hypothesis),
        runner=MismatchedRunner(),
        beliefs=beliefs,
        memory=memory,
    )

    with pytest.raises(ValueError, match="different hypothesis"):
        loop.step(question="was the committed hypothesis tested?", wing="cairntir", room="reason")

    assert len(memory.drawers) == 1
    assert beliefs.masses == {}


def test_reason_loop_rejects_outcome_without_an_experiment() -> None:
    hypothesis = Hypothesis(
        claim="the runner records its experiment",
        predicted_outcome="the outcome cites the tested hypothesis",
        wing="cairntir",
        room="reason",
    )

    class MissingExperimentRunner:
        def run(self, proposed: Hypothesis) -> Outcome:
            _ = proposed
            return Outcome(
                experiment=None,  # type: ignore[arg-type]
                observed="the outcome cites nothing",
                success=True,
            )

    memory = FakeMemoryGateway()
    loop = ReasonLoop(
        proposer=FakeProposer(hypothesis=hypothesis),
        runner=MissingExperimentRunner(),
        beliefs=FakeBeliefStore(),
        memory=memory,
    )

    with pytest.raises(TypeError, match="Experiment"):
        loop.step(question="what was tested?", wing="cairntir", room="reason")

    assert len(memory.drawers) == 1


@pytest.mark.parametrize(
    ("description", "observed", "success", "exception_type", "message"),
    [
        ("   ", "observed", True, ValueError, "experiment description"),
        ("experiment", "   ", True, ValueError, "empty observation"),
        ("experiment", "observed", "yes", TypeError, "boolean verdict"),
    ],
)
def test_reason_loop_rejects_incomplete_outcome_evidence(
    description: str,
    observed: str,
    success: object,
    exception_type: type[Exception],
    message: str,
) -> None:
    hypothesis = Hypothesis(
        claim="outcome evidence is complete",
        predicted_outcome="the runner returns a bound record",
        wing="cairntir",
        room="reason",
    )

    class IncompleteRunner:
        def run(self, proposed: Hypothesis) -> Outcome:
            return Outcome(
                experiment=Experiment(hypothesis=proposed, description=description),
                observed=observed,
                success=success,  # type: ignore[arg-type]
            )

    memory = FakeMemoryGateway()
    beliefs = FakeBeliefStore()
    loop = ReasonLoop(
        proposer=FakeProposer(hypothesis=hypothesis),
        runner=IncompleteRunner(),
        beliefs=beliefs,
        memory=memory,
    )

    with pytest.raises(exception_type, match=message):
        loop.step(question="is the outcome complete?", wing="cairntir", room="reason")

    assert len(memory.drawers) == 1
    assert beliefs.masses == {}


def test_successful_step_preserves_explicit_surprise_delta() -> None:
    hypothesis = Hypothesis(
        claim="the release publishes",
        predicted_outcome="the release becomes publicly installable",
        wing="cairntir",
        room="reason",
    )

    class SurprisingSuccessRunner:
        def run(self, proposed: Hypothesis) -> Outcome:
            return Outcome(
                experiment=Experiment(
                    hypothesis=proposed,
                    description="inspect the published release and workflow provenance",
                ),
                observed="the release became publicly installable after manual dispatch",
                success=True,
                delta="the result held, but the tag trigger never started",
            )

    memory = FakeMemoryGateway()
    beliefs = FakeBeliefStore()
    loop = ReasonLoop(
        proposer=FakeProposer(hypothesis=hypothesis),
        runner=SurprisingSuccessRunner(),
        beliefs=beliefs,
        memory=memory,
    )

    update = loop.step(question="did publication hold?", wing="cairntir", room="reason")
    observation = memory.drawers[update.observation_id]

    assert update.mass_change == pytest.approx(1.0)
    assert update.delta == "the result held, but the tag trigger never started"
    assert observation.delta == update.delta
    assert observation.metadata["success"] is True
    assert observation.metadata["experiment"] == (
        "inspect the published release and workflow provenance"
    )
    assert "Experiment: inspect the published release" in observation.content


def test_non_durable_memory_rejects_idempotency_key() -> None:
    hypothesis = Hypothesis(
        claim="replay is honest",
        predicted_outcome="unsupported durability is rejected",
        wing="cairntir",
        room="reason",
    )
    proposer = FakeProposer(hypothesis=hypothesis)
    memory = FakeMemoryGateway()
    loop = ReasonLoop(
        proposer=proposer,
        runner=FakeRunner(observed="unsupported durability is rejected", success=True),
        beliefs=FakeBeliefStore(),
        memory=memory,
    )

    with pytest.raises(ValueError, match="durable memory gateway"):
        loop.step(
            question="will this replay?",
            wing="cairntir",
            room="reason",
            idempotency_key="pretend-durable",
        )

    assert proposer.seen == []
    assert memory.drawers == {}


@pytest.mark.parametrize(
    ("question", "supersedes_id", "message"),
    [
        ("   ", None, "question must be non-empty"),
        ("valid question", 0, "supersedes_id must be a positive integer"),
        ("valid question", True, "supersedes_id must be a positive integer"),
    ],
)
def test_reason_loop_rejects_invalid_invocation_before_proposal(
    question: str,
    supersedes_id: int | None,
    message: str,
) -> None:
    hypothesis = Hypothesis(
        claim="inputs are valid",
        predicted_outcome="the proposer is not called for invalid input",
        wing="cairntir",
        room="reason",
    )
    proposer = FakeProposer(hypothesis=hypothesis)
    memory = FakeMemoryGateway()
    loop = ReasonLoop(
        proposer=proposer,
        runner=FakeRunner(observed="unused", success=True),
        beliefs=FakeBeliefStore(),
        memory=memory,
    )

    with pytest.raises(ValueError, match=message):
        loop.step(
            question=question,
            wing="cairntir",
            room="reason",
            supersedes_id=supersedes_id,
        )

    assert proposer.seen == []
    assert memory.drawers == {}


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


def test_step_with_supersedes_id_chains_new_prediction_onto_existing_chain() -> None:
    """A replay-style step extends an existing chain via the prediction's
    ``supersedes_id`` pointer, not by mutating the original drawer."""
    hypothesis = Hypothesis(
        claim="fastembed default kills the cold-start hang",
        predicted_outcome="MCP startup stays under 5s on every install",
        wing="cairntir",
        room="journey",
    )
    proposer = FakeProposer(hypothesis=hypothesis)
    runner = FakeRunner(observed="cold start steady at ~1.4s for four days", success=True)
    beliefs = FakeBeliefStore()
    memory = FakeMemoryGateway()

    # Pretend an earlier prediction already exists at id 42 — this is the
    # leaf of the chain we want to extend.
    loop = ReasonLoop(proposer=proposer, runner=runner, beliefs=beliefs, memory=memory)
    update = loop.step(
        question="did the fastembed default hold?",
        wing="cairntir",
        room="journey",
        supersedes_id=42,
    )

    prediction = memory.drawers[update.prediction_id]
    observation = memory.drawers[update.observation_id]
    # New prediction extends the chain: supersedes the prior leaf id (42).
    assert prediction.supersedes_id == 42
    # New observation supersedes the new prediction (unchanged behavior).
    assert observation.supersedes_id == update.prediction_id


def test_step_without_supersedes_id_starts_fresh_chain() -> None:
    """The default behavior — no supersedes_id — leaves the prediction
    drawer rootless, as v0.6 has always done."""
    hypothesis = Hypothesis(claim="x", predicted_outcome="y", wing="cairntir", room="phase-6")
    memory = FakeMemoryGateway()
    loop = ReasonLoop(
        proposer=FakeProposer(hypothesis=hypothesis),
        runner=FakeRunner(observed="y", success=True),
        beliefs=FakeBeliefStore(),
        memory=memory,
    )
    update = loop.step(question="q", wing="cairntir", room="phase-6")
    # The fresh-chain default is preserved — the prediction is rootless,
    # the observation supersedes the prediction (unchanged from v0.6).
    prediction = memory.drawers[update.prediction_id]
    observation = memory.drawers[update.observation_id]
    assert prediction.supersedes_id is None
    assert observation.supersedes_id == update.prediction_id


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
