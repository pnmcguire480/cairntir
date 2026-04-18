"""Unit tests for the non-LLM production adapters."""

from __future__ import annotations

from pathlib import Path

import pytest

from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer, Layer
from cairntir.production.adapters import (
    ManualProposer,
    NullRunner,
    StoreBackedBeliefs,
    StoreBackedMemory,
)
from cairntir.reason.model import Hypothesis
from cairntir.reason.ports import (
    BeliefStore,
    ExperimentRunner,
    HypothesisProposer,
    MemoryGateway,
)


@pytest.fixture()
def store(tmp_path: Path) -> DrawerStore:
    return DrawerStore(tmp_path / "prod.db", HashEmbeddingProvider(dimension=32))


# --------- Protocol conformance ----------------------------------------


def test_adapters_satisfy_protocols(store: DrawerStore) -> None:
    memory = StoreBackedMemory(store=store)
    beliefs = StoreBackedBeliefs(store=store)
    runner = NullRunner(observed="x", success=True)

    assert isinstance(memory, MemoryGateway)
    assert isinstance(beliefs, BeliefStore)
    assert isinstance(runner, ExperimentRunner)


# --------- StoreBackedMemory -------------------------------------------


def test_store_backed_memory_remember_and_recall(store: DrawerStore) -> None:
    memory = StoreBackedMemory(store=store)
    new_id = memory.remember(
        Drawer(
            wing="cairntir",
            room="notes",
            content="sqlite-vec is embedded",
            layer=Layer.ON_DEMAND,
        )
    )
    assert new_id >= 1

    hits = memory.recall("sqlite-vec is embedded", wing="cairntir", limit=5)
    assert any("sqlite-vec" in d.content for d in hits)


def test_store_backed_memory_recall_respects_wing(store: DrawerStore) -> None:
    memory = StoreBackedMemory(store=store)
    memory.remember(Drawer(wing="cairntir", room="notes", content="alpha alpha alpha"))
    memory.remember(Drawer(wing="stars-2026", room="notes", content="alpha alpha alpha"))

    hits = memory.recall("alpha alpha alpha", wing="cairntir", limit=10)
    assert hits, "expected at least one hit"
    for drawer in hits:
        assert drawer.wing == "cairntir"


# --------- StoreBackedBeliefs ------------------------------------------


def test_store_backed_beliefs_reinforce_and_weaken(store: DrawerStore) -> None:
    memory = StoreBackedMemory(store=store)
    beliefs = StoreBackedBeliefs(store=store)
    new_id = memory.remember(Drawer(wing="cairntir", room="notes", content="test"))

    after_up = beliefs.reinforce(new_id, amount=0.5)
    assert after_up == pytest.approx(1.5)

    after_down = beliefs.weaken(new_id, amount=2.0)
    assert after_down == pytest.approx(0.0)  # clamped at 0


# --------- NullRunner --------------------------------------------------


def test_null_runner_without_verdict_raises() -> None:
    runner = NullRunner()
    hypothesis = Hypothesis(
        claim="c", predicted_outcome="p", wing="cairntir", room="room-a"
    )
    with pytest.raises(RuntimeError, match="set_verdict"):
        runner.run(hypothesis)


def test_null_runner_returns_outcome_matching_verdict() -> None:
    runner = NullRunner()
    hypothesis = Hypothesis(
        claim="c", predicted_outcome="p", wing="cairntir", room="room-a"
    )
    runner.set_verdict(observed="it happened as predicted", success=True)
    outcome = runner.run(hypothesis)
    assert outcome.success is True
    assert outcome.observed == "it happened as predicted"
    assert outcome.experiment.hypothesis is hypothesis


def test_null_runner_constructor_verdict_is_also_consumed() -> None:
    runner = NullRunner(observed="preset", success=False)
    hypothesis = Hypothesis(
        claim="c", predicted_outcome="p", wing="cairntir", room="room-a"
    )
    outcome = runner.run(hypothesis)
    assert outcome.success is False
    assert outcome.observed == "preset"


# --------- ManualProposer ----------------------------------------------


def test_manual_proposer_with_prebuilt_hypothesis_returns_it() -> None:
    hypothesis = Hypothesis(
        claim="lazy embedder fixes cold start",
        predicted_outcome="startup <2s",
        wing="cairntir",
        room="predictions",
    )
    proposer = ManualProposer(hypothesis)
    assert isinstance(proposer, HypothesisProposer)
    result = proposer.propose(
        question="does startup pass?",
        wing="ignored-because-hypothesis-already-has-wing",
        room="ignored",
    )
    assert result is hypothesis


def test_manual_proposer_with_strings_builds_hypothesis_per_call() -> None:
    proposer = ManualProposer(
        claim="sqlite-vec is embedded",
        predicted_outcome="no network during search",
    )
    first = proposer.propose(
        question="q1", wing="cairntir", room="predictions"
    )
    second = proposer.propose(question="q2", wing="stars-2026", room="notes")
    assert first.claim == "sqlite-vec is embedded"
    assert first.wing == "cairntir"
    assert second.wing == "stars-2026"
    assert second.claim == first.claim


def test_manual_proposer_requires_hypothesis_or_strings() -> None:
    with pytest.raises(ValueError, match="prebuilt hypothesis or both"):
        ManualProposer()
    with pytest.raises(ValueError, match="prebuilt hypothesis or both"):
        ManualProposer(claim="missing predicted")
