"""Durable, unverified human checklist records for PALADIN runs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from functools import wraps
from inspect import signature
from pathlib import Path
from typing import Any, ParamSpec, TypeVar
from uuid import UUID

from cairntir._paladin_contract import canonical_sha
from cairntir.durability import WorkflowState, request_hash
from cairntir.errors import CairntirError
from cairntir.memory.taxonomy import Drawer
from cairntir.paladin_python import PaladinPythonRun

_P = ParamSpec("_P")
_T = TypeVar("_T")
_SCHEMA = "cairntir.paladin-human-capabilities.v1"


class HumanWallError(CairntirError):
    """A human checklist binding or evidence record is invalid."""


def _boundary(function: Callable[_P, _T]) -> Callable[_P, _T]:
    declared = signature(function)

    @wraps(function)
    def call(*args: _P.args, **kwargs: _P.kwargs) -> _T:
        declared.bind(*args, **kwargs)
        try:
            return function(*args, **kwargs)
        except (CairntirError, OSError, ValueError, TypeError, KeyError) as exc:
            if isinstance(exc, HumanWallError):
                raise
            raise HumanWallError(str(exc)) from exc

    return call


def _nonempty(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise HumanWallError(f"{name} must be a non-empty string")
    value.encode("utf-8")
    return value


class HumanWallRun:
    """Record routing and submissions without claiming operator authority."""

    @_boundary
    def __init__(self, paladin_run: PaladinPythonRun, *, capability_map: dict[str, Any]) -> None:
        """Bind a generated checklist to one immutable PALADIN run."""
        if not isinstance(paladin_run, PaladinPythonRun):
            raise HumanWallError("paladin_run must be a PaladinPythonRun")
        self._paladin = paladin_run
        self._store = paladin_run._store
        self._plan = paladin_run._plan
        self._run_id = paladin_run._run_id
        self._attempt_id = paladin_run._attempt["attempt_id"]
        self._plan_sha256 = paladin_run._checked.plan_sha256
        self._wing = self._plan["wing"]
        self._room = paladin_run._runtime._room
        self._human = {item["id"]: item for item in self._plan["human_items"]}
        self._map = self._validate_map(capability_map)
        self._map_sha256 = canonical_sha(self._map)
        self._map_key = f"paladin.human.map:{self._run_id}"
        self._base()
        self._check_map()

    def _validate_map(self, mapping: object) -> dict[str, Any]:
        if not isinstance(mapping, dict) or mapping.keys() != {"schema", "checks"}:
            raise HumanWallError("invalid capability map fields")
        if mapping["schema"] != _SCHEMA or not isinstance(mapping["checks"], list):
            raise HumanWallError("invalid capability map schema")
        expected = {stage["stage_id"]: "automated" for stage in self._plan["stages"]}
        if set(expected) & self._human.keys():
            raise HumanWallError("human and automated check IDs overlap")
        expected.update(dict.fromkeys(self._human, "human"))
        checks: dict[str, dict[str, Any]] = {}
        for item in mapping["checks"]:
            if not isinstance(item, dict) or item.keys() != {
                "id",
                "kind",
                "capability",
                "required",
            }:
                raise HumanWallError("invalid capability check fields")
            item_id = _nonempty(item["id"], "check ID")
            if (
                item_id in checks
                or expected.get(item_id) != item["kind"]
                or item["required"] is not True
            ):
                raise HumanWallError("duplicate, extra, optional or wrong-kind check")
            checks[item_id] = {
                "id": item_id,
                "kind": item["kind"],
                "capability": _nonempty(item["capability"], "capability"),
                "required": True,
            }
        if checks.keys() != expected.keys():
            raise HumanWallError("capability map is missing checks")
        return {"schema": _SCHEMA, "checks": [checks[key] for key in sorted(checks)]}

    def _base(self) -> dict[str, Any]:
        report = self._paladin.report()
        if (report["run_id"], report["attempt_id"], report["plan_sha256"]) != (
            self._run_id,
            self._attempt_id,
            self._plan_sha256,
        ):
            raise HumanWallError("PALADIN report differs from bound run")
        return report

    def _identity(self, item_id: str | None = None) -> dict[str, Any]:
        value: dict[str, Any] = {
            "run_id": self._run_id,
            "attempt_id": self._attempt_id,
            "plan_sha256": self._plan_sha256,
            "map_sha256": self._map_sha256,
        }
        if item_id is not None:
            value["item_id"] = item_id
        return value

    def _map_request(self) -> dict[str, Any]:
        return {
            "run_id": self._run_id,
            "plan_sha256": self._plan_sha256,
            "map_sha256": self._map_sha256,
            "capability_map": self._map,
        }

    @staticmethod
    def _metadata(operation: str, key: str, request: dict[str, Any]) -> dict[str, Any]:
        return {
            "kind": "paladin.human",
            "operation": operation,
            "key": key,
            "run_id": request["run_id"],
            "attempt_id": request.get("attempt_id"),
            "plan_sha256": request["plan_sha256"],
            "map_sha256": request["map_sha256"],
            "item_id": request.get("item_id"),
        }

    @staticmethod
    def _body(operation: str, request: dict[str, Any], result: dict[str, Any]) -> str:
        return json.dumps(
            {"operation": operation, "request_sha256": request_hash(request), "result": result},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )

    def _load(self, key: str, operation: str) -> dict[str, Any] | None:
        receipt = self._store.paladin_human_receipt(key, wing=self._wing)
        if receipt is None:
            return None
        record = receipt.result
        if (
            receipt.state is not WorkflowState.COMMITTED
            or receipt.operation != operation
            or not isinstance(record, dict)
            or record.keys() != {"request", "result", "evidence"}
            or not isinstance(record["request"], dict)
            or not isinstance(record["result"], dict)
            or not isinstance(record["evidence"], dict)
            or receipt.request_hash != request_hash(record["request"])
        ):
            raise HumanWallError("invalid human checklist registry binding")
        drawer = self._paladin._verify_reference(record["evidence"])
        if drawer.content != self._body(operation, record["request"], record["result"]) or (
            drawer.metadata != self._metadata(operation, key, record["request"])
        ):
            raise HumanWallError("human checklist drawer differs from receipt")
        return record

    def _check_map(self) -> None:
        request = self._map_request()
        if self._store.paladin_human_pending_map(self._map_key, wing=self._wing, request=request):
            return
        record = self._load(self._map_key, "paladin.human.map.v1")
        if record is not None and record["request"] != request:
            raise HumanWallError("run is already bound to another capability map")

    def _save(
        self,
        key: str,
        operation: str,
        request: dict[str, Any],
        produce: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        if self._store.transaction_active:
            raise HumanWallError("human checklist cannot write inside caller transaction")

        def append() -> dict[str, Any]:
            result = produce()
            drawer = self._store.add(
                Drawer(
                    wing=self._wing,
                    room=self._room,
                    content=self._body(operation, request, result),
                    metadata=self._metadata(operation, key, request),
                )
            )
            if drawer.id is None:
                raise HumanWallError("human checklist drawer has no persisted identity")
            return {
                "request": request,
                "result": result,
                "evidence": self._paladin._reference(drawer.id),
            }

        self._store.paladin_human_execute_once(
            wing=self._wing,
            room=self._room,
            idempotency_key=key,
            operation=operation,
            request=request,
            action=append,
        )
        record = self._load(key, operation)
        if record is None or record["request"] != request:
            raise HumanWallError("human checklist result was not committed")
        return record

    def _bind_map(self) -> None:
        self._save(
            self._map_key,
            "paladin.human.map.v1",
            self._map_request(),
            lambda: {"map_sha256": self._map_sha256},
        )

    def _records(self) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        assignments: dict[str, dict[str, Any]] = {}
        submissions: dict[str, dict[str, Any]] = {}
        for drawer in sorted(
            self._store.paladin_human_drawers(wing=self._wing), key=lambda item: item.id or 0
        ):
            meta = drawer.metadata
            if (
                meta.get("kind") != "paladin.human"
                or meta.get("run_id") != self._run_id
                or (meta.get("attempt_id") != self._attempt_id)
            ):
                continue
            key, operation = meta.get("key"), meta.get("operation")
            prefixes = {
                "paladin.human.assign.v1": "paladin.human.assignment:",
                "paladin.human.submit.v1": "paladin.human.submission:",
            }
            if (
                not isinstance(operation, str)
                or operation not in prefixes
                or not isinstance(key, str)
                or not key.startswith(prefixes[operation])
            ):
                continue
            # Only the drawer its own committed receipt names is a checklist
            # record; any other drawer carrying lookalike metadata is ignored.
            record = self._load(key, operation)
            if record is None or record["evidence"]["drawer_id"] != drawer.id:
                continue
            request = record["request"]
            item_id = request.get("item_id")
            if item_id not in self._human or any(
                request.get(name) != expected for name, expected in self._identity().items()
            ):
                raise HumanWallError("human checklist record belongs to another binding")
            if operation == "paladin.human.assign.v1":
                previous = assignments.get(item_id)
                expected_prior = previous["evidence"]["drawer_id"] if previous else 0
                if request.get("prior_assignment_id") != expected_prior or record["result"].get(
                    "assignee"
                ) != request.get("assignee"):
                    raise HumanWallError("human assignment chain is inconsistent")
                assignments[item_id] = record
            else:
                if record["result"].get("evidence_sha256") != request.get("evidence_sha256") or (
                    record["result"].get("submission_id") != request.get("submission_id")
                ):
                    raise HumanWallError("human submission receipt is inconsistent")
                submissions[item_id] = record
        return assignments, submissions

    def _rows(self, base: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        assignments, submissions = self._records()
        caps = {check["id"]: check["capability"] for check in self._map["checks"]}
        human = []
        for item in self._plan["human_items"]:
            item_id = item["id"]
            assignment, submission = assignments.get(item_id), submissions.get(item_id)
            state, diagnostics, submitted = "PENDING", [], None
            if submission is not None:
                saved = submission["request"]
                submitted = {**submission["result"], "evidence": submission["evidence"]}
                try:
                    if (
                        hashlib.sha256(Path(saved["evidence_path"]).read_bytes()).hexdigest()
                        != saved["evidence_sha256"]
                    ):
                        diagnostics.append("submitted evidence bytes changed")
                except OSError as exc:
                    diagnostics.append(f"submitted evidence is unavailable: {exc}")
                state = "STALE" if diagnostics else "SUBMITTED"
            human.append(
                {
                    "id": item_id,
                    "description": item["description"],
                    "capability": caps[item_id],
                    "required": True,
                    "assigned_to": assignment["result"]["assignee"] if assignment else None,
                    "state": state,
                    "submission": submitted,
                    "diagnostics": diagnostics,
                }
            )
        stage_state = {stage["stage_id"]: stage["status"] for stage in base["stages"]}
        automated = [
            {
                "id": stage["stage_id"],
                "capability": caps[stage["stage_id"]],
                "required": True,
                "status": stage_state[stage["stage_id"]],
            }
            for stage in self._plan["stages"]
        ]
        return human, automated

    @_boundary
    def checklist(self) -> dict[str, Any]:
        """Return current human and automated checks without writing."""
        self._check_map()
        human, automated = self._rows(self._base())
        return {
            "schema": "cairntir.paladin-human-checklist.v1",
            **self._identity(),
            "human_items": human,
            "automated_items": automated,
        }

    @_boundary
    def assign(self, item_id: str, *, assignee: str) -> dict[str, Any]:
        """Persist a routing assignment without operator approval."""
        if item_id not in self._human:
            raise HumanWallError("unknown human checklist item")
        assignee = _nonempty(assignee, "assignee")
        self._base()
        self._check_map()
        assignments, _ = self._records()
        previous = assignments.get(item_id)
        if previous is not None and previous["result"]["assignee"] == assignee:
            return {**previous["result"], "evidence": previous["evidence"]}
        self._bind_map()
        prior_id = previous["evidence"]["drawer_id"] if previous else 0
        request = {**self._identity(item_id), "assignee": assignee, "prior_assignment_id": prior_id}
        item_key = request_hash(
            {"run_id": self._run_id, "attempt_id": self._attempt_id, "item_id": item_id}
        )
        record = self._save(
            f"paladin.human.assignment:{item_key}:{prior_id}",
            "paladin.human.assign.v1",
            request,
            lambda: {
                **self._identity(item_id),
                "assignee": assignee,
                "assigned_at": datetime.now(UTC).isoformat(),
                "authority_verified": False,
            },
        )
        return {**record["result"], "evidence": record["evidence"]}

    @_boundary
    def submit(
        self, item_id: str, *, evidence_path: Path, submission_id: str, operator_claim: str
    ) -> dict[str, Any]:
        """Persist the actual evidence bytes as an unverified submission."""
        if item_id not in self._human:
            raise HumanWallError("unknown human checklist item")
        submission_id = str(UUID(_nonempty(submission_id, "submission ID")))
        operator_claim = _nonempty(operator_claim, "operator claim")
        path = Path(evidence_path).resolve(strict=True)
        if not path.is_file():
            raise HumanWallError("submitted evidence path is not a file")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        self._base()
        self._check_map()
        self._bind_map()
        request = {
            **self._identity(item_id),
            "submission_id": submission_id,
            "evidence_path": str(path),
            "evidence_sha256": digest,
            "operator_claim": operator_claim,
        }
        record = self._save(
            f"paladin.human.submission:{submission_id}",
            "paladin.human.submit.v1",
            request,
            lambda: {
                **self._identity(item_id),
                "submission_id": submission_id,
                "evidence_path": str(path),
                "evidence_sha256": digest,
                "operator_claim": operator_claim,
                "submitted_at": datetime.now(UTC).isoformat(),
                "authority_verified": False,
            },
        )
        return {**record["result"], "evidence": record["evidence"]}

    @_boundary
    def report(self) -> dict[str, Any]:
        """Recheck submissions and retain the PALADIN outcome."""
        self._check_map()
        base = self._base()
        human, automated = self._rows(base)
        return {
            "schema": "cairntir.paladin-human-wall-report.v1",
            **self._identity(),
            "human_items": human,
            "automated_items": automated,
            "human_gate": "PENDING",
            "authority_verified": False,
            "outcome": base["outcome"],
            "paladin_outcome": base["outcome"],
            "disposition": base["disposition"],
        }


__all__ = ["HumanWallError", "HumanWallRun"]
