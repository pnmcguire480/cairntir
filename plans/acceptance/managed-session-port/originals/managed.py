"""Acknowledged intake and durable intent for explicitly configured local actions."""

from __future__ import annotations

import hashlib
import json
import subprocess
import threading
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path
from typing import Any, ParamSpec, TypeVar, cast
from uuid import UUID, uuid4

from cairntir.access import ScopedStore
from cairntir.durability import WorkflowExecution
from cairntir.errors import CairntirError
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer, _validate_ident
from cairntir.provenance import Sensitivity
from cairntir.tasks import TaskBook

_P = ParamSpec("_P")
_T = TypeVar("_T")
_Store = DrawerStore | ScopedStore


class ManagedRuntimeError(CairntirError):
    """A managed request could not meet its capture or execution contract."""


def _boundary(function: Callable[_P, _T]) -> Callable[_P, _T]:
    @wraps(function)
    def call(*args: _P.args, **kwargs: _P.kwargs) -> _T:
        try:
            return function(*args, **kwargs)
        except (CairntirError, OSError, ValueError) as exc:
            if isinstance(exc, ManagedRuntimeError):
                raise
            raise ManagedRuntimeError(str(exc)) from exc

    return call


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManagedRuntimeError(f"{name} must be nonblank text")
    value.encode("utf-8")
    return value


def _uuid(value: object, name: str) -> str:
    value = _text(value, name)
    if str(UUID(value)) != value:
        raise ManagedRuntimeError(f"{name} must be a canonical UUID")
    return value


def _integer(value: object, name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ManagedRuntimeError(f"{name} must be an integer in {minimum}..{maximum}")
    return value


def _fields(value: object, schema: str, names: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or value.keys() != names | {"schema"}:
        raise ManagedRuntimeError("request fields do not match the schema")
    if value["schema"] != schema:
        raise ManagedRuntimeError("request schema does not match")
    return deepcopy(value)


def _public(record: dict[str, Any], replayed: bool | None = None) -> dict[str, Any]:
    result = deepcopy({key: value for key, value in record.items() if key != "_managed"})
    if replayed is not None:
        result["replayed"] = replayed
    return result


def _configuration(value: object) -> dict[str, Any]:
    config = _fields(
        value,
        "cairntir.managed-config.v1",
        {"wing", "room", "project_root", "brief_budget_chars", "profiles"},
    )
    for name in ("wing", "room"):
        _validate_ident(config[name], name)
    root = Path(_text(config["project_root"], "project_root"))
    if not root.is_absolute() or not root.is_dir():
        raise ManagedRuntimeError("project_root must be an existing absolute directory")
    config["project_root"] = str(root.resolve())
    _integer(config["brief_budget_chars"], "brief_budget_chars", 1024, 262144)
    profiles = config["profiles"]
    if not isinstance(profiles, dict) or not profiles:
        raise ManagedRuntimeError("profiles must be a nonempty mapping")
    for name, profile in profiles.items():
        _validate_ident(name, "profile")
        if not isinstance(profile, dict) or profile.keys() != {
            "argv",
            "cwd",
            "timeout_seconds",
            "output_limit_bytes",
        }:
            raise ManagedRuntimeError("profile fields do not match the schema")
        argv = profile["argv"]
        if not isinstance(argv, list) or not argv:
            raise ManagedRuntimeError("argv must be a nonempty list")
        for argument in argv:
            if not isinstance(argument, str) or "\x00" in argument:
                raise ManagedRuntimeError("argv must contain valid argument strings")
            argument.encode("utf-8")
        executable = Path(argv[0])
        cwd = Path(_text(profile["cwd"], "cwd"))
        if not executable.is_absolute() or not executable.is_file():
            raise ManagedRuntimeError("executable must be an existing absolute file")
        if (
            not cwd.is_absolute()
            or not cwd.is_dir()
            or not cwd.resolve().is_relative_to(root.resolve())
        ):
            raise ManagedRuntimeError("cwd must be an existing directory within project_root")
        argv[0] = str(executable.resolve())
        profile["cwd"] = str(cwd.resolve())
        _integer(profile["timeout_seconds"], "timeout_seconds", 1, 300)
        _integer(profile["output_limit_bytes"], "output_limit_bytes", 1, 1048576)
        profile["executable_sha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()
    return config


class ManagedRuntime:
    """Save exact producer events before allowing an acknowledged configured action."""

    @_boundary
    def __init__(self, store: _Store, *, config: object) -> None:
        """Bind a store and an immutable copy of trusted startup configuration."""
        self._store = store
        self._input_config = deepcopy(config)
        self._config = _configuration(config)
        self._config_sha = _sha(_json(self._config))
        self._wing = self._config["wing"]
        self._room = self._config["room"]
        self._book = TaskBook(cast(DrawerStore, store))
        self._session: str | None = None
        self._epoch = str(uuid4())
        self._task_id: str | None = None
        self._closed = False
        self._latest: dict[str, Any] | None = None
        self._pending_captures: set[str] = set()

    def _authorize(self) -> None:
        if isinstance(self._store, ScopedStore):
            for capability in ("read", "write"):
                self._store.authorize(capability, wing=self._wing, room=self._room)

    def _check(self) -> None:
        self._authorize()
        if self._session is None or self._closed:
            raise ManagedRuntimeError("managed runtime is not active")
        if _sha(_json(_configuration(self._input_config))) != self._config_sha:
            raise ManagedRuntimeError("configured executable or profile has changed")

    def _records(self, operation: str | None = None) -> list[dict[str, Any]]:
        records = self._store._managed_records(wing=self._wing)
        return [
            item
            for item in records
            if operation is None or item["_managed"]["operation"] == f"managed.{operation}.v1"
        ]

    def _execute(
        self,
        operation: str,
        key: str,
        request: dict[str, Any],
        action: Callable[[], tuple[dict[str, Any], list[int]]],
    ) -> WorkflowExecution:
        bound = {"wing": self._wing, "room": self._room, "request": request}

        def append() -> dict[str, Any]:
            result, evidence = action()
            return {
                **result,
                "_managed": {
                    "operation": f"managed.{operation}.v1",
                    "request": bound,
                    "evidence_ids": evidence,
                    "epoch": self._epoch,
                    "session_id": self._session,
                },
            }

        return self._store.execute_once(
            idempotency_key=f"managed:{operation}:{key}",
            operation=f"managed.{operation}.v1",
            request=bound,
            action=append,
        )

    def _resume(self) -> dict[str, Any]:
        result: dict[str, Any] = json.loads(self._book.resume(self._wing, self._task_id, 262144))
        return result

    def _events(self) -> list[dict[str, Any]]:
        return [item for item in self._records("event") if item["session_id"] == self._session]

    def _uncertain(self) -> list[dict[str, Any]]:
        outcomes = {item["action_id"] for item in self._records("outcome")}
        return [
            {"action_id": item["action_id"], "prediction_drawer_id": item["prediction_drawer_id"]}
            for item in self._records("dispatch")
            if item["task_id"] == self._task_id and item["action_id"] not in outcomes
        ]

    def _state(self) -> dict[str, Any]:
        events = self._events()
        sequences = sorted({item["sequence"] for item in events})
        gaps = []
        previous = 0
        for number in sequences:
            if number > previous + 1:
                gaps.append([previous + 1, number - 1])
            previous = number
        return {
            "task": self._resume(),
            "uncertain_actions": self._uncertain(),
            "gap_ranges": gaps,
            "last_sequence": previous,
            "events": sorted((item["event_id"], item["sequence"]) for item in events),
            "config_sha256": self._config_sha,
            "pending_captures": self._pending(),
        }

    def _unclean_sessions(self) -> list[dict[str, Any]]:
        closed = {item["epoch"] for item in self._records("close")}
        sessions: dict[str, dict[str, Any]] = {}
        for record in self._records():
            epoch = record["_managed"]["epoch"]
            session = record["_managed"]["session_id"]
            task_id = record.get("task_id")
            if epoch == self._epoch or epoch in closed:
                continue
            if session != self._session and task_id != self._task_id:
                continue
            item = sessions.setdefault(
                epoch, {"session_id": session, "epoch": epoch, "task_id": None}
            )
            if task_id is not None:
                item["task_id"] = task_id
        return [sessions[key] for key in sorted(sessions)]

    @staticmethod
    def _capture_key(event: object) -> str:
        try:
            return _sha(json.dumps(event, ensure_ascii=True, sort_keys=True, allow_nan=False))
        except (TypeError, ValueError):
            return str(uuid4())

    def _pending(self) -> list[str]:
        keys = self._pending_captures.copy()
        for record in self._records("close"):
            if record["session_id"] == self._session:
                keys.update(record["pending_captures"])
        captured = {
            self._capture_key(event["_managed"]["request"]["request"]) for event in self._events()
        }
        return sorted(keys - captured)

    def _gaps(self, state: dict[str, Any]) -> tuple[list[int], int]:
        count = sum(end - start + 1 for start, end in state["gap_ranges"])
        limit = self._config["brief_budget_chars"] // 4
        gaps: list[int] = []
        for start, end in state["gap_ranges"]:
            gaps.extend(range(start, min(end + 1, start + limit - len(gaps))))
            if len(gaps) >= limit:
                break
        return gaps, count - len(gaps)

    @_boundary
    def start(self, session_id: str, *, task_id: str | None = None) -> dict[str, Any]:
        """Discover or explicitly select a task and emit a fresh-epoch brief."""
        self._authorize()
        if self._session is not None:
            raise ManagedRuntimeError("a runtime may start only once")
        self._session = _uuid(session_id, "session_id")
        if task_id is not None:
            _uuid(task_id, "task_id")
        self._task_id = task_id
        discovered = self._resume()
        if discovered["status"] == "ready":
            self._task_id = discovered["task_id"]
        return self.brief()

    def _verify_event(self, record: dict[str, Any]) -> None:
        key = record["drawer_id"]
        records = self._store._task_drawers([key])
        pair = records.get(key)
        if pair is None:
            raise ManagedRuntimeError("captured event evidence is unavailable")
        drawer, provenance = pair
        now = datetime.now(UTC)
        if (
            drawer.wing != self._wing
            or drawer.room != self._room
            or _sha(drawer.content) != record["content_sha256"]
            or self._store.portable_identity(key) != record["source_identity"]
            or provenance.sensitivity == Sensitivity.SECRET
            or (provenance.valid_from is not None and provenance.valid_from > now)
            or (provenance.valid_until is not None and provenance.valid_until <= now)
        ):
            raise ManagedRuntimeError("captured event identity or availability has changed")

    @_boundary
    def capture(self, event: object) -> dict[str, Any]:
        """Atomically save an exact producer event and the resulting task checkpoint."""
        self._check()
        capture_key = self._capture_key(event)
        self._pending_captures.add(capture_key)
        payload = _fields(
            event,
            "cairntir.managed-event.v1",
            {
                "event_id",
                "session_id",
                "sequence",
                "task_id",
                "expected_revision",
                "content",
            },
        )
        for name in ("event_id", "session_id"):
            _uuid(payload[name], name)
        _integer(payload["sequence"], "sequence", 1, 2**63 - 1)
        _integer(payload["expected_revision"], "expected_revision", 0, 2**63 - 1)
        _text(payload["content"], "content")
        if payload["task_id"] is not None:
            _uuid(payload["task_id"], "task_id")
        if payload["session_id"] != self._session:
            raise ManagedRuntimeError("event session does not match")

        def append() -> tuple[dict[str, Any], list[int]]:
            current = self._resume()
            creating = current["status"] == "none" and self._task_id is None
            if not creating and (
                current["status"] != "ready" or payload["task_id"] != self._task_id
            ):
                raise ManagedRuntimeError("event requires the selected active task")
            if creating and (payload["task_id"] is not None or payload["expected_revision"] != 0):
                raise ManagedRuntimeError("new task requires revision zero and no task_id")
            old = current["checkpoint"] if not creating else None
            checkpoint = {
                "expected_revision": payload["expected_revision"],
                "idempotency_key": f"managed-event:{payload['event_id']}",
                "status": "active",
                "completed": old["completed"] if old else [],
                "outstanding": [*(old["outstanding"] if old else []), payload["content"]],
                "next_action": "Resume the captured commitments with a fresh managed brief.",
                "evidence_ids": list(
                    dict.fromkeys(
                        [
                            *(old["evidence_ids"] if old else []),
                            *([old["checkpoint_drawer_id"]] if old else []),
                        ]
                    )
                ),
            }
            if not creating:
                checkpoint["task_id"] = self._task_id
            saved = json.loads(
                self._book.checkpoint(
                    self._wing,
                    self._room,
                    payload["content"],
                    checkpoint,
                )
            )
            key = saved["checkpoint_drawer_id"]
            return {
                "schema": "cairntir.managed-event-receipt.v1",
                "status": "committed",
                "wing": self._wing,
                "event_id": payload["event_id"],
                "session_id": self._session,
                "sequence": payload["sequence"],
                "content_sha256": _sha(payload["content"]),
                "task_id": saved["task_id"],
                "revision": saved["revision"],
                "drawer_id": key,
                "source_identity": self._store.portable_identity(key),
            }, [key]

        with self._store.transaction():
            self._execute(
                "sequence",
                f"{self._session}:{payload['sequence']}",
                payload,
                lambda: ({"session_id": self._session, "event_id": payload["event_id"]}, []),
            )
            result = self._execute("event", payload["event_id"], payload, append)
            self._verify_event(result.result)
            if self._task_id is not None and result.result["task_id"] != self._task_id:
                raise ManagedRuntimeError("event belongs to a different task")
        self._task_id = result.result["task_id"]
        self._latest = None
        self._pending_captures.discard(capture_key)
        return _public(result.result, result.replayed)

    @_boundary
    def brief(self) -> dict[str, Any]:
        """Return and register complete task evidence or an explicit bounded omission."""
        self._check()
        with self._store.transaction():
            state = self._state()
            task = state["task"]
            gaps, omitted = self._gaps(state)
            result = {
                "schema": "cairntir.managed-brief.v1",
                "session_id": self._session,
                "epoch": self._epoch,
                "brief_id": str(uuid4()),
                "wing": self._wing,
                "task_id": task["task_id"],
                "revision": task["revision"],
                "status": task["status"],
                "task": task,
                "uncertain_actions": state["uncertain_actions"],
                "gaps": gaps,
                "complete": task["status"] == "ready"
                and not gaps
                and not omitted
                and not state["pending_captures"],
                "state_sha256": _sha(_json(state)),
                "unclean_sessions": self._unclean_sessions(),
                "pending_captures": state["pending_captures"],
            }
            result["brief_sha256"] = _sha(_json(result))
            limit = self._config["brief_budget_chars"]
            if len(_json(result)) > limit or omitted:
                required = len(_json(result))
                result.update(
                    status="omitted",
                    complete=False,
                    task={
                        "schema": "cairntir.task-resume.v1",
                        "status": "omitted",
                        "task_id": task["task_id"],
                        "revision": task["revision"],
                        "required_chars": max(required, task.get("required_chars", 0)),
                    },
                    uncertain_actions=[],
                    gaps=[],
                    unclean_sessions=[],
                    pending_captures=[],
                )
                result["omitted_groups"] = [
                    "task",
                    "uncertain_actions",
                    "gaps",
                    "unclean_sessions",
                    "pending_captures",
                ]
                result.pop("brief_sha256")
                result["brief_sha256"] = _sha(_json(result))
            evidence = []
            if task.get("checkpoint"):
                evidence = list(
                    dict.fromkeys(
                        [
                            task["checkpoint"]["original_drawer_id"],
                            task["checkpoint"]["checkpoint_drawer_id"],
                            *task["checkpoint"]["evidence_ids"],
                        ]
                    )
                )
            execution = self._execute(
                "brief", result["brief_id"], result, lambda: (result, evidence)
            )
        self._latest = _public(execution.result)
        return deepcopy(self._latest)

    def _ack_state(self, brief: dict[str, Any]) -> None:
        if (
            not brief["complete"]
            or brief["status"] != "ready"
            or brief["epoch"] != self._epoch
            or brief["state_sha256"] != _sha(_json(self._state()))
        ):
            raise ManagedRuntimeError("brief is incomplete, stale or from another epoch")

    @_boundary
    def acknowledge(self, request: object) -> dict[str, Any]:
        """Bind the exact current brief to this runtime epoch and state."""
        self._check()
        payload = _fields(request, "cairntir.managed-ack.v1", {"brief_id", "brief_sha256"})
        _uuid(payload["brief_id"], "brief_id")
        with self._store.transaction():
            brief = self._latest
            if brief is None or any(
                payload[name] != brief[name] for name in ("brief_id", "brief_sha256")
            ):
                raise ManagedRuntimeError("acknowledgement does not match the latest brief")
            self._ack_state(brief)
            registered = next(
                (item for item in self._records("brief") if item["brief_id"] == brief["brief_id"]),
                None,
            )
            if registered is None or _public(registered) != brief:
                raise ManagedRuntimeError("brief has no matching committed registry record")
            result = {
                "schema": "cairntir.managed-ack-receipt.v1",
                "status": "committed",
                "ack_id": str(uuid4()),
                "brief_id": brief["brief_id"],
                "brief_sha256": brief["brief_sha256"],
                "epoch": self._epoch,
                "session_id": self._session,
                "task_id": self._task_id,
                "revision": brief["revision"],
            }
            execution = self._execute(
                "ack",
                brief["brief_id"],
                payload,
                lambda: (
                    result,
                    registered["_managed"]["evidence_ids"],
                ),
            )
        return _public(execution.result, execution.replayed)

    def _intent(self, action_id: str) -> dict[str, Any] | None:
        return next(
            (item for item in self._records("dispatch") if item["action_id"] == action_id), None
        )

    def _action_events(self, request: dict[str, Any]) -> list[int]:
        available = self._records("event")
        keys = []
        for event_id in request["event_ids"]:
            matches = [item for item in available if item["event_id"] == event_id]
            if not matches or any(item["task_id"] != self._task_id for item in matches):
                raise ManagedRuntimeError("action references an unavailable event or another task")
            if len({_sha(_json(item["_managed"]["request"])) for item in matches}) != 1:
                raise ManagedRuntimeError("event identity has conflicting committed bindings")
            for event in matches:
                self._verify_event(event)
                keys.append(event["drawer_id"])
        return list(dict.fromkeys(keys))

    def _action_status(self, intent: dict[str, Any], *, replayed: bool) -> dict[str, Any]:
        if intent["task_id"] != self._task_id:
            raise ManagedRuntimeError("action belongs to another task")
        self._action_events(intent["request"])
        outcome = next(
            (item for item in self._records("outcome") if item["action_id"] == intent["action_id"]),
            None,
        )
        if outcome is not None:
            return _public(outcome, replayed)
        observation = next(
            (
                item
                for item in self._records("observation")
                if item["action_id"] == intent["action_id"]
            ),
            {},
        )
        return {
            "schema": "cairntir.managed-action-receipt.v1",
            "status": "uncertain",
            "action_id": intent["action_id"],
            "task_id": intent["task_id"],
            "prediction_drawer_id": intent["prediction_drawer_id"],
            "outcome_drawer_id": None,
            "exit_code": None,
            "stdout": observation.get("stdout", ""),
            "stderr": observation.get("stderr", ""),
            "timed_out": observation.get("timed_out", False),
            "output_truncated": observation.get("output_truncated", False),
            "replayed": replayed,
        }

    @_boundary
    def status(self, action_id: str) -> dict[str, Any]:
        """Inspect a committed action without repeating its external effect."""
        self._check()
        _uuid(action_id, "action_id")
        intent = self._intent(action_id)
        if intent is None:
            raise ManagedRuntimeError("action is unavailable")
        return self._action_status(intent, replayed=True)

    def _run(self, profile: dict[str, Any]) -> dict[str, Any]:
        process = subprocess.Popen(  # noqa: S603 - immutable trusted profile, shell disabled
            profile["argv"],
            cwd=profile["cwd"],
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        streams = [bytearray(), bytearray()]
        truncated = threading.Event()
        read_failed = threading.Event()
        limit = profile["output_limit_bytes"]

        def read(pipe: Any, target: bytearray) -> None:
            try:
                with pipe:
                    while chunk := pipe.read1(8192):
                        remaining = limit - len(target)
                        target.extend(chunk[:remaining])
                        if len(chunk) > remaining:
                            truncated.set()
                            process.kill()
                            break
            except OSError:
                read_failed.set()

        readers = [
            threading.Thread(target=read, args=(pipe, data), daemon=True)
            for pipe, data in zip((process.stdout, process.stderr), streams, strict=True)
        ]
        for reader in readers:
            reader.start()
        timed_out = False
        try:
            exit_code = process.wait(timeout=profile["timeout_seconds"])
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            exit_code = process.wait(timeout=5)
        for reader in readers:
            reader.join(timeout=1)
        return {
            "exit_code": exit_code,
            "stdout": bytes(streams[0]).decode("utf-8", errors="replace"),
            "stderr": bytes(streams[1]).decode("utf-8", errors="replace"),
            "timed_out": timed_out,
            "output_truncated": truncated.is_set(),
            "cleanup_uncertain": timed_out
            or truncated.is_set()
            or read_failed.is_set()
            or any(reader.is_alive() for reader in readers),
        }

    @_boundary
    def dispatch(self, request: object) -> dict[str, Any]:
        """Commit a prediction before one permitted launch and retain uncertain outcomes."""
        self._check()
        if self._store.transaction_active:
            raise ManagedRuntimeError("dispatch cannot run inside a caller transaction")
        payload = _fields(
            request,
            "cairntir.managed-action.v1",
            {
                "action_id",
                "ack_id",
                "profile",
                "claim",
                "predicted_outcome",
                "event_ids",
            },
        )
        for name in ("action_id", "ack_id"):
            _uuid(payload[name], name)
        for name in ("claim", "predicted_outcome"):
            _text(payload[name], name)
        _validate_ident(payload["profile"], "profile")
        if payload["profile"] not in self._config["profiles"]:
            raise ManagedRuntimeError("action profile is not configured")
        events = payload["event_ids"]
        if not isinstance(events, list) or not events:
            raise ManagedRuntimeError("event_ids must be a nonempty unique UUID list")
        for event_id in events:
            _uuid(event_id, "event_id")
        if len(set(events)) != len(events):
            raise ManagedRuntimeError("event_ids must be unique")
        profile = self._config["profiles"][payload["profile"]]

        def prepare() -> tuple[dict[str, Any], list[int]]:
            self._check()
            if self._uncertain():
                raise ManagedRuntimeError("an uncertain action requires explicit reconciliation")
            ack = next(
                (item for item in self._records("ack") if item["ack_id"] == payload["ack_id"]), None
            )
            if ack is None or self._latest is None or ack["brief_id"] != self._latest["brief_id"]:
                raise ManagedRuntimeError("action has no current committed acknowledgement")
            if ack["epoch"] != self._epoch or ack["brief_sha256"] != self._latest["brief_sha256"]:
                raise ManagedRuntimeError("action acknowledgement is from another epoch or brief")
            self._ack_state(self._latest)
            keys = self._action_events(payload)
            saved = self._store.add(
                Drawer(
                    wing=self._wing,
                    room=self._room,
                    content=payload["claim"],
                    claim=payload["claim"],
                    predicted_outcome=payload["predicted_outcome"],
                    metadata={
                        "kind": "managed.prediction",
                        "action_id": payload["action_id"],
                        "event_ids": events,
                        "task_id": self._task_id,
                    },
                )
            )
            if saved.id is None:
                raise ManagedRuntimeError("prediction append has no persisted drawer")
            return {
                "schema": "cairntir.managed-dispatch-intent.v1",
                "status": "committed",
                "action_id": payload["action_id"],
                "task_id": self._task_id,
                "epoch": self._epoch,
                "ack_id": payload["ack_id"],
                "profile_sha256": _sha(_json(profile)),
                "prediction_drawer_id": saved.id,
                "request": payload,
            }, [*keys, saved.id]

        with self._store.transaction():
            execution = self._execute("dispatch", payload["action_id"], payload, prepare)
            intent = execution.result
            self._action_events(payload)
            if intent["task_id"] != self._task_id or intent["profile_sha256"] != _sha(
                _json(profile)
            ):
                raise ManagedRuntimeError("action task or profile binding has changed")
        if execution.replayed:
            return self._action_status(intent, replayed=True)
        self._check()
        actual = self._run(profile)

        def observe() -> tuple[dict[str, Any], list[int]]:
            self._authorize()
            self._action_events(payload)
            saved = self._store.add(
                Drawer(
                    wing=self._wing,
                    room=self._room,
                    content=_json(actual),
                    observed_outcome=_json(actual),
                    supersedes_id=intent["prediction_drawer_id"],
                    metadata={"kind": "managed.observation", "action_id": payload["action_id"]},
                )
            )
            if saved.id is None:
                raise ManagedRuntimeError("observation append has no persisted drawer")
            current = self._resume()
            if current["status"] != "ready":
                raise ManagedRuntimeError("task is unavailable for the outcome checkpoint")
            old = current["checkpoint"]
            checkpoint = {
                "task_id": self._task_id,
                "expected_revision": current["revision"],
                "idempotency_key": f"managed-outcome:{payload['action_id']}",
                "status": "active",
                "completed": old["completed"],
                "outstanding": old["outstanding"],
                "next_action": old["next_action"],
                "evidence_ids": list(
                    dict.fromkeys(
                        [
                            *old["evidence_ids"],
                            old["checkpoint_drawer_id"],
                            intent["prediction_drawer_id"],
                            saved.id,
                        ]
                    )
                ),
            }
            self._book.checkpoint(self._wing, self._room, _json(actual), checkpoint)
            return {
                "schema": "cairntir.managed-action-receipt.v1",
                "status": "uncertain"
                if actual["cleanup_uncertain"]
                else ("completed" if actual["exit_code"] == 0 else "failed"),
                "action_id": payload["action_id"],
                "task_id": self._task_id,
                "prediction_drawer_id": intent["prediction_drawer_id"],
                "outcome_drawer_id": saved.id,
                **{
                    name: actual[name]
                    for name in ("exit_code", "stdout", "stderr", "timed_out", "output_truncated")
                },
            }, [*intent["_managed"]["evidence_ids"], saved.id]

        with self._store.transaction():
            operation = "observation" if actual["cleanup_uncertain"] else "outcome"
            self._execute(
                operation, payload["action_id"], {"intent": payload, "actual": actual}, observe
            )
        self._latest = None
        return self._action_status(intent, replayed=False)

    @_boundary
    def close(self, *, last_sequence: int | None = None) -> dict[str, Any]:
        """Record a producer watermark without completing its outstanding task."""
        self._check()
        if last_sequence is not None:
            _integer(last_sequence, "last_sequence", 0, 2**63 - 1)
        with self._store.transaction():
            state = self._state()
            gaps, omitted = self._gaps(state)
            result = {
                "schema": "cairntir.managed-close.v1",
                "status": "closed",
                "session_id": self._session,
                "epoch": self._epoch,
                "task_id": self._task_id,
                "revision": state["task"]["revision"],
                "last_received_sequence": state["last_sequence"],
                "declared_last_sequence": last_sequence,
                "gaps": gaps,
                "gaps_omitted": omitted,
                "capture_complete": last_sequence is not None
                and last_sequence == state["last_sequence"]
                and not gaps
                and not omitted
                and not state["pending_captures"],
                "uncertain_actions": state["uncertain_actions"],
                "unclean_sessions": self._unclean_sessions(),
                "pending_captures": state["pending_captures"],
            }
            self._execute("close", self._epoch, result, lambda: (result, []))
        self._closed = True
        return result


def stream_command(runtime: ManagedRuntime, value: object) -> dict[str, Any]:
    """Dispatch one strict JSONL envelope without accepting arbitrary method names."""
    command = _fields(value, "cairntir.managed-command.v1", {"operation", "request"})
    operation = command["operation"]
    request = command["request"]
    if not isinstance(request, dict):
        raise ManagedRuntimeError("command request must be an object")
    if operation == "capture":
        return runtime.capture(request)
    if operation == "acknowledge":
        return runtime.acknowledge(request)
    if operation == "dispatch":
        return runtime.dispatch(request)
    if operation == "brief" and not request:
        return runtime.brief()
    if operation == "status" and request.keys() == {"action_id"}:
        return runtime.status(request["action_id"])
    if operation == "close" and request.keys() == {"last_sequence"}:
        return runtime.close(last_sequence=request["last_sequence"])
    raise ManagedRuntimeError("unsupported operation or command fields")
