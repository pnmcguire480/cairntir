"""Local bearer grants, bound by trusted startup and checked at every store boundary."""

from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
import re
import secrets
import sqlite3
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from multiprocessing.connection import Connection
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from typing import Any, NoReturn

from cairntir.durability import WorkflowExecution, WorkflowReceipt
from cairntir.errors import CairntirError
from cairntir.memory.belief import rerank_results
from cairntir.memory.store import (
    DrawerStore,
    _context_record,
    _copy_locked_database,
    _row_to_drawer,
)
from cairntir.memory.taxonomy import Drawer, Layer
from cairntir.provenance import TrustLevel, WriteProvenance

_CAPABILITIES = frozenset({"read", "write", "export", "approve", "manage"})
_DENIED = "access denied"


class AccessDenied(CairntirError):  # noqa: N818 - frozen public API
    """The bound grant does not authorize this operation."""


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def startup_token() -> str | None:
    """Read the configured token once; absence alone selects owner mode."""
    configured = os.environ.get("CAIRNTIR_GRANT_FILE")
    if configured is None:
        return None
    try:
        token = Path(configured).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise AccessDenied(_DENIED) from exc
    if not token:
        raise AccessDenied(_DENIED)
    return token


def validate_startup(path: Path, token: str) -> None:
    """Reject an invalid configured grant before store initialization can write."""
    _active(_authoritative_grant(path, _digest(token)))


def _grant_worker(path: Path, token_hash: str, connection: Connection) -> None:
    with connection:
        while True:
            try:
                request = connection.recv()
            except EOFError:
                return
            if request is not None:
                return
            try:
                with TemporaryDirectory(prefix="cairntir-grant-") as directory:
                    copied = Path(directory) / "grant.db"
                    _copy_locked_database(path, copied)
                    with closing(sqlite3.connect(copied)) as conn:
                        conn.row_factory = sqlite3.Row
                        row = conn.execute(
                            "SELECT * FROM access_grants WHERE token_hash=?", (token_hash,)
                        ).fetchone()
                        grant = dict(row) if row is not None else None
                response = (True, grant)
            except (OSError, sqlite3.Error, CairntirError):
                response = (False, None)
            try:
                connection.send(response)
            except (OSError, EOFError):
                return


class _GrantReader:
    def __init__(self, path: Path, token_hash: str) -> None:
        self._lock = Lock()
        self._closed = False
        self._token_hash = token_hash
        context = multiprocessing.get_context("spawn")
        self._connection, child = context.Pipe()
        self._process = context.Process(
            target=_grant_worker, args=(path.resolve(), token_hash, child), daemon=True
        )
        try:
            self._process.start()
        except (OSError, RuntimeError, AssertionError) as exc:
            self._connection.close()
            self._process.close()
            raise AccessDenied(_DENIED) from exc
        finally:
            child.close()

    def read(self) -> dict[str, Any] | None:
        """Read a fresh authority snapshot through this reader's isolated helper."""
        with self._lock:
            if self._closed:
                raise AccessDenied(_DENIED)
            response: object = None
            try:
                if self._process.is_alive():
                    self._connection.send(None)
                    if self._connection.poll(12):
                        response = self._connection.recv()
            except (OSError, EOFError, ValueError) as exc:
                self._close()
                raise AccessDenied(_DENIED) from exc
            if not isinstance(response, tuple) or len(response) != 2 or response[0] is not True:
                self._close()
                raise AccessDenied(_DENIED)
            row = response[1]
            if row is None:
                return None
            if (
                not isinstance(row, dict)
                or row.get("token_hash") != self._token_hash
                or not isinstance(row.get("scopes"), str)
                or not isinstance(row.get("capabilities"), str)
                or type(row.get("revoked")) is not int
                or "expires_at" not in row
                or (row["expires_at"] is not None and not isinstance(row["expires_at"], str))
            ):
                self._close()
                raise AccessDenied(_DENIED)
            return row

    def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._connection.close()
        self._process.join(timeout=1)
        if self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=1)
        if self._process.is_alive():
            self._process.kill()
            self._process.join(timeout=1)
        if self._process.is_alive():
            raise AccessDenied(_DENIED)
        self._process.close()

    def close(self) -> None:
        """Close the pipe and reap only this reader's owned process."""
        with self._lock:
            self._close()


def _authoritative_grant(path: Path, token_hash: str) -> dict[str, Any] | None:
    reader = _GrantReader(path, token_hash)
    try:
        return reader.read()
    finally:
        reader.close()


def _active(row: sqlite3.Row | dict[str, Any] | None) -> sqlite3.Row | dict[str, Any]:
    if (
        row is None
        or row["revoked"]
        or (row["expires_at"] and datetime.fromisoformat(row["expires_at"]) <= datetime.now(UTC))
    ):
        raise AccessDenied(_DENIED)
    return row


def issue_grant(
    owner_store: DrawerStore,
    *,
    scopes: Sequence[dict[str, Any]],
    capabilities: Sequence[str],
    expires_at: datetime | None = None,
    principal: str = "local",
) -> str:
    """Issue an owner-created grant and persist only its token hash."""
    if isinstance(owner_store, ScopedStore):
        raise AccessDenied(_DENIED)
    copied = json.loads(json.dumps(scopes))
    if not isinstance(copied, list) or any(
        not isinstance(scope, dict)
        or set(scope) - {"wing", "rooms", "drawer_ids"}
        or not isinstance(scope.get("wing"), str)
        or not scope["wing"]
        or (
            "rooms" in scope
            and (
                not isinstance(scope["rooms"], list)
                or any(not isinstance(room, str) for room in scope["rooms"])
            )
        )
        or (
            "drawer_ids" in scope
            and (
                not isinstance(scope["drawer_ids"], list)
                or any(type(key) is not int or key <= 0 for key in scope["drawer_ids"])
            )
        )
        for scope in copied
    ):
        raise AccessDenied("invalid grant scope")
    if isinstance(capabilities, str) or not set(capabilities) <= _CAPABILITIES:
        raise AccessDenied("invalid grant capabilities")
    if expires_at is not None and expires_at.tzinfo is None:
        raise AccessDenied("grant expiry must include a timezone")
    token = secrets.token_urlsafe(32)
    with owner_store.transaction():
        owner_store._conn.execute(
            "CREATE TABLE IF NOT EXISTS access_grants ("
            "token_hash TEXT PRIMARY KEY, scopes TEXT NOT NULL, capabilities TEXT NOT NULL, "
            "expires_at TEXT, principal TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0)"
        )
        owner_store._conn.execute(
            "INSERT INTO access_grants(token_hash,scopes,capabilities,expires_at,principal) "
            "VALUES (?,?,?,?,?)",
            (
                _digest(token),
                json.dumps(copied),
                json.dumps(sorted(set(capabilities))),
                expires_at.astimezone(UTC).isoformat() if expires_at else None,
                principal,
            ),
        )
    return token


def revoke_grant(owner_store: DrawerStore, token: str) -> None:
    """Revoke future access without changing the underlying evidence."""
    if isinstance(owner_store, ScopedStore):
        raise AccessDenied(_DENIED)
    with owner_store.transaction():
        try:
            owner_store._conn.execute(
                "UPDATE access_grants SET revoked=1 WHERE token_hash=?", (_digest(token),)
            )
        except sqlite3.Error as exc:
            raise AccessDenied(_DENIED) from exc


def bind_grant(store: DrawerStore, token: str) -> ScopedStore:
    """Bind one validated token to a store without widening its authority."""
    if isinstance(store, ScopedStore) or not isinstance(token, str) or not token.strip():
        raise AccessDenied(_DENIED)
    scoped = ScopedStore(store, _digest(token))
    bound = False
    try:
        scoped._grant()
        bound = True
    finally:
        if not bound:
            scoped._close_grant_reader()
    return scoped


def _paladin_ui_records(
    owner: DrawerStore, *, wing: str, room: str, run_id: str, task_id: str, baseline_id: str
) -> dict[str, list[dict[str, Any]]]:
    """Read authenticated UI runs and their shared, scoped baseline history."""
    from cairntir._paladin_contract import _record, _uuid, canonical_sha
    from cairntir.durability import request_hash
    from cairntir.managed_projection import _bindings
    from cairntir.memory.taxonomy import _validate_ident
    from cairntir.paladin_ui import _profile
    from cairntir.provenance import Sensitivity

    def require(condition: bool) -> None:
        if not condition:
            raise AccessDenied("invalid UI registry binding")

    def encoded(value: object) -> str:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )

    def logical(key: str) -> str:
        if key.startswith("grant:"):
            parts = key.split(":", 2)
            if len(parts) != 3 or re.fullmatch(r"[0-9a-f]{64}", parts[1]) is None:
                return ""
            return parts[2]
        return key

    def source(key: int) -> Drawer:
        require(type(key) is int and key > 0)
        available = owner._task_drawers([key])
        require(key in available)
        drawer, provenance = available[key]
        now = datetime.now(UTC)
        require(
            drawer.wing == wing
            and drawer.room == room
            and provenance.sensitivity != Sensitivity.SECRET
            and (provenance.valid_from is None or provenance.valid_from <= now)
            and (provenance.valid_until is None or provenance.valid_until > now)
        )
        return drawer

    def reference(value: object) -> Drawer:
        ref = _record(value, "drawer_id source_identity content_sha256")
        _uuid(ref["source_identity"])
        drawer = source(ref["drawer_id"])
        require(
            owner.portable_identity(ref["drawer_id"]) == ref["source_identity"]
            and _digest(drawer.content) == ref["content_sha256"]
        )
        return drawer

    try:
        require(isinstance(owner, DrawerStore))
        _validate_ident(wing, "wing")
        _validate_ident(room, "room")
        for identity in (run_id, task_id, baseline_id):
            _uuid(identity)
        rows = owner._conn.execute(
            "SELECT idempotency_key,operation,request_hash,state,result FROM workflow_runs"
        ).fetchall()
        plans: dict[str, dict[str, Any]] = {}
        for row in rows:
            key = logical(row["idempotency_key"])
            if not key.startswith("paladin-ui:") or not key.endswith(":plan"):
                continue
            envelope = json.loads(row["result"] or "null")
            request = envelope.get("request", {}) if isinstance(envelope, dict) else {}
            contract = request.get("contract", {})
            if not isinstance(contract, dict) or contract.get("baseline_id") != baseline_id:
                require(not key.startswith(f"paladin-ui:{run_id}:"))
                continue
            if request.get("wing") != wing or request.get("room") != room:
                require(not key.startswith(f"paladin-ui:{run_id}:"))
                continue
            current = request["run_id"]
            require(key == f"paladin-ui:{current}:plan" and current not in plans)
            plans[current] = envelope
        require(
            run_id in plans
            or not any(
                logical(row["idempotency_key"]).startswith(f"paladin-ui:{run_id}:") for row in rows
            )
        )
        selected: dict[str, dict[str, Any]] = {}
        baseline_prefix = f"paladin-ui-baseline:{baseline_id}:review:"
        for row in rows:
            key = logical(row["idempotency_key"])
            parts = key.split(":")
            review = key.startswith(baseline_prefix)
            if not review and not (
                len(parts) >= 3 and parts[0] == "paladin-ui" and parts[1] in plans
            ):
                continue
            require(key not in selected and row["state"] == "committed")
            if review:
                require(len(parts) == 4)
                _uuid(parts[3])
                kind = "review"
            else:
                require(
                    (len(parts) == 3 and parts[2] == "plan")
                    or (
                        len(parts) == 5
                        and parts[2] == "attempt"
                        and parts[4] in {"prepare", "result"}
                    )
                )
                kind = parts[-1]
            operation = f"paladin.ui.{kind}.v1"
            require(row["operation"] == operation)
            envelope = _record(json.loads(row["result"]), "request result evidence")
            request = envelope["request"]
            extra = {
                "plan": "contract",
                "prepare": "attempt_id action producer_request producer_request_sha256",
                "result": "attempt_id preparation",
            }
            if review:
                _record(
                    request,
                    "baseline_id wing room task_id candidate_id candidate "
                    "expected_revision review_evidence idempotency_key",
                )
                require(
                    request["baseline_id"] == baseline_id and request["idempotency_key"] == parts[3]
                )
                reference(request["candidate"])
            else:
                _record(request, "run_id task_id wing room contract_sha256 " + extra[kind])
                plan = plans[parts[1]]
                contract = plan["request"]["contract"]
                require(
                    request["run_id"] == parts[1]
                    and request["task_id"] == contract["task_id"]
                    and request["contract_sha256"] == canonical_sha(contract)
                )
                if kind == "plan":
                    require(
                        contract["run_id"] == parts[1]
                        and contract["wing"] == wing
                        and contract["room"] == room
                        and envelope["result"] == {"contract_sha256": canonical_sha(contract)}
                    )
                else:
                    require(request["attempt_id"] == parts[3])
            require(
                request["wing"] == wing
                and request["room"] == room
                and request_hash(request) == row["request_hash"]
            )
            _uuid(request["task_id"])
            drawer = reference(envelope["evidence"])
            require(
                drawer.content
                == encoded(
                    {
                        "operation": operation,
                        "request_sha256": row["request_hash"],
                        "result": envelope["result"],
                    }
                )
            )
            selected[key] = {
                "idempotency_key": key,
                "operation": operation,
                "request_hash": row["request_hash"],
                "state": "committed",
                "result": envelope,
            }
        if run_id in plans:
            require(plans[run_id]["request"]["task_id"] == task_id)
        preparations: dict[str, dict[str, Any]] = {}
        wanted: dict[str, tuple[str, str]] = {}
        for row in selected.values():
            if row["operation"] != "paladin.ui.prepare.v1":
                continue
            envelope = row["result"]
            request = envelope["request"]
            action = _record(
                request["action"],
                "schema action_id ack_id profile claim predicted_outcome event_ids",
            )
            for name in ("action_id", "ack_id"):
                _uuid(action[name])
            attempts = plans[request["run_id"]]["request"]["contract"]["attempts"]
            attempt = next(item for item in attempts if item["attempt_id"] == request["attempt_id"])
            producer_request = request["producer_request"]
            require(
                action["schema"] == "cairntir.managed-action.v1"
                and action["profile"] == attempt["profile"]
                and canonical_sha(producer_request) == request["producer_request_sha256"]
                and producer_request
                == {
                    "schema": "cairntir.paladin-ui-producer.v1",
                    "run_id": request["run_id"],
                    "attempt_id": request["attempt_id"],
                    "action_id": action["action_id"],
                    "contract_sha256": request["contract_sha256"],
                    "template_sha256": attempt["template_file"]["sha256"],
                    "template": attempt["template"],
                }
                and envelope["result"]
                == {
                    "status": "PREPARED",
                    "action_id": action["action_id"],
                    "producer_request_sha256": request["producer_request_sha256"],
                }
                and action["action_id"] not in preparations
            )
            preparations[action["action_id"]] = {"envelope": envelope, "attempt": attempt}
            require(
                isinstance(action["event_ids"], list)
                and bool(action["event_ids"])
                and len(set(action["event_ids"])) == len(action["event_ids"])
            )
            for event_id in action["event_ids"]:
                _uuid(event_id)
                target = ("managed.event.v1", request["task_id"])
                event_key = f"managed:event:{event_id}"
                require(event_key not in wanted or wanted[event_key] == target)
                wanted[event_key] = target
            for kind in ("dispatch", "outcome", "observation"):
                wanted[f"managed:{kind}:{action['action_id']}"] = (
                    f"managed.{kind}.v1",
                    request["task_id"],
                )
        for key, row in selected.items():
            if row["operation"] != "paladin.ui.result.v1":
                continue
            preparation_key = key.rsplit(":", 1)[0] + ":prepare"
            require(preparation_key in selected)
            prepared = selected[preparation_key]["result"]
            result = row["result"]
            require(
                result["request"]["preparation"] == prepared["evidence"]
                and result["result"]["run_id"] == prepared["request"]["run_id"]
                and result["result"]["attempt_id"] == prepared["request"]["attempt_id"]
                and result["result"]["action_id"] == prepared["request"]["action"]["action_id"]
                and result["result"]["request_sha256"]
                == prepared["request"]["producer_request_sha256"]
            )
        managed: dict[str, dict[str, Any]] = {}
        for row in rows:
            key = logical(row["idempotency_key"])
            if key not in wanted:
                continue
            operation, selected_task = wanted[key]
            require(
                key not in managed and row["state"] == "committed" and row["operation"] == operation
            )
            record = json.loads(row["result"])
            binding = _record(record["_managed"], "operation request evidence_ids epoch session_id")
            request = _record(binding["request"], "wing room request")
            require(
                binding["operation"] == operation
                and request_hash(request) == row["request_hash"]
                and request["wing"] == wing
                and request["room"] == room
                and record["task_id"] == selected_task
            )
            for name in ("epoch", "session_id"):
                _uuid(binding[name])
            for evidence_id in binding["evidence_ids"]:
                source(evidence_id)
            if operation == "managed.event.v1":
                event = request["request"]
                drawer = source(record["drawer_id"])
                require(
                    key == f"managed:event:{record['event_id']}"
                    and record["drawer_id"] in binding["evidence_ids"]
                    and event["content"] == drawer.content
                    and record["content_sha256"] == _digest(drawer.content)
                    and record["source_identity"] == owner.portable_identity(record["drawer_id"])
                    and all(
                        record[name] == event[name]
                        for name in ("event_id", "session_id", "sequence")
                    )
                    and record["revision"] == event["expected_revision"] + 1
                    and event["task_id"] in (None, selected_task)
                )
            else:
                require(record["action_id"] == key.rsplit(":", 1)[1])
            managed[key] = record
        _bindings(list(managed.values()))
        for action_id, item in preparations.items():
            envelope, attempt = item["envelope"], item["attempt"]
            request = envelope["request"]
            action = request["action"]
            events = [managed.get(f"managed:event:{event}") for event in action["event_ids"]]
            require(all(event is not None for event in events))
            intent = managed.get(f"managed:dispatch:{action_id}")
            outcomes = [
                managed[key]
                for kind in ("outcome", "observation")
                if (key := f"managed:{kind}:{action_id}") in managed
            ]
            result = selected.get(
                f"paladin-ui:{request['run_id']}:attempt:{request['attempt_id']}:result"
            )
            require(len(outcomes) <= 1)
            if intent is None:
                require(not outcomes and result is None)
                continue
            require(
                intent["request"] == action
                and intent["profile_sha256"] == canonical_sha(_profile(attempt))
            )
            prediction = source(intent["prediction_drawer_id"])
            require(
                prediction.content == action["claim"]
                and prediction.claim == action["claim"]
                and prediction.predicted_outcome == action["predicted_outcome"]
                and prediction.id in intent["_managed"]["evidence_ids"]
                and all(
                    event["drawer_id"] in intent["_managed"]["evidence_ids"]
                    for event in events
                    if event is not None
                )
            )
            for outcome in outcomes:
                observed = source(outcome["outcome_drawer_id"])
                actual = encoded(outcome["_managed"]["request"]["request"]["actual"])
                require(
                    observed.content == actual
                    and observed.observed_outcome == actual
                    and observed.supersedes_id == prediction.id
                    and observed.id in outcome["_managed"]["evidence_ids"]
                    and set(intent["_managed"]["evidence_ids"])
                    <= set(outcome["_managed"]["evidence_ids"])
                )
            if result is not None:
                saved = result["result"]
                require(bool(outcomes) and saved["request"]["preparation"] == envelope["evidence"])
                value = saved["result"]
                require(
                    value["action_id"] == action_id
                    and value["managed_result"]
                    == {name: value for name, value in outcomes[0].items() if name != "_managed"}
                    and set(outcomes[0]["_managed"]["evidence_ids"]) <= set(value["evidence_ids"])
                )
        ordered = sorted(
            selected.values(), key=lambda item: item["result"]["evidence"]["drawer_id"]
        )
        require(len(encoded(ordered).encode()) <= 2097152)
        return {"ui": ordered, "managed": list(managed.values())}
    except (
        CairntirError,
        sqlite3.Error,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        StopIteration,
    ) as exc:
        if isinstance(exc, AccessDenied):
            raise
        raise AccessDenied("invalid UI registry binding") from exc


def _paladin_resources_records(
    owner: DrawerStore, *, wing: str, room: str, run_id: str, task_id: str
) -> dict[str, list[dict[str, Any]]]:
    """Project one authenticated resource registry without changing store state."""
    from cairntir._paladin_contract import (
        _digest as check_digest,
    )
    from cairntir._paladin_contract import (
        _record,
        _uuid,
        canonical_sha,
    )
    from cairntir.durability import request_hash
    from cairntir.managed_projection import _bindings
    from cairntir.memory.taxonomy import _validate_ident
    from cairntir.provenance import Sensitivity

    def require(condition: bool) -> None:
        if not condition:
            raise AccessDenied("invalid resource registry binding")

    def encoded(value: object) -> str:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )

    def logical(key: str) -> str:
        if key.startswith("grant:"):
            parts = key.split(":", 2)
            if len(parts) != 3 or re.fullmatch(r"[0-9a-f]{64}", parts[1]) is None:
                return ""
            return parts[2]
        return key

    try:
        require(isinstance(owner, DrawerStore))
        _validate_ident(wing, "wing")
        _validate_ident(room, "room")
        _uuid(run_id)
        _uuid(task_id)
        prefix = f"paladin-resources:{run_id}:"
        suffixes = {"plan": "plan"} | {
            f"stage:{stage}:{kind}": kind
            for stage in ("performance", "bundle", "security")
            for kind in ("prepare", "result")
        }
        rows = owner._conn.execute(
            "SELECT idempotency_key,operation,request_hash,state,result FROM workflow_runs"
        ).fetchall()
        selected: dict[str, dict[str, Any]] = {}
        for row in rows:
            key = logical(row["idempotency_key"])
            if not key.startswith(prefix):
                continue
            suffix = key[len(prefix) :]
            require(suffix in suffixes and key not in selected)
            operation = f"paladin.resources.{suffixes[suffix]}.v1"
            require(row["state"] == "committed" and row["operation"] == operation)
            selected[key] = {
                "idempotency_key": key,
                "operation": operation,
                "request_hash": row["request_hash"],
                "state": "committed",
                "result": json.loads(row["result"]),
            }
        if not selected:
            return {"resources": [], "managed": []}

        def source(key: int) -> Drawer:
            require(type(key) is int and key > 0)
            available = owner._task_drawers([key])
            require(key in available)
            drawer, provenance = available[key]
            now = datetime.now(UTC)
            require(
                drawer.wing == wing
                and drawer.room == room
                and provenance.sensitivity != Sensitivity.SECRET
                and (provenance.valid_from is None or provenance.valid_from <= now)
                and (provenance.valid_until is None or provenance.valid_until > now)
            )
            return drawer

        def reference(value: object) -> Drawer:
            ref = _record(value, "drawer_id source_identity content_sha256")
            _uuid(ref["source_identity"])
            check_digest(ref["content_sha256"])
            drawer = source(ref["drawer_id"])
            require(
                owner.portable_identity(ref["drawer_id"]) == ref["source_identity"]
                and _digest(drawer.content) == ref["content_sha256"]
            )
            return drawer

        common = {"run_id": run_id, "wing": wing, "room": room, "task_id": task_id}
        contract_digest: str | None = None
        for key, row in selected.items():
            envelope = _record(row["result"], "request result evidence")
            request = envelope["request"]
            suffix = key[len(prefix) :]
            kind = suffixes[suffix]
            extra = (
                "contract"
                if kind == "plan"
                else ("stage_id action" if kind == "prepare" else "stage_id preparation")
            )
            _record(request, "run_id wing room task_id contract_sha256 " + extra)
            require(all(request[name] == value for name, value in common.items()))
            check_digest(request["contract_sha256"])
            if contract_digest is None:
                contract_digest = request["contract_sha256"]
            require(request["contract_sha256"] == contract_digest)
            require(request_hash(request) == row["request_hash"])
            drawer = reference(envelope["evidence"])
            require(
                drawer.content
                == encoded(
                    {
                        "operation": row["operation"],
                        "request_sha256": row["request_hash"],
                        "result": envelope["result"],
                    }
                )
            )
            if kind != "plan":
                require(request["stage_id"] == suffix.split(":")[1])

        require(prefix + "plan" in selected)
        plan = selected[prefix + "plan"]["result"]
        contract = plan["request"]["contract"]
        require(
            canonical_sha(contract) == contract_digest
            and all(contract[name] == common[name] for name in ("run_id", "wing", "task_id"))
            and plan["result"] == {"contract_sha256": contract_digest}
        )
        stages = {item["stage_id"]: item for item in contract["stages"]}
        preparations: dict[str, dict[str, Any]] = {}
        wanted: dict[str, str] = {}
        for stage_id in ("performance", "bundle", "security"):
            prepared = selected.get(prefix + f"stage:{stage_id}:prepare")
            result = selected.get(prefix + f"stage:{stage_id}:result")
            if prepared is None:
                require(result is None)
                continue
            envelope = prepared["result"]
            action = _record(
                envelope["request"]["action"],
                "schema action_id ack_id profile claim predicted_outcome event_ids",
            )
            for name in ("action_id", "ack_id"):
                _uuid(action[name])
            require(
                action["schema"] == "cairntir.managed-action.v1"
                and action["profile"] == stages[stage_id]["profile"]
                and isinstance(action["event_ids"], list)
                and bool(action["event_ids"])
                and len(set(action["event_ids"])) == len(action["event_ids"])
                and envelope["result"] == {"status": "PREPARED", "action_id": action["action_id"]}
            )
            for event_id in action["event_ids"]:
                _uuid(event_id)
                wanted[f"managed:event:{event_id}"] = "managed.event.v1"
            require(action["action_id"] not in preparations)
            preparations[action["action_id"]] = {"stage_id": stage_id, "envelope": envelope}
            for kind in ("dispatch", "outcome", "observation"):
                wanted[f"managed:{kind}:{action['action_id']}"] = f"managed.{kind}.v1"
            if result is not None:
                require(result["result"]["request"]["preparation"] == envelope["evidence"])

        managed: dict[str, dict[str, Any]] = {}
        for row in rows:
            key = logical(row["idempotency_key"])
            if key not in wanted:
                continue
            require(key not in managed and row["state"] == "committed")
            require(row["operation"] == wanted[key])
            record = json.loads(row["result"])
            binding = _record(record["_managed"], "operation request evidence_ids epoch session_id")
            request = _record(binding["request"], "wing room request")
            require(
                binding["operation"] == row["operation"]
                and request_hash(request) == row["request_hash"]
                and request["wing"] == wing
                and request["room"] == room
                and record["task_id"] == task_id
                and isinstance(binding["evidence_ids"], list)
            )
            _uuid(binding["epoch"])
            _uuid(binding["session_id"])
            for evidence_id in binding["evidence_ids"]:
                source(evidence_id)
            if row["operation"] == "managed.event.v1":
                event = request["request"]
                require(key == f"managed:event:{record['event_id']}")
                drawer = source(record["drawer_id"])
                require(
                    record["drawer_id"] in binding["evidence_ids"]
                    and event["content"] == drawer.content
                    and record["content_sha256"] == _digest(drawer.content)
                    and record["source_identity"] == owner.portable_identity(record["drawer_id"])
                    and all(
                        record[name] == event[name]
                        for name in ("event_id", "session_id", "sequence")
                    )
                    and record["revision"] == event["expected_revision"] + 1
                    and event["task_id"] in (None, task_id)
                )
            else:
                action_id = key.rsplit(":", 1)[1]
                require(record["action_id"] == action_id and action_id in preparations)
            managed[key] = record
        _bindings(list(managed.values()))
        for action_id, preparation in preparations.items():
            stage_id = preparation["stage_id"]
            action = preparation["envelope"]["request"]["action"]
            events = [managed.get(f"managed:event:{event_id}") for event_id in action["event_ids"]]
            require(all(event is not None for event in events))
            intent = managed.get(f"managed:dispatch:{action_id}")
            outcomes = [
                managed[key]
                for kind in ("outcome", "observation")
                if (key := f"managed:{kind}:{action_id}") in managed
            ]
            require(len(outcomes) <= 1)
            result = selected.get(prefix + f"stage:{stage_id}:result")
            if intent is None:
                require(not outcomes and result is None)
                continue
            command = stages[stage_id]["command"]
            configured = {**command, "executable_path": str(Path(command["argv"][0]).resolve())}
            require(
                intent["request"] == action
                and intent["profile_sha256"] == canonical_sha(configured)
                and intent["prediction_drawer_id"] in intent["_managed"]["evidence_ids"]
                and all(
                    event["drawer_id"] in intent["_managed"]["evidence_ids"]
                    for event in events
                    if event
                )
            )
            prediction = source(intent["prediction_drawer_id"])
            require(
                prediction.content == action["claim"]
                and prediction.claim == action["claim"]
                and prediction.predicted_outcome == action["predicted_outcome"]
            )
            for outcome in outcomes:
                actual = encoded(outcome["_managed"]["request"]["request"]["actual"])
                observed = source(outcome["outcome_drawer_id"])
                require(
                    outcome["outcome_drawer_id"] in outcome["_managed"]["evidence_ids"]
                    and set(intent["_managed"]["evidence_ids"])
                    <= set(outcome["_managed"]["evidence_ids"])
                    and observed.content == actual
                    and observed.observed_outcome == actual
                    and observed.supersedes_id == prediction.id
                )
            if result is not None:
                receipt = result["result"]["result"]
                require(bool(outcomes))
                expected = {
                    name: value for name, value in outcomes[0].items() if name != "_managed"
                }
                actual_result = receipt["managed_result"]
                require(
                    receipt["stage_id"] == stage_id
                    and receipt["action_id"] == action_id
                    and {name: value for name, value in actual_result.items() if name != "replayed"}
                    == expected
                    and set(outcomes[0]["_managed"]["evidence_ids"]) <= set(receipt["evidence_ids"])
                )
        return {"resources": list(selected.values()), "managed": list(managed.values())}
    except (CairntirError, sqlite3.Error, ValueError, TypeError, KeyError, IndexError) as exc:
        if isinstance(exc, AccessDenied):
            raise
        raise AccessDenied("invalid resource registry binding") from exc


class ScopedStore:
    """A capability-limited store; raw owner SQL is never exposed through this view."""

    @contextmanager
    def _managed_foreground(self, wing: str, room: str, action_id: str) -> Iterator[None]:
        self.authorize("read", wing=wing, room=room)
        self.authorize("write", wing=wing, room=room)
        with self._owner._managed_foreground(wing, room, action_id):
            yield

    def __init__(self, owner: DrawerStore, token_hash: str) -> None:
        """Bind an owner store and a token digest without opening another store."""
        self._owner = owner
        self._token_hash = token_hash
        self._grant_reader: _GrantReader | None = None
        self._export_depth = 0
        self._import_depth = 0

    def __getattr__(self, name: str) -> NoReturn:
        """Deny unsupported operations instead of exposing owner state."""
        raise AccessDenied(_DENIED)

    def __enter__(self) -> ScopedStore:
        """Enter the bound view without opening another store."""
        return self

    def __exit__(self, *_: object) -> None:
        """Close the owner store on context exit."""
        self.close()

    def _authority_row(self) -> dict[str, Any] | None:
        if self._grant_reader is None:
            self._grant_reader = _GrantReader(self._owner._path, self._token_hash)
        return self._grant_reader.read()

    def _close_grant_reader(self) -> None:
        if self._grant_reader is not None:
            self._grant_reader.close()

    def _grant(self) -> dict[str, Any]:
        try:
            if self._owner._read_snapshot is None:
                row = self._owner._conn.execute(
                    "SELECT * FROM access_grants WHERE token_hash=?", (self._token_hash,)
                ).fetchone()
            else:
                # A private task snapshot is not the authority for live revocation.
                row = self._authority_row()
        except sqlite3.Error as exc:
            raise AccessDenied(_DENIED) from exc
        row = _active(row)
        return {
            "scopes": json.loads(row["scopes"]),
            "capabilities": json.loads(row["capabilities"]),
        }

    @staticmethod
    def _matches(scope: dict[str, Any], wing: str, room: str | None, key: int | None) -> bool:
        return (
            scope["wing"] == wing
            and (
                "rooms" not in scope
                or (room in scope["rooms"] if room is not None else bool(scope["rooms"]))
            )
            and (
                "drawer_ids" not in scope
                or (key in scope["drawer_ids"] if key is not None else bool(scope["drawer_ids"]))
            )
        )

    def _rows(self, *, capability: str = "read") -> dict[int, sqlite3.Row]:
        grant = self._grant()
        if capability not in grant["capabilities"]:
            raise AccessDenied(_DENIED)
        rows = self._owner._conn.execute("SELECT * FROM drawers ORDER BY id DESC").fetchall()
        allowed = {
            int(row["id"]): row
            for row in rows
            if any(
                self._matches(scope, row["wing"], row["room"], int(row["id"]))
                for scope in grant["scopes"]
            )
        }
        try:
            identities = {
                row["identity"]: row["drawer_id"]
                for row in self._owner._conn.execute(
                    "SELECT identity, drawer_id FROM portable_records"
                )
            }
        except sqlite3.Error as exc:
            raise AccessDenied(_DENIED) from exc
        dependencies: dict[int, set[int]] = {}
        for key in allowed:
            try:
                targets = [
                    reference["target_identity"]
                    for reference in self._owner.portable_source(key)["references"]
                ]
                if all(isinstance(target, str) for target in targets):
                    for target in targets:
                        target.encode("utf-8")
                    dependencies[key] = {
                        int(identities[target]) if target in identities else -1
                        for target in targets
                    }
                else:
                    dependencies[key] = {
                        item["target_drawer_id"] for item in self._owner.portable_relations(key)
                    }
            except CairntirError:
                dependencies[key] = {-1}
        while True:
            withheld = {key for key in allowed if not dependencies[key] <= allowed.keys()}
            if not withheld:
                return allowed
            for key in withheld:
                del allowed[key]

    def authorize(
        self,
        capability: str,
        *,
        wing: str | None = None,
        room: str | None = None,
        drawer_id: int | None = None,
    ) -> None:
        """Check the live grant capability and any requested scope."""
        grant = self._grant()
        if capability not in grant["capabilities"]:
            raise AccessDenied(_DENIED)
        if drawer_id is not None:
            if drawer_id not in self._rows(capability=capability):
                raise AccessDenied(_DENIED)
        elif wing is not None and not any(
            self._matches(scope, wing, room, None) for scope in grant["scopes"]
        ):
            raise AccessDenied(_DENIED)

    def _authorize_complete_wing(self, wing: str) -> None:
        """Require complete existing read authority without exposing withheld rows."""
        grant = self._grant()
        if "read" not in grant["capabilities"] or not any(
            scope["wing"] == wing and "rooms" not in scope and "drawer_ids" not in scope
            for scope in grant["scopes"]
        ):
            raise AccessDenied(_DENIED)
        try:
            expected = {
                int(row["id"])
                for row in self._owner._conn.execute(
                    "SELECT id FROM drawers WHERE wing=?", (wing,)
                ).fetchall()
            }
            if not expected <= self._rows().keys():
                raise AccessDenied(_DENIED)
        except sqlite3.Error as exc:
            raise AccessDenied(_DENIED) from exc
        if self._grant() != grant:
            raise AccessDenied(_DENIED)

    def _verify_practice_record_inventory(self, wing: str) -> None:
        """Delegate inventory checks only under complete existing wing authority."""
        self._authorize_complete_wing(wing)
        try:
            self._owner._verify_practice_record_inventory(wing)
        except CairntirError as exc:
            raise AccessDenied(_DENIED) from exc
        self._authorize_complete_wing(wing)

    def _creation(self, drawer: Drawer) -> None:
        grant = self._grant()
        if "write" not in grant["capabilities"] or not any(
            "drawer_ids" not in scope and self._matches(scope, drawer.wing, drawer.room, None)
            for scope in grant["scopes"]
        ):
            raise AccessDenied(_DENIED)

    def _references(self, drawer: Drawer) -> None:
        from cairntir.portable import _reference_specs

        references = {
            reference["source_target_id"]
            for reference in _reference_specs(drawer.model_dump(mode="json"))
        }
        if references:
            grant = self._grant()
            if not references <= self._rows().keys() or self._grant() != grant:
                raise AccessDenied(_DENIED)

    def close(self) -> None:
        """Close the authority helper, owned connection and any private snapshot."""
        try:
            self._close_grant_reader()
        finally:
            self._owner.close()

    @property
    def transaction_active(self) -> bool:
        """Check a live read grant before inspecting transaction ownership."""
        self.authorize("read")
        return self._owner.transaction_active

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Apply the bound grant to the corresponding drawer-store operation."""
        self.authorize("write")
        with self._owner.transaction():
            yield
            self.authorize("write")

    def add(
        self, drawer: Drawer, *, provenance: WriteProvenance | None = None, model: str | None = None
    ) -> Drawer:
        """Apply the bound grant to the corresponding drawer-store operation."""
        self._creation(drawer)
        self._references(drawer)
        with self.transaction():
            return self._owner.add(drawer, provenance=provenance, model=model)

    def get(self, drawer_id: int) -> Drawer | None:
        """Apply the bound grant to the corresponding drawer-store operation."""
        row = self._rows().get(drawer_id)
        if row is None:
            raise AccessDenied(_DENIED)
        return _row_to_drawer(row)

    def _iteration_artifact_attach(
        self, iteration_id: int, kind: str, label: str, data: bytes
    ) -> dict[str, Any]:
        self.authorize("read", drawer_id=iteration_id)
        self.authorize("write", drawer_id=iteration_id)
        with self.transaction():
            result = self._owner._iteration_artifact_attach(iteration_id, kind, label, data)
            self.authorize("read", drawer_id=iteration_id)
            self.authorize("write", drawer_id=iteration_id)
            return result

    def _iteration_artifact_refs(self, iteration_id: int) -> list[dict[str, Any]]:
        self.authorize("read", drawer_id=iteration_id)
        result = self._owner._iteration_artifact_refs(iteration_id)
        self.authorize("read", drawer_id=iteration_id)
        return result

    def _iteration_artifact_blob(
        self, iteration_id: int, artifact_id: int
    ) -> tuple[dict[str, Any], bytes | None] | None:
        self.authorize("read", drawer_id=iteration_id)
        result = self._owner._iteration_artifact_blob(iteration_id, artifact_id)
        self.authorize("read", drawer_id=iteration_id)
        return result

    def get_provenance(self, drawer_id: int) -> WriteProvenance | None:
        """Apply the bound grant to the corresponding drawer-store operation."""
        self.authorize("read", drawer_id=drawer_id)
        return self._owner.get_provenance(drawer_id)

    def _list(
        self,
        *,
        capability: str = "read",
        wing: str | None = None,
        room: str | None = None,
        layer: Layer | None = None,
        limit: int | None = 100,
        include_expired: bool = False,
    ) -> list[Drawer]:
        now = datetime.now(UTC).isoformat()
        rows = [
            row
            for row in self._rows(capability=capability).values()
            if (wing is None or row["wing"] == wing)
            and (room is None or row["room"] == room)
            and (layer is None or row["layer"] == layer.value)
            and (include_expired or row["valid_until"] > now)
        ]
        return [_row_to_drawer(row) for row in (rows if limit is None else rows[:limit])]

    def list_by(
        self,
        *,
        wing: str | None = None,
        room: str | None = None,
        layer: Layer | None = None,
        limit: int | None = 100,
        include_expired: bool = False,
    ) -> list[Drawer]:
        """Apply the bound grant to the corresponding drawer-store operation."""
        return self._list(
            wing=wing, room=room, layer=layer, limit=limit, include_expired=include_expired
        )

    def list_for_export(
        self,
        *,
        wing: str | None = None,
        room: str | None = None,
        limit: int | None = 100,
        include_expired: bool = False,
    ) -> list[Drawer]:
        """List whole permitted records under the independent export capability."""
        return self._list(
            capability="export", wing=wing, room=room, limit=limit, include_expired=include_expired
        )

    @contextmanager
    def _portable_export(self) -> Iterator[None]:
        self.authorize("export")
        self._export_depth += 1
        try:
            yield
            self.authorize("export")
        finally:
            self._export_depth -= 1

    def _portable_capability(self) -> str:
        return "export" if self._export_depth else "write" if self._import_depth else "read"

    def portable_store_identity(self) -> str:
        """Expose the physical store UUID only under the current read grant."""
        self.authorize("read")
        identity = self._owner.portable_store_identity()
        self.authorize("read")
        return identity

    def reference_drawer(self, drawer_id: int) -> Drawer | None:
        """Read an authorized drawer without recording a retrieval."""
        grant = self._grant()
        drawer = self.get(drawer_id)
        self.authorize("read", drawer_id=drawer_id)
        if self._grant() != grant:
            raise AccessDenied(_DENIED)
        return drawer

    def reference_family(self, drawer_id: int) -> list[tuple[Drawer, WriteProvenance]]:
        """Return a whole source family only when every member is readable."""
        self.authorize("read", drawer_id=drawer_id)
        grant = self._grant()
        family = self._owner.reference_family(drawer_id)
        for drawer, _ in family:
            if drawer.id is None:
                raise AccessDenied(_DENIED)
            self.authorize("read", drawer_id=drawer.id)
        self.authorize("read", drawer_id=drawer_id)
        if self._grant() != grant:
            raise AccessDenied(_DENIED)
        return family

    def portable_identity(self, drawer_id: int) -> str:
        """Apply the bound grant to the corresponding drawer-store operation."""
        self.authorize(self._portable_capability(), drawer_id=drawer_id)
        return self._owner.portable_identity(drawer_id)

    def portable_source(self, drawer_id: int) -> dict[str, Any]:
        """Apply the bound grant to the corresponding drawer-store operation."""
        self.authorize(self._portable_capability(), drawer_id=drawer_id)
        return self._owner.portable_source(drawer_id)

    def portable_relations(self, drawer_id: int) -> list[dict[str, Any]]:
        """Apply the bound grant to the corresponding drawer-store operation."""
        self.authorize(self._portable_capability(), drawer_id=drawer_id)
        return self._owner.portable_relations(drawer_id)

    def _portable_lookup(self, identity: str) -> int | None:
        key = self._owner._portable_lookup(identity)
        if key is not None:
            self.authorize(self._portable_capability(), drawer_id=key)
        return key

    def _portable_replace(self, drawer_id: int, identity: str, record: dict[str, Any]) -> None:
        self.authorize("write", drawer_id=drawer_id)
        self._owner._portable_replace(drawer_id, identity, record)

    def _portable_supersedes(self, drawer_id: int, target_id: int) -> None:
        self.authorize("write", drawer_id=drawer_id)
        self.authorize("read", drawer_id=target_id)
        self._owner._portable_supersedes(drawer_id, target_id)

    def context_candidates(
        self, *, wing: str, limit: int | None = None
    ) -> tuple[list[tuple[Drawer, WriteProvenance]], int]:
        """Apply the bound grant to the corresponding drawer-store operation."""
        rows = [row for row in self._rows().values() if row["wing"] == wing]
        return [_context_record(row) for row in (rows if limit is None else rows[:limit])], len(
            rows
        )

    def context_relatives(
        self, *, wing: str, drawer_ids: Sequence[int]
    ) -> list[tuple[Drawer, WriteProvenance]]:
        """Apply the bound grant to the corresponding drawer-store operation."""
        rows = self._rows()
        if any(key not in rows for key in drawer_ids):
            raise AccessDenied(_DENIED)
        wanted = set(drawer_ids)
        while True:
            connected = {
                key
                for key, row in rows.items()
                if row["wing"] == wing
                and (
                    key in wanted
                    or row["supersedes_id"] in wanted
                    or any(rows[k]["supersedes_id"] == key for k in wanted)
                )
            }
            if connected == wanted:
                return [_context_record(rows[key]) for key in sorted(wanted)]
            wanted = connected

    def context_suppressed_ids(self, drawer_ids: Sequence[int]) -> set[int]:
        """Return visible predecessors displaced by a hidden current successor."""
        visible = self._rows()
        if any(key not in visible for key in drawer_ids):
            raise AccessDenied(_DENIED)
        now = datetime.now(UTC)
        suppressed = set()
        for key in drawer_ids:
            for row in self._owner._conn.execute(
                "SELECT * FROM drawers WHERE supersedes_id=?", (key,)
            ):
                receipt = WriteProvenance.from_json(row["provenance"])
                if (
                    int(row["id"]) not in visible
                    and row["valid_until"] > now.isoformat()
                    and (receipt.valid_from is None or receipt.valid_from <= now)
                ):
                    suppressed.add(key)
        return suppressed

    def has_export_successor(self, drawer_id: int) -> bool:
        """Check export currentness without granting read or write authority."""
        self.authorize("export", drawer_id=drawer_id)
        result = self._owner.has_export_successor(drawer_id)
        self.authorize("export", drawer_id=drawer_id)
        return result

    def has_direct_successor(self, drawer_id: int) -> bool:
        """Check a visible writable source's lineage without exposing its children."""
        self.authorize("read", drawer_id=drawer_id)
        self.authorize("write", drawer_id=drawer_id)
        try:
            exists = (
                self._owner._conn.execute(
                    "SELECT 1 FROM drawers WHERE supersedes_id=? LIMIT 1", (drawer_id,)
                ).fetchone()
                is not None
            )
        except sqlite3.Error as exc:
            raise AccessDenied(_DENIED) from exc
        self.authorize("read", drawer_id=drawer_id)
        self.authorize("write", drawer_id=drawer_id)
        return exists

    def context_similarities(self, query: str, drawer_ids: Sequence[int]) -> dict[int, float]:
        """Apply the bound grant to the corresponding drawer-store operation."""
        rows = self._rows()
        if any(key not in rows for key in drawer_ids):
            raise AccessDenied(_DENIED)
        return self._owner.context_similarities(query, drawer_ids)

    def search(
        self,
        query: str,
        *,
        wing: str | None = None,
        room: str | None = None,
        layer: Layer | None = None,
        limit: int = 10,
        rerank_by_belief: bool = True,
        trust: TrustLevel | None = None,
        include_expired: bool = False,
    ) -> list[tuple[Drawer, float]]:
        """Apply the bound grant to the corresponding drawer-store operation."""
        drawers = self.list_by(
            wing=wing, room=room, layer=layer, limit=None, include_expired=include_expired
        )
        if trust is not None:
            drawers = [
                drawer
                for drawer in drawers
                if (receipt := self._owner.get_provenance(int(drawer.id or 0))) is not None
                and receipt.trust == trust
            ]
        scores = self.context_similarities(query, [int(drawer.id or 0) for drawer in drawers])
        results = sorted(
            ((drawer, 1.0 - scores[int(drawer.id or 0)]) for drawer in drawers),
            key=lambda item: item[1],
        )[:limit]
        return rerank_results(results) if rerank_by_belief else results

    def update_layer(self, drawer_id: int, layer: Layer) -> None:
        """Apply the bound grant to the corresponding drawer-store operation."""
        self.authorize("write", drawer_id=drawer_id)
        with self.transaction():
            self._owner.update_layer(drawer_id, layer)

    def add_anchors(
        self, drawer_id: int, anchors: Sequence[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Apply the bound grant to the corresponding drawer-store operation."""
        self.authorize("read", drawer_id=drawer_id)
        self.authorize("write", drawer_id=drawer_id)
        with self.transaction():
            return self._owner.add_anchors(drawer_id, anchors)

    def repair_anchors(self, drawer_id: int) -> list[dict[str, Any]]:
        """Apply the bound grant to the corresponding drawer-store operation."""
        self.authorize("read", drawer_id=drawer_id)
        self.authorize("write", drawer_id=drawer_id)
        with self.transaction():
            return self._owner.repair_anchors(drawer_id)

    def reinforce(self, drawer_id: int, *, amount: float = 1.0) -> float:
        """Apply the bound grant to the corresponding drawer-store operation."""
        self.authorize("write", drawer_id=drawer_id)
        with self.transaction():
            return self._owner.reinforce(drawer_id, amount=amount)

    def weaken(self, drawer_id: int, *, amount: float = 1.0) -> float:
        """Apply the bound grant to the corresponding drawer-store operation."""
        self.authorize("write", drawer_id=drawer_id)
        with self.transaction():
            return self._owner.weaken(drawer_id, amount=amount)

    def stale_ids(
        self, *, older_than: datetime, layer: Layer, wing: str | None = None
    ) -> list[int]:
        """Apply the bound grant to the corresponding drawer-store operation."""
        return [
            key
            for key, row in self._rows().items()
            if row["layer"] == layer.value
            and (wing is None or row["wing"] == wing)
            and row["last_accessed_at"] is not None
            and row["last_accessed_at"] < older_than.isoformat()
        ]

    def has_content_since(self, *, wing: str, content: str, created_at: datetime) -> bool:
        """Apply the bound grant to the corresponding drawer-store operation."""
        return any(
            drawer.content == content and drawer.created_at >= created_at
            for drawer in self.list_by(wing=wing, limit=None)
        )

    def wing_exists(self, wing: str, *, include_expired: bool = False) -> bool:
        """Apply the bound grant to the corresponding drawer-store operation."""
        return bool(self.list_by(wing=wing, limit=1, include_expired=include_expired))

    def content_lengths(
        self, *, wing: str | None = None, include_expired: bool = False
    ) -> list[int]:
        """Apply the bound grant to the corresponding drawer-store operation."""
        return sorted(
            len(drawer.content)
            for drawer in self.list_by(wing=wing, limit=None, include_expired=include_expired)
        )

    def wing_counts(self, *, include_expired: bool = False) -> dict[str, int]:
        """Apply the bound grant to the corresponding drawer-store operation."""
        return dict(
            Counter(
                drawer.wing for drawer in self.list_by(limit=None, include_expired=include_expired)
            )
        )

    def _workflow_key(self, key: str) -> str:
        return f"grant:{self._token_hash}:{key}"

    def workflow_receipt(self, idempotency_key: str) -> WorkflowReceipt | None:
        """Apply the bound grant to the corresponding drawer-store operation."""
        self.authorize("read")
        return self._owner.workflow_receipt(self._workflow_key(idempotency_key))

    def paladin_human_drawers(self, *, wing: str) -> list[Drawer]:
        """Read only a fully authorized Q06 wing."""
        self._authorize_complete_wing(wing)
        drawers = self._owner.paladin_human_drawers(wing=wing)
        self._authorize_complete_wing(wing)
        return drawers

    def paladin_human_receipt(self, idempotency_key: str, *, wing: str) -> WorkflowReceipt | None:
        """Read a Q06 receipt through the complete-wing boundary."""
        self._authorize_complete_wing(wing)
        receipt = self._owner.paladin_human_receipt(idempotency_key, wing=wing)
        self._authorize_complete_wing(wing)
        return receipt

    def paladin_human_pending_map(
        self, idempotency_key: str, *, wing: str, request: dict[str, Any]
    ) -> bool:
        """Check a pending map only within an authorized wing."""
        self._authorize_complete_wing(wing)
        pending = self._owner.paladin_human_pending_map(idempotency_key, wing=wing, request=request)
        self._authorize_complete_wing(wing)
        return pending

    def paladin_human_execute_once(
        self,
        *,
        wing: str,
        room: str,
        idempotency_key: str,
        operation: str,
        request: dict[str, Any],
        action: Callable[[], dict[str, Any]],
    ) -> WorkflowExecution:
        """Execute Q06 outside a scoped outer transaction for durability."""
        self._authorize_complete_wing(wing)
        self._creation(Drawer(wing=wing, room=room, content="Q06 receipt"))

        def checked_action() -> dict[str, Any]:
            self._authorize_complete_wing(wing)
            self._creation(Drawer(wing=wing, room=room, content="Q06 receipt"))
            result = action()
            self._authorize_complete_wing(wing)
            self._creation(Drawer(wing=wing, room=room, content="Q06 receipt"))
            return result

        execution = self._owner.paladin_human_execute_once(
            wing=wing,
            room=room,
            idempotency_key=idempotency_key,
            operation=operation,
            request=request,
            action=checked_action,
        )
        self._authorize_complete_wing(wing)
        self._creation(Drawer(wing=wing, room=room, content="Q06 receipt"))
        return execution

    def _paladin_resources_records(
        self, *, wing: str, room: str, run_id: str, task_id: str
    ) -> dict[str, list[dict[str, Any]]]:
        """Read one complete resource run through the current complete-wing grant."""

        def live_grant() -> dict[str, Any]:
            row = (
                self._owner._conn.execute(
                    "SELECT * FROM access_grants WHERE token_hash=?", (self._token_hash,)
                ).fetchone()
                if self._owner._read_snapshot is None
                else self._authority_row()
            )
            return dict(_active(row))

        try:
            grant = live_grant()
            self._authorize_complete_wing(wing)
            result = _paladin_resources_records(
                self._owner, wing=wing, room=room, run_id=run_id, task_id=task_id
            )
            self._authorize_complete_wing(wing)
            if live_grant() != grant:
                raise AccessDenied(_DENIED)
        except sqlite3.Error as exc:
            raise AccessDenied(_DENIED) from exc
        else:
            return result

    def _paladin_ui_records(
        self, *, wing: str, room: str, run_id: str, task_id: str, baseline_id: str
    ) -> dict[str, list[dict[str, Any]]]:
        """Read fixed UI history through a live complete-wing grant."""

        def live_grant() -> dict[str, Any]:
            row = (
                self._owner._conn.execute(
                    "SELECT * FROM access_grants WHERE token_hash=?", (self._token_hash,)
                ).fetchone()
                if self._owner._read_snapshot is None
                else self._authority_row()
            )
            return dict(_active(row))

        try:
            grant = live_grant()
            self._authorize_complete_wing(wing)
            result = _paladin_ui_records(
                self._owner,
                wing=wing,
                room=room,
                run_id=run_id,
                task_id=task_id,
                baseline_id=baseline_id,
            )
            self._authorize_complete_wing(wing)
            if live_grant() != grant:
                raise AccessDenied(_DENIED)
        except sqlite3.Error as exc:
            raise AccessDenied(_DENIED) from exc
        else:
            return result

    def _managed_records(
        self, *, wing: str, room: str | None = None, selected_task_id: str | None = None
    ) -> list[dict[str, Any]]:
        self.authorize("read", wing=wing)
        records = self._owner._managed_records(
            wing=wing,
            key_prefix=self._workflow_key(""),
            include_events=True,
            include_reconciliations=True,
            include_closes=True,
        )
        visible = self._rows()
        allowed = []
        for record in records:
            bound = record["_managed"]["request"]
            if room is not None and bound["room"] != room:
                continue
            if (
                record["_managed"]["operation"] == "managed.reconcile.v1"
                and record["task_id"] != selected_task_id
            ):
                continue
            if not set(record["_managed"]["evidence_ids"]) <= visible.keys():
                if record["_managed"]["operation"] == "managed.event.v1":
                    continue
                raise AccessDenied("managed workflow evidence is unavailable")
            allowed.append(record)
        return allowed

    def _managed_event_identity_occupied(
        self, *, wing: str, room: str, session_id: str, sequence: int, event_id: str
    ) -> bool:
        self.authorize("read", wing=wing, room=room)
        self.authorize("write", wing=wing, room=room)
        return self._owner._managed_event_identity_occupied(
            wing=wing, room=room, session_id=session_id, sequence=sequence, event_id=event_id
        )

    def _managed_shared_once(
        self,
        *,
        idempotency_key: str,
        operation: str,
        request: dict[str, Any],
        action: Callable[[], dict[str, Any]],
    ) -> WorkflowExecution:
        payload = request.get("request")
        if request.keys() != {"wing", "room", "request"} or not isinstance(payload, dict):
            raise AccessDenied(_DENIED)
        wing, room = request["wing"], request["room"]
        if operation == "managed.sequence.v1":
            session_id, sequence = payload.get("session_id"), payload.get("sequence")
            expected = f"managed:sequence:{wing}:{session_id}:{sequence}"
            schema = "cairntir.managed-event.v1"
        elif operation == "managed.event.v1":
            expected = f"managed:event:{payload.get('event_id')}"
            schema = "cairntir.managed-event.v1"
        elif operation == "managed.reconcile.v1":
            expected = f"managed:reconcile:{payload.get('reconciliation_id')}"
            schema = "cairntir.managed-reconcile.v1"
        else:
            raise AccessDenied(_DENIED)
        if idempotency_key != expected or payload.get("schema") != schema:
            raise AccessDenied(_DENIED)
        with self.transaction():
            self.authorize("read", wing=wing, room=room)
            self.authorize("write", wing=wing, room=room)
            if not any(
                "drawer_ids" not in scope and self._matches(scope, wing, room, None)
                for scope in self._grant()["scopes"]
            ):
                raise AccessDenied(_DENIED)
            if operation == "managed.reconcile.v1":
                self.authorize("read", drawer_id=payload["event_drawer_id"])
                for drawer_id in payload["evidence_ids"]:
                    self.authorize("read", drawer_id=drawer_id)
            result = self._owner.execute_once(
                idempotency_key=idempotency_key,
                operation=operation,
                request=request,
                action=action,
            )
            for drawer_id in result.result["_managed"]["evidence_ids"]:
                self.authorize("read", drawer_id=drawer_id)
            return result

    def _task_records(self, *, wing: str) -> list[dict[str, Any]]:
        self.authorize("read")
        records = self._owner._task_records(wing=wing)
        visible = self._rows()
        hidden = set()
        for record in records:
            required = {
                record["original_drawer_id"],
                record["checkpoint_drawer_id"],
                *record["_task"]["evidence_ids"],
            }
            if not required <= visible.keys():
                hidden.add(record["task_id"])
        return [record for record in records if record["task_id"] not in hidden]

    def _task_drawers(self, drawer_ids: Sequence[int]) -> dict[int, tuple[Drawer, WriteProvenance]]:
        visible = self._rows()
        if not set(drawer_ids) <= visible.keys():
            raise AccessDenied(_DENIED)
        return {key: _context_record(visible[key]) for key in drawer_ids}

    def _question_records(self, *, wing: str) -> tuple[list[dict[str, Any]], set[int]]:
        visible = self._rows()
        records, _ = self._owner._question_records(wing=wing)
        hidden: set[int] = set()
        for record in records:
            required = {
                record["question_drawer_id"],
                *(ref["drawer_id"] for ref in record["_question"]["evidence"]),
            }
            if record["resolution_drawer_id"] is not None:
                required.add(record["resolution_drawer_id"])
            if not required <= visible.keys():
                hidden.add(record["question_drawer_id"])
        return (
            [record for record in records if record["question_drawer_id"] not in hidden],
            hidden & visible.keys(),
        )

    def execute_once(
        self,
        *,
        idempotency_key: str,
        operation: str,
        request: dict[str, Any],
        action: Callable[[], dict[str, Any]],
    ) -> WorkflowExecution:
        """Apply the bound grant to the corresponding drawer-store operation."""
        with self.transaction():
            if operation == "portable.import.v2":
                self._import_depth += 1
            try:
                return self._owner.execute_once(
                    idempotency_key=self._workflow_key(idempotency_key),
                    operation=operation,
                    request=request,
                    action=action,
                )
            finally:
                if operation == "portable.import.v2":
                    self._import_depth -= 1

    def _procedure_record(self, drawer_id: int) -> dict[str, Any] | None:
        self.authorize("read", drawer_id=drawer_id)
        record = self._owner._procedure_record(drawer_id)
        if record is not None and not self._registry_ids(record) <= self._rows().keys():
            raise AccessDenied(_DENIED)
        return record

    @staticmethod
    def _registry_ids(value: dict[str, Any]) -> set[int]:
        names = {
            "drawer_id",
            "root_id",
            "supersedes_id",
            "evaluation_id",
            "procedure_id",
            "current_id",
            "evidence_id",
            "baseline_prediction_id",
            "baseline_observation_id",
            "candidate_prediction_id",
            "candidate_observation_id",
            "evidence_ids",
            "counterexample_ids",
        }
        result: set[int] = set()

        def visit(item: Any, key: str = "") -> None:
            if isinstance(item, dict):
                for name, child in item.items():
                    visit(child, name)
            elif isinstance(item, (list, tuple)):
                for child in item:
                    visit(child, key)
            elif key in names and type(item) is int and item > 0:
                result.add(item)

        visit(value)
        return result

    def _discovery_practice_wings(self, wing: str | None) -> frozenset[str]:
        """Require history for selected methods before dependency closure hides them."""
        grant = self._grant()
        if "read" not in grant["capabilities"]:
            raise AccessDenied(_DENIED)
        wings: set[str] = set()
        try:
            rows = self._owner._conn.execute(
                "SELECT d.id,d.wing,d.room,d.metadata,p.drawer_id AS registered_id "
                "FROM drawers d LEFT JOIN procedure_records p ON p.drawer_id=d.id "
                "WHERE (? IS NULL OR d.wing=?) "
                "AND (d.room='discoveries' OR p.drawer_id IS NOT NULL)",
                (wing, wing),
            )
            for row in rows:
                if not any(
                    self._matches(scope, row["wing"], row["room"], int(row["id"]))
                    for scope in grant["scopes"]
                ):
                    continue
                metadata = json.loads(row["metadata"])
                if not isinstance(metadata, dict):
                    raise AccessDenied(_DENIED)
                if row["registered_id"] is not None or "procedure_revision" in metadata:
                    wings.add(str(row["wing"]))
        except (sqlite3.Error, TypeError, ValueError) as exc:
            raise AccessDenied(_DENIED) from exc
        for selected in wings:
            self._authorize_complete_wing(selected)
        if self._grant() != grant:
            raise AccessDenied(_DENIED)
        return frozenset(wings)

    def _procedure_records(self, wing: str | None = None) -> list[dict[str, Any]]:
        visible = self._rows()
        return [
            record
            for record in self._owner._procedure_records(wing)
            if self._registry_ids(record) <= visible.keys()
        ]

    def is_registered_procedure(self, drawer_id: int) -> bool:
        """Apply the bound grant to the corresponding drawer-store operation."""
        return self._procedure_record(drawer_id) is not None

    def _register_procedure(
        self, drawer_id: int, *, root_id: int, parent_id: int | None, payload: dict[str, Any]
    ) -> None:
        with self.transaction():
            self.authorize("write", drawer_id=drawer_id)
            for key in (root_id, parent_id):
                if key is not None:
                    self.authorize("read", drawer_id=key)
            if not self._registry_ids(payload) <= self._rows().keys():
                raise AccessDenied(_DENIED)
            self._owner._register_procedure(
                drawer_id, root_id=root_id, parent_id=parent_id, payload=payload
            )

    def _procedure_evaluation(self, drawer_id: int) -> dict[str, Any] | None:
        self.authorize("read", drawer_id=drawer_id)
        record = self._owner._procedure_evaluation(drawer_id)
        if record is not None and not self._registry_ids(record) <= self._rows().keys():
            raise AccessDenied(_DENIED)
        return record

    def _register_procedure_evaluation(self, drawer_id: int, payload: dict[str, Any]) -> None:
        with self.transaction():
            self.authorize("write", drawer_id=drawer_id)
            if not self._registry_ids(payload) <= self._rows().keys():
                raise AccessDenied(_DENIED)
            self._owner._register_procedure_evaluation(drawer_id, payload)
