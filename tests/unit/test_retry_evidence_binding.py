"""A retry key must not silently swallow changed manual evidence.

Reported by the independent evaluator against 2.0.0a2: reusing a key with a
changed claim or observation returned the original receipt with exit code 0
and did not save or warn about the new evidence.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cairntir.cli import app
from cairntir.errors import IdempotencyConflictError
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer, Layer
from cairntir.production.adapters import (
    ManualProposer,
    NullRunner,
    StoreBackedBeliefs,
    StoreBackedMemory,
)
from cairntir.reason.loop import ReasonLoop
from cairntir.reason.model import Hypothesis
from cairntir.recipes.contract import RecipeContract
from cairntir.recipes.runner import RecipeRunner

runner = CliRunner()

REASON_FLAGS = {
    "--claim": "original claim",
    "--predicted": "original prediction",
    "--observed": "original observation",
    "--delta": "original delta",
}


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))
    monkeypatch.setattr(
        "cairntir.cli.production_embedding_provider",
        lambda: HashEmbeddingProvider(dimension=384),
    )
    DrawerStore(tmp_path / "cairntir.db", HashEmbeddingProvider(dimension=384)).close()
    return tmp_path


def _flags(values: dict[str, str]) -> list[str]:
    return [item for pair in values.items() for item in pair]


def _reason(*extra: str, key: str = "reason-key", **changes: str) -> object:
    flags = {**REASON_FLAGS, **{f"--{name}": value for name, value in changes.items()}}
    return runner.invoke(
        app,
        [
            "reason",
            "same question",
            "--wing",
            "probe",
            *_flags(flags),
            *(extra or ("--success",)),
            "--idempotency-key",
            key,
        ],
    )


def _recipe(*extra: str, key: str = "recipe-key", **changes: str) -> object:
    flags = {**REASON_FLAGS, **{f"--{name}": value for name, value in changes.items()}}
    return runner.invoke(
        app,
        [
            "recipe-run",
            "decision-replay",
            "--input",
            "decision_drawer_id=1",
            "--input",
            "current_evidence=same evidence",
            *_flags(flags),
            *(extra or ("--success",)),
            "--idempotency-key",
            key,
        ],
    )


def _rows(home: Path) -> list[tuple[object, ...]]:
    connection = sqlite3.connect(home / "cairntir.db")
    try:
        return connection.execute(
            "SELECT id, content, claim, predicted_outcome, observed_outcome, delta "
            "FROM drawers ORDER BY id"
        ).fetchall()
    finally:
        connection.close()


@pytest.mark.parametrize(
    "changes",
    [
        {"claim": "changed claim"},
        {"predicted": "changed prediction"},
        {"observed": "changed observation"},
        {"delta": "changed delta"},
    ],
    ids=["claim", "prediction", "observation", "delta"],
)
@pytest.mark.parametrize("command", [_reason, _recipe], ids=["reason", "recipe"])
def test_changed_evidence_under_a_used_key_conflicts_and_saves_nothing(
    home: Path, command: object, changes: dict[str, str]
) -> None:
    first = command()  # type: ignore[operator]
    assert first.exit_code == 0, first.output
    before = _rows(home)

    retry = command(**changes)  # type: ignore[operator]

    assert retry.exit_code != 0, retry.output
    assert isinstance(retry.exception, IdempotencyConflictError)
    assert _rows(home) == before


@pytest.mark.parametrize("command", [_reason, _recipe], ids=["reason", "recipe"])
def test_changed_verdict_under_a_used_key_conflicts_and_saves_nothing(
    home: Path, command: object
) -> None:
    first = command()  # type: ignore[operator]
    assert first.exit_code == 0, first.output
    before = _rows(home)

    retry = command("--fail")  # type: ignore[operator]

    assert retry.exit_code != 0, retry.output
    assert isinstance(retry.exception, IdempotencyConflictError)
    assert _rows(home) == before


@pytest.mark.parametrize("command", [_reason, _recipe], ids=["reason", "recipe"])
def test_exact_retry_still_replays_without_new_records(home: Path, command: object) -> None:
    first = command()  # type: ignore[operator]
    assert first.exit_code == 0, first.output
    before = _rows(home)

    retry = command()  # type: ignore[operator]

    assert retry.exit_code == 0, retry.output
    assert retry.output == first.output
    assert _rows(home) == before


def _replay(decision_id: int, *extra: str, observed: str = "original observation") -> object:
    return runner.invoke(
        app,
        [
            "replay",
            str(decision_id),
            "--evidence",
            "same evidence",
            "--observed",
            observed,
            *(extra or ("--success",)),
            "--idempotency-key",
            "replay-key",
        ],
    )


def _decision(home: Path) -> int:
    store = DrawerStore(home / "cairntir.db", HashEmbeddingProvider(dimension=384))
    try:
        drawer = store.add(
            Drawer(
                wing="probe",
                room="journey",
                content="a past decision",
                layer=Layer.ESSENTIAL,
                claim="the decision holds",
                predicted_outcome="it keeps working",
            )
        )
    finally:
        store.close()
    assert drawer.id is not None
    return drawer.id


def test_replay_exact_retry_replays_without_new_records(home: Path) -> None:
    decision = _decision(home)
    first = _replay(decision)
    assert first.exit_code == 0, first.output
    before = _rows(home)

    retry = _replay(decision)

    assert retry.exit_code == 0, retry.output
    assert _rows(home) == before


def test_replay_changed_observation_conflicts_and_saves_nothing(home: Path) -> None:
    decision = _decision(home)
    first = _replay(decision)
    assert first.exit_code == 0, first.output
    before = _rows(home)

    retry = _replay(decision, observed="changed observation")

    assert retry.exit_code != 0, retry.output
    assert isinstance(retry.exception, IdempotencyConflictError)
    assert _rows(home) == before


def _store(tmp_path: Path) -> DrawerStore:
    return DrawerStore(tmp_path / "workflow.db", HashEmbeddingProvider(dimension=32))


def _loop(store: DrawerStore, *, observed: str = "seen") -> ReasonLoop:
    return ReasonLoop(
        proposer=ManualProposer(claim="claim", predicted_outcome="predicted"),
        runner=NullRunner(observed=observed, success=True),
        memory=StoreBackedMemory(store),
        beliefs=StoreBackedBeliefs(store),
    )


def test_changed_prebuilt_hypothesis_conflicts(tmp_path: Path) -> None:
    def loop(store: DrawerStore, claim: str) -> ReasonLoop:
        return ReasonLoop(
            proposer=ManualProposer(
                Hypothesis(claim=claim, predicted_outcome="same", wing="probe", room="reason")
            ),
            runner=NullRunner(observed="seen", success=True),
            memory=StoreBackedMemory(store),
            beliefs=StoreBackedBeliefs(store),
        )

    with _store(tmp_path) as store:
        step = {"question": "q", "wing": "probe", "room": "reason", "idempotency_key": "key"}
        first = loop(store, "one").step(**step)

        assert loop(store, "one").step(**step) == first
        with pytest.raises(IdempotencyConflictError):
            loop(store, "two").step(**step)


def test_generating_proposer_that_declares_no_evidence_replays_on_the_question(
    tmp_path: Path,
) -> None:
    class DraftingProposer:
        drafts = 0

        def propose(self, *, question: str, wing: str, room: str) -> Hypothesis:
            DraftingProposer.drafts += 1
            return Hypothesis(
                claim=f"draft {DraftingProposer.drafts} of {question}",
                predicted_outcome="it holds",
                wing=wing,
                room=room,
            )

    with _store(tmp_path) as store:
        loop = ReasonLoop(
            proposer=DraftingProposer(),
            runner=NullRunner(observed="seen", success=True),
            memory=StoreBackedMemory(store),
            beliefs=StoreBackedBeliefs(store),
        )
        step = {"question": "q", "wing": "probe", "room": "reason", "idempotency_key": "key"}

        assert loop.step(**step) == loop.step(**step)
        assert DraftingProposer.drafts == 1


LEGACY_REQUEST = {"question": "q", "wing": "probe", "room": "reason", "supersedes_id": None}


def test_key_committed_before_the_fix_still_replays_on_exact_retry(tmp_path: Path) -> None:
    with _store(tmp_path) as store:
        recorded = {
            "prediction_id": 7,
            "observation_id": 8,
            "mass_change": 1.0,
            "delta": "",
        }
        store.execute_once(
            idempotency_key="old-key",
            operation="reason.step",
            request=LEGACY_REQUEST,
            action=lambda: recorded,
        )
        before = store.workflow_receipt("old-key")

        update = _loop(store).step(
            question="q", wing="probe", room="reason", idempotency_key="old-key"
        )

        assert (update.prediction_id, update.observation_id) == (7, 8)
        assert store.list_by() == []
        assert store.workflow_receipt("old-key") == before


def test_interrupted_key_from_before_the_fix_binds_to_the_evidence_that_finishes_it(
    tmp_path: Path,
) -> None:
    with _store(tmp_path) as store:
        with pytest.raises(RuntimeError, match="interrupted"):
            store.execute_once(
                idempotency_key="old-key",
                operation="reason.step",
                request=LEGACY_REQUEST,
                action=_raise_interrupted,
            )

        finished = _loop(store).step(
            question="q", wing="probe", room="reason", idempotency_key="old-key"
        )
        assert len(store.list_by()) == 2

        with pytest.raises(IdempotencyConflictError):
            _loop(store, observed="different").step(
                question="q", wing="probe", room="reason", idempotency_key="old-key"
            )

        again = _loop(store).step(
            question="q", wing="probe", room="reason", idempotency_key="old-key"
        )
        assert again == finished
        assert len(store.list_by()) == 2


def _raise_interrupted() -> dict[str, object]:
    raise RuntimeError("interrupted")


def test_recipe_without_reason_ignores_adapters_it_never_uses(tmp_path: Path) -> None:
    contract = RecipeContract(
        name="marker-only",
        description="writes only a crucible marker",
        version="1",
        output_wing="probe",
        skills=("crucible",),
        inputs=(),
    )
    with _store(tmp_path) as store:

        def recipe(observed: str) -> RecipeRunner:
            return RecipeRunner(
                proposer=ManualProposer(claim="(no claim)", predicted_outcome="(none)"),
                runner=NullRunner(observed=observed, success=True),
                memory=StoreBackedMemory(store),
                beliefs=StoreBackedBeliefs(store),
            )

        first = recipe("one").run(contract, {}, idempotency_key="marker-key")
        retry = recipe("two").run(contract, {}, idempotency_key="marker-key")

        assert retry == first
