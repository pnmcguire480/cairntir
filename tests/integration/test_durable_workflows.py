"""Production-adapter continuity tests for atomic Reason and recipe workflows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from cairntir.learning import list_discoveries
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.production.adapters import StoreBackedBeliefs, StoreBackedMemory
from cairntir.reason.loop import ReasonLoop
from cairntir.reason.model import Experiment, Hypothesis, Outcome
from cairntir.recipes.contract import RecipeContract
from cairntir.recipes.runner import RecipeRunner


@dataclass
class _Proposer:
    calls: int = 0

    def propose(self, *, question: str, wing: str, room: str) -> Hypothesis:
        self.calls += 1
        return Hypothesis(
            claim=f"{question} is testable",
            predicted_outcome="the operation completes",
            wing=wing,
            room=room,
        )


@dataclass
class _Runner:
    fail: bool = False
    calls: int = 0

    def run(self, hypothesis: Hypothesis) -> Outcome:
        self.calls += 1
        if self.fail:
            raise RuntimeError("simulated runner crash")
        return Outcome(
            experiment=Experiment(hypothesis=hypothesis, description="test"),
            observed="the operation completes",
            success=True,
        )


def _store(tmp_path: Path) -> DrawerStore:
    return DrawerStore(tmp_path / "workflow.db", HashEmbeddingProvider(dimension=32))


def test_reason_production_adapter_rolls_back_incomplete_step(tmp_path: Path) -> None:
    with _store(tmp_path) as store:
        loop = ReasonLoop(
            proposer=_Proposer(),
            runner=_Runner(fail=True),
            memory=StoreBackedMemory(store),
            beliefs=StoreBackedBeliefs(store),
        )
        with pytest.raises(RuntimeError, match="runner crash"):
            loop.step(question="atomic?", wing="cairntir", room="reason")

        assert store.list_by() == []


def test_reason_retry_replays_ids_without_rerunning_adapters(tmp_path: Path) -> None:
    with _store(tmp_path) as store:
        proposer = _Proposer()
        runner = _Runner()
        loop = ReasonLoop(
            proposer=proposer,
            runner=runner,
            memory=StoreBackedMemory(store),
            beliefs=StoreBackedBeliefs(store),
        )
        first = loop.step(
            question="idempotent?",
            wing="cairntir",
            room="reason",
            idempotency_key="reason:continuity",
        )
        replay = loop.step(
            question="idempotent?",
            wing="cairntir",
            room="reason",
            idempotency_key="reason:continuity",
        )

        assert replay == first
        assert proposer.calls == 1
        assert runner.calls == 1
        assert len(store.list_by()) == 2


def test_recipe_is_atomic_and_idempotent_across_all_drawers(tmp_path: Path) -> None:
    contract = RecipeContract(
        name="durable-reason",
        description="prove recipe durability",
        version="1",
        output_wing="cairntir",
        skills=("reason",),
        inputs=(),
    )
    with _store(tmp_path) as store:
        proposer = _Proposer()
        runner = _Runner()
        recipe = RecipeRunner(
            proposer=proposer,
            runner=runner,
            memory=StoreBackedMemory(store),
            beliefs=StoreBackedBeliefs(store),
        )
        first = recipe.run(contract, {}, idempotency_key="recipe:continuity")
        replay = recipe.run(contract, {}, idempotency_key="recipe:continuity")

        assert replay == first
        assert proposer.calls == 1
        assert runner.calls == 1
        assert len(store.list_by()) == 4


def test_recipe_failure_rolls_back_seed_and_prediction(tmp_path: Path) -> None:
    contract = RecipeContract(
        name="durable-reason",
        description="prove recipe rollback",
        version="1",
        output_wing="cairntir",
        skills=("reason",),
        inputs=(),
    )
    with _store(tmp_path) as store:
        recipe = RecipeRunner(
            proposer=_Proposer(),
            runner=_Runner(fail=True),
            memory=StoreBackedMemory(store),
            beliefs=StoreBackedBeliefs(store),
        )
        with pytest.raises(RuntimeError, match="runner crash"):
            recipe.run(contract, {}, idempotency_key="recipe:failure")

        assert store.list_by() == []


def test_reason_automatically_surfaces_repeated_episode_pattern(tmp_path: Path) -> None:
    with _store(tmp_path) as store:
        loop = ReasonLoop(
            proposer=_Proposer(),
            runner=_Runner(),
            memory=StoreBackedMemory(store),
            beliefs=StoreBackedBeliefs(store),
        )
        for _ in range(3):
            loop.step(question="same repeatable claim", wing="cairntir", room="reason")

        discoveries = list_discoveries(store, wing="cairntir")
        assert len(discoveries) == 1
        assert discoveries[0].state == "candidate"
        assert discoveries[0].observation_count == 3
        assert discoveries[0].confidence == pytest.approx(1.0)
