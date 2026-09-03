"""Append-only, bounded hotfix reasoning without host execution authority."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from cairntir.durability import WorkflowExecution, WorkflowState
from cairntir.errors import HotfixError
from cairntir.memory.taxonomy import Drawer, Layer

if TYPE_CHECKING:
    from cairntir.memory.store import DrawerStore


HOTFIX_SCHEMA = "cairntir.hotfix.v1"
HOTFIX_ROOM = "hotfix-ledger"

__all__ = (
    "HotfixAction",
    "HotfixCommand",
    "HotfixCoordinator",
    "HotfixReceipt",
    "HotfixState",
)


class HotfixAction(StrEnum):
    """Commands accepted by :class:`HotfixCoordinator`."""

    OPEN = "open"
    RECOMMEND = "recommend"
    AUTHORIZE = "authorize"
    PREFLIGHT = "preflight"
    RECORD_ATTEMPT = "record_attempt"
    ROLLBACK = "rollback"
    VERIFY = "verify"
    SETTLE = "settle"
    STATUS = "status"


class HotfixState(StrEnum):
    """Projected state of a hotfix case."""

    OPEN = "open"
    RECOMMENDED = "recommended"
    AUTHORIZED = "authorized"
    PREFLIGHTED = "preflighted"
    ATTEMPTED = "attempted"
    REPAIR_REQUIRED = "repair_required"
    VERIFIED = "verified"
    ROLLED_BACK = "rolled_back"
    COMPLETE = "complete"
    BLOCKED = "blocked"
    EXHAUSTED = "exhausted"


@dataclass(frozen=True, slots=True)
class HotfixCommand:
    """One command crossing the hotfix module's interface."""

    action: HotfixAction
    wing: str
    payload: dict[str, Any]
    case_id: str | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True, slots=True)
class HotfixReceipt:
    """Observable result of a hotfix command."""

    case_id: str
    action: HotfixAction
    state: HotfixState
    fingerprint: str
    failure_class: str
    event_drawer_id: int | None
    replayed: bool
    next_action: str
    card: str
    legal_actions: tuple[str, ...]
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class _LedgerEvent:
    drawer: Drawer
    kind: HotfixAction
    state: HotfixState
    payload: dict[str, Any]
    event_hash: str


_WINDOWS_PATH = re.compile(r"\b[a-zA-Z]:\\[^\r\n\t ]+")
_POSIX_PATH = re.compile(r"(?<![\w.])/(?:[^/\s]+/)*[^/\s]+")
_HEX_TOKEN = re.compile(r"\b[0-9a-fA-F]{8,}\b")
_NUMBER = re.compile(r"\b\d+\b")
_SPACE = re.compile(r"\s+")
_TERMINAL_STATES = {
    HotfixState.COMPLETE,
    HotfixState.BLOCKED,
    HotfixState.EXHAUSTED,
}


def _canonical(payload: dict[str, Any]) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise HotfixError(f"hotfix payload is not JSON-serializable: {exc}") from exc


def _hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _event_hash(
    *,
    wing: str,
    case_id: str,
    kind: HotfixAction,
    state: HotfixState,
    fingerprint: str,
    failure_class: str,
    payload: dict[str, Any],
    previous_event_hash: str | None,
    parent_drawer_id: int | None,
    content: str,
) -> str:
    return _hash(
        {
            "schema": HOTFIX_SCHEMA,
            "wing": wing,
            "case_id": case_id,
            "kind": kind.value,
            "state": state.value,
            "fingerprint": fingerprint,
            "failure_class": failure_class,
            "payload": payload,
            "previous_event_hash": previous_event_hash,
            "parent_drawer_id": parent_drawer_id,
            "content": content,
        }
    )


def _text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise HotfixError(f"{key} must be a non-empty string")
    return value.strip()


def _strings(payload: dict[str, Any], key: str, *, required: bool = False) -> tuple[str, ...]:
    value = payload.get(key, [])
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise HotfixError(f"{key} must be a list of non-empty strings")
    normalized = tuple(dict.fromkeys(item.strip() for item in value))
    if required and not normalized:
        raise HotfixError(f"{key} must contain at least one item")
    return normalized


def _normalize_failure(text: str) -> str:
    normalized = _WINDOWS_PATH.sub("<path>", text)
    normalized = _POSIX_PATH.sub("<path>", normalized)
    normalized = _HEX_TOKEN.sub("<hex>", normalized)
    normalized = _NUMBER.sub("<n>", normalized)
    return _SPACE.sub(" ", normalized).strip().lower()


def _classify_failure(symptom: str) -> str:
    lowered = symptom.lower()
    rules = (
        ("permission", ("access denied", "permission", "acl", "unauthorized", "forbidden")),
        ("timeout", ("timeout", "timed out", "deadline")),
        ("dependency", ("not found", "missing dependency", "no module named", "unavailable")),
        ("validation", ("invalid", "schema", "validation")),
        ("assertion", ("assert", "expected", "mismatch")),
        ("crash", ("crash", "exception", "segfault", "panic")),
    )
    return next((kind for kind, needles in rules if any(n in lowered for n in needles)), "unknown")


class HotfixCoordinator:
    """Validate and persist a bounded hotfix ledger behind one interface."""

    def __init__(self, store: DrawerStore) -> None:
        """Create a coordinator over an existing drawer store."""
        self._store = store

    def run(self, command: HotfixCommand) -> HotfixReceipt:
        """Run one hotfix command and return its durable operator receipt."""
        try:
            action = HotfixAction(command.action)
        except ValueError as exc:
            raise HotfixError(f"unknown hotfix action {command.action!r}") from exc
        if action not in {HotfixAction.OPEN, HotfixAction.STATUS}:
            replay = self._committed_replay(command, action)
            if replay is not None:
                return replay
        if action is HotfixAction.OPEN:
            return self._open(command)
        if action is HotfixAction.RECOMMEND:
            return self._recommend(command)
        if action is HotfixAction.AUTHORIZE:
            return self._authorize(command)
        if action is HotfixAction.PREFLIGHT:
            return self._preflight(command)
        if action is HotfixAction.RECORD_ATTEMPT:
            return self._record_attempt(command)
        if action is HotfixAction.ROLLBACK:
            return self._rollback(command)
        if action is HotfixAction.VERIFY:
            return self._verify(command)
        if action is HotfixAction.SETTLE:
            return self._settle(command)
        if action is HotfixAction.STATUS:
            return self._status(command)
        raise HotfixError(f"hotfix action {action.value!r} is not implemented")

    def _open(self, command: HotfixCommand) -> HotfixReceipt:
        payload = command.payload
        title = _text(payload, "title")
        stage = _text(payload, "stage")
        symptom = _text(payload, "symptom")
        acceptance = _strings(payload, "acceptance", required=True)
        non_goals = _strings(payload, "non_goals")
        failure_class = str(payload.get("failure_class") or _classify_failure(symptom)).strip()
        if not failure_class:
            raise HotfixError("failure_class must be a non-empty string")
        evidence_ids = self._evidence_ids(payload, "evidence_ids", wing=command.wing)
        max_attempts = payload.get("max_attempts", 2)
        if (
            isinstance(max_attempts, bool)
            or not isinstance(max_attempts, int)
            or not 1 <= max_attempts <= 2
        ):
            raise HotfixError("max_attempts must be 1 or 2")
        fingerprint = _hash(
            {
                "failure_class": failure_class,
                "stage": stage.lower(),
                "symptom": _normalize_failure(symptom),
            }
        )
        idempotency_key = (command.idempotency_key or "").strip()
        if not idempotency_key:
            raise HotfixError("mutating hotfix commands require idempotency_key")
        case_id = f"hf-{_hash({'fingerprint': fingerprint, 'key': idempotency_key})[:12]}"
        event_payload: dict[str, Any] = {
            "title": title,
            "stage": stage,
            "symptom": symptom,
            "acceptance": list(acceptance),
            "non_goals": list(non_goals),
            "evidence_ids": list(evidence_ids),
            "max_attempts": max_attempts,
        }
        action = HotfixAction.OPEN
        state = HotfixState.OPEN
        content = f"Hotfix {case_id} opened: {title}\nFailure: {symptom}"
        event_hash = _event_hash(
            wing=command.wing,
            case_id=case_id,
            kind=action,
            state=state,
            fingerprint=fingerprint,
            failure_class=failure_class,
            payload=event_payload,
            previous_event_hash=None,
            parent_drawer_id=None,
            content=content,
        )

        def _record() -> dict[str, Any]:
            saved = self._store.add(
                Drawer(
                    wing=command.wing,
                    room=HOTFIX_ROOM,
                    content=content,
                    layer=Layer.ON_DEMAND,
                    metadata={
                        "hotfix_schema": HOTFIX_SCHEMA,
                        "case_id": case_id,
                        "kind": action.value,
                        "state": state.value,
                        "fingerprint": fingerprint,
                        "failure_class": failure_class,
                        "open_question": True,
                        "previous_event_hash": None,
                        "event_hash": event_hash,
                        "payload": event_payload,
                    },
                )
            )
            if saved.id is None:
                raise HotfixError("hotfix event was stored without a drawer id")
            return {"drawer_id": saved.id}

        execution = self._store.execute_once(
            idempotency_key=f"hotfix:{idempotency_key}",
            operation="hotfix.open",
            request={
                "wing": command.wing,
                "case_id": case_id,
                "fingerprint": fingerprint,
                "failure_class": failure_class,
                "payload": event_payload,
            },
            action=_record,
        )
        event_id = execution.result["drawer_id"]
        if not isinstance(event_id, int):
            raise HotfixError("hotfix workflow receipt has an invalid drawer id")
        card = (
            f"Hotfix {case_id}\n"
            f"State: {HotfixState.OPEN.value}\n"
            f"Class: {failure_class}\n"
            f"Fingerprint: {fingerprint}\n"
            "Next legal action: recommend"
        )
        return HotfixReceipt(
            case_id=case_id,
            action=action,
            state=state,
            fingerprint=fingerprint,
            failure_class=failure_class,
            event_drawer_id=event_id,
            replayed=execution.replayed,
            next_action=HotfixAction.RECOMMEND.value,
            card=card,
            legal_actions=self._legal_actions(state),
        )

    def _recommend(self, command: HotfixCommand) -> HotfixReceipt:
        case_id = self._case_id(command)
        events = self._events(command.wing, case_id)
        raw_candidates = command.payload.get("candidates")
        if not isinstance(raw_candidates, list) or not raw_candidates:
            raise HotfixError("candidates must be a non-empty list")
        candidates: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        risk_order = {"low": 0, "medium": 1, "high": 2}
        for raw in raw_candidates:
            if not isinstance(raw, dict):
                raise HotfixError("each candidate must be an object")
            candidate_id = _text(raw, "id")
            if candidate_id in seen_ids:
                raise HotfixError(f"candidate id {candidate_id!r} is duplicated")
            seen_ids.add(candidate_id)
            summary = _text(raw, "summary")
            state_change = _text(raw, "state_change")
            evidence_ids = self._evidence_ids(raw, "evidence_ids", wing=command.wing, required=True)
            reversible = raw.get("reversible")
            if not isinstance(reversible, bool):
                raise HotfixError(f"candidate {candidate_id!r} reversible must be boolean")
            risk = raw.get("risk")
            if risk not in risk_order:
                raise HotfixError(f"candidate {candidate_id!r} risk must be low, medium, or high")
            precedent_ids = _strings(raw, "precedent_case_ids")
            precedents = [
                self._precedent(events[0], command.wing, precedent_id)
                for precedent_id in precedent_ids
            ]
            precedent_strength = max((precedent["strength"] for precedent in precedents), default=0)
            progress = state_change.strip().lower() not in {"none", "no change", "unchanged"}
            candidate = {
                "id": candidate_id,
                "summary": summary,
                "evidence_ids": list(evidence_ids),
                "precedent_case_ids": list(precedent_ids),
                "precedents": precedents,
                "state_change": state_change,
                "reversible": reversible,
                "risk": risk,
                "rank": {
                    "completed_precedent": precedent_strength,
                    "changes_state": progress,
                    "evidence_count": len(evidence_ids),
                    "reversible": reversible,
                    "risk": risk,
                },
                "_sort": (
                    -precedent_strength,
                    -int(progress),
                    -len(evidence_ids),
                    -int(reversible),
                    risk_order[risk],
                    candidate_id,
                ),
            }
            candidates.append(candidate)
        candidates.sort(key=lambda candidate: candidate["_sort"])
        for candidate in candidates:
            candidate.pop("_sort")
        selected = candidates[0]
        event_payload = {
            "selected_candidate": selected["id"],
            "ranking": candidates,
        }
        return self._append(
            command,
            expected=HotfixState.OPEN,
            new_state=HotfixState.RECOMMENDED,
            payload=event_payload,
            content=(f"Hotfix {case_id} recommendation: {selected['id']}\n{selected['summary']}"),
            data={"selected_candidate": selected["id"], "ranking": candidates},
        )

    def _authorize(self, command: HotfixCommand) -> HotfixReceipt:
        case_id = self._case_id(command)
        events = self._events(command.wing, case_id)
        first = events[0]
        recommendation = self._last(events, HotfixAction.RECOMMEND)
        payload = command.payload
        authority_id = _text(payload, "authority_id")
        candidate_id = _text(payload, "candidate_id")
        if candidate_id != recommendation.payload["selected_candidate"]:
            raise HotfixError(
                f"candidate {candidate_id!r} is not the selected recommendation "
                f"{recommendation.payload['selected_candidate']!r}"
            )
        sequence = self._positive_int(payload, "sequence")
        previous_sequence = payload.get("previous_sequence")
        if previous_sequence is not None and (
            isinstance(previous_sequence, bool)
            or not isinstance(previous_sequence, int)
            or previous_sequence < 0
            or previous_sequence != sequence - 1
        ):
            raise HotfixError("previous_sequence must be exactly sequence - 1")
        prior_authorities = [event for event in events if event.kind is HotfixAction.AUTHORIZE]
        if prior_authorities:
            prior_sequence = prior_authorities[-1].payload["sequence"]
            if sequence != prior_sequence + 1 or previous_sequence != prior_sequence:
                raise HotfixError(
                    f"authority sequence must advance {prior_sequence} to {prior_sequence + 1}"
                )
        attempts = sum(event.kind is HotfixAction.RECORD_ATTEMPT for event in events)
        max_attempts = first.payload["max_attempts"]
        if attempts >= max_attempts:
            raise HotfixError(f"hotfix {case_id} exhausted its {max_attempts} attempt budget")
        candidate_hash = self._sha256(payload, "candidate_hash")
        plan_hash = self._sha256(payload, "plan_hash")
        toolchain_hash = self._sha256(payload, "toolchain_hash")
        target = _text(payload, "target")
        executor = _text(payload, "executor")
        capabilities = tuple(sorted(_strings(payload, "capabilities", required=True)))
        allowed_actions = tuple(sorted(_strings(payload, "allowed_actions", required=True)))
        prohibited_actions = tuple(sorted(_strings(payload, "prohibited_actions")))
        overlap = set(allowed_actions) & set(prohibited_actions)
        if overlap:
            raise HotfixError(f"actions cannot be both allowed and prohibited: {sorted(overlap)}")
        required_checks = tuple(sorted(_strings(payload, "required_checks", required=True)))
        evidence_ids = self._evidence_ids(payload, "evidence_ids", wing=command.wing, required=True)
        acceptance = first.payload["acceptance"]
        envelope: dict[str, Any] = {
            "authority_id": authority_id,
            "sequence": sequence,
            "previous_sequence": previous_sequence,
            "fingerprint": first.drawer.metadata["fingerprint"],
            "candidate_id": candidate_id,
            "candidate_hash": candidate_hash,
            "plan_hash": plan_hash,
            "toolchain_hash": toolchain_hash,
            "target": target,
            "executor": executor,
            "capabilities": list(capabilities),
            "allowed_actions": list(allowed_actions),
            "prohibited_actions": list(prohibited_actions),
            "required_checks": list(required_checks),
            "acceptance_hash": _hash({"acceptance": acceptance}),
            "evidence_ids": list(evidence_ids),
        }
        envelope["authority_hash"] = _hash(envelope)
        return self._append(
            command,
            expected=(
                HotfixState.RECOMMENDED,
                HotfixState.REPAIR_REQUIRED,
                HotfixState.ROLLED_BACK,
            ),
            new_state=HotfixState.AUTHORIZED,
            payload=envelope,
            content=(
                f"Hotfix {case_id} authority {authority_id} sequence {sequence} sealed\n"
                f"Candidate: {candidate_id}\nTarget: {target}"
            ),
            data={
                "authority_hash": envelope["authority_hash"],
                "sequence": sequence,
                "candidate_id": candidate_id,
            },
        )

    def _preflight(self, command: HotfixCommand) -> HotfixReceipt:
        case_id = self._case_id(command)
        events = self._events(command.wing, case_id)
        authority = self._last(events, HotfixAction.AUTHORIZE)
        payload = command.payload
        authority_hash = self._matching_authority_hash(payload, authority)
        inspector = _text(payload, "inspector")
        if inspector == authority.payload["executor"]:
            raise HotfixError("preflight inspector must differ from the authorized executor")
        observed = payload.get("observed_bindings")
        if not isinstance(observed, dict):
            raise HotfixError("observed_bindings must be an object")
        expected_bindings = {
            key: authority.payload[key]
            for key in ("candidate_hash", "plan_hash", "toolchain_hash", "target")
        }
        if observed != expected_bindings:
            mismatched = sorted(
                key
                for key in set(observed) | set(expected_bindings)
                if observed.get(key) != expected_bindings.get(key)
            )
            raise HotfixError(f"preflight authority binding mismatch: {mismatched}")
        capabilities = tuple(sorted(_strings(payload, "capabilities", required=True)))
        if list(capabilities) != authority.payload["capabilities"]:
            raise HotfixError("preflight capabilities do not exactly match the authority envelope")
        observed_state_hash = self._sha256(payload, "observed_state_hash")
        checks = payload.get("checks")
        if not isinstance(checks, dict):
            raise HotfixError("checks must be an object")
        required_checks = set(authority.payload["required_checks"])
        if set(checks) != required_checks:
            raise HotfixError(
                "preflight checks must exactly match required_checks: "
                f"expected {sorted(required_checks)}, got {sorted(checks)}"
            )
        normalized_checks: dict[str, Any] = {}
        for name in sorted(required_checks):
            result = checks[name]
            if not isinstance(result, dict):
                raise HotfixError(f"preflight check {name!r} must be an object")
            if result.get("passed") is not True:
                raise HotfixError(f"preflight check {name!r} did not pass")
            detail = _text(result, "detail")
            evidence_ids = self._evidence_ids(
                result, "evidence_ids", wing=command.wing, required=True
            )
            normalized_checks[name] = {
                "passed": True,
                "detail": detail,
                "evidence_ids": list(evidence_ids),
            }
        event_payload = {
            "authority_hash": authority_hash,
            "inspector": inspector,
            "observed_bindings": expected_bindings,
            "capabilities": list(capabilities),
            "observed_state_hash": observed_state_hash,
            "checks": normalized_checks,
        }
        return self._append(
            command,
            expected=HotfixState.AUTHORIZED,
            new_state=HotfixState.PREFLIGHTED,
            payload=event_payload,
            content=f"Hotfix {case_id} preflight passed for authority {authority_hash}",
            data={"authority_hash": authority_hash, "observed_state_hash": observed_state_hash},
        )

    def _record_attempt(self, command: HotfixCommand) -> HotfixReceipt:
        case_id = self._case_id(command)
        events = self._events(command.wing, case_id)
        first = events[0]
        authority = self._last(events, HotfixAction.AUTHORIZE)
        preflight = self._last(events, HotfixAction.PREFLIGHT)
        payload = command.payload
        authority_hash = self._matching_authority_hash(payload, authority)
        if preflight.payload["authority_hash"] != authority_hash:
            raise HotfixError("attempt is not bound to the latest preflight authority")
        executor = _text(payload, "executor")
        if executor != authority.payload["executor"]:
            raise HotfixError("attempt executor does not match the authority envelope")
        executed_actions = tuple(sorted(_strings(payload, "executed_actions", required=True)))
        allowed = set(authority.payload["allowed_actions"])
        prohibited = set(authority.payload["prohibited_actions"])
        if not set(executed_actions) <= allowed:
            raise HotfixError(
                f"attempt contains unauthorized actions: {sorted(set(executed_actions) - allowed)}"
            )
        if set(executed_actions) & prohibited:
            raise HotfixError("attempt contains an explicitly prohibited action")
        state_hash_before = self._sha256(payload, "state_hash_before")
        state_hash_after = self._sha256(payload, "state_hash_after")
        if state_hash_before != preflight.payload["observed_state_hash"]:
            raise HotfixError("attempt state_hash_before does not match preflight state")
        prior_attempts = [event for event in events if event.kind is HotfixAction.RECORD_ATTEMPT]
        max_attempts = first.payload["max_attempts"]
        if len(prior_attempts) >= max_attempts:
            raise HotfixError(f"hotfix {case_id} exhausted its {max_attempts} attempt budget")
        if prior_attempts:
            prior = prior_attempts[-1]
            if (
                prior.payload["outcome"] != "pass"
                and state_hash_before == prior.payload["state_hash_after"]
            ):
                raise HotfixError(
                    "unchanged failed state cannot be attempted again; record a real repair first"
                )
        if any(event.payload.get("authority_hash") == authority_hash for event in prior_attempts):
            raise HotfixError("one authority envelope permits only one attempt")
        outcome = payload.get("outcome")
        if outcome not in {"pass", "fail", "inconclusive"}:
            raise HotfixError("outcome must be pass, fail, or inconclusive")
        summary = _text(payload, "summary")
        evidence_ids = self._evidence_ids(payload, "evidence_ids", wing=command.wing, required=True)
        rollback_ref = _text(payload, "rollback_ref")
        artifacts = self._artifacts(payload)
        attempt_number = len(prior_attempts) + 1
        event_payload = {
            "attempt": attempt_number,
            "authority_hash": authority_hash,
            "executor": executor,
            "executed_actions": list(executed_actions),
            "state_hash_before": state_hash_before,
            "state_hash_after": state_hash_after,
            "outcome": outcome,
            "summary": summary,
            "evidence_ids": list(evidence_ids),
            "artifacts": artifacts,
            "rollback_ref": rollback_ref,
        }
        return self._append(
            command,
            expected=HotfixState.PREFLIGHTED,
            new_state=HotfixState.ATTEMPTED,
            payload=event_payload,
            content=f"Hotfix {case_id} attempt {attempt_number}: {outcome}\n{summary}",
            data={"attempt": attempt_number, "outcome": outcome},
        )

    def _verify(self, command: HotfixCommand) -> HotfixReceipt:
        case_id = self._case_id(command)
        events = self._events(command.wing, case_id)
        first = events[0]
        authority = self._last(events, HotfixAction.AUTHORIZE)
        attempt = self._last(events, HotfixAction.RECORD_ATTEMPT)
        payload = command.payload
        authority_hash = self._matching_authority_hash(payload, authority)
        if attempt.payload["authority_hash"] != authority_hash:
            raise HotfixError("verification is not bound to the latest attempt authority")
        verifier = _text(payload, "verifier")
        if verifier == attempt.payload["executor"]:
            raise HotfixError("verifier must differ from the attempt executor")
        observed_state_hash = self._sha256(payload, "observed_state_hash")
        if observed_state_hash != attempt.payload["state_hash_after"]:
            raise HotfixError("verification observed_state_hash does not match attempt output")
        raw_results = payload.get("results")
        if not isinstance(raw_results, dict):
            raise HotfixError("results must be an object keyed by acceptance item")
        acceptance = first.payload["acceptance"]
        if set(raw_results) != set(acceptance):
            raise HotfixError("verification must cover the frozen acceptance inventory exactly")
        results: dict[str, Any] = {}
        for item in acceptance:
            result = raw_results[item]
            if not isinstance(result, dict):
                raise HotfixError(f"verification result for {item!r} must be an object")
            verdict = result.get("verdict")
            if verdict not in {"pass", "fail", "inconclusive"}:
                raise HotfixError(
                    f"verification verdict for {item!r} must be pass, fail, or inconclusive"
                )
            detail = _text(result, "detail")
            evidence_ids = self._evidence_ids(
                result, "evidence_ids", wing=command.wing, required=True
            )
            results[item] = {
                "verdict": verdict,
                "detail": detail,
                "evidence_ids": list(evidence_ids),
            }
        all_pass = all(result["verdict"] == "pass" for result in results.values())
        accepted = all_pass and attempt.payload["outcome"] == "pass"
        new_state = HotfixState.VERIFIED if accepted else HotfixState.REPAIR_REQUIRED
        event_payload = {
            "authority_hash": authority_hash,
            "attempt": attempt.payload["attempt"],
            "verifier": verifier,
            "observed_state_hash": observed_state_hash,
            "results": results,
            "accepted": accepted,
        }
        return self._append(
            command,
            expected=HotfixState.ATTEMPTED,
            new_state=new_state,
            payload=event_payload,
            content=(
                f"Hotfix {case_id} verification by {verifier}: {'PASS' if accepted else 'FAIL'}"
            ),
            data={"accepted": accepted, "verdict": "pass" if accepted else "fail"},
        )

    def _rollback(self, command: HotfixCommand) -> HotfixReceipt:
        case_id = self._case_id(command)
        events = self._events(command.wing, case_id)
        authority = self._last(events, HotfixAction.AUTHORIZE)
        attempt = self._last(events, HotfixAction.RECORD_ATTEMPT)
        payload = command.payload
        authority_hash = self._matching_authority_hash(payload, authority)
        if attempt.payload["authority_hash"] != authority_hash:
            raise HotfixError("rollback is not bound to the latest attempt authority")
        rollback_executor = _text(payload, "rollback_executor")
        if rollback_executor != authority.payload["executor"]:
            raise HotfixError("rollback executor does not match the authority envelope")
        verifier = _text(payload, "verifier")
        if verifier == rollback_executor:
            raise HotfixError("rollback verifier must differ from the rollback executor")
        rollback_ref = _text(payload, "rollback_ref")
        if rollback_ref != attempt.payload["rollback_ref"]:
            raise HotfixError("rollback_ref does not match the attempted rollback binding")
        observed_state_hash = self._sha256(payload, "observed_state_hash")
        if observed_state_hash != attempt.payload["state_hash_before"]:
            raise HotfixError("rollback did not restore the exact pre-attempt state")
        summary = _text(payload, "summary")
        evidence_ids = self._evidence_ids(payload, "evidence_ids", wing=command.wing, required=True)
        event_payload = {
            "authority_hash": authority_hash,
            "attempt": attempt.payload["attempt"],
            "rollback_executor": rollback_executor,
            "verifier": verifier,
            "rollback_ref": rollback_ref,
            "restored_state_hash": observed_state_hash,
            "summary": summary,
            "evidence_ids": list(evidence_ids),
        }
        return self._append(
            command,
            expected=(
                HotfixState.ATTEMPTED,
                HotfixState.REPAIR_REQUIRED,
            ),
            new_state=HotfixState.ROLLED_BACK,
            payload=event_payload,
            content=f"Hotfix {case_id} exact rollback verified by {verifier}\n{summary}",
            data={
                "attempt": attempt.payload["attempt"],
                "restored_state_hash": observed_state_hash,
            },
        )

    def _settle(self, command: HotfixCommand) -> HotfixReceipt:
        case_id = self._case_id(command)
        events = self._events(command.wing, case_id)
        payload = command.payload
        disposition_raw = payload.get("disposition")
        try:
            disposition = HotfixState(str(disposition_raw))
        except ValueError as exc:
            raise HotfixError("disposition must be complete, blocked, or exhausted") from exc
        if disposition not in {
            HotfixState.COMPLETE,
            HotfixState.BLOCKED,
            HotfixState.EXHAUSTED,
        }:
            raise HotfixError("disposition must be complete, blocked, or exhausted")
        observed_outcome = _text(payload, "observed_outcome")
        evidence_ids = self._evidence_ids(payload, "evidence_ids", wing=command.wing, required=True)
        resolution = payload.get("resolution")
        delta = payload.get("delta")
        if resolution is not None and (not isinstance(resolution, str) or not resolution.strip()):
            raise HotfixError("resolution must be a non-empty string when provided")
        if delta is not None and (not isinstance(delta, str) or not delta.strip()):
            raise HotfixError("delta must be a non-empty string when provided")
        if disposition is HotfixState.COMPLETE:
            if not isinstance(resolution, str) or not resolution.strip():
                raise HotfixError("complete settlement requires a reusable resolution")
            expected: HotfixState | tuple[HotfixState, ...] = HotfixState.VERIFIED
        elif disposition is HotfixState.BLOCKED:
            _text(payload, "blocker")
            _text(payload, "smallest_unblock")
            expected = (
                HotfixState.OPEN,
                HotfixState.RECOMMENDED,
                HotfixState.AUTHORIZED,
                HotfixState.PREFLIGHTED,
                HotfixState.REPAIR_REQUIRED,
                HotfixState.ROLLED_BACK,
            )
        else:
            _text(payload, "budget_exhausted")
            attempts = sum(event.kind is HotfixAction.RECORD_ATTEMPT for event in events)
            max_attempts = events[0].payload["max_attempts"]
            if attempts < max_attempts:
                raise HotfixError(
                    f"hotfix {case_id} has {attempts}/{max_attempts} attempts; "
                    "its budget is not exhausted"
                )
            expected = (HotfixState.REPAIR_REQUIRED, HotfixState.ROLLED_BACK)

        if disposition in {HotfixState.BLOCKED, HotfixState.EXHAUSTED}:
            attempt_events = [
                event for event in events if event.kind is HotfixAction.RECORD_ATTEMPT
            ]
            latest = events[-1]
            if (
                attempt_events
                and attempt_events[-1].payload["state_hash_before"]
                != attempt_events[-1].payload["state_hash_after"]
                and latest.state is HotfixState.REPAIR_REQUIRED
            ):
                raise HotfixError(
                    "changed failed state must be rolled back before terminal settlement"
                )
        event_payload = {
            "disposition": disposition.value,
            "observed_outcome": observed_outcome,
            "resolution": resolution.strip() if isinstance(resolution, str) else None,
            "delta": delta.strip() if isinstance(delta, str) else None,
            "blocker": payload.get("blocker"),
            "smallest_unblock": payload.get("smallest_unblock"),
            "budget_exhausted": payload.get("budget_exhausted"),
            "evidence_ids": list(evidence_ids),
        }
        return self._append(
            command,
            expected=expected,
            new_state=disposition,
            payload=event_payload,
            content=f"Hotfix {case_id} settled {disposition.value}: {observed_outcome}",
            data=event_payload,
        )

    @staticmethod
    def _last(events: list[_LedgerEvent], kind: HotfixAction) -> _LedgerEvent:
        try:
            return next(event for event in reversed(events) if event.kind is kind)
        except StopIteration as exc:
            raise HotfixError(f"hotfix has no {kind.value} event") from exc

    @staticmethod
    def _positive_int(payload: dict[str, Any], key: str) -> int:
        value = payload.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise HotfixError(f"{key} must be a positive integer")
        return value

    @staticmethod
    def _sha256(payload: dict[str, Any], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise HotfixError(f"{key} must be a lowercase SHA-256 digest")
        return value

    @staticmethod
    def _matching_authority_hash(payload: dict[str, Any], authority: _LedgerEvent) -> str:
        authority_hash = payload.get("authority_hash")
        expected = authority.payload["authority_hash"]
        if authority_hash != expected:
            raise HotfixError("authority_hash does not match the latest authority envelope")
        return str(authority_hash)

    def _artifacts(self, payload: dict[str, Any]) -> list[dict[str, str]]:
        raw = payload.get("artifacts", [])
        if not isinstance(raw, list):
            raise HotfixError("artifacts must be a list")
        artifacts: list[dict[str, str]] = []
        names: set[str] = set()
        for item in raw:
            if not isinstance(item, dict):
                raise HotfixError("each artifact must be an object")
            name = _text(item, "name")
            if name in names:
                raise HotfixError(f"artifact name {name!r} is duplicated")
            names.add(name)
            artifacts.append({"name": name, "sha256": self._sha256(item, "sha256")})
        return artifacts

    def _append(
        self,
        command: HotfixCommand,
        *,
        expected: HotfixState | tuple[HotfixState, ...],
        new_state: HotfixState,
        payload: dict[str, Any],
        content: str,
        data: dict[str, Any] | None = None,
    ) -> HotfixReceipt:
        case_id = self._case_id(command)
        idempotency_key = (command.idempotency_key or "").strip()
        if not idempotency_key:
            raise HotfixError("mutating hotfix commands require idempotency_key")
        action = HotfixAction(command.action)
        expected_states = (expected,) if isinstance(expected, HotfixState) else expected
        request = self._command_request(command, action)

        def _record() -> dict[str, Any]:
            current = self._events(command.wing, case_id)
            latest = current[-1]
            if latest.state not in expected_states:
                allowed = ", ".join(state.value for state in expected_states)
                raise HotfixError(
                    f"hotfix {case_id} is {latest.state.value}; {action.value} requires {allowed}"
                )
            parent_id = latest.drawer.id
            if parent_id is None:
                raise HotfixError(f"hotfix {case_id} has an event without a drawer id")
            fingerprint = str(current[0].drawer.metadata["fingerprint"])
            failure_class = str(current[0].drawer.metadata["failure_class"])
            event_digest = _event_hash(
                wing=command.wing,
                case_id=case_id,
                kind=action,
                state=new_state,
                fingerprint=fingerprint,
                failure_class=failure_class,
                payload=payload,
                previous_event_hash=latest.event_hash,
                parent_drawer_id=parent_id,
                content=content,
            )
            saved = self._store.add(
                Drawer(
                    wing=command.wing,
                    room=HOTFIX_ROOM,
                    content=content,
                    layer=Layer.ON_DEMAND,
                    metadata={
                        "hotfix_schema": HOTFIX_SCHEMA,
                        "case_id": case_id,
                        "kind": action.value,
                        "state": new_state.value,
                        "fingerprint": fingerprint,
                        "failure_class": failure_class,
                        "open_question": new_state not in _TERMINAL_STATES,
                        "previous_event_hash": latest.event_hash,
                        "event_hash": event_digest,
                        "payload": payload,
                    },
                    supersedes_id=parent_id,
                )
            )
            if saved.id is None:
                raise HotfixError("hotfix event was stored without a drawer id")
            attempt_count = sum(
                event.kind is HotfixAction.RECORD_ATTEMPT for event in current
            ) + int(action is HotfixAction.RECORD_ATTEMPT)
            max_attempts = current[0].payload["max_attempts"]
            requires_rollback = self._requires_rollback(current, new_state)
            next_action = self._next_action(
                new_state,
                attempts=attempt_count,
                max_attempts=max_attempts,
                requires_rollback=requires_rollback,
            )
            receipt_data = data or {}
            card_lines = [
                f"Hotfix {case_id}",
                f"Action: {action.value}",
                f"State: {new_state.value}",
            ]
            selected = receipt_data.get("selected_candidate")
            if isinstance(selected, str):
                card_lines.append(f"Recommended: {selected}")
            legal_actions = self._legal_actions(
                new_state,
                attempts=attempt_count,
                max_attempts=max_attempts,
            )
            card_lines.append(f"Next legal action: {next_action}")
            return {
                "case_id": case_id,
                "action": action.value,
                "state": new_state.value,
                "fingerprint": fingerprint,
                "failure_class": failure_class,
                "drawer_id": saved.id,
                "next_action": next_action,
                "legal_actions": list(legal_actions),
                "card": "\n".join(card_lines),
                "data": receipt_data,
            }

        execution = self._store.execute_once(
            idempotency_key=f"hotfix:{idempotency_key}",
            operation=f"hotfix.{action.value}",
            request=request,
            action=_record,
        )
        return self._receipt_from_execution(execution)

    @staticmethod
    def _command_request(command: HotfixCommand, action: HotfixAction) -> dict[str, Any]:
        return {
            "wing": command.wing,
            "case_id": command.case_id,
            "action": action.value,
            "payload": command.payload,
        }

    def _committed_replay(
        self, command: HotfixCommand, action: HotfixAction
    ) -> HotfixReceipt | None:
        idempotency_key = (command.idempotency_key or "").strip()
        if not idempotency_key:
            return None
        durable_key = f"hotfix:{idempotency_key}"
        receipt = self._store.workflow_receipt(durable_key)
        if receipt is None or receipt.state is not WorkflowState.COMMITTED:
            return None

        def _must_not_run() -> dict[str, Any]:
            raise HotfixError("committed hotfix replay unexpectedly attempted execution")

        execution = self._store.execute_once(
            idempotency_key=durable_key,
            operation=f"hotfix.{action.value}",
            request=self._command_request(command, action),
            action=_must_not_run,
        )
        return self._receipt_from_execution(execution)

    @staticmethod
    def _receipt_from_execution(execution: WorkflowExecution) -> HotfixReceipt:
        result = execution.result
        try:
            state = HotfixState(str(result["state"]))
            result_action = HotfixAction(str(result["action"]))
            event_id = int(result["drawer_id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise HotfixError("hotfix workflow returned an invalid durable receipt") from exc
        result_data = result.get("data", {})
        if not isinstance(result_data, dict):
            raise HotfixError("hotfix workflow receipt data is not an object")
        return HotfixReceipt(
            case_id=str(result["case_id"]),
            action=result_action,
            state=state,
            fingerprint=str(result["fingerprint"]),
            failure_class=str(result["failure_class"]),
            event_drawer_id=event_id,
            replayed=execution.replayed,
            next_action=str(result["next_action"]),
            card=str(result["card"]),
            legal_actions=tuple(str(action) for action in result.get("legal_actions", [])),
            data=result_data,
        )

    def _evidence_ids(
        self,
        payload: dict[str, Any],
        key: str,
        *,
        wing: str,
        required: bool = False,
    ) -> tuple[int, ...]:
        raw = payload.get(key, [])
        if not isinstance(raw, list) or any(
            isinstance(item, bool) or not isinstance(item, int) or item < 1 for item in raw
        ):
            raise HotfixError(f"{key} must be a list of positive drawer ids")
        ids = tuple(dict.fromkeys(raw))
        if required and not ids:
            raise HotfixError(f"{key} must cite at least one drawer")
        for drawer_id in ids:
            drawer = self._store.get(drawer_id)
            if drawer is None:
                raise HotfixError(f"evidence drawer #{drawer_id} does not exist")
            if drawer.wing != wing:
                raise HotfixError(
                    f"evidence drawer #{drawer_id} belongs to wing {drawer.wing!r}, not {wing!r}"
                )
        return ids

    def _precedent(
        self,
        current: _LedgerEvent,
        wing: str,
        precedent_case_id: str,
    ) -> dict[str, Any]:
        precedent = self._events(wing, precedent_case_id)
        if precedent[-1].state is not HotfixState.COMPLETE:
            raise HotfixError(
                f"precedent {precedent_case_id!r} is {precedent[-1].state.value}, not complete"
            )
        current_meta = current.drawer.metadata
        precedent_meta = precedent[0].drawer.metadata
        if current_meta["fingerprint"] == precedent_meta["fingerprint"]:
            strength = 3
        elif (
            current_meta["failure_class"] == precedent_meta["failure_class"]
            and str(current.payload["stage"]).lower() == str(precedent[0].payload["stage"]).lower()
        ):
            strength = 2
        elif current_meta["failure_class"] == precedent_meta["failure_class"]:
            strength = 1
        else:
            strength = 0
        settlement = self._last(precedent, HotfixAction.SETTLE)
        return {
            "case_id": precedent_case_id,
            "strength": strength,
            "resolution": settlement.payload["resolution"],
            "observed_outcome": settlement.payload["observed_outcome"],
            "evidence_ids": settlement.payload["evidence_ids"],
        }

    def _status(self, command: HotfixCommand) -> HotfixReceipt:
        case_id = self._case_id(command)
        events = self._events(command.wing, case_id)
        first = events[0]
        latest = events[-1]
        acceptance = first.payload["acceptance"]
        if not isinstance(acceptance, list):
            raise HotfixError(f"hotfix {case_id} has invalid acceptance inventory")
        attempts = sum(event.kind is HotfixAction.RECORD_ATTEMPT for event in events)
        max_attempts = first.payload["max_attempts"]
        passed = 0
        for event in reversed(events):
            if event.kind is HotfixAction.VERIFY:
                results = event.payload.get("results", {})
                if isinstance(results, dict):
                    passed = sum(
                        isinstance(result, dict) and result.get("verdict") == "pass"
                        for result in results.values()
                    )
                break
        requires_rollback = self._requires_rollback(events, latest.state)
        next_action = self._next_action(
            latest.state,
            attempts=attempts,
            max_attempts=max_attempts,
            requires_rollback=requires_rollback,
        )
        title = first.payload["title"]
        stage = first.payload["stage"]
        card = (
            f"Hotfix {case_id}: {title}\n"
            f"State: {latest.state.value}\n"
            f"Stage: {stage}\n"
            f"Class: {first.drawer.metadata['failure_class']}\n"
            f"Fingerprint: {first.drawer.metadata['fingerprint']}\n"
            f"Attempts: {attempts}/{max_attempts}\n"
            f"Acceptance: {passed}/{len(acceptance)}\n"
            f"Next legal action: {next_action}"
        )
        latest_id = latest.drawer.id
        if latest_id is None:
            raise HotfixError(f"hotfix {case_id} has an event without a drawer id")
        data: dict[str, Any] = {
            "attempts": attempts,
            "max_attempts": max_attempts,
            "acceptance_passed": passed,
            "acceptance_total": len(acceptance),
            "acceptance_hash": _hash({"acceptance": acceptance}),
        }
        if latest.kind is HotfixAction.SETTLE:
            data["settlement"] = latest.payload
        return HotfixReceipt(
            case_id=case_id,
            action=HotfixAction.STATUS,
            state=latest.state,
            fingerprint=str(first.drawer.metadata["fingerprint"]),
            failure_class=str(first.drawer.metadata["failure_class"]),
            event_drawer_id=latest_id,
            replayed=False,
            next_action=next_action,
            card=card,
            legal_actions=self._legal_actions(
                latest.state,
                attempts=attempts,
                max_attempts=max_attempts,
            ),
            data=data,
        )

    @staticmethod
    def _case_id(command: HotfixCommand) -> str:
        case_id = (command.case_id or "").strip()
        if not case_id:
            action = HotfixAction(command.action)
            raise HotfixError(f"hotfix action {action.value!r} requires case_id")
        return case_id

    def _events(self, wing: str, case_id: str) -> list[_LedgerEvent]:
        drawers = [
            drawer
            for drawer in self._store.list_by(wing=wing, room=HOTFIX_ROOM, limit=None)
            if drawer.metadata.get("hotfix_schema") == HOTFIX_SCHEMA
            and drawer.metadata.get("case_id") == case_id
        ]
        drawers.sort(key=lambda drawer: drawer.id or 0)
        if not drawers:
            raise HotfixError(f"hotfix {case_id!r} does not exist in wing {wing!r}")

        events: list[_LedgerEvent] = []
        previous_hash: str | None = None
        previous_id: int | None = None
        fingerprint = str(drawers[0].metadata.get("fingerprint", ""))
        failure_class = str(drawers[0].metadata.get("failure_class", ""))
        for index, drawer in enumerate(drawers):
            metadata = drawer.metadata
            try:
                kind = HotfixAction(str(metadata["kind"]))
                state = HotfixState(str(metadata["state"]))
                payload = metadata["payload"]
                stored_hash = str(metadata["event_hash"])
            except (KeyError, ValueError) as exc:
                raise HotfixError(f"hotfix {case_id} event #{drawer.id} is malformed") from exc
            if not isinstance(payload, dict):
                raise HotfixError(f"hotfix {case_id} event #{drawer.id} payload is not an object")
            if index == 0 and kind is not HotfixAction.OPEN:
                raise HotfixError(f"hotfix {case_id} does not begin with an open event")
            if metadata.get("previous_event_hash") != previous_hash:
                raise HotfixError(f"hotfix {case_id} event hash chain is forked or out of order")
            if drawer.supersedes_id != previous_id:
                raise HotfixError(f"hotfix {case_id} supersession chain is forked or out of order")
            actual_hash = _event_hash(
                wing=wing,
                case_id=case_id,
                kind=kind,
                state=state,
                fingerprint=str(metadata.get("fingerprint", "")),
                failure_class=str(metadata.get("failure_class", "")),
                payload=payload,
                previous_event_hash=previous_hash,
                parent_drawer_id=previous_id,
                content=drawer.content,
            )
            if stored_hash != actual_hash:
                raise HotfixError(
                    f"hotfix {case_id} event #{drawer.id} failed integrity validation"
                )
            if (
                metadata.get("fingerprint") != fingerprint
                or metadata.get("failure_class") != failure_class
            ):
                raise HotfixError(f"hotfix {case_id} identity changed inside its event chain")
            expected_open_question = state not in _TERMINAL_STATES
            if metadata.get("open_question") is not expected_open_question:
                raise HotfixError(
                    f"hotfix {case_id} event #{drawer.id} has invalid open-state metadata"
                )
            events.append(
                _LedgerEvent(
                    drawer=drawer,
                    kind=kind,
                    state=state,
                    payload=payload,
                    event_hash=stored_hash,
                )
            )
            previous_hash = stored_hash
            previous_id = drawer.id
        return events

    @staticmethod
    def _requires_rollback(events: list[_LedgerEvent], state: HotfixState) -> bool:
        if state is not HotfixState.REPAIR_REQUIRED:
            return False
        attempts = [event for event in events if event.kind is HotfixAction.RECORD_ATTEMPT]
        return bool(
            attempts
            and attempts[-1].payload["state_hash_before"]
            != attempts[-1].payload["state_hash_after"]
        )

    @staticmethod
    def _next_action(
        state: HotfixState,
        *,
        attempts: int = 0,
        max_attempts: int = 2,
        requires_rollback: bool = False,
    ) -> str:
        if state is HotfixState.REPAIR_REQUIRED:
            if attempts >= max_attempts:
                return (
                    HotfixAction.ROLLBACK.value if requires_rollback else HotfixAction.SETTLE.value
                )
            return HotfixAction.AUTHORIZE.value
        if state is HotfixState.ROLLED_BACK and attempts >= max_attempts:
            return HotfixAction.SETTLE.value
        return {
            HotfixState.OPEN: HotfixAction.RECOMMEND.value,
            HotfixState.RECOMMENDED: HotfixAction.AUTHORIZE.value,
            HotfixState.AUTHORIZED: HotfixAction.PREFLIGHT.value,
            HotfixState.PREFLIGHTED: HotfixAction.RECORD_ATTEMPT.value,
            HotfixState.ATTEMPTED: HotfixAction.VERIFY.value,
            HotfixState.REPAIR_REQUIRED: HotfixAction.AUTHORIZE.value,
            HotfixState.ROLLED_BACK: HotfixAction.AUTHORIZE.value,
            HotfixState.VERIFIED: HotfixAction.SETTLE.value,
            HotfixState.COMPLETE: "none (terminal)",
            HotfixState.BLOCKED: "none (terminal)",
            HotfixState.EXHAUSTED: "none (terminal)",
        }[state]

    @staticmethod
    def _legal_actions(
        state: HotfixState,
        *,
        attempts: int = 0,
        max_attempts: int = 2,
    ) -> tuple[str, ...]:
        if state is HotfixState.REPAIR_REQUIRED:
            actions = [HotfixAction.ROLLBACK.value, HotfixAction.SETTLE.value]
            if attempts < max_attempts:
                actions.insert(0, HotfixAction.AUTHORIZE.value)
            return tuple(actions)
        if state is HotfixState.ROLLED_BACK:
            actions = [HotfixAction.SETTLE.value]
            if attempts < max_attempts:
                actions.insert(0, HotfixAction.AUTHORIZE.value)
            return tuple(actions)
        return {
            HotfixState.OPEN: (HotfixAction.RECOMMEND.value, HotfixAction.SETTLE.value),
            HotfixState.RECOMMENDED: (
                HotfixAction.AUTHORIZE.value,
                HotfixAction.SETTLE.value,
            ),
            HotfixState.AUTHORIZED: (
                HotfixAction.PREFLIGHT.value,
                HotfixAction.SETTLE.value,
            ),
            HotfixState.PREFLIGHTED: (
                HotfixAction.RECORD_ATTEMPT.value,
                HotfixAction.SETTLE.value,
            ),
            HotfixState.ATTEMPTED: (
                HotfixAction.VERIFY.value,
                HotfixAction.ROLLBACK.value,
            ),
            HotfixState.REPAIR_REQUIRED: (),
            HotfixState.ROLLED_BACK: (),
            HotfixState.VERIFIED: (HotfixAction.SETTLE.value,),
            HotfixState.COMPLETE: (),
            HotfixState.BLOCKED: (),
            HotfixState.EXHAUSTED: (),
        }[state]
