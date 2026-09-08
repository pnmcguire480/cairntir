"""Opt-in, per-database SQLite backups with verified publication and retention."""

from __future__ import annotations

import errno
import hashlib
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
import time
import warnings
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import sqlite_vec

from cairntir.errors import BackupError

_FORMAT = "cairntir.backups.v1"
_RECEIPT = "cairntir.backup-receipt.v1"
_PENDING = "cairntir.backup-pending.v1"
_PARTIAL = re.compile(r"\.partial-[0-9a-f]{32}\Z")
_ARCHIVE = re.compile(r"[0-9]{8}T[0-9]{12}Z-[0-9a-f]{32}\Z")


class BackupWarning(UserWarning):
    """An automatic backup or managed cleanup failed without blocking memory use."""


def utc_now() -> datetime:
    """Return the UTC clock used for backup cadence and retention."""
    return datetime.now(UTC)


def _source(database: Path) -> Path:
    try:
        return database.resolve()
    except (OSError, ValueError) as exc:
        raise BackupError(f"cannot resolve backup source: {exc}") from exc


def _paths(database: Path) -> tuple[Path, Path]:
    return (
        database.with_name(database.name + ".backups.json"),
        database.with_name(database.name + ".backups.lock"),
    )


def _instant(value: str) -> datetime:
    instant = datetime.fromisoformat(value)
    if instant.tzinfo is None:
        raise ValueError("backup timestamp must include its UTC offset")
    return instant.astimezone(UTC)


def _interval(value: object) -> timedelta:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BackupError("backup interval_hours must be a finite positive number")
    try:
        if not math.isfinite(value) or value <= 0:
            raise BackupError("backup interval_hours must be a finite positive number")
        return timedelta(hours=value)
    except OverflowError as exc:
        raise BackupError("backup interval_hours is outside the supported time range") from exc


def _load(database: Path) -> dict[str, Any]:
    path, _ = _paths(database)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {
            "format": _FORMAT,
            "database": str(database),
            "owner": None,
            "enabled": False,
            "destination": None,
            "interval_hours": 12,
            "last_success_at": None,
            "last_error": None,
            "snapshots": [],
        }
    except (OSError, UnicodeError) as exc:
        raise BackupError(f"cannot read backup configuration: {exc}") from exc
    try:
        state = json.loads(raw)
        if (
            state["format"] != _FORMAT
            or state["database"] != str(database)
            or not isinstance(state["owner"], str)
            or str(UUID(state["owner"])) != state["owner"]
            or type(state["enabled"]) is not bool
            or not isinstance(state["destination"], str)
            or not Path(state["destination"]).is_absolute()
            or not isinstance(state["snapshots"], list)
        ):
            raise BackupError("invalid backup configuration fields")
        interval = _interval(state["interval_hours"])
        if state["last_success_at"] is not None:
            _instant(state["last_success_at"]) + interval
        if state["last_error"] is not None and not isinstance(state["last_error"], str):
            raise BackupError("invalid backup error record")
        for item in state["snapshots"]:
            if (
                not isinstance(item["path"], str)
                or not Path(item["path"]).is_absolute()
                or type(item["size_bytes"]) is not int
                or item["size_bytes"] <= 0
                or not isinstance(item["sha256"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"])
            ):
                raise BackupError("invalid backup snapshot record")
            _instant(item["created_at"])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise BackupError("invalid backup configuration") from exc
    return dict(state)


def _save(database: Path, state: dict[str, Any]) -> None:
    path, _ = _paths(database)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(state, handle, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except (OSError, ValueError) as exc:
        raise BackupError(f"cannot save backup configuration: {exc}") from exc
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError as exc:
            warnings.warn(
                f"backup temporary configuration cleanup failed: {exc}", BackupWarning, stacklevel=2
            )


@contextmanager
def _lock(database: Path, *, create: bool) -> Iterator[bool]:
    deadline = time.monotonic() + 0.25
    while True:
        with _file_lock(_paths(database)[1], create=create) as acquired:
            if acquired or not create or time.monotonic() >= deadline:
                yield acquired
                return
        time.sleep(0.01)


@contextmanager
def _file_lock(path: Path, *, create: bool, exclusive_create: bool = False) -> Iterator[bool]:
    try:
        handle = path.open("x+b" if exclusive_create else "a+b" if create else "rb")
    except FileNotFoundError:
        if not create:
            yield False
            return
        raise BackupError("backup source directory is unavailable") from None
    except OSError as exc:
        raise BackupError(f"cannot open backup coordination lock: {exc}") from exc
    with handle:
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
                raise BackupError(f"cannot acquire backup coordination lock: {exc}") from exc
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


def _public(state: dict[str, Any], *, in_progress: bool = False) -> dict[str, Any]:
    due = (
        (_instant(state["last_success_at"]) + _interval(state["interval_hours"])).isoformat()
        if state["last_success_at"] is not None
        else None
    )
    return {
        "enabled": state["enabled"],
        "destination": state["destination"],
        "interval_hours": state["interval_hours"],
        "last_success_at": state["last_success_at"],
        "next_due_at": due,
        "last_error": state["last_error"],
        "in_progress": in_progress,
        "snapshots": state["snapshots"],
    }


def status(database: Path) -> dict[str, Any]:
    """Read backup configuration and observe an existing lock without creating files."""
    database = _source(database)
    state = _load(database)
    state["snapshots"] = [item for item in state["snapshots"] if Path(item["path"]).is_file()]
    _, lock_path = _paths(database)
    if not lock_path.exists():
        return _public(state)
    with _lock(database, create=False) as acquired:
        return _public(state, in_progress=not acquired)


def configure(database: Path, destination: Path, *, interval_hours: float = 12) -> dict[str, Any]:
    """Enable backups without requiring the destination to be available yet."""
    _interval(interval_hours)
    database, destination = _source(database), _source(destination)
    if database == destination:
        raise BackupError("backup destination must differ from the source database")
    try:
        database.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise BackupError(f"cannot create backup configuration directory: {exc}") from exc
    with _lock(database, create=True) as acquired:
        if not acquired:
            raise BackupError("backup is in progress; configuration was not changed")
        state = _load(database)
        if state["destination"] != str(destination):
            state.update(last_success_at=None, last_error=None, snapshots=[])
        state.update(
            enabled=True,
            destination=str(destination),
            interval_hours=interval_hours,
            owner=state["owner"] or str(uuid4()),
        )
        _save(database, state)
        return _public(state)


def disable(database: Path) -> dict[str, Any]:
    """Disable future automatic copies without deleting recovery points."""
    database = _source(database)
    state = _load(database)
    if state["owner"] is None:
        return _public(state)
    with _lock(database, create=True) as acquired:
        if not acquired:
            raise BackupError("backup is in progress; configuration was not changed")
        state = _load(database)
        state["enabled"] = False
        _save(database, state)
        return _public(state)


def _due(state: dict[str, Any], now: datetime) -> bool:
    return state["last_success_at"] is None or now >= _instant(
        state["last_success_at"]
    ) + _interval(state["interval_hours"])


def _namespace(state: dict[str, Any]) -> Path:
    return Path(state["destination"]) / ("cairntir-" + UUID(state["owner"]).hex)


def _hash(path: Path, deadline: float) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            _check_deadline(deadline)
            digest.update(chunk)
    return digest.hexdigest()


def _receipt(state: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    return {
        "format": _RECEIPT,
        "owner": state["owner"],
        "database": state["database"],
        "filename": "snapshot.db",
        **{key: item[key] for key in ("created_at", "sha256", "size_bytes")},
    }


def _check_deadline(deadline: float) -> None:
    if time.monotonic() >= deadline:
        raise BackupError("backup operation reached its time limit")


def _prepare_snapshot(source: Path, destination: Path, deadline: float) -> None:
    from cairntir.memory.store import _copy_locked_database

    _copy_locked_database(source, destination)
    with closing(sqlite3.connect(destination, timeout=0.25)) as connection:
        connection.enable_load_extension(True)
        sqlite_vec.load(connection)
        connection.enable_load_extension(False)
        connection.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
        connection.execute("PRAGMA journal_mode=DELETE")
        if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise BackupError("backup SQLite integrity check failed")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise BackupError("backup SQLite foreign-key check failed")


def _claim_path(directory: Path) -> Path:
    return directory.with_name(directory.name + ".lock")


def _clean_partial(directory: Path, state: dict[str, Any]) -> None:
    if directory.is_symlink() or not _PARTIAL.fullmatch(directory.name):
        return
    claim = _claim_path(directory)
    if claim.is_symlink():
        return
    try:
        # Only the creator makes this unique claim. Cleaners never recreate an unlinked lock.
        with _file_lock(claim, create=False) as acquired:
            if not acquired:
                return
            _remove_partial(directory, state)
        if not directory.exists():
            claim.unlink(missing_ok=True)
    except (BackupError, OSError) as exc:
        warnings.warn(f"backup staging cleanup deferred: {exc}", BackupWarning, stacklevel=2)


def _remove_partial(directory: Path, state: dict[str, Any]) -> None:
    if directory.is_symlink() or not _PARTIAL.fullmatch(directory.name):
        return
    allowed = {
        "pending.json",
        "receipt.json",
        "snapshot.db",
        "snapshot.db-wal",
        "snapshot.db-shm",
        "snapshot.db-journal",
    }
    try:
        paths = list(directory.iterdir())
        if any(
            path.is_symlink() or not path.is_file() or path.name not in allowed for path in paths
        ):
            return
        marker = directory / "pending.json"
        if not marker.is_file():
            marker = directory / "receipt.json"
        value = json.loads(marker.read_text(encoding="utf-8"))
        if (
            value.get("format") not in {_PENDING, _RECEIPT}
            or value.get("owner") != state["owner"]
            or value.get("database") != state["database"]
        ):
            return
        for path in sorted(paths, key=lambda item: item == marker):
            path.unlink()
        directory.rmdir()
    except (ValueError, AttributeError):
        return
    except OSError as exc:
        warnings.warn(f"backup staging cleanup deferred: {exc}", BackupWarning, stacklevel=2)


def _publish_snapshot(
    database: Path, state: dict[str, Any], now: datetime, deadline: float
) -> dict[str, Any]:
    namespace = _namespace(state)
    partial: Path | None = None
    claim: Path | None = None
    claimed = False
    try:
        if namespace.is_symlink():
            raise BackupError("backup namespace must not be a symbolic link")
        namespace.mkdir(parents=True, exist_ok=True)
        for orphan in namespace.glob(".partial-*"):
            _check_deadline(deadline)
            _clean_partial(orphan, state)
        partial = namespace / (".partial-" + uuid4().hex)
        claim = _claim_path(partial)
        # The sibling claim survives directory rename on Windows and coordinator death.
        with _file_lock(claim, create=True, exclusive_create=True) as acquired:
            if not acquired:
                raise BackupError("backup staging claim is already owned")
            claimed = True
            partial.mkdir()
            try:
                marker = partial / "pending.json"
                marker.write_text(
                    json.dumps(
                        {"format": _PENDING, "owner": state["owner"], "database": str(database)}
                    ),
                    encoding="utf-8",
                )
                snapshot = partial / "snapshot.db"
                _prepare_snapshot(database, snapshot, deadline)
                published = namespace / (now.strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid4().hex)
                item = {
                    "path": str(published / snapshot.name),
                    "created_at": now.isoformat(),
                    "sha256": _hash(snapshot, deadline),
                    "size_bytes": snapshot.stat().st_size,
                }
                receipt_path = partial / "receipt.json"
                with receipt_path.open("x", encoding="utf-8", newline="\n") as handle:
                    json.dump(_receipt(state, item), handle, separators=(",", ":"))
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                with snapshot.open("r+b") as handle:
                    os.fsync(handle.fileno())
                _check_deadline(deadline)
                marker.unlink()
                os.rename(partial, published)
            finally:
                if partial.exists():
                    _remove_partial(partial, state)
    except OSError as exc:
        raise BackupError(f"backup failed: {exc}") from exc
    else:
        return item
    finally:
        if claimed and claim is not None and partial is not None and not partial.exists():
            try:
                claim.unlink(missing_ok=True)
            except OSError as exc:
                warnings.warn(f"backup claim cleanup deferred: {exc}", BackupWarning, stacklevel=2)


def _verified(item: dict[str, Any], state: dict[str, Any], deadline: float) -> bool:
    try:
        path = Path(item["path"])
        namespace = _namespace(state)
        if (
            path.name != "snapshot.db"
            or path.parent.parent != namespace
            or not _ARCHIVE.fullmatch(path.parent.name)
            or namespace.is_symlink()
            or path.parent.is_symlink()
            or path.is_symlink()
            or path.resolve() != path
            or path.samefile(Path(state["database"]))
        ):
            return False
        receipt = path.with_name("receipt.json")
        if receipt.is_symlink() or set(path.parent.iterdir()) != {path, receipt}:
            return False
        _instant(item["created_at"])
        return bool(
            json.loads(receipt.read_text(encoding="utf-8")) == _receipt(state, item)
            and path.stat().st_size == item["size_bytes"]
            and _hash(path, deadline) == item["sha256"]
        )
    except (OSError, ValueError, TypeError, KeyError):
        return False


def _prune(state: dict[str, Any], now: datetime, deadline: float) -> dict[str, Any]:
    older: list[dict[str, Any]] = []
    for item in state["snapshots"]:
        _check_deadline(deadline)
        if now - _instant(item["created_at"]) > timedelta(days=7) and _verified(
            item, state, deadline
        ):
            older.append(item)
    weeks: dict[tuple[int, int], dict[str, Any]] = {}
    for item in sorted(older, key=lambda entry: _instant(entry["created_at"])):
        weeks[_instant(item["created_at"]).isocalendar()[:2]] = item
    retained = {weeks[key]["path"] for key in sorted(weeks, reverse=True)[:4]}
    removed = set()
    for item in older:
        if item["path"] in retained:
            continue
        _check_deadline(deadline)
        path = Path(item["path"])
        try:
            path.unlink()
            removed.add(item["path"])
            path.with_name("receipt.json").unlink()
            path.parent.rmdir()
        except OSError as exc:
            warnings.warn(
                f"backup retention could not remove {path}: {exc}", BackupWarning, stacklevel=2
            )
    state["snapshots"] = [item for item in state["snapshots"] if item["path"] not in removed]
    return state


def _worker(
    operation: str, database: Path, state: dict[str, Any], now: datetime, deadline: float
) -> dict[str, Any]:
    _check_deadline(deadline)
    try:
        result = subprocess.run(
            [sys.executable, "-c", "from cairntir.backups import _worker_main; _worker_main()"],
            input=json.dumps(
                {
                    "operation": operation,
                    "database": str(database),
                    "state": state,
                    "now": now.isoformat(),
                    "deadline": deadline,
                }
            ),
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(0.1, deadline - time.monotonic()),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.stderr.strip():
            warnings.warn(result.stderr.strip()[-1000:], BackupWarning, stacklevel=2)
        value = json.loads(result.stdout)
        if not isinstance(value, dict):
            raise BackupError("invalid backup worker result")
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip().splitlines()[-1] if exc.stderr.strip() else str(exc.returncode)
        raise BackupError(f"backup failed: {detail[-800:]}") from exc
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise BackupError(f"backup worker failed: {exc}") from exc
    else:
        return value


def _worker_main() -> None:
    arguments = json.load(sys.stdin)
    state, now, deadline = arguments["state"], _instant(arguments["now"]), arguments["deadline"]
    if arguments["operation"] == "create":
        value = _publish_snapshot(Path(arguments["database"]), state, now, deadline)
    else:
        value = _prune(state, now, deadline)
    print(json.dumps(value), flush=True)


def run(database: Path, *, force: bool = True) -> dict[str, Any]:
    """Create and verify one backup, or return a disabled, busy, or not-due receipt."""
    deadline = time.monotonic() + 18
    if type(force) is not bool:
        raise BackupError("backup force must be a boolean")
    database = _source(database)
    state = _load(database)
    if not state["enabled"]:
        return {"status": "disabled", **_public(state)}
    now = utc_now().astimezone(UTC)
    if not force and not _due(state, now):
        return {"status": "not_due", **_public(state)}
    with _lock(database, create=True) as acquired:
        if not acquired:
            return {"status": "busy", **_public(state, in_progress=True)}
        state = _load(database)
        if not state["enabled"]:
            return {"status": "disabled", **_public(state)}
        if not force and not _due(state, now):
            return {"status": "not_due", **_public(state)}
        try:
            item = _worker("create", database, state, now, min(deadline, time.monotonic() + 15))
        except BackupError as exc:
            state["last_error"] = str(exc)
            _save(database, state)
            raise
        state["snapshots"].append(item)
        state.update(last_success_at=now.isoformat(), last_error=None)
        _save(database, state)
        try:
            state = _worker("prune", database, state, now, deadline)
        except BackupError as exc:
            warnings.warn(
                f"backup succeeded; retention deferred: {exc}", BackupWarning, stacklevel=2
            )
            return {"status": "created", "snapshot": item, **_public(state), "snapshots": [item]}
        _save(database, state)
        return {"status": "created", "snapshot": item, **_public(state)}
