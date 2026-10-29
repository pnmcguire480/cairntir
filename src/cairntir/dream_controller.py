"""Durable, fair scheduling for an explicitly enabled local Dream worker."""

from __future__ import annotations

import json
import math
import os
import queue
import sqlite3
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from cairntir.backups import _file_lock
from cairntir.dream import DreamError, _config, _connection, _eligible, _save
from cairntir.memory.embeddings import EmbeddingProvider
from cairntir.memory.store import backup_database

DEFAULTS: dict[str, Any] = {
    "poll_seconds": 30,
    "review_seconds": 86400,
    "retry_seconds": 60,
    "inference_seconds": 30,
    "max_calls": 4,
    "window_seconds": 3600,
    "max_pending": 128,
    "exclude_wings": [],
}
_SCHEMA = """
CREATE TABLE IF NOT EXISTS dream_control (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1), config TEXT NOT NULL, state TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dream_work (
    job_id TEXT PRIMARY KEY, wing TEXT NOT NULL UNIQUE, reason TEXT NOT NULL,
    evidence_ids TEXT NOT NULL, next_at REAL NOT NULL, priority REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS dream_reviews (evidence_id INTEGER PRIMARY KEY, reviewed REAL NOT NULL);
CREATE TABLE IF NOT EXISTS dream_turns (wing TEXT PRIMARY KEY, served REAL NOT NULL);
CREATE TABLE IF NOT EXISTS dream_attempts (
    id TEXT PRIMARY KEY, job_id TEXT, owner_key TEXT, worker_pid INTEGER,
    launched REAL, created REAL NOT NULL, receipt TEXT NOT NULL, done INTEGER NOT NULL
);
"""


def _stamp(value: float | None = None) -> str:
    return datetime.fromtimestamp(time.time() if value is None else value, UTC).isoformat()


def lock_path(path: Path, kind: str) -> Path:
    """Derive a coordination path from the explicitly selected database."""
    return path.with_name(path.name + f".dream-{kind}.lock")


def _busy(path: Path) -> bool:
    if not path.exists():
        return False
    with _file_lock(path, create=False) as acquired:
        return not acquired


@contextmanager
def _gate(path: Path) -> Iterator[None]:
    deadline = time.monotonic() + 2
    while True:
        with _file_lock(lock_path(path, "gate"), create=True) as acquired:
            if acquired:
                yield
                return
        if time.monotonic() >= deadline:
            raise DreamError("Dream coordination is busy")
        time.sleep(0.01)


def configured(path: Path) -> bool:
    """Inspect scheduling opt-in without creating state."""
    if not path.is_file():
        return False
    with closing(_connection(path, read_only=True)) as connection:
        return (
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name='dream_control' AND type='table'"
            ).fetchone()
            is not None
        )


def _read(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if not configured(path):
        return dict(DEFAULTS), {}
    with closing(_connection(path, read_only=True)) as connection:
        row = connection.execute(
            "SELECT config,state FROM dream_control WHERE singleton=1"
        ).fetchone()
    return (json.loads(row[0]), json.loads(row[1])) if row else (dict(DEFAULTS), {})


def _initialize(path: Path) -> None:
    if _config(path) is None:
        raise DreamError("Enable local Dream before configuring or starting its controller")
    if configured(path):
        return
    with _gate(path):
        if configured(path):
            return
        suffix = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        backup_database(
            path, path.with_name(f"{path.stem}.pre-dream-controller-{suffix}{path.suffix}")
        )
        with closing(_connection(path)) as connection, connection:
            connection.executescript(_SCHEMA)
            connection.execute(
                "INSERT INTO dream_control VALUES(1,?,?)", (json.dumps(DEFAULTS), "{}")
            )
            connection.execute(
                "INSERT INTO dream_reviews SELECT p.evidence_id, "
                "COALESCE((julianday(r.created_at)-2440587.5)*86400,?) "
                "FROM dream_processed p LEFT JOIN dream_receipts r ON r.receipt_id=p.receipt_id",
                (time.time(),),
            )


def configure(path: Path, **changes: Any) -> dict[str, Any]:
    """Validate all requested settings before changing the persisted policy."""
    for key, value in changes.items():
        if key not in DEFAULTS:
            raise DreamError(f"Unknown Dream setting: {key}")
        if key in {"max_calls", "max_pending"}:
            if type(value) is not int or value < 1:
                raise DreamError(f"{key} must be a positive integer")
        elif key == "exclude_wings":
            if not isinstance(value, list) or any(
                not isinstance(w, str) or not w.strip() for w in value
            ):
                raise DreamError("exclude_wings must contain nonempty wing names")
        elif (
            type(value) not in {int, float}
            or not math.isfinite(value)
            or value <= 0
            or (key != "inference_seconds" and value < 0.1)
            or (key == "inference_seconds" and value > 60)
        ):
            raise DreamError(f"Invalid Dream duration: {key}")
    _initialize(path)
    with _gate(path), closing(_connection(path)) as connection, connection:
        settings, _ = _read(path)
        settings.update(changes)
        connection.execute(
            "UPDATE dream_control SET config=? WHERE singleton=1", (json.dumps(settings),)
        )
    return {"schema": "cairntir.dream-controller-config.v1", **settings}


def _state(path: Path, **changes: Any) -> None:
    with closing(_connection(path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        state = json.loads(
            connection.execute("SELECT state FROM dream_control WHERE singleton=1").fetchone()[0]
        )
        state.update(changes)
        connection.execute(
            "UPDATE dream_control SET state=? WHERE singleton=1", (json.dumps(state),)
        )


def foreground_active(path: Path) -> bool:
    """Observe real foreground owner locks; dead owners cannot retain priority."""
    directory = path.with_name(path.name + ".dream-foreground")
    return directory.is_dir() and any(_busy(item) for item in directory.glob("*.lock"))


@contextmanager
def foreground(path: Path, action_id: str) -> Iterator[None]:
    """Mark authorized managed execution without waiting for existing inference."""
    if _config(path) is None:
        yield
        return
    token = str(uuid4())
    directory = path.with_name(path.name + ".dream-foreground")
    directory.mkdir(exist_ok=True)
    marker = directory / f"{token}.lock"
    with _gate(path):
        lease = _file_lock(marker, create=True)
        acquired = lease.__enter__()
        if not acquired:
            lease.__exit__(None, None, None)
            raise DreamError("Cannot acquire foreground activity identity")
        marker.with_suffix(".json").write_text(
            json.dumps(
                {"action_id": action_id, "pid": os.getpid(), "owner": token, "started_at": _stamp()}
            ),
            encoding="utf-8",
        )
    try:
        yield
    finally:
        lease.__exit__(None, None, None)


def _budget(path: Path, settings: dict[str, Any]) -> tuple[int, float | None]:
    with closing(_connection(path, read_only=True)) as connection:
        row = connection.execute(
            "SELECT COUNT(*),MIN(launched) FROM dream_attempts WHERE launched>?",
            (time.time() - settings["window_seconds"],),
        ).fetchone()
    return row[0], row[1] + settings["window_seconds"] if row[1] is not None else None


def receipts(path: Path, limit: int = 100) -> dict[str, Any]:
    """Return complete finished attempt history without driving work."""
    if limit < 1:
        raise DreamError("receipt limit must be positive")
    rows: list[Any] = []
    if configured(path):
        with closing(_connection(path, read_only=True)) as connection:
            rows = connection.execute(
                "SELECT receipt FROM dream_attempts WHERE done=1 ORDER BY rowid DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return {
        "schema": "cairntir.dream-controller-receipts.v1",
        "receipts": [json.loads(r[0]) for r in reversed(rows)],
    }


def _process_identity(pid: int) -> str | None:
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetProcessTimes.argtypes = [
            wintypes.HANDLE,
            *[ctypes.POINTER(wintypes.FILETIME)] * 4,
        ]
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            if ctypes.get_last_error() == 87:
                return None
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            times = [wintypes.FILETIME() for _ in range(4)]
            if not kernel.GetProcessTimes(handle, *[ctypes.byref(item) for item in times]):
                raise ctypes.WinError(ctypes.get_last_error())
            code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
                raise ctypes.WinError(ctypes.get_last_error())
            if code.value != 259:
                return None
            return str((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime)
        finally:
            kernel.CloseHandle(handle)
    try:
        if sys.platform.startswith("linux"):
            raw = Path(f"/proc/{pid}/stat").read_text()
            fields = raw[raw.rfind(")") + 2 :].split()
            return None if fields[0] == "Z" else fields[19]
        os.kill(pid, 0)
    except (FileNotFoundError, ProcessLookupError):
        return None
    return str(pid)


def _live_owner(state: dict[str, Any]) -> bool:
    pid = state.get("pid")
    if not isinstance(pid, int) or pid <= 0:
        return False
    identity = _process_identity(pid)
    return identity is not None and identity == state.get("process_identity")


def status(path: Path, *, _data_path: Path | None = None) -> dict[str, Any]:
    """Report persisted observations alongside actual process-lock ownership."""
    data_path = path if _data_path is None else _data_path
    settings, state = _read(data_path)
    initialized = configured(data_path)
    running = _busy(lock_path(path, "controller")) and _live_owner(state)
    count, reset = _budget(data_path, settings) if initialized else (0, None)
    last = receipts(data_path, 1)["receipts"]
    active = None
    queued = 0
    if initialized:
        with closing(_connection(data_path, read_only=True)) as connection:
            queued = connection.execute("SELECT COUNT(*) FROM dream_work").fetchone()[0]
            row = connection.execute(
                "SELECT id,worker_pid,created FROM dream_attempts WHERE done=0 "
                "AND worker_pid IS NOT NULL ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
        if row is not None and _busy(lock_path(path, "inference")):
            active = {"attempt_id": row[0], "pid": row[1], "started_at": _stamp(row[2])}
    return {
        "running": running,
        "controller_id": state.get("controller_id") if running else None,
        "pid": state.get("pid") if running else None,
        "state": state.get("state", "idle") if running else "stopped",
        "config": settings,
        "last_run": last[0] if last else None,
        "next_run_at": state.get("next_run_at") if running else None,
        "queued_jobs": queued,
        "deferred_wings": state.get("deferred_wings", 0),
        "foreground_active": foreground_active(path),
        "requests_in_window": count,
        "budget_resets_at": _stamp(reset) if reset is not None else None,
        "active_inference": active,
    }


def _worker_ready(line: str) -> tuple[bool, int]:
    info = json.loads(line)
    acquired, pid = info["ready"], info["pid"]
    if type(acquired) is not bool or type(pid) is not int or pid <= 0:
        raise ValueError("Invalid worker identity")
    return acquired, pid


def _spawn_worker(path: Path) -> tuple[subprocess.Popen[str], int]:
    process = subprocess.Popen(  # noqa: S603 - fixed worker file, selected interpreter, no shell
        [sys.executable, str(Path(__file__).with_name("dream_worker.py")), str(path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    ready: queue.Queue[str] = queue.Queue()

    def read() -> None:
        if process.stdout is not None:
            ready.put(process.stdout.readline())

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    try:
        line = ready.get(timeout=5)
        acquired, pid = _worker_ready(line)
    except (queue.Empty, ValueError, KeyError, TypeError):
        process.kill()
        process.communicate(timeout=5)
        raise DreamError("Dream inference worker did not acquire ownership") from None
    if not acquired:
        process.communicate(timeout=5)
        raise DreamError("Dream inference is busy")
    return process, pid


class _CancelledError(DreamError):
    """The owning controller received a durable cancellation request."""


def _cancelled(path: Path, controller_id: str | None) -> bool:
    if controller_id is None:
        return False
    _, state = _read(path)
    return state.get("controller_id") == controller_id and bool(state.get("stop_requested"))


def _check_cancelled(path: Path, controller_id: str | None) -> None:
    if _cancelled(path, controller_id):
        raise _CancelledError("Dream result cancelled before saving by its controller")


def _communicate(process: subprocess.Popen[str], request: dict[str, Any]) -> tuple[str, str] | None:
    try:
        out, err = process.communicate(
            json.dumps(request, ensure_ascii=False) + "\n", timeout=request["timeout"] + 3
        )
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate(timeout=5)
        raise TimeoutError("Dream inference worker exceeded its deadline") from None
    if process.returncode == 125:
        raise _CancelledError(
            "Dream inference cancelled by its controller; server completion is unknown"
        )
    if process.returncode == 124:
        raise TimeoutError("Dream inference exceeded its total deadline")
    if process.returncode:
        raise DreamError(f"Local inference worker failed ({process.returncode}): {err[-1000:]}")
    result = json.loads(out)
    if result["status"] != "ok":
        raise DreamError("Dream inference deferred before launch")
    proposal = result["proposal"]
    return (str(proposal[0]), str(proposal[1])) if proposal is not None else None


def infer(
    path: Path,
    endpoint: str,
    model: str,
    wing: str,
    evidence: list[dict[str, Any]],
    timeout: float,
    claim_token: str,
) -> tuple[str, str] | None:
    """Run a legacy one-shot request in the same exclusively owned child boundary."""
    process, _ = _spawn_worker(path)
    return _communicate(
        process,
        {
            "claim_token": claim_token,
            "endpoint": endpoint,
            "model": model,
            "wing": wing,
            "evidence": evidence,
            "timeout": timeout,
        },
    )


def _receipt(controller_id: str | None, job: dict[str, Any] | None, now: float) -> dict[str, Any]:
    return {
        "receipt_id": str(uuid4()),
        "job_id": job["job_id"] if job else None,
        "attempt_id": str(uuid4()) if job else None,
        "controller_id": controller_id or str(uuid4()),
        "wing": job["wing"] if job else None,
        "reason": job["reason"] if job else "empty",
        "evidence_ids": json.loads(job["evidence_ids"]) if job else [],
        "status": "no_work",
        "candidate_id": None,
        "started_at": _stamp(now),
        "finished_at": _stamp(now),
        "next_run_at": _stamp(now),
        "error": None,
        "uncertain": False,
    }


def _recover(path: Path, settings: dict[str, Any]) -> None:
    if _busy(lock_path(path, "inference")):
        return
    with closing(_connection(path)) as connection, connection:
        for row in connection.execute("SELECT * FROM dream_attempts WHERE done=0").fetchall():
            if _busy(lock_path(path, row["owner_key"])):
                continue
            receipt = json.loads(row["receipt"])
            due = time.time() + settings["retry_seconds"]
            receipt.update(
                status="interrupted",
                uncertain=True,
                error="Controller exited before a confirmed result",
                finished_at=_stamp(),
                next_run_at=_stamp(due),
            )
            connection.execute(
                "UPDATE dream_attempts SET done=1,receipt=? WHERE id=?",
                (json.dumps(receipt), row["id"]),
            )
            connection.execute(
                "UPDATE dream_work SET reason='retry',next_at=? WHERE job_id=?",
                (due, row["job_id"]),
            )


def _refresh(
    path: Path, settings: dict[str, Any], provider_factory: Callable[[], EmbeddingProvider]
) -> dict[int, dict[str, Any]]:
    wings = _eligible(path, provider_factory)
    for excluded in settings["exclude_wings"]:
        wings.pop(excluded, None)
    evidence = {item["id"]: item for items in wings.values() for item in items}
    now = time.time()
    with closing(_connection(path)) as connection, connection:
        reviewed = dict(
            connection.execute("SELECT evidence_id,reviewed FROM dream_reviews").fetchall()
        )
        turns = dict(connection.execute("SELECT wing,served FROM dream_turns").fetchall())
        existing = {r["wing"]: dict(r) for r in connection.execute("SELECT * FROM dream_work")}
        for wing, job in list(existing.items()):
            ids = json.loads(job["evidence_ids"])
            if wing not in wings or any(key not in evidence for key in ids):
                connection.execute("DELETE FROM dream_work WHERE job_id=?", (job["job_id"],))
                del existing[wing]
        due_wings = []
        for wing, items in wings.items():
            due = [
                i
                for i in items
                if i["id"] not in reviewed or reviewed[i["id"]] + settings["review_seconds"] <= now
            ]
            if due:
                due.sort(key=lambda i: (reviewed.get(i["id"], 0), i["id"]))
                due_wings.append((turns.get(wing, 0), min(i["id"] for i in due), wing, due[:6]))
        for priority, _, wing, items in sorted(due_wings):
            if wing in existing or len(existing) >= settings["max_pending"]:
                continue
            ids = [i["id"] for i in items]
            reason = (
                "new_evidence" if any(key not in reviewed for key in ids) else "periodic_review"
            )
            job_id = str(uuid4())
            connection.execute(
                "INSERT INTO dream_work VALUES(?,?,?,?,?,?)",
                (job_id, wing, reason, json.dumps(ids), now, priority),
            )
            existing[wing] = {"job_id": job_id}
        deferred = sum(wing not in existing for _, _, wing, _ in due_wings)
    _state(path, deferred_wings=deferred)
    return evidence


def _empty(path: Path, controller_id: str | None, next_at: float) -> dict[str, Any]:
    now = time.time()
    receipt = _receipt(controller_id, None, now)
    receipt["next_run_at"] = _stamp(next_at)
    with closing(_connection(path)) as connection, connection:
        connection.execute(
            "INSERT INTO dream_attempts(id,created,receipt,done) VALUES(?,?,?,1)",
            (receipt["receipt_id"], now, json.dumps(receipt)),
        )
    return receipt


def _close_worker(process: subprocess.Popen[str]) -> None:
    try:
        process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate(timeout=5)
    finally:
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                stream.close()


def step(
    path: Path,
    provider_factory: Callable[[], EmbeddingProvider],
    controller_id: str | None,
    timeout: float | None = None,
) -> dict[str, Any] | None:
    """Admit and finish at most one durable due job without holding a writer lock."""
    settings, state = _read(path)
    if controller_id is not None and state.get("stop_requested"):
        return None
    if _busy(lock_path(path, "inference")):
        _state(path, state="running", next_run_at=_stamp(time.time() + settings["poll_seconds"]))
        return None
    with _file_lock(lock_path(path, "gate"), create=True) as acquired:
        if not acquired or _busy(lock_path(path, "inference")):
            return None
        _recover(path, settings)
        evidence = _refresh(path, settings, provider_factory)
        now = time.time()
        if foreground_active(path):
            _state(path, state="foreground", next_run_at=_stamp(now + settings["poll_seconds"]))
            return None
        count, reset = _budget(path, settings)
        if count >= settings["max_calls"]:
            _state(path, state="budget_wait", next_run_at=_stamp(reset))
            return None
        _, state = _read(path)
        if state.get("cooldown", 0) > now:
            _state(path, state="model_wait", next_run_at=_stamp(state["cooldown"]))
            return None
        with closing(_connection(path, read_only=True)) as connection:
            row = connection.execute(
                "SELECT * FROM dream_work WHERE next_at<=? ORDER BY priority,next_at,wing LIMIT 1",
                (now,),
            ).fetchone()
        if row is None:
            _state(path, state="idle", next_run_at=_stamp(now + settings["poll_seconds"]))
            return _empty(path, controller_id, now + settings["poll_seconds"])
        job = dict(row)
        receipt = _receipt(controller_id, job, now)
        attempt = receipt["attempt_id"]
        owner_key = "attempt-" + attempt
        lease = _file_lock(lock_path(path, owner_key), create=True)
        if not lease.__enter__():
            lease.__exit__(None, None, None)
            raise DreamError("Cannot own the new Dream attempt")
        process = None
        try:
            with closing(_connection(path)) as connection, connection:
                connection.execute(
                    "INSERT INTO dream_attempts(id,job_id,owner_key,created,receipt,done) "
                    "VALUES(?,?,?,?,?,0)",
                    (attempt, job["job_id"], owner_key, now, json.dumps(receipt)),
                )
            process, worker_pid = _spawn_worker(path)
            with closing(_connection(path)) as connection, connection:
                connection.execute(
                    "UPDATE dream_attempts SET worker_pid=? WHERE id=?", (worker_pid, attempt)
                )
            _state(
                path,
                state="running",
                next_run_at=_stamp(now + (timeout or settings["inference_seconds"])),
            )
        except (OSError, DreamError, sqlite3.Error) as launch_error:
            try:
                if process is not None:
                    _close_worker(process)
            except (OSError, subprocess.TimeoutExpired) as cleanup_error:
                launch_error.add_note(f"Dream worker cleanup failed: {cleanup_error}")
            finally:
                lease.__exit__(None, None, None)
            raise
    try:
        config = _config(path)
        if config is None:
            raise DreamError("Dream configuration disappeared")
        request = {
            "attempt_id": attempt,
            "endpoint": config["endpoint"],
            "model": config["model"],
            "wing": job["wing"],
            "evidence": [evidence[key] for key in receipt["evidence_ids"]],
            "timeout": min(timeout, settings["inference_seconds"])
            if timeout
            else settings["inference_seconds"],
        }
        error = None
        uncertain = False
        try:
            proposal = _communicate(process, request)
            with _gate(path):
                _check_cancelled(path, controller_id)
                saved = _save(
                    path,
                    status="candidate" if proposal else "no_work",
                    wing=job["wing"],
                    evidence_ids=receipt["evidence_ids"],
                    proposal=proposal,
                )
            receipt.update(status=saved["status"], candidate_id=saved["candidate_id"])
        except _CancelledError as exc:
            error = str(exc)
            uncertain = True
            receipt.update(status="interrupted")
        except (OSError, DreamError, ValueError, KeyError, TypeError) as exc:
            error = str(exc)
            uncertain = isinstance(exc, TimeoutError)
            receipt.update(status="model_unavailable")
        now = time.time()
        due = now + (settings["retry_seconds"] if error else settings["review_seconds"])
        receipt.update(
            finished_at=_stamp(now), next_run_at=_stamp(due), error=error, uncertain=uncertain
        )
        with _gate(path), closing(_connection(path)) as connection, connection:
            connection.execute(
                "UPDATE dream_attempts SET receipt=?,done=1 WHERE id=?",
                (json.dumps(receipt), attempt),
            )
            connection.execute(
                "INSERT INTO dream_turns VALUES(?,?) ON CONFLICT(wing) "
                "DO UPDATE SET served=excluded.served",
                (job["wing"], now),
            )
            if error:
                connection.execute(
                    "UPDATE dream_work SET next_at=?,reason='retry',priority=? WHERE job_id=?",
                    (due, now, job["job_id"]),
                )
            else:
                connection.executemany(
                    "INSERT INTO dream_reviews VALUES(?,?) ON CONFLICT(evidence_id) "
                    "DO UPDATE SET reviewed=excluded.reviewed",
                    [(key, now) for key in receipt["evidence_ids"]],
                )
                connection.execute("DELETE FROM dream_work WHERE job_id=?", (job["job_id"],))
        _state(
            path,
            state="model_wait" if error else "idle",
            cooldown=due if error else 0,
            next_run_at=_stamp(due if error else now + settings["poll_seconds"]),
        )
        return receipt
    finally:
        active_error = sys.exception()
        try:
            _close_worker(process)
        except (OSError, subprocess.TimeoutExpired) as cleanup_error:
            if active_error is None:
                raise
            active_error.add_note(f"Dream worker cleanup failed: {cleanup_error}")
        finally:
            lease.__exit__(None, None, None)


def run(path: Path, provider_factory: Callable[[], EmbeddingProvider]) -> dict[str, Any]:
    """Run the product controller until durable cancellation is requested."""
    _initialize(path)
    with _file_lock(lock_path(path, "controller"), create=True) as acquired:
        if not acquired:
            current = status(path)
            return {
                "schema": "cairntir.dream-controller.v1",
                "status": "already_running",
                "controller_id": current["controller_id"],
                "pid": current["pid"],
            }
        owner = str(UUID(os.environ.pop("CAIRNTIR_DREAM_LAUNCH_ID", str(uuid4()))))
        _state(
            path,
            controller_id=owner,
            pid=os.getpid(),
            process_identity=_process_identity(os.getpid()),
            stop_requested=False,
            state="idle",
            next_run_at=_stamp(),
        )
        try:
            while not _read(path)[1].get("stop_requested"):
                step(path, provider_factory, owner)
                settings, _ = _read(path)
                deadline = time.monotonic() + settings["poll_seconds"]
                while time.monotonic() < deadline and not _read(path)[1].get("stop_requested"):
                    time.sleep(min(0.1, max(0, deadline - time.monotonic())))
        finally:
            _state(path, pid=None, controller_id=None, state="stopped", next_run_at=None)
    return {
        "schema": "cairntir.dream-controller.v1",
        "status": "stopped",
        "controller_id": None,
        "pid": None,
    }


def start(path: Path) -> dict[str, Any]:
    """Launch a detached controller and acknowledge its observed ownership."""
    _initialize(path)
    current = status(path)
    if current["running"]:
        return {
            "schema": "cairntir.dream-controller.v1",
            "status": "already_running",
            "controller_id": current["controller_id"],
            "pid": current["pid"],
        }
    owner = str(uuid4())
    environment = dict(os.environ, CAIRNTIR_HOME=str(path.parent), CAIRNTIR_DREAM_LAUNCH_ID=owner)
    log_path = path.with_name(path.name + ".dream-controller.log")
    with log_path.open("ab") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "cairntir", "dream", "run"],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            env=environment,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            start_new_session=os.name != "nt",
        )
    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        current = status(path)
        if current["running"]:
            return {
                "schema": "cairntir.dream-controller.v1",
                "status": "started" if current["controller_id"] == owner else "already_running",
                "controller_id": current["controller_id"],
                "pid": current["pid"],
            }
        if process.poll() is not None:
            raise DreamError(f"Dream controller exited during startup; see {log_path}")
        time.sleep(0.05)
    process.kill()
    process.wait(timeout=5)
    raise DreamError(f"Dream controller did not confirm ownership; see {log_path}")


def stop(path: Path) -> dict[str, Any]:
    """Cancel controller work and wait for its owned process to drain."""
    if configured(path):
        settings, _ = _read(path)
        with _gate(path):
            _state(path, stop_requested=True)
        deadline = time.monotonic() + settings["inference_seconds"] + 5
        while _busy(lock_path(path, "controller")) or _busy(lock_path(path, "inference")):
            if time.monotonic() >= deadline:
                raise DreamError("Dream cancellation is not yet confirmed")
            time.sleep(0.05)
    return {
        "schema": "cairntir.dream-controller.v1",
        "status": "stopped",
        "controller_id": None,
        "pid": None,
    }


def manual_tick(
    path: Path, provider_factory: Callable[[], EmbeddingProvider], timeout: float
) -> dict[str, Any]:
    """Retain the one-shot receipt while obeying configured scheduling budgets."""
    receipt = step(path, provider_factory, None, timeout)
    return {
        "schema": "cairntir.dream-tick.v1",
        "receipt_id": receipt["receipt_id"] if receipt else str(uuid4()),
        "status": receipt["status"] if receipt else "no_work",
        "wing": receipt["wing"] if receipt else None,
        "evidence_ids": receipt["evidence_ids"] if receipt else [],
        "candidate_id": receipt["candidate_id"] if receipt else None,
    }
