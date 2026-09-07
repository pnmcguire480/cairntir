from __future__ import annotations

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


def contract(**changes):
    parameters = {
        "roadmap_modes": ["implementation", "finalization"],
        "thesis": "Restore complete evidence after an interrupted backup.",
        "issue": "A partial copy must never be advertised as recoverable.",
        "acceptance_criteria": ["Restore all memories, vectors and task history."],
        "test_parameters": ["Disposable databases and actual processes."],
        "non_goals": ["Production writes."],
        "verification_reserve": 25,
        "max_repair_rounds": 2,
        "gate_kind": "offline",
    }
    return FinalizationContract.freeze(**(parameters | changes))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("thesis", " "),
        ("issue", ""),
        ("verification_reserve", 0),
        ("verification_reserve", True),
        ("max_repair_rounds", 3),
        ("max_repair_rounds", False),
        ("gate_kind", "unchecked"),
        ("acceptance_criteria", "not a sequence"),
        ("acceptance_criteria", [""]),
        ("test_parameters", []),
        ("non_goals", [None]),
    ],
)
def test_incomplete_finish_line_cannot_replace_a_valid_contract(field, value):
    frozen = contract()
    with pytest.raises(FinalizationError):
        contract(**{field: value})
    assert contract() == frozen
    assert frozen.acceptance_criteria == ("Restore all memories, vectors and task history.",)


@pytest.mark.parametrize(
    ("tester", "artifacts"),
    [
        (" ", {"tests/restore.py": b"original assertions"}),
        ("tester", {}),
        ("tester", {"tests/restore.py": "unencoded content"}),
        ("tester", {"../restore.py": b"outside"}),
        ("tester", {"tests/../restore.py": b"ambiguous path"}),
    ],
)
def test_invalid_acceptance_inventory_cannot_count_as_frozen_evidence(tester, artifacts):
    with pytest.raises(FinalizationError):
        AcceptanceEvidence.freeze(tester_id=tester, artifacts=artifacts)
    valid = AcceptanceEvidence.freeze(
        tester_id="tester", artifacts={"tests/restore.py": b"original assertions"}
    )
    valid.verify({"tests/restore.py": b"original assertions"})
    with pytest.raises(EvidenceMutationError):
        valid.verify({"tests/restore.py": b"assert True"})


def new_run():
    artifacts = {"tests/restore.py": b"original assertions"}
    return FinalizationRun.start(
        contract=contract(),
        evidence=AcceptanceEvidence.freeze(tester_id="tester", artifacts=artifacts),
        coder_id="coder",
        implementation_paths=["src"],
    ), artifacts


@pytest.mark.parametrize(
    "changes",
    [
        {"tester_id": "coder"},
        {"classification": "ignore failure"},
        {"relevant_state_sha256": "unbound result"},
        {"relevant_state_sha256": "A" * 64},
    ],
)
def test_unattributable_pass_cannot_complete_or_consume_verification_state(changes):
    run, artifacts = new_run()
    arguments = {
        "outcome": TestOutcome.PASS,
        "tester_id": "tester",
        "artifacts": artifacts,
        "relevant_state_sha256": "a" * 64,
    }
    with pytest.raises(FinalizationError):
        run.record_result(**(arguments | changes))
    assert run.disposition == Disposition.BLOCKED
    assert run.last_outcome is None and run.repair_rounds_used == 0
    run.record_result(**arguments)
    assert run.disposition == Disposition.COMPLETE


def test_unassigned_coder_cannot_consume_the_repair_budget():
    run, _ = new_run()
    with pytest.raises(FinalizationError, match="assigned coder"):
        run.authorize_repair(coder_id="somebody else")
    assert run.repair_rounds_used == 0
    run.authorize_repair(coder_id="coder")
    assert run.repair_rounds_used == 1


def test_mutated_evidence_cannot_authorize_further_repairs():
    run, _ = new_run()
    with pytest.raises(EvidenceMutationError):
        run.record_result(
            outcome=TestOutcome.PASS,
            tester_id="tester",
            artifacts={"tests/restore.py": b"assert True"},
            relevant_state_sha256="a" * 64,
        )
    with pytest.raises(FinalizationError, match="invalidated"):
        run.authorize_repair(coder_id="coder")
    assert run.disposition == Disposition.BLOCKED and run.repair_rounds_used == 0


def test_missing_write_scope_cannot_authorize_unbounded_implementation():
    run, _ = new_run()
    with pytest.raises(FinalizationError, match="write scope"):
        FinalizationRun.start(
            contract=run.contract,
            evidence=run.evidence,
            coder_id="coder",
            implementation_paths=[],
        )
