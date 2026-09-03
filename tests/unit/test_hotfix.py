from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from cairntir.errors import HotfixError
from cairntir.hotfix import HotfixAction, HotfixCommand, HotfixCoordinator, HotfixReceipt
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer


def _coordinator(tmp_path: Path) -> HotfixCoordinator:
    return HotfixCoordinator(_store(tmp_path))


def _store(tmp_path: Path) -> DrawerStore:
    return DrawerStore(tmp_path / "hotfix.db", HashEmbeddingProvider(dimension=32))


def _evidence(store: DrawerStore, content: str) -> int:
    saved = store.add(Drawer(wing="cairntir", room="evidence", content=content))
    assert saved.id is not None
    return saved.id


def _open_and_recommend(
    coordinator: HotfixCoordinator,
    evidence_id: int,
    *,
    suffix: str,
    max_attempts: int = 2,
) -> tuple[HotfixReceipt, HotfixReceipt]:
    opened = coordinator.run(
        HotfixCommand(
            action=HotfixAction.OPEN,
            wing="cairntir",
            payload={
                "title": f"bounded repair {suffix}",
                "stage": "a4",
                "symptom": "protected smoke assertion failed",
                "acceptance": ["bounded smoke passes"],
                "evidence_ids": [evidence_id],
                "max_attempts": max_attempts,
            },
            idempotency_key=f"open-{suffix}",
        )
    )
    recommended = coordinator.run(
        HotfixCommand(
            action=HotfixAction.RECOMMEND,
            wing="cairntir",
            case_id=opened.case_id,
            payload={
                "candidates": [
                    {
                        "id": "repair",
                        "summary": "repair the observed defect",
                        "evidence_ids": [evidence_id],
                        "state_change": "candidate digest changes",
                        "reversible": True,
                        "risk": "low",
                    }
                ]
            },
            idempotency_key=f"recommend-{suffix}",
        )
    )
    return opened, recommended


def _authorize(
    coordinator: HotfixCoordinator,
    opened: HotfixReceipt,
    evidence_id: int,
    *,
    suffix: str,
    sequence: int,
    previous_sequence: int | None,
) -> HotfixReceipt:
    return coordinator.run(
        HotfixCommand(
            action=HotfixAction.AUTHORIZE,
            wing="cairntir",
            case_id=opened.case_id,
            payload={
                "authority_id": f"AUTH-{suffix}-{sequence}",
                "sequence": sequence,
                "previous_sequence": previous_sequence,
                "candidate_id": "repair",
                "candidate_hash": "a" * 64,
                "plan_hash": "b" * 64,
                "toolchain_hash": "c" * 64,
                "target": "clone/cache-only/a4",
                "executor": "codex",
                "capabilities": ["repair", "smoke"],
                "allowed_actions": ["repair", "smoke"],
                "prohibited_actions": ["live-mutation"],
                "required_checks": ["binding", "containment"],
                "evidence_ids": [evidence_id],
            },
            idempotency_key=f"authorize-{suffix}-{sequence}",
        )
    )


def _preflight(
    coordinator: HotfixCoordinator,
    opened: HotfixReceipt,
    authorized: HotfixReceipt,
    evidence_id: int,
    *,
    suffix: str,
    state_hash: str,
) -> HotfixReceipt:
    return coordinator.run(
        HotfixCommand(
            action=HotfixAction.PREFLIGHT,
            wing="cairntir",
            case_id=opened.case_id,
            payload={
                "authority_hash": authorized.data["authority_hash"],
                "inspector": "opus5",
                "observed_bindings": {
                    "candidate_hash": "a" * 64,
                    "plan_hash": "b" * 64,
                    "toolchain_hash": "c" * 64,
                    "target": "clone/cache-only/a4",
                },
                "capabilities": ["repair", "smoke"],
                "observed_state_hash": state_hash,
                "checks": {
                    name: {
                        "passed": True,
                        "detail": f"{name} passed",
                        "evidence_ids": [evidence_id],
                    }
                    for name in ("binding", "containment")
                },
            },
            idempotency_key=f"preflight-{suffix}",
        )
    )


def _attempt(
    coordinator: HotfixCoordinator,
    opened: HotfixReceipt,
    authorized: HotfixReceipt,
    evidence_id: int,
    *,
    suffix: str,
    before: str,
    after: str,
    outcome: str,
) -> HotfixReceipt:
    return coordinator.run(
        HotfixCommand(
            action=HotfixAction.RECORD_ATTEMPT,
            wing="cairntir",
            case_id=opened.case_id,
            payload={
                "authority_hash": authorized.data["authority_hash"],
                "executor": "codex",
                "executed_actions": ["repair", "smoke"],
                "state_hash_before": before,
                "state_hash_after": after,
                "outcome": outcome,
                "summary": f"attempt ended {outcome}",
                "evidence_ids": [evidence_id],
                "artifacts": [],
                "rollback_ref": f"rollback-{before[:8]}",
            },
            idempotency_key=f"attempt-{suffix}",
        )
    )


def _verify(
    coordinator: HotfixCoordinator,
    opened: HotfixReceipt,
    authorized: HotfixReceipt,
    evidence_id: int,
    *,
    suffix: str,
    state_hash: str,
    verdict: str,
) -> HotfixReceipt:
    return coordinator.run(
        HotfixCommand(
            action=HotfixAction.VERIFY,
            wing="cairntir",
            case_id=opened.case_id,
            payload={
                "authority_hash": authorized.data["authority_hash"],
                "verifier": "cursor",
                "observed_state_hash": state_hash,
                "results": {
                    "bounded smoke passes": {
                        "verdict": verdict,
                        "detail": f"independent {verdict}",
                        "evidence_ids": [evidence_id],
                    }
                },
            },
            idempotency_key=f"verify-{suffix}",
        )
    )


def _rollback(
    coordinator: HotfixCoordinator,
    opened: HotfixReceipt,
    authorized: HotfixReceipt,
    evidence_id: int,
    *,
    suffix: str,
    restored: str,
) -> HotfixReceipt:
    return coordinator.run(
        HotfixCommand(
            action=HotfixAction.ROLLBACK,
            wing="cairntir",
            case_id=opened.case_id,
            payload={
                "authority_hash": authorized.data["authority_hash"],
                "rollback_executor": "codex",
                "verifier": "cursor",
                "rollback_ref": f"rollback-{restored[:8]}",
                "observed_state_hash": restored,
                "summary": "pre-attempt state restored and independently observed",
                "evidence_ids": [evidence_id],
            },
            idempotency_key=f"rollback-{suffix}",
        )
    )


def test_same_failure_produces_one_stable_fingerprint(tmp_path: Path) -> None:
    coordinator = _coordinator(tmp_path)
    common = {
        "title": "protected broker smoke failed",
        "stage": "a4-smoke",
        "acceptance": ["protected ACL passes", "worker has zero capabilities"],
        "non_goals": ["live-product mutation"],
    }

    first = coordinator.run(
        HotfixCommand(
            action=HotfixAction.OPEN,
            wing="cairntir",
            payload={
                **common,
                "symptom": "Access denied at C:\\Temp\\stage-16\\permit-a1b2c3d4.json",
            },
            idempotency_key="open-16",
        )
    )
    second = coordinator.run(
        HotfixCommand(
            action=HotfixAction.OPEN,
            wing="cairntir",
            payload={
                **common,
                "symptom": "Access denied at C:\\Temp\\stage-17\\permit-deadbeef.json",
            },
            idempotency_key="open-17",
        )
    )

    assert first.case_id != second.case_id
    assert first.fingerprint == second.fingerprint
    assert first.failure_class == "permission"
    assert second.failure_class == "permission"


def test_open_replays_without_duplicates_and_status_is_read_only(tmp_path: Path) -> None:
    coordinator = _coordinator(tmp_path)
    command = HotfixCommand(
        action=HotfixAction.OPEN,
        wing="cairntir",
        payload={
            "title": "cache smoke",
            "stage": "a4",
            "symptom": "timeout after 1860 seconds",
            "acceptance": ["smoke passes"],
        },
        idempotency_key="open-cache-smoke",
    )

    first = coordinator.run(command)
    replay = coordinator.run(command)
    status = coordinator.run(
        HotfixCommand(
            action=HotfixAction.STATUS,
            wing="cairntir",
            case_id=first.case_id,
            payload={},
        )
    )

    assert replay.replayed is True
    assert replay.event_drawer_id == first.event_drawer_id
    assert status.state.value == "open"
    assert status.event_drawer_id == first.event_drawer_id
    assert status.next_action == "recommend"
    assert status.legal_actions == ("recommend", "settle")
    assert status.data["attempts"] == 0
    assert status.data["max_attempts"] == 2
    assert status.data["acceptance_passed"] == 0
    assert status.data["acceptance_total"] == 1
    assert "Attempts: 0/2" in status.card


def test_recommendation_ranks_cited_reversible_low_risk_path(tmp_path: Path) -> None:
    store = _store(tmp_path)
    coordinator = HotfixCoordinator(store)
    evidence = store.add(
        Drawer(
            wing="cairntir",
            room="failures",
            content="The ACL repair changed protected broker state before the smoke passed.",
        )
    )
    assert evidence.id is not None
    opened = coordinator.run(
        HotfixCommand(
            action=HotfixAction.OPEN,
            wing="cairntir",
            payload={
                "title": "broker smoke",
                "stage": "a4",
                "symptom": "ACL access denied",
                "acceptance": ["smoke passes"],
                "evidence_ids": [evidence.id],
            },
            idempotency_key="open-broker",
        )
    )

    recommendation = coordinator.run(
        HotfixCommand(
            action=HotfixAction.RECOMMEND,
            wing="cairntir",
            case_id=opened.case_id,
            payload={
                "candidates": [
                    {
                        "id": "blind-retry",
                        "summary": "run the same smoke again",
                        "evidence_ids": [evidence.id],
                        "state_change": "none",
                        "reversible": False,
                        "risk": "high",
                    },
                    {
                        "id": "repair-acl",
                        "summary": "repair and independently inspect the ACL",
                        "evidence_ids": [evidence.id],
                        "state_change": "protected ACL digest changes",
                        "reversible": True,
                        "risk": "low",
                    },
                ]
            },
            idempotency_key="recommend-broker",
        )
    )

    assert recommendation.state.value == "recommended"
    assert recommendation.data["selected_candidate"] == "repair-acl"
    assert recommendation.next_action == "authorize"
    assert "repair-acl" in recommendation.card


def test_authority_preflight_attempt_and_independent_verification_complete(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    coordinator = HotfixCoordinator(store)
    failure_id = _evidence(store, "The protected broker failed before worker bootstrap.")
    preflight_id = _evidence(store, "ACL and zero-capability worker inspected independently.")
    attempt_id = _evidence(store, "Repair and bounded smoke completed in the clone.")
    verify_id = _evidence(store, "Independent acceptance observed both invariants.")
    opened = coordinator.run(
        HotfixCommand(
            action=HotfixAction.OPEN,
            wing="cairntir",
            payload={
                "title": "protected broker repair",
                "stage": "a4",
                "symptom": "SYSTEM-only ACL access denied",
                "acceptance": ["protected ACL passes", "worker has zero capabilities"],
                "non_goals": ["live-product mutation", "a5"],
                "evidence_ids": [failure_id],
            },
            idempotency_key="open-protected-broker",
        )
    )
    recommendation = coordinator.run(
        HotfixCommand(
            action=HotfixAction.RECOMMEND,
            wing="cairntir",
            case_id=opened.case_id,
            payload={
                "candidates": [
                    {
                        "id": "repair-broker",
                        "summary": "repair the broker then run one bounded smoke",
                        "evidence_ids": [failure_id],
                        "state_change": "ACL and bootstrap digests change",
                        "reversible": True,
                        "risk": "low",
                    }
                ]
            },
            idempotency_key="recommend-protected-broker",
        )
    )
    authorized = coordinator.run(
        HotfixCommand(
            action=HotfixAction.AUTHORIZE,
            wing="cairntir",
            case_id=opened.case_id,
            payload={
                "authority_id": "CE-A4-PROTECTED-BROKER-REPAIR-002",
                "sequence": 17,
                "previous_sequence": 16,
                "candidate_id": recommendation.data["selected_candidate"],
                "candidate_hash": "a" * 64,
                "plan_hash": "b" * 64,
                "toolchain_hash": "c" * 64,
                "target": "clone/cache-only/a4",
                "executor": "codex",
                "capabilities": ["acl:repair", "smoke:run"],
                "allowed_actions": ["repair-acl", "run-smoke"],
                "prohibited_actions": ["live-product-mutation", "a5"],
                "required_checks": ["source-frozen", "acl-bound", "worker-zero-capability"],
                "evidence_ids": [failure_id],
            },
            idempotency_key="authorize-protected-broker-17",
        )
    )
    preflight = coordinator.run(
        HotfixCommand(
            action=HotfixAction.PREFLIGHT,
            wing="cairntir",
            case_id=opened.case_id,
            payload={
                "authority_hash": authorized.data["authority_hash"],
                "inspector": "opus5",
                "observed_bindings": {
                    "candidate_hash": "a" * 64,
                    "plan_hash": "b" * 64,
                    "toolchain_hash": "c" * 64,
                    "target": "clone/cache-only/a4",
                },
                "capabilities": ["acl:repair", "smoke:run"],
                "observed_state_hash": "d" * 64,
                "checks": {
                    name: {
                        "passed": True,
                        "detail": f"{name} observed",
                        "evidence_ids": [preflight_id],
                    }
                    for name in ("source-frozen", "acl-bound", "worker-zero-capability")
                },
            },
            idempotency_key="preflight-protected-broker-17",
        )
    )
    attempt = coordinator.run(
        HotfixCommand(
            action=HotfixAction.RECORD_ATTEMPT,
            wing="cairntir",
            case_id=opened.case_id,
            payload={
                "authority_hash": authorized.data["authority_hash"],
                "executor": "codex",
                "executed_actions": ["repair-acl", "run-smoke"],
                "state_hash_before": "d" * 64,
                "state_hash_after": "e" * 64,
                "outcome": "pass",
                "summary": "broker repaired and bounded smoke passed",
                "evidence_ids": [attempt_id],
                "artifacts": [{"name": "smoke-receipt", "sha256": "f" * 64}],
                "rollback_ref": "restore-state-digest-d",
            },
            idempotency_key="attempt-protected-broker-17",
        )
    )
    verified = coordinator.run(
        HotfixCommand(
            action=HotfixAction.VERIFY,
            wing="cairntir",
            case_id=opened.case_id,
            payload={
                "authority_hash": authorized.data["authority_hash"],
                "verifier": "cursor",
                "observed_state_hash": "e" * 64,
                "results": {
                    item: {
                        "verdict": "pass",
                        "detail": f"{item} independently observed",
                        "evidence_ids": [verify_id],
                    }
                    for item in ("protected ACL passes", "worker has zero capabilities")
                },
            },
            idempotency_key="verify-protected-broker-17",
        )
    )
    settled = coordinator.run(
        HotfixCommand(
            action=HotfixAction.SETTLE,
            wing="cairntir",
            case_id=opened.case_id,
            payload={
                "disposition": "complete",
                "observed_outcome": "both acceptance items passed independently",
                "resolution": "repair the bound ACL before one bounded smoke",
                "delta": "worker bootstrap also needed exact zero-capability evidence",
                "evidence_ids": [verify_id],
            },
            idempotency_key="settle-protected-broker-17",
        )
    )
    status = coordinator.run(
        HotfixCommand(
            action=HotfixAction.STATUS,
            wing="cairntir",
            case_id=opened.case_id,
            payload={},
        )
    )

    assert preflight.state.value == "preflighted"
    assert attempt.data["attempt"] == 1
    assert attempt.legal_actions == ("verify", "rollback")
    assert verified.state.value == "verified"
    assert settled.state.value == "complete"
    assert status.state.value == "complete"
    assert status.next_action == "none (terminal)"
    assert status.legal_actions == ()
    assert "Acceptance: 2/2" in status.card


def test_unchanged_failed_state_cannot_be_attempted_again(tmp_path: Path) -> None:
    store = _store(tmp_path)
    coordinator = HotfixCoordinator(store)
    evidence_id = _evidence(store, "The first bounded smoke failed.")
    opened, _ = _open_and_recommend(coordinator, evidence_id, suffix="no-progress")
    first_authority = _authorize(
        coordinator,
        opened,
        evidence_id,
        suffix="no-progress",
        sequence=1,
        previous_sequence=None,
    )
    _preflight(
        coordinator,
        opened,
        first_authority,
        evidence_id,
        suffix="no-progress-1",
        state_hash="1" * 64,
    )
    _attempt(
        coordinator,
        opened,
        first_authority,
        evidence_id,
        suffix="no-progress-1",
        before="1" * 64,
        after="2" * 64,
        outcome="fail",
    )
    failed = _verify(
        coordinator,
        opened,
        first_authority,
        evidence_id,
        suffix="no-progress-1",
        state_hash="2" * 64,
        verdict="fail",
    )
    assert failed.state.value == "repair_required"
    second_authority = _authorize(
        coordinator,
        opened,
        evidence_id,
        suffix="no-progress",
        sequence=2,
        previous_sequence=1,
    )
    _preflight(
        coordinator,
        opened,
        second_authority,
        evidence_id,
        suffix="no-progress-2",
        state_hash="2" * 64,
    )

    with pytest.raises(HotfixError, match="unchanged failed state"):
        _attempt(
            coordinator,
            opened,
            second_authority,
            evidence_id,
            suffix="no-progress-2",
            before="2" * 64,
            after="3" * 64,
            outcome="pass",
        )


def test_preflight_binding_mismatch_writes_no_event(tmp_path: Path) -> None:
    store = _store(tmp_path)
    coordinator = HotfixCoordinator(store)
    evidence_id = _evidence(store, "The candidate bindings were inspected.")
    opened, _ = _open_and_recommend(coordinator, evidence_id, suffix="binding-mismatch")
    authority = _authorize(
        coordinator,
        opened,
        evidence_id,
        suffix="binding-mismatch",
        sequence=1,
        previous_sequence=None,
    )

    with pytest.raises(HotfixError, match="authority binding mismatch"):
        coordinator.run(
            HotfixCommand(
                action=HotfixAction.PREFLIGHT,
                wing="cairntir",
                case_id=opened.case_id,
                payload={
                    "authority_hash": authority.data["authority_hash"],
                    "inspector": "opus5",
                    "observed_bindings": {
                        "candidate_hash": "a" * 64,
                        "plan_hash": "f" * 64,
                        "toolchain_hash": "c" * 64,
                        "target": "clone/cache-only/a4",
                    },
                    "capabilities": ["repair", "smoke"],
                    "observed_state_hash": "1" * 64,
                    "checks": {},
                },
                idempotency_key="preflight-binding-mismatch",
            )
        )

    status = coordinator.run(
        HotfixCommand(
            action=HotfixAction.STATUS,
            wing="cairntir",
            case_id=opened.case_id,
            payload={},
        )
    )
    assert status.state.value == "authorized"
    assert status.event_drawer_id == authority.event_drawer_id


@pytest.mark.parametrize(
    ("fault", "message"),
    [
        ("same-verifier", "verifier must differ"),
        ("stale-state", "does not match attempt output"),
        ("missing-acceptance", "frozen acceptance inventory exactly"),
    ],
)
def test_verification_fails_closed_without_writing_event(
    tmp_path: Path, fault: str, message: str
) -> None:
    store = _store(tmp_path)
    coordinator = HotfixCoordinator(store)
    evidence_id = _evidence(store, "Independent verification evidence exists.")
    opened, _ = _open_and_recommend(coordinator, evidence_id, suffix=fault)
    authority = _authorize(
        coordinator,
        opened,
        evidence_id,
        suffix=fault,
        sequence=1,
        previous_sequence=None,
    )
    _preflight(
        coordinator,
        opened,
        authority,
        evidence_id,
        suffix=fault,
        state_hash="1" * 64,
    )
    attempted = _attempt(
        coordinator,
        opened,
        authority,
        evidence_id,
        suffix=fault,
        before="1" * 64,
        after="2" * 64,
        outcome="pass",
    )
    payload = {
        "authority_hash": authority.data["authority_hash"],
        "verifier": "cursor",
        "observed_state_hash": "2" * 64,
        "results": {
            "bounded smoke passes": {
                "verdict": "pass",
                "detail": "independent pass",
                "evidence_ids": [evidence_id],
            }
        },
    }
    if fault == "same-verifier":
        payload["verifier"] = "codex"
    elif fault == "stale-state":
        payload["observed_state_hash"] = "3" * 64
    else:
        payload["results"] = {}

    with pytest.raises(HotfixError, match=message):
        coordinator.run(
            HotfixCommand(
                action=HotfixAction.VERIFY,
                wing="cairntir",
                case_id=opened.case_id,
                payload=payload,
                idempotency_key=f"verify-{fault}",
            )
        )

    status = coordinator.run(
        HotfixCommand(
            action=HotfixAction.STATUS,
            wing="cairntir",
            case_id=opened.case_id,
            payload={},
        )
    )
    assert status.state.value == "attempted"
    assert status.event_drawer_id == attempted.event_drawer_id


def test_attempt_budget_requires_rollback_before_exhausted_settlement(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    coordinator = HotfixCoordinator(store)
    evidence_id = _evidence(store, "The only attempt failed and rollback was verified.")
    opened, _ = _open_and_recommend(
        coordinator,
        evidence_id,
        suffix="exhausted",
        max_attempts=1,
    )
    authority = _authorize(
        coordinator,
        opened,
        evidence_id,
        suffix="exhausted",
        sequence=1,
        previous_sequence=None,
    )
    _preflight(
        coordinator,
        opened,
        authority,
        evidence_id,
        suffix="exhausted",
        state_hash="1" * 64,
    )
    _attempt(
        coordinator,
        opened,
        authority,
        evidence_id,
        suffix="exhausted",
        before="1" * 64,
        after="2" * 64,
        outcome="fail",
    )
    failed = _verify(
        coordinator,
        opened,
        authority,
        evidence_id,
        suffix="exhausted",
        state_hash="2" * 64,
        verdict="fail",
    )
    settlement = {
        "disposition": "exhausted",
        "observed_outcome": "the bounded attempt did not pass",
        "budget_exhausted": "1/1 attempt consumed",
        "evidence_ids": [evidence_id],
    }

    assert failed.state.value == "repair_required"
    assert failed.next_action == "rollback"
    assert failed.legal_actions == ("rollback", "settle")
    with pytest.raises(HotfixError, match="rolled back before terminal"):
        coordinator.run(
            HotfixCommand(
                action=HotfixAction.SETTLE,
                wing="cairntir",
                case_id=opened.case_id,
                payload=settlement,
                idempotency_key="settle-exhausted-too-early",
            )
        )

    rolled_back = _rollback(
        coordinator,
        opened,
        authority,
        evidence_id,
        suffix="exhausted",
        restored="1" * 64,
    )
    assert rolled_back.next_action == "settle"
    exhausted = coordinator.run(
        HotfixCommand(
            action=HotfixAction.SETTLE,
            wing="cairntir",
            case_id=opened.case_id,
            payload=settlement,
            idempotency_key="settle-exhausted",
        )
    )
    assert exhausted.state.value == "exhausted"
    assert exhausted.legal_actions == ()

    with pytest.raises(HotfixError, match="requires"):
        coordinator.run(
            HotfixCommand(
                action=HotfixAction.SETTLE,
                wing="cairntir",
                case_id=opened.case_id,
                payload={
                    "disposition": "blocked",
                    "observed_outcome": "late rewrite",
                    "blocker": "none",
                    "smallest_unblock": "none",
                    "evidence_ids": [evidence_id],
                },
                idempotency_key="settle-after-terminal",
            )
        )


def test_rollback_requires_independent_exact_pre_attempt_state(tmp_path: Path) -> None:
    store = _store(tmp_path)
    coordinator = HotfixCoordinator(store)
    evidence_id = _evidence(store, "Rollback restored the protected state digest.")
    opened, _ = _open_and_recommend(coordinator, evidence_id, suffix="rollback")
    authority = _authorize(
        coordinator,
        opened,
        evidence_id,
        suffix="rollback",
        sequence=1,
        previous_sequence=None,
    )
    _preflight(
        coordinator,
        opened,
        authority,
        evidence_id,
        suffix="rollback",
        state_hash="1" * 64,
    )
    _attempt(
        coordinator,
        opened,
        authority,
        evidence_id,
        suffix="rollback",
        before="1" * 64,
        after="2" * 64,
        outcome="fail",
    )

    with pytest.raises(HotfixError, match="pre-attempt state"):
        coordinator.run(
            HotfixCommand(
                action=HotfixAction.ROLLBACK,
                wing="cairntir",
                case_id=opened.case_id,
                payload={
                    "authority_hash": authority.data["authority_hash"],
                    "rollback_executor": "codex",
                    "verifier": "cursor",
                    "rollback_ref": f"rollback-{'1' * 8}",
                    "observed_state_hash": "3" * 64,
                    "summary": "wrong state observed",
                    "evidence_ids": [evidence_id],
                },
                idempotency_key="rollback-wrong",
            )
        )

    rolled_back = coordinator.run(
        HotfixCommand(
            action=HotfixAction.ROLLBACK,
            wing="cairntir",
            case_id=opened.case_id,
            payload={
                "authority_hash": authority.data["authority_hash"],
                "rollback_executor": "codex",
                "verifier": "cursor",
                "rollback_ref": f"rollback-{'1' * 8}",
                "observed_state_hash": "1" * 64,
                "summary": "pre-attempt state restored and independently observed",
                "evidence_ids": [evidence_id],
            },
            idempotency_key="rollback-correct",
        )
    )

    assert rolled_back.state.value == "rolled_back"
    assert rolled_back.next_action == "authorize"
    assert rolled_back.data["restored_state_hash"] == "1" * 64


def test_authority_replay_returns_original_receipt_after_state_advanced(tmp_path: Path) -> None:
    store = _store(tmp_path)
    coordinator = HotfixCoordinator(store)
    evidence_id = _evidence(store, "Authority replay must not append a second envelope.")
    opened, _ = _open_and_recommend(coordinator, evidence_id, suffix="authority-replay")
    command = HotfixCommand(
        action=HotfixAction.AUTHORIZE,
        wing="cairntir",
        case_id=opened.case_id,
        payload={
            "authority_id": "AUTH-REPLAY-1",
            "sequence": 1,
            "previous_sequence": None,
            "candidate_id": "repair",
            "candidate_hash": "a" * 64,
            "plan_hash": "b" * 64,
            "toolchain_hash": "c" * 64,
            "target": "clone/cache-only/a4",
            "executor": "codex",
            "capabilities": ["repair", "smoke"],
            "allowed_actions": ["repair", "smoke"],
            "prohibited_actions": ["live-mutation"],
            "required_checks": ["binding", "containment"],
            "evidence_ids": [evidence_id],
        },
        idempotency_key="authority-replay-1",
    )

    first = coordinator.run(command)
    _preflight(
        coordinator,
        opened,
        first,
        evidence_id,
        suffix="authority-replay",
        state_hash="1" * 64,
    )
    replay = coordinator.run(command)

    assert replay.replayed is True
    assert replay.event_drawer_id == first.event_drawer_id
    assert replay.data == first.data


def test_cross_wing_evidence_is_rejected(tmp_path: Path) -> None:
    store = _store(tmp_path)
    other = store.add(Drawer(wing="other", room="evidence", content="not this project"))
    assert other.id is not None
    coordinator = HotfixCoordinator(store)

    with pytest.raises(HotfixError, match="belongs to wing 'other'"):
        coordinator.run(
            HotfixCommand(
                action=HotfixAction.OPEN,
                wing="cairntir",
                payload={
                    "title": "wrong evidence",
                    "stage": "a4",
                    "symptom": "assertion failed",
                    "acceptance": ["fixed"],
                    "evidence_ids": [other.id],
                },
                idempotency_key="cross-wing",
            )
        )


def test_event_content_tampering_is_detected_on_status(tmp_path: Path) -> None:
    store = _store(tmp_path)
    coordinator = HotfixCoordinator(store)
    opened = coordinator.run(
        HotfixCommand(
            action=HotfixAction.OPEN,
            wing="cairntir",
            payload={
                "title": "tamper check",
                "stage": "a4",
                "symptom": "assertion failed",
                "acceptance": ["integrity holds"],
            },
            idempotency_key="tamper-check",
        )
    )
    store.close()
    connection = sqlite3.connect(tmp_path / "hotfix.db")
    connection.execute(
        "UPDATE drawers SET content = ? WHERE id = ?",
        ("rewritten", opened.event_drawer_id),
    )
    connection.commit()
    connection.close()
    reopened = HotfixCoordinator(
        DrawerStore(tmp_path / "hotfix.db", HashEmbeddingProvider(dimension=32))
    )

    with pytest.raises(HotfixError, match="failed integrity validation"):
        reopened.run(
            HotfixCommand(
                action=HotfixAction.STATUS,
                wing="cairntir",
                case_id=opened.case_id,
                payload={},
            )
        )


def test_open_state_metadata_tampering_is_detected_on_status(tmp_path: Path) -> None:
    store = _store(tmp_path)
    coordinator = HotfixCoordinator(store)
    opened = coordinator.run(
        HotfixCommand(
            action=HotfixAction.OPEN,
            wing="cairntir",
            payload={
                "title": "open-state tamper check",
                "stage": "a4",
                "symptom": "assertion failed",
                "acceptance": ["integrity holds"],
            },
            idempotency_key="open-state-tamper-check",
        )
    )
    store.close()
    connection = sqlite3.connect(tmp_path / "hotfix.db")
    row = connection.execute(
        "SELECT metadata FROM drawers WHERE id = ?", (opened.event_drawer_id,)
    ).fetchone()
    assert row is not None
    metadata = json.loads(row[0])
    metadata["open_question"] = False
    connection.execute(
        "UPDATE drawers SET metadata = ? WHERE id = ?",
        (json.dumps(metadata), opened.event_drawer_id),
    )
    connection.commit()
    connection.close()
    reopened = HotfixCoordinator(
        DrawerStore(tmp_path / "hotfix.db", HashEmbeddingProvider(dimension=32))
    )

    with pytest.raises(HotfixError, match="invalid open-state metadata"):
        reopened.run(
            HotfixCommand(
                action=HotfixAction.STATUS,
                wing="cairntir",
                case_id=opened.case_id,
                payload={},
            )
        )


def test_forked_supersession_chain_is_detected_on_status(tmp_path: Path) -> None:
    store = _store(tmp_path)
    coordinator = HotfixCoordinator(store)
    evidence_id = _evidence(store, "A recommendation exists once.")
    opened, recommended = _open_and_recommend(
        coordinator, evidence_id, suffix="forked-chain"
    )
    child = store.get(recommended.event_drawer_id or 0)
    assert child is not None
    store.add(
        Drawer(
            wing=child.wing,
            room=child.room,
            content=child.content,
            layer=child.layer,
            metadata=json.loads(json.dumps(child.metadata)),
            supersedes_id=opened.event_drawer_id,
        )
    )

    with pytest.raises(HotfixError, match="chain is forked"):
        coordinator.run(
            HotfixCommand(
                action=HotfixAction.STATUS,
                wing="cairntir",
                case_id=opened.case_id,
                payload={},
            )
        )


def test_matching_completed_precedent_returns_its_resolution(tmp_path: Path) -> None:
    store = _store(tmp_path)
    coordinator = HotfixCoordinator(store)
    evidence_id = _evidence(store, "The repaired digest made the bounded smoke pass.")
    prior, _ = _open_and_recommend(coordinator, evidence_id, suffix="prior-success")
    authority = _authorize(
        coordinator,
        prior,
        evidence_id,
        suffix="prior-success",
        sequence=1,
        previous_sequence=None,
    )
    _preflight(
        coordinator,
        prior,
        authority,
        evidence_id,
        suffix="prior-success",
        state_hash="1" * 64,
    )
    _attempt(
        coordinator,
        prior,
        authority,
        evidence_id,
        suffix="prior-success",
        before="1" * 64,
        after="2" * 64,
        outcome="pass",
    )
    _verify(
        coordinator,
        prior,
        authority,
        evidence_id,
        suffix="prior-success",
        state_hash="2" * 64,
        verdict="pass",
    )
    coordinator.run(
        HotfixCommand(
            action=HotfixAction.SETTLE,
            wing="cairntir",
            case_id=prior.case_id,
            payload={
                "disposition": "complete",
                "observed_outcome": "bounded smoke passed",
                "resolution": "rebuild the ACL digest before the smoke",
                "evidence_ids": [evidence_id],
            },
            idempotency_key="settle-prior-success",
        )
    )
    current = coordinator.run(
        HotfixCommand(
            action=HotfixAction.OPEN,
            wing="cairntir",
            payload={
                "title": "same failure again",
                "stage": "a4",
                "symptom": "protected smoke assertion failed",
                "acceptance": ["bounded smoke passes"],
                "evidence_ids": [evidence_id],
            },
            idempotency_key="open-current-precedent",
        )
    )
    recommendation = coordinator.run(
        HotfixCommand(
            action=HotfixAction.RECOMMEND,
            wing="cairntir",
            case_id=current.case_id,
            payload={
                "candidates": [
                    {
                        "id": "new-guess",
                        "summary": "try a new low-risk guess",
                        "evidence_ids": [evidence_id],
                        "state_change": "new candidate digest",
                        "reversible": True,
                        "risk": "low",
                    },
                    {
                        "id": "reuse-proven-repair",
                        "summary": "reuse the completed repair",
                        "evidence_ids": [evidence_id],
                        "precedent_case_ids": [prior.case_id],
                        "state_change": "ACL digest changes",
                        "reversible": False,
                        "risk": "high",
                    },
                ]
            },
            idempotency_key="recommend-current-precedent",
        )
    )

    selected = recommendation.data["ranking"][0]
    assert recommendation.data["selected_candidate"] == "reuse-proven-repair"
    assert selected["precedents"][0]["case_id"] == prior.case_id
    assert selected["precedents"][0]["resolution"] == (
        "rebuild the ACL digest before the smoke"
    )
    assert selected["precedents"][0]["strength"] == 3
