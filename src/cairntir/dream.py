"""Opt-in, local-only Dream pilot with separately held review candidates."""

from __future__ import annotations

import http.client
import json
import sqlite3
import subprocess
import sys
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from uuid import uuid4

from cairntir.errors import EmbeddingSpaceError, MemoryStoreError
from cairntir.memory.embeddings import EmbeddingProvider
from cairntir.memory.store import (
    SCHEMA_VERSION,
    DrawerStore,
    _context_record,
    _copy_locked_database,
    _row_to_drawer,
    backup_database,
    inspect_embedding_space,
)
from cairntir.memory.taxonomy import Drawer
from cairntir.provenance import WriteProvenance


class DreamError(ValueError):
    """A Dream configuration, storage, or candidate error."""


_SCHEMA = """
CREATE TABLE IF NOT EXISTS dream_config (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    scope TEXT NOT NULL,
    model TEXT NOT NULL,
    endpoint TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dream_receipts (
    receipt_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    wing TEXT,
    evidence_ids TEXT NOT NULL,
    candidate_id TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dream_candidates (
    candidate_id TEXT PRIMARY KEY,
    wing TEXT NOT NULL,
    evidence_ids TEXT NOT NULL,
    title TEXT NOT NULL,
    proposal TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status = 'pending'),
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dream_processed (
    evidence_id INTEGER PRIMARY KEY,
    wing TEXT NOT NULL,
    receipt_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dream_claims (
    evidence_id INTEGER PRIMARY KEY,
    wing TEXT NOT NULL,
    claim_token TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _connection(path: Path, *, read_only: bool = False) -> sqlite3.Connection:
    connection = sqlite3.connect(
        f"{path.as_uri()}?mode=ro" if read_only else path,
        uri=read_only,
        timeout=5,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def _has_schema(connection: sqlite3.Connection) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'dream_config'"
        ).fetchone()
        is not None
    )


def _config(path: Path) -> dict[str, str] | None:
    if not path.is_file():
        return None
    with closing(_connection(path, read_only=True)) as connection:
        if not _has_schema(connection):
            return None
        row = connection.execute(
            "SELECT scope, model, endpoint FROM dream_config WHERE singleton = 1"
        ).fetchone()
    return dict(row) if row is not None else None


def _validate_endpoint(endpoint: str) -> tuple[str, int]:
    from cairntir.dream_worker import validate_endpoint

    try:
        return validate_endpoint(endpoint)
    except ValueError as exc:
        raise DreamError(str(exc)) from exc


def enable(
    path: Path,
    *,
    scope: str,
    model: str,
    endpoint: str,
    provider_factory: Callable[[], EmbeddingProvider],
) -> dict[str, str]:
    """Persist a local-only opt-in after preserving an existing store."""
    if scope != "all-local":
        raise DreamError("Dream pilot supports only --scope all-local")
    if not model.strip():
        raise DreamError("Dream model must be nonempty")
    _validate_endpoint(endpoint)
    existing = path.is_file()
    if existing:
        with closing(_connection(path, read_only=True)) as connection:
            missing_schema = not _has_schema(connection)
        if missing_schema:
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
            backup_database(path, path.with_name(f"{path.stem}.pre-dream-{stamp}{path.suffix}"))
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with DrawerStore(path, provider_factory()):
            pass
    with closing(_connection(path)) as connection, connection:
        connection.executescript(_SCHEMA)
        connection.execute(
            "INSERT INTO dream_config(singleton, scope, model, endpoint) VALUES (1, ?, ?, ?) "
            "ON CONFLICT(singleton) DO UPDATE SET scope=excluded.scope, "
            "model=excluded.model, endpoint=excluded.endpoint",
            (scope, model.strip(), endpoint),
        )
    return {"schema": "cairntir.dream-config.v1", "status": "enabled", "scope": scope}


def _select_eligible(
    entries: list[Drawer], get_provenance: Callable[[int], WriteProvenance | None]
) -> dict[str, list[dict[str, Any]]]:
    from cairntir.context import _exclusions

    wings: dict[str, list[dict[str, Any]]] = {}
    now = datetime.now(UTC)
    drawers = {drawer.id: drawer for drawer in entries}
    superseded = {
        drawer.supersedes_id
        for drawer in drawers.values()
        if drawer.supersedes_id in drawers and drawers[drawer.supersedes_id].wing == drawer.wing
    }
    for drawer in drawers.values():
        if drawer.id is None or drawer.id in superseded:
            continue
        provenance = get_provenance(drawer.id)
        if provenance is None or _exclusions((drawer, provenance), now):
            continue
        wings.setdefault(drawer.wing, []).append(
            {"id": drawer.id, "room": drawer.room, "content": drawer.content[:1200]}
        )
    return wings


def _eligible(
    path: Path, provider_factory: Callable[[], EmbeddingProvider]
) -> dict[str, list[dict[str, Any]]]:
    with DrawerStore(path, provider_factory(), read_only=True) as store:
        return _select_eligible(store.list_by(limit=None), store.get_provenance)


def _eligible_snapshot(
    path: Path, provider_factory: Callable[[], EmbeddingProvider]
) -> dict[str, list[dict[str, Any]]]:
    with closing(_connection(path, read_only=True)) as connection:
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if version != SCHEMA_VERSION:
            raise MemoryStoreError(
                f"read-only task context requires schema v{SCHEMA_VERSION}, found v{version}; "
                "open the store normally to migrate or upgrade Cairntir"
            )
        index = inspect_embedding_space(path, provider_factory())
        if not index.verified:
            raise EmbeddingSpaceError(
                f"semantic index is {index.state}: {index.detail}. "
                "Run cairntir doctor, then cairntir reindex."
            )
        rows = {
            int(row["id"]): row
            for row in connection.execute(
                "SELECT * FROM drawers WHERE valid_until > ? ORDER BY id DESC", (_now(),)
            )
        }
        return _select_eligible(
            [_row_to_drawer(row) for row in rows.values()],
            lambda drawer_id: _context_record(rows[drawer_id])[1],
        )


def _evidence(
    path: Path,
    provider_factory: Callable[[], EmbeddingProvider],
    *,
    eligible: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    with closing(_connection(path, read_only=True)) as connection:
        unavailable = {
            int(row[0]) for row in connection.execute("SELECT evidence_id FROM dream_processed")
        }
        unavailable.update(
            int(row[0])
            for row in connection.execute(
                "SELECT evidence_id FROM dream_claims WHERE expires_at > ?", (_now(),)
            )
        )
    return {
        wing: available[:6]
        for wing, items in (
            eligible if eligible is not None else _eligible(path, provider_factory)
        ).items()
        if (available := [item for item in items if item["id"] not in unavailable])
    }


def status(path: Path, *, provider_factory: Callable[[], EmbeddingProvider]) -> dict[str, Any]:
    """Report current evidence from a private snapshot and observe real owner locks."""
    if not path.is_file():
        return _status(path, path, provider_factory)
    with TemporaryDirectory(prefix="cairntir-dream-status-") as directory:
        copied = Path(directory) / path.name
        try:
            if sys.platform == "win32":
                _copy_locked_database(path.resolve(), copied)
            else:
                subprocess.run(  # noqa: S603 - fixed interpreter/helper; paths are arguments
                    [
                        sys.executable,
                        "-c",
                        "from pathlib import Path; import sys; "
                        "from cairntir.memory.store import _copy_locked_database; "
                        "_copy_locked_database(Path(sys.argv[1]), Path(sys.argv[2]))",
                        str(path.resolve()),
                        str(copied),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=12,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
        except (OSError, sqlite3.Error, MemoryStoreError, subprocess.SubprocessError) as exc:
            detail = (
                exc.stderr.strip()[-1000:]
                if isinstance(exc, subprocess.CalledProcessError)
                else str(exc)
            )
            raise MemoryStoreError(f"failed to snapshot Dream status at {path}: {detail}") from exc
        return _status(copied, path, provider_factory)


def _status(
    data_path: Path, source_path: Path, provider_factory: Callable[[], EmbeddingProvider]
) -> dict[str, Any]:
    path = data_path
    from cairntir.dream_controller import status as controller_status

    result: dict[str, Any] = {
        "controller": controller_status(source_path, _data_path=data_path),
        "schema": "cairntir.dream-status.v1",
        "enabled": False,
        "last_tick": None,
        "pending_candidates": 0,
        "queued_wings": 0,
    }
    if _config(path) is None:
        return result
    with closing(_connection(path, read_only=True)) as connection:
        row = connection.execute(
            "SELECT receipt_id, status, wing, evidence_ids, candidate_id "
            "FROM dream_receipts ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        result["last_tick"] = _receipt(row) if row is not None else None
        result["pending_candidates"] = int(
            connection.execute(
                "SELECT COUNT(*) FROM dream_candidates WHERE status='pending'"
            ).fetchone()[0]
        )
    result["enabled"] = True
    result["queued_wings"] = len(
        _evidence(path, provider_factory, eligible=_eligible_snapshot(path, provider_factory))
    )
    return result


def candidate(path: Path, candidate_id: str) -> dict[str, Any]:
    """Fetch one advisory record without exposing it through ordinary memory."""
    if _config(path) is None:
        raise DreamError("Dream is disabled")
    with closing(_connection(path, read_only=True)) as connection:
        row = connection.execute(
            "SELECT candidate_id, status, wing, evidence_ids, title, proposal "
            "FROM dream_candidates WHERE candidate_id = ?",
            (candidate_id,),
        ).fetchone()
    if row is None:
        raise DreamError(f"Dream candidate {candidate_id!r} does not exist")
    return {
        "schema": "cairntir.dream-candidate.v1",
        "candidate_id": str(row["candidate_id"]),
        "status": str(row["status"]),
        "wing": str(row["wing"]),
        "evidence_ids": json.loads(str(row["evidence_ids"])),
        "title": str(row["title"]),
        "proposal": str(row["proposal"]),
    }


def _receipt(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "schema": "cairntir.dream-tick.v1",
        "receipt_id": str(row["receipt_id"]),
        "status": str(row["status"]),
        "wing": str(row["wing"]) if row["wing"] is not None else None,
        "evidence_ids": json.loads(str(row["evidence_ids"])),
        "candidate_id": str(row["candidate_id"]) if row["candidate_id"] else None,
    }


def _save(
    path: Path,
    *,
    status: str,
    wing: str | None,
    evidence_ids: list[int],
    claim_token: str | None = None,
    proposal: tuple[str, str] | None = None,
) -> dict[str, Any]:
    receipt_id = str(uuid4())
    candidate_id = str(uuid4()) if proposal else None
    with closing(_connection(path)) as connection, connection:
        if claim_token is not None:
            rows = connection.execute(
                "SELECT evidence_id FROM dream_claims WHERE claim_token IN (?, ?)",
                (claim_token, claim_token + ":used"),
            ).fetchall()
            if {int(row[0]) for row in rows} != set(evidence_ids):
                status, candidate_id, proposal = "no_work", None, None
            else:
                connection.execute(
                    "DELETE FROM dream_claims WHERE claim_token IN (?, ?)",
                    (claim_token, claim_token + ":used"),
                )
                if status != "model_unavailable":
                    connection.executemany(
                        "INSERT OR IGNORE INTO dream_processed(evidence_id, wing, receipt_id) "
                        "VALUES (?, ?, ?)",
                        [(item, wing, receipt_id) for item in evidence_ids],
                    )
        if proposal is not None and candidate_id is not None and wing is not None:
            prior = connection.execute(
                "SELECT candidate_id FROM dream_candidates WHERE wing=? AND evidence_ids=? "
                "AND title=? AND proposal=? AND status='pending' ORDER BY rowid LIMIT 1",
                (wing, json.dumps(sorted(evidence_ids)), *proposal),
            ).fetchone()
            if prior is not None:
                candidate_id = str(prior[0])
            connection.execute(
                "INSERT OR IGNORE INTO dream_candidates(candidate_id, wing, evidence_ids, title, "
                "proposal, status, created_at) VALUES (?, ?, ?, ?, ?, 'pending', ?)",
                (candidate_id, wing, json.dumps(sorted(evidence_ids)), *proposal, _now()),
            )
        connection.execute(
            "INSERT INTO dream_receipts(receipt_id, status, wing, evidence_ids, "
            "candidate_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (receipt_id, status, wing, json.dumps(evidence_ids), candidate_id, _now()),
        )
    return {
        "schema": "cairntir.dream-tick.v1",
        "receipt_id": receipt_id,
        "status": status,
        "wing": wing,
        "evidence_ids": evidence_ids,
        "candidate_id": candidate_id,
    }


def _claim(path: Path, wing: str, ids: list[int], timeout_seconds: int) -> str | None:
    token = str(uuid4())
    expiry = (datetime.now(UTC) + timedelta(seconds=timeout_seconds + 10)).isoformat()
    with closing(_connection(path)) as connection, connection:
        connection.execute("DELETE FROM dream_claims WHERE expires_at <= ?", (_now(),))
        for source_id in ids:
            if (
                connection.execute(
                    "SELECT 1 FROM dream_processed WHERE evidence_id = ?", (source_id,)
                ).fetchone()
                is not None
            ):
                return None
            if (
                connection.execute(
                    "SELECT 1 FROM dream_claims WHERE evidence_id = ?", (source_id,)
                ).fetchone()
                is not None
            ):
                return None
        connection.executemany(
            "INSERT INTO dream_claims(evidence_id, wing, claim_token, expires_at) "
            "VALUES (?, ?, ?, ?)",
            [(item, wing, token, expiry) for item in ids],
        )
    return token


def tick(
    path: Path,
    *,
    provider_factory: Callable[[], EmbeddingProvider],
    max_wings: int = 1,
    timeout_seconds: int = 5,
) -> dict[str, Any]:
    """Process at most one wing with one local model request."""
    if max_wings < 1 or not 1 <= timeout_seconds <= 60:
        raise DreamError("Dream limits require max-wings >= 1 and timeout-seconds in 1..60")
    config = _config(path)
    if config is None:
        return {
            "schema": "cairntir.dream-tick.v1",
            "receipt_id": str(uuid4()),
            "status": "disabled",
            "wing": None,
            "evidence_ids": [],
            "candidate_id": None,
        }
    from cairntir.dream_controller import configured, infer, manual_tick

    if configured(path):
        return manual_tick(path, provider_factory, timeout_seconds)
    queue = _evidence(path, provider_factory)
    if not queue:
        return _save(path, status="no_work", wing=None, evidence_ids=[])
    wing = min(queue, key=lambda key: min(int(item["id"]) for item in queue[key]))
    evidence = queue[wing]
    evidence_ids = [int(item["id"]) for item in evidence]
    claim_token = _claim(path, wing, evidence_ids, timeout_seconds)
    if claim_token is None:
        return _save(path, status="no_work", wing=None, evidence_ids=[])
    try:
        proposal = infer(
            path, config["endpoint"], config["model"], wing, evidence, timeout_seconds, claim_token
        )
    except (OSError, http.client.HTTPException, DreamError, ValueError, KeyError, TypeError):
        return _save(
            path,
            status="model_unavailable",
            wing=wing,
            evidence_ids=evidence_ids,
            claim_token=claim_token,
        )
    return _save(
        path,
        status="candidate" if proposal else "no_work",
        wing=wing,
        evidence_ids=evidence_ids,
        claim_token=claim_token,
        proposal=proposal,
    )
