from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from cairntir.finalization import (
    AcceptanceEvidence,
    Disposition,
    EvidenceMutationError,
    FinalizationContract,
    FinalizationError,
    FinalizationRun,
    TestOutcome,
)

TESTER_ID = "acceptance-agent"
CODER_ID = "implementation-agent"
TEST_PATH = "tests/unit/test_finalization_mode.py"
TEST_BYTES = b"independent acceptance suite v1"


def _contract(
    *,
    gate_kind: str = "offline",
    max_repair_rounds: int = 2,
) -> FinalizationContract:
    return FinalizationContract.freeze(
        roadmap_modes=("discovery", "implementation", "finalization"),
        thesis="A mutable grader can be optimized instead of the user's outcome.",
        issue="Coder-mutable tests enable weakening and unbounded testing loops.",
        acceptance_criteria=(
            "independent acceptance evidence is required",
            "test mutation invalidates the run",
        ),
        test_parameters=("focused pytest suite", "hash-bound artifacts"),
        non_goals=("rebaseline tests during repair",),
        verification_reserve=1_000,
        max_repair_rounds=max_repair_rounds,
        gate_kind=gate_kind,
    )


def _evidence() -> AcceptanceEvidence:
    return AcceptanceEvidence.freeze(
        tester_id=TESTER_ID,
        artifacts={TEST_PATH: TEST_BYTES},
    )


def _run(
    *,
    gate_kind: str = "offline",
    max_repair_rounds: int = 2,
) -> FinalizationRun:
    return FinalizationRun.start(
        contract=_contract(
            gate_kind=gate_kind,
            max_repair_rounds=max_repair_rounds,
        ),
        evidence=_evidence(),
        coder_id=CODER_ID,
        implementation_paths=("src/cairntir/finalization.py",),
    )


def test_finalization_must_be_the_last_roadmap_mode() -> None:
    with pytest.raises(FinalizationError, match=r"last|final"):
        FinalizationContract.freeze(
            roadmap_modes=("finalization", "implementation"),
            thesis="t",
            issue="i",
            acceptance_criteria=("a",),
            test_parameters=("p",),
            non_goals=("n",),
            verification_reserve=1,
            max_repair_rounds=2,
            gate_kind="offline",
        )


def test_freeze_copies_every_finish_line_field() -> None:
    criteria = ["atomic criterion"]
    parameters = ["frozen parameter"]
    non_goals = ["out of scope"]
    contract = FinalizationContract.freeze(
        roadmap_modes=["implementation", "finalization"],
        thesis="thesis",
        issue="issue",
        acceptance_criteria=criteria,
        test_parameters=parameters,
        non_goals=non_goals,
        verification_reserve=40,
        max_repair_rounds=2,
        gate_kind="offline",
    )
    criteria.append("weakened")
    parameters.clear()
    non_goals.clear()

    assert (
        contract.roadmap_modes,
        contract.thesis,
        contract.issue,
        contract.acceptance_criteria,
        contract.test_parameters,
        contract.non_goals,
        contract.verification_reserve,
        contract.max_repair_rounds,
    ) == (
        ("implementation", "finalization"),
        "thesis",
        "issue",
        ("atomic criterion",),
        ("frozen parameter",),
        ("out of scope",),
        40,
        2,
    )


def test_frozen_contract_cannot_be_rebaselined() -> None:
    with pytest.raises(FrozenInstanceError):
        _contract().max_repair_rounds = 99


def test_contract_hash_binds_non_goals() -> None:
    original = _contract()
    changed = FinalizationContract.freeze(
        roadmap_modes=original.roadmap_modes,
        thesis=original.thesis,
        issue=original.issue,
        acceptance_criteria=original.acceptance_criteria,
        test_parameters=original.test_parameters,
        non_goals=("different scope",),
        verification_reserve=original.verification_reserve,
        max_repair_rounds=original.max_repair_rounds,
        gate_kind=original.gate_kind,
    )

    assert changed.contract_sha256 != original.contract_sha256


@pytest.mark.parametrize("gate_kind", ["protected", "billed"])
def test_protected_or_billed_contract_rejects_more_than_one_repair(
    gate_kind: str,
) -> None:
    with pytest.raises(FinalizationError, match=r"one|1|repair"):
        _contract(gate_kind=gate_kind, max_repair_rounds=2)


def test_acceptance_evidence_hash_detects_test_mutation() -> None:
    evidence = _evidence()

    with pytest.raises(EvidenceMutationError, match=r"hash|mutat"):
        evidence.verify({TEST_PATH: b"weakened suite"})


def test_coder_and_tester_must_be_distinct_identities() -> None:
    with pytest.raises(FinalizationError, match=r"distinct|identity|tester"):
        FinalizationRun.start(
            contract=_contract(),
            evidence=_evidence(),
            coder_id=TESTER_ID,
            implementation_paths=("src/cairntir/finalization.py",),
        )


def test_test_artifacts_must_be_outside_coder_write_scope() -> None:
    with pytest.raises(FinalizationError, match=r"write|scope|artifact"):
        FinalizationRun.start(
            contract=_contract(),
            evidence=_evidence(),
            coder_id=CODER_ID,
            implementation_paths=(TEST_PATH,),
        )


def test_coder_dispatch_contains_contract_failure_evidence_and_only_owned_paths() -> None:
    run = _run()

    dispatch = run.coder_dispatch(failure_evidence=("assertion 7 failed",))

    assert (
        dispatch.thesis,
        dispatch.issue,
        dispatch.acceptance_criteria,
        dispatch.test_parameters,
        dispatch.test_artifact_hashes,
        dispatch.failure_evidence,
        dispatch.write_paths,
    ) == (
        run.contract.thesis,
        run.contract.issue,
        run.contract.acceptance_criteria,
        run.contract.test_parameters,
        run.evidence.artifact_hashes,
        ("assertion 7 failed",),
        ("src/cairntir/finalization.py",),
    )


def test_mutated_test_artifact_invalidates_the_run() -> None:
    run = _run()

    with pytest.raises(EvidenceMutationError):
        run.record_result(
            outcome=TestOutcome.PASS,
            tester_id=TESTER_ID,
            artifacts={TEST_PATH: b"changed"},
            relevant_state_sha256="a" * 64,
        )

    assert run.invalidated is True


def test_test_mutation_is_not_counted_as_a_repair_attempt() -> None:
    run = _run()

    with pytest.raises(EvidenceMutationError):
        run.record_result(
            outcome=TestOutcome.FAIL,
            tester_id=TESTER_ID,
            artifacts={TEST_PATH: b"changed"},
            relevant_state_sha256="a" * 64,
        )

    assert run.repair_rounds_used == 0


def test_only_independent_pass_can_complete_the_roadmap() -> None:
    run = _run()
    run.record_result(
        outcome=TestOutcome.PASS,
        tester_id=TESTER_ID,
        artifacts={TEST_PATH: TEST_BYTES},
        relevant_state_sha256="a" * 64,
    )

    assert run.disposition is Disposition.COMPLETE


def test_coder_cannot_submit_pass_evidence() -> None:
    run = _run()

    with pytest.raises(FinalizationError, match=r"tester|independent"):
        run.record_result(
            outcome=TestOutcome.PASS,
            tester_id=CODER_ID,
            artifacts={TEST_PATH: TEST_BYTES},
            relevant_state_sha256="a" * 64,
        )


@pytest.mark.parametrize("outcome", [TestOutcome.FAIL, TestOutcome.INCONCLUSIVE])
def test_non_passing_result_blocks_while_repair_budget_remains(
    outcome: TestOutcome,
) -> None:
    run = _run()
    run.record_result(
        outcome=outcome,
        tester_id=TESTER_ID,
        artifacts={TEST_PATH: TEST_BYTES},
        relevant_state_sha256="a" * 64,
    )

    assert run.disposition is Disposition.BLOCKED


def test_offline_run_rejects_a_third_repair_round() -> None:
    run = _run()
    run.authorize_repair(coder_id=CODER_ID)
    run.authorize_repair(coder_id=CODER_ID)

    with pytest.raises(FinalizationError, match=r"exhaust|repair"):
        run.authorize_repair(coder_id=CODER_ID)


def test_protected_run_rejects_a_second_repair_round() -> None:
    run = _run(gate_kind="protected", max_repair_rounds=1)
    run.authorize_repair(coder_id=CODER_ID)

    with pytest.raises(FinalizationError, match=r"exhaust|repair"):
        run.authorize_repair(coder_id=CODER_ID)


def test_failed_result_is_exhausted_after_repair_budget_is_spent() -> None:
    run = _run()
    run.authorize_repair(coder_id=CODER_ID)
    run.authorize_repair(coder_id=CODER_ID)
    run.record_result(
        outcome=TestOutcome.FAIL,
        tester_id=TESTER_ID,
        artifacts={TEST_PATH: TEST_BYTES},
        relevant_state_sha256="a" * 64,
    )

    assert run.disposition is Disposition.EXHAUSTED


def test_identical_rerun_against_identical_state_is_rejected() -> None:
    run = _run()
    result = {
        "outcome": TestOutcome.FAIL,
        "tester_id": TESTER_ID,
        "artifacts": {TEST_PATH: TEST_BYTES},
        "relevant_state_sha256": "a" * 64,
    }
    run.record_result(**result)

    with pytest.raises(FinalizationError, match=r"identical|state|rerun"):
        run.record_result(**result)


@pytest.mark.parametrize("classification", ["transient", "flaky"])
def test_explicitly_transient_or_flaky_rerun_of_same_state_is_allowed(
    classification: str,
) -> None:
    run = _run()
    result = {
        "outcome": TestOutcome.INCONCLUSIVE,
        "tester_id": TESTER_ID,
        "artifacts": {TEST_PATH: TEST_BYTES},
        "relevant_state_sha256": "a" * 64,
    }
    run.record_result(**result)

    run.record_result(**result, classification=classification)

    assert run.last_outcome is TestOutcome.INCONCLUSIVE
