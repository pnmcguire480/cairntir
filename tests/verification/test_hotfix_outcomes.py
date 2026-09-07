from __future__ import annotations

import json
from copy import deepcopy

import pytest

from cairntir.errors import HotfixError
from cairntir.hotfix import HotfixAction, HotfixCommand, HotfixCoordinator, HotfixState
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer


@pytest.fixture()
def workflow(tmp_cairntir_home):
    with DrawerStore(tmp_cairntir_home / "hotfix.db", HashEmbeddingProvider(dimension=32)) as store:
        evidence = store.add(Drawer(wing="repair", room="evidence", content="Observed failure."))
        cited = [evidence.id]
        coordinator = HotfixCoordinator(store)
        payloads = {
            "open": {
                "title": "Repair retrieval",
                "stage": "recall",
                "symptom": "missing result",
                "acceptance": ["retrieval works"],
                "evidence_ids": cited,
            },
            "recommend": {
                "candidates": [
                    {
                        "id": "fix",
                        "summary": "restore the missing result",
                        "evidence_ids": cited,
                        "state_change": "query corrected",
                        "reversible": True,
                        "risk": "low",
                    }
                ]
            },
            "authorize": {
                "authority_id": "AUTH-1",
                "sequence": 1,
                "previous_sequence": None,
                "candidate_id": "fix",
                "candidate_hash": "a" * 64,
                "plan_hash": "b" * 64,
                "toolchain_hash": "c" * 64,
                "target": "disposable checkout",
                "executor": "author",
                "capabilities": ["repair"],
                "allowed_actions": ["repair"],
                "prohibited_actions": ["publish"],
                "required_checks": ["scope"],
                "evidence_ids": cited,
            },
            "preflight": {
                "inspector": "tester",
                "observed_bindings": {
                    "candidate_hash": "a" * 64,
                    "plan_hash": "b" * 64,
                    "toolchain_hash": "c" * 64,
                    "target": "disposable checkout",
                },
                "capabilities": ["repair"],
                "observed_state_hash": "d" * 64,
                "checks": {"scope": {"passed": True, "detail": "isolated", "evidence_ids": cited}},
            },
            "record_attempt": {
                "executor": "author",
                "executed_actions": ["repair"],
                "state_hash_before": "d" * 64,
                "state_hash_after": "e" * 64,
                "outcome": "pass",
                "summary": "retrieval corrected",
                "evidence_ids": cited,
                "rollback_ref": "before-repair",
            },
            "verify": {
                "verifier": "tester",
                "observed_state_hash": "e" * 64,
                "results": {
                    "retrieval works": {
                        "verdict": "pass",
                        "detail": "restored",
                        "evidence_ids": cited,
                    }
                },
            },
            "settle": {
                "disposition": "complete",
                "observed_outcome": "retrieval verified",
                "resolution": "query corrected",
                "evidence_ids": cited,
            },
        }
        receipts = []

        def command_for(action):
            return HotfixCommand(
                action=HotfixAction(action),
                wing="repair",
                payload=deepcopy(payloads[action]),
                case_id=receipts[0].case_id if receipts else None,
                idempotency_key=f"workflow-{action}",
            )

        def advance_to(action):
            for preceding in payloads:
                if preceding == action:
                    break
                receipt = coordinator.run(command_for(preceding))
                receipts.append(receipt)
                if preceding == "authorize":
                    for dependent in ("preflight", "record_attempt", "verify"):
                        payloads[dependent]["authority_hash"] = receipt.data["authority_hash"]
            return command_for(action)

        yield store, coordinator, advance_to, receipts


INVALID = [
    ("open", "title", ""),
    ("open", "acceptance", []),
    ("open", "acceptance", [""]),
    ("open", "non_goals", "none"),
    ("open", "failure_class", " "),
    ("open", "max_attempts", True),
    ("open", "max_attempts", 3),
    ("open", "evidence_ids", [0]),
    ("open", "evidence_ids", [True]),
    ("open", "evidence_ids", [9999]),
    ("recommend", "candidates", []),
    ("recommend", "candidates", "fix"),
    ("recommend", "candidates", [1]),
    ("recommend", "candidates.0.id", ""),
    ("recommend", "candidates.0.summary", ""),
    ("recommend", "candidates.0.state_change", ""),
    ("recommend", "candidates.0.evidence_ids", []),
    ("recommend", "candidates.0.reversible", "yes"),
    ("recommend", "candidates.0.risk", "none"),
    ("recommend", "candidates.0.precedent_case_ids", ["missing-case"]),
    ("authorize", "candidate_id", "unselected"),
    ("authorize", "sequence", 0),
    ("authorize", "sequence", True),
    ("authorize", "previous_sequence", 8),
    ("authorize", "candidate_hash", "z" * 64),
    ("authorize", "plan_hash", "b" * 63),
    ("authorize", "capabilities", []),
    ("authorize", "prohibited_actions", ["REPAIR"]),
    ("authorize", "evidence_ids", []),
    ("authorize", "evidence_ids", [9999]),
    ("preflight", "authority_hash", "f" * 64),
    ("preflight", "inspector", "AUTHOR"),
    ("preflight", "observed_bindings", []),
    ("preflight", "observed_bindings", {}),
    ("preflight", "capabilities", ["publish"]),
    ("preflight", "checks", []),
    ("preflight", "checks", {}),
    ("preflight", "checks.scope", "passed"),
    ("preflight", "checks.scope.passed", False),
    ("preflight", "checks.scope.evidence_ids", []),
    ("record_attempt", "executor", "other"),
    ("record_attempt", "executed_actions", ["publish"]),
    ("record_attempt", "state_hash_before", "f" * 64),
    ("record_attempt", "outcome", "success"),
    ("record_attempt", "rollback_ref", ""),
    ("record_attempt", "artifacts", {}),
    ("record_attempt", "artifacts", ["log"]),
    ("record_attempt", "artifacts", [{"name": ""}]),
    ("record_attempt", "artifacts", [{"name": "log", "sha256": "invalid"}]),
    ("record_attempt", "artifacts", [{"name": "log", "sha256": "a" * 64}] * 2),
    ("verify", "verifier", "AUTHOR"),
    ("verify", "observed_state_hash", "f" * 64),
    ("verify", "results", []),
    ("verify", "results", {}),
    ("verify", "results.retrieval works", True),
    ("verify", "results.retrieval works.verdict", "success"),
    ("verify", "results.retrieval works.evidence_ids", []),
    ("settle", "disposition", "unknown"),
    ("settle", "disposition", "open"),
    ("settle", "resolution", ""),
    ("settle", "resolution", None),
    ("settle", "delta", ""),
    ("settle", "evidence_ids", []),
]


def ledger(store):
    return [
        (row.id, row.content, row.metadata, row.supersedes_id)
        for row in store.list_by(wing="repair", room="hotfix-ledger", limit=None)
    ]


@pytest.mark.parametrize(("action", "field", "value"), INVALID)
def test_invalid_transition_cannot_advance_the_ledger_or_consume_its_retry(
    workflow, action, field, value
):
    store, coordinator, advance_to, receipts = workflow
    valid = advance_to(action)
    payload = deepcopy(valid.payload)
    parts = field.split(".")
    target = payload
    for part in parts[:-1]:
        target = target[int(part)] if isinstance(target, list) else target[part]
    target[parts[-1]] = value
    bad = HotfixCommand(valid.action, valid.wing, payload, valid.case_id, valid.idempotency_key)
    before = ledger(store)
    assert bool(before) == bool(receipts)
    with pytest.raises(HotfixError):
        coordinator.run(bad)
    assert ledger(store) == before
    assert store.workflow_receipt(f"hotfix:{valid.idempotency_key}") is None
    accepted = coordinator.run(valid)
    assert not accepted.replayed and accepted.event_drawer_id is not None
    assert len(ledger(store)) == len(before) + 1
    replayed = coordinator.run(valid)
    assert replayed.replayed and replayed.event_drawer_id == accepted.event_drawer_id
    assert len(ledger(store)) == len(before) + 1


@pytest.mark.parametrize("field", ["kind", "state", "payload", "previous_event_hash", "event_hash"])
def test_damaged_durable_hotfix_event_is_reported_without_repairing_or_advancing_it(
    workflow, field
):
    store, coordinator, advance_to, receipts = workflow
    advance_to("recommend")
    row = store.list_by(wing="repair", room="hotfix-ledger", limit=None)[0]
    metadata = dict(row.metadata)
    metadata[field] = "damaged"
    store._conn.execute("UPDATE drawers SET metadata=? WHERE id=?", (json.dumps(metadata), row.id))
    store._conn.commit()
    before = ledger(store)
    with pytest.raises(HotfixError):
        coordinator.run(HotfixCommand(HotfixAction.STATUS, "repair", {}, receipts[0].case_id))
    assert ledger(store) == before


def test_full_valid_hotfix_has_complete_acceptance_and_terminal_receipt(workflow):
    store, coordinator, advance_to, _ = workflow
    settled = coordinator.run(advance_to("settle"))
    assert settled.state is HotfixState.COMPLETE
    assert settled.legal_actions == ()
    assert len(ledger(store)) == 7
    status = coordinator.run(HotfixCommand(HotfixAction.STATUS, "repair", {}, settled.case_id))
    assert status.state is HotfixState.COMPLETE
    assert "Acceptance: 1/1" in status.card
    originals = [metadata for _, _, metadata, _ in ledger(store) if metadata["kind"] == "open"]
    assert len(originals) == 1
    assert originals[0]["payload"]["acceptance"] == ["retrieval works"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("authority_hash", "f" * 64),
        ("rollback_executor", "other"),
        ("verifier", "AUTHOR"),
        ("rollback_ref", "different-snapshot"),
        ("observed_state_hash", "f" * 64),
        ("summary", ""),
        ("evidence_ids", []),
    ],
)
def test_invalid_rollback_cannot_claim_recovery_of_another_state(workflow, field, value):
    store, coordinator, advance_to, receipts = workflow
    advance_to("verify")
    valid = {
        "authority_hash": receipts[2].data["authority_hash"],
        "rollback_executor": "author",
        "verifier": "tester",
        "rollback_ref": "before-repair",
        "observed_state_hash": "d" * 64,
        "summary": "exact pre-attempt state restored",
        "evidence_ids": [1],
    }
    bad = valid | {field: value}
    before = ledger(store)
    with pytest.raises(HotfixError):
        coordinator.run(
            HotfixCommand(
                HotfixAction.ROLLBACK, "repair", bad, receipts[0].case_id, "rollback-retry"
            )
        )
    assert ledger(store) == before
    result = coordinator.run(
        HotfixCommand(HotfixAction.ROLLBACK, "repair", valid, receipts[0].case_id, "rollback-retry")
    )
    assert result.state is HotfixState.ROLLED_BACK
    assert result.data["restored_state_hash"] == "d" * 64
    assert len(ledger(store)) == len(before) + 1


def test_attempt_artifact_hashes_survive_receipt_and_replay(workflow):
    store, coordinator, advance_to, _ = workflow
    command = advance_to("record_attempt")
    command.payload["artifacts"] = [{"name": "regression-results.xml", "sha256": "a" * 64}]
    result = coordinator.run(command)
    artifact_rows = [
        metadata for _, _, metadata, _ in ledger(store) if metadata["kind"] == "record_attempt"
    ]
    assert len(artifact_rows) == 1
    assert artifact_rows[0]["payload"]["artifacts"] == command.payload["artifacts"]
    replay = coordinator.run(command)
    assert replay.replayed and replay.event_drawer_id == result.event_drawer_id
