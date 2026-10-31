"""One finite, exclusively owned local inference process using only the standard library."""

from __future__ import annotations

import errno
import http.client
import ipaddress
import json
import math
import os
import sqlite3
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID


def lock_path(path: Path, kind: str) -> Path:
    """Use the same store-scoped coordination files as the controller."""
    return path.with_name(path.name + f".dream-{kind}.lock")


@contextmanager
def _lock(path: Path, *, create: bool = True) -> Iterator[bool]:
    with path.open("a+b" if create else "rb") as handle:
        try:
            if sys.platform == "win32":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno not in {errno.EACCES, errno.EAGAIN}:
                raise
            yield False
            return
        try:
            yield True
        finally:
            if sys.platform == "win32":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def validate_endpoint(endpoint: str) -> tuple[str, int]:
    """Require an explicit local HTTP endpoint without forwarding."""
    try:
        parsed = urlsplit(endpoint)
        host, port = parsed.hostname, parsed.port
        address = ipaddress.ip_address(host or "")
    except ValueError as exc:
        raise ValueError("Dream endpoint must be an explicit loopback HTTP address") from exc
    if (
        parsed.scheme != "http"
        or not address.is_loopback
        or host not in {"127.0.0.1", "::1"}
        or port is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Dream endpoint must be an explicit loopback HTTP address")
    return host, port


def _request(raw: bytes) -> dict[str, Any]:
    if not raw or len(raw) > 65536 or not raw.endswith(b"\n"):
        raise ValueError("missing, unterminated or oversized inference request")
    request = json.loads(raw)
    if not isinstance(request, dict):
        raise TypeError("inference request must be an object")
    for key in ("endpoint", "model", "wing"):
        if not isinstance(request.get(key), str) or not request[key].strip():
            raise ValueError(f"invalid inference {key}")
    validate_endpoint(request["endpoint"])
    timeout = request.get("timeout")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or not 0 < timeout <= 60
    ):
        raise ValueError("invalid inference timeout")
    evidence = request.get("evidence")
    if not isinstance(evidence, list) or not 1 <= len(evidence) <= 6:
        raise ValueError("invalid inference evidence")
    ids = set()
    for item in evidence:
        if (
            not isinstance(item, dict)
            or type(item.get("id")) is not int
            or item["id"] <= 0
            or item["id"] in ids
            or not isinstance(item.get("content"), str)
            or not item["content"].strip()
            or len(item["content"]) > 1200
        ):
            raise ValueError("invalid inference evidence entry")
        ids.add(item["id"])
    keys = [key for key in ("attempt_id", "claim_token") if key in request]
    if len(keys) != 1 or not isinstance(request[keys[0]], str):
        raise ValueError("inference requires exactly one admission")
    token = request[keys[0]]
    if str(UUID(token)) != token:
        raise ValueError("invalid inference admission")
    return request


def _admit(path: Path, request: dict[str, Any]) -> bool:
    deadline = time.monotonic() + 2
    while True:
        with _lock(lock_path(path, "gate")) as acquired:
            if acquired:
                return _admit_locked(path, request)
        if time.monotonic() >= deadline:
            raise ValueError("Dream coordination is busy")
        time.sleep(0.01)


def _admit_locked(path: Path, request: dict[str, Any]) -> bool:
    directory = path.with_name(path.name + ".dream-foreground")
    for marker in directory.glob("*.lock"):
        with _lock(marker, create=False) as available:
            if not available:
                return False
    with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=rw", uri=True)) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        config = conn.execute(
            "SELECT endpoint,model FROM dream_config WHERE singleton=1"
        ).fetchone()
        if config != (request["endpoint"], request["model"]):
            return False
        ids = {item["id"] for item in request["evidence"]}
        for item in request["evidence"]:
            row = conn.execute(
                "SELECT wing,content FROM drawers WHERE id=?", (item["id"],)
            ).fetchone()
            if row is None or row[0] != request["wing"] or row[1][:1200] != item["content"]:
                return False
        if "claim_token" in request:
            token = request["claim_token"]
            rows = conn.execute(
                "SELECT evidence_id,wing,expires_at FROM dream_claims WHERE claim_token=?", (token,)
            ).fetchall()
            now = datetime.now(UTC)
            if {row[0] for row in rows} != ids or any(
                row[1] != request["wing"] or datetime.fromisoformat(row[2]) <= now for row in rows
            ):
                return False
            # Keep the claim held for its owner to save, but make the admission single-use.
            conn.execute(
                "UPDATE dream_claims SET claim_token=? WHERE claim_token=?",
                (token + ":used", token),
            )
            return True
        attempt = request["attempt_id"]
        row = conn.execute(
            "SELECT receipt FROM dream_attempts WHERE id=? AND done=0 AND launched IS NULL",
            (attempt,),
        ).fetchone()
        if row is None:
            return False
        receipt = json.loads(row[0])
        if receipt["wing"] != request["wing"] or set(receipt["evidence_ids"]) != ids:
            return False
        control = conn.execute(
            "SELECT config,state FROM dream_control WHERE singleton=1"
        ).fetchone()
        if control is None:
            return False
        settings, state = (json.loads(value) for value in control)
        if request["wing"] in settings["exclude_wings"] or (
            receipt["controller_id"] == state.get("controller_id") and state.get("stop_requested")
        ):
            return False
        count = conn.execute(
            "SELECT COUNT(*) FROM dream_attempts WHERE launched>?",
            (time.time() - settings["window_seconds"],),
        ).fetchone()[0]
        if count >= settings["max_calls"]:
            return False
        conn.execute(
            "UPDATE dream_attempts SET launched=?,worker_pid=? WHERE id=?",
            (time.time(), os.getpid(), attempt),
        )
        return True


def infer_http(
    endpoint: str, model: str, wing: str, evidence: list[dict[str, Any]], timeout: float
) -> tuple[str, str] | None:
    """Read one bounded local response without following redirects."""
    host, port = validate_endpoint(endpoint)
    prompt = json.dumps(
        {
            "wing": wing,
            "evidence": evidence,
            "instruction": "Suggest one consequential review item, or no proposals.",
        },
        ensure_ascii=False,
    )
    body = json.dumps({"model": model, "stream": False, "prompt": prompt}).encode()
    with closing(http.client.HTTPConnection(host, port, timeout=timeout)) as connection:
        connection.request(
            "POST", "/api/generate", body=body, headers={"Content-Type": "application/json"}
        )
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError(f"local model returned HTTP {response.status}")
        raw = response.read(65537)
    if len(raw) > 65536:
        raise ValueError("local model response exceeds 64 KiB")
    payload = json.loads(raw)
    result = json.loads(payload["response"])
    proposals = result["proposals"]
    if not isinstance(proposals, list):
        raise TypeError("local model proposals must be a list")
    for item in proposals:
        if isinstance(item, dict):
            title, proposal = item.get("title"), item.get("proposal")
            if (
                isinstance(title, str)
                and title.strip()
                and isinstance(proposal, str)
                and proposal.strip()
            ):
                return title.strip(), proposal.strip()
    return None


def _watch_cancellation(path: Path, attempt: str, finished: threading.Event) -> None:
    try:
        while not finished.wait(0.1):
            with closing(
                sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=0.5)
            ) as conn:
                row = conn.execute(
                    "SELECT a.receipt,c.state FROM dream_attempts a "
                    "JOIN dream_control c ON c.singleton=1 "
                    "WHERE a.id=? AND a.worker_pid=? AND a.done=0",
                    (attempt, os.getpid()),
                ).fetchone()
            if row is not None:
                receipt, state = (json.loads(value) for value in row)
                if receipt["controller_id"] == state.get("controller_id") and state.get(
                    "stop_requested"
                ):
                    os._exit(125)
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError) as exc:
        print(f"Dream cancellation observation failed: {exc}", file=sys.stderr, flush=True)
        os._exit(1)


def main() -> None:
    """Retain ownership and a hard deadline independently of the parent process."""
    database = Path(sys.argv[1])
    startup = threading.Timer(10, lambda: os._exit(124))
    startup.daemon = True
    startup.start()
    try:
        with _lock(lock_path(database, "inference")) as acquired:
            print(json.dumps({"ready": acquired, "pid": os.getpid()}), flush=True)
            if not acquired:
                return
            request = _request(sys.stdin.buffer.readline(65537))
            timer = threading.Timer(request["timeout"], lambda: os._exit(124))
            timer.daemon = True
            timer.start()
            startup.cancel()
            finished = threading.Event()
            watcher = None
            try:
                if not _admit(database, request):
                    result: dict[str, Any] = {"status": "deferred"}
                else:
                    if "attempt_id" in request:
                        watcher = threading.Thread(
                            target=_watch_cancellation,
                            args=(database, request["attempt_id"], finished),
                            daemon=True,
                        )
                        watcher.start()
                    proposal = infer_http(
                        request["endpoint"],
                        request["model"],
                        request["wing"],
                        request["evidence"],
                        request["timeout"],
                    )
                    result = {"status": "ok", "proposal": proposal}
                print(json.dumps(result, ensure_ascii=False), flush=True)
            finally:
                finished.set()
                if watcher is not None:
                    watcher.join(timeout=1)
                timer.cancel()
    finally:
        startup.cancel()


if __name__ == "__main__":
    main()
