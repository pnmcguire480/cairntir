"""Durable, hash-verified print artifacts attached to remembered iterations."""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import stat
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

from cairntir.errors import MemoryStoreError

if TYPE_CHECKING:
    from cairntir.access import ScopedStore
    from cairntir.memory.store import DrawerStore

_MAX_BYTES = 64 * 1024 * 1024


class IterationArtifactError(MemoryStoreError):
    """A visible attachment refusal with a stable caller-facing code."""

    def __init__(self, code: str, message: str) -> None:
        """Retain the stable refusal code and its explanation."""
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ArtifactRef:
    """Immutable identity, parent and integrity receipt; no producer path."""

    artifact_id: int
    iteration_id: int
    iteration_identity: str
    wing: str
    kind: Literal["stl", "gcode"]
    label: str
    byte_count: int
    sha256: str
    created_at: str


@dataclass(frozen=True)
class ArtifactRead:
    """Complete bytes verified against their saved reference."""

    reference: ArtifactRef
    data: bytes


def _positive(value: object) -> bool:
    return type(value) is int and value > 0


def _label(kind: str, label: str) -> None:
    if kind not in ("stl", "gcode"):
        raise IterationArtifactError("UNSUPPORTED_ARTIFACT", "Expected stl or gcode")
    if not isinstance(label, str):
        raise IterationArtifactError("UNSAFE_SOURCE", "Expected a simple artifact label")
    try:
        encoded = label.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise IterationArtifactError("UNSAFE_SOURCE", "Artifact label is not valid UTF-8") from exc
    if (
        not isinstance(label, str)
        or not label
        or len(encoded) > 255
        or label != label.strip()
        or any(c in label for c in "/\\:")
        or any(ord(c) < 32 or ord(c) == 127 for c in label)
        or label.startswith(".")
        or label.endswith(".")
    ):
        raise IterationArtifactError("UNSAFE_SOURCE", "Expected a simple artifact label")
    if Path(label).suffix.lower() != "." + kind:
        raise IterationArtifactError("UNSUPPORTED_ARTIFACT", "Label extension does not match kind")


def _source(source: Path, kind: str, label: str | None, limit: int) -> tuple[str, bytes]:
    if not isinstance(source, Path):
        raise IterationArtifactError("UNSAFE_SOURCE", "Expected a local file path")
    chosen = source.name if label is None else label
    _label(kind, chosen)
    if source.suffix.lower() != "." + kind:
        raise IterationArtifactError("UNSUPPORTED_ARTIFACT", "Source extension does not match kind")

    def safe_path() -> os.stat_result:
        for part in (source, *source.parents):
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise IterationArtifactError("UNSAFE_SOURCE", "Linked artifact paths are refused")
        info = source.lstat()
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
            raise IterationArtifactError(
                "UNSAFE_SOURCE", "Artifact must be a nonempty bounded file"
            )
        return info

    def identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
        return (
            info.st_dev,
            info.st_ino,
            info.st_size,
            info.st_mtime_ns,
            getattr(info, "st_birthtime_ns", info.st_ctime_ns),
        )

    try:
        before = safe_path()
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        with os.fdopen(os.open(source, flags), "rb") as handle:
            opened = os.fstat(handle.fileno())
            if identity(before) != identity(opened):
                raise IterationArtifactError("UNSAFE_SOURCE", "Artifact changed while opening")
            data = handle.read(limit + 1)
            after = os.fstat(handle.fileno())
        final_path = safe_path()
        # Windows ctime differs across APIs; retain each API's change-clock check.
        if (
            identity(before) != identity(after)
            or identity(before) != identity(final_path)
            or before.st_ctime_ns != final_path.st_ctime_ns
            or opened.st_ctime_ns != after.st_ctime_ns
            or len(data) != before.st_size
        ):
            raise IterationArtifactError("UNSAFE_SOURCE", "Artifact changed while reading")
    except OSError as exc:
        raise IterationArtifactError("UNSAFE_SOURCE", "Artifact file is unavailable") from exc
    return chosen, data


def _parent(store: DrawerStore, iteration_id: int) -> tuple[str, str]:
    if not _positive(iteration_id):
        raise IterationArtifactError("ITERATION_UNAVAILABLE", "Expected an existing iteration ID")
    drawer = store._read_drawer(iteration_id)
    if drawer is None:
        raise IterationArtifactError("ITERATION_UNAVAILABLE", "Iteration is unavailable")
    identity = store.portable_identity(iteration_id)
    try:
        UUID(identity)
    except ValueError as exc:
        raise IterationArtifactError(
            "ITERATION_UNAVAILABLE", "Iteration identity is invalid"
        ) from exc
    return identity, drawer.wing


def _reference(row: dict[str, Any]) -> ArtifactRef:
    try:
        ref = ArtifactRef(**{key: row[key] for key in ArtifactRef.__dataclass_fields__})
        _label(ref.kind, ref.label)
        UUID(ref.iteration_identity)
        created = datetime.fromisoformat(ref.created_at)
    except (KeyError, TypeError, ValueError, AttributeError, IterationArtifactError) as exc:
        raise IterationArtifactError("ARTIFACT_CORRUPT", "Artifact reference is invalid") from exc
    if (
        not _positive(ref.artifact_id)
        or not _positive(ref.iteration_id)
        or not _positive(ref.byte_count)
        or ref.byte_count > _MAX_BYTES
        or not isinstance(ref.wing, str)
        or not ref.wing
        or not isinstance(ref.sha256, str)
        or re.fullmatch("[0-9a-f]{64}", ref.sha256) is None
        or created.tzinfo is None
    ):
        raise IterationArtifactError("ARTIFACT_CORRUPT", "Artifact reference is invalid")
    return ref


def _verified(ref: ArtifactRef, data: bytes | None) -> ArtifactRead:
    if data is None:
        raise IterationArtifactError("ARTIFACT_MISSING", "Saved artifact bytes are missing")
    if (
        not isinstance(data, bytes)
        or len(data) != ref.byte_count
        or hashlib.sha256(data).hexdigest() != ref.sha256
    ):
        raise IterationArtifactError(
            "ARTIFACT_CORRUPT", "Saved artifact bytes fail integrity checks"
        )
    return ArtifactRead(ref, data)


def _tables(store: DrawerStore) -> bool:
    names = {
        row[0]
        for row in store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('iteration_artifact_refs', 'iteration_artifact_blobs')"
        )
    }
    if names and len(names) != 2:
        raise IterationArtifactError("STORE_UNAVAILABLE", "Attachment storage is incomplete")
    return bool(names)


def _refs(store: DrawerStore, iteration_id: int) -> list[dict[str, Any]]:
    identity, wing = _parent(store, iteration_id)
    if not _tables(store):
        return []
    rows = store._conn.execute(
        "SELECT artifact_id, iteration_id, iteration_identity, wing, kind, label, "
        "byte_count, sha256, created_at FROM iteration_artifact_refs "
        "WHERE iteration_id=? ORDER BY artifact_id",
        (iteration_id,),
    ).fetchall()
    result = []
    for row in rows:
        ref = _reference(dict(row))
        if ref.iteration_identity != identity or ref.wing != wing:
            raise IterationArtifactError("ARTIFACT_CORRUPT", "Artifact parent binding changed")
        result.append(asdict(ref))
    if _parent(store, iteration_id) != (identity, wing):
        raise IterationArtifactError("ITERATION_UNAVAILABLE", "Iteration changed during access")
    return result


def _blob(
    store: DrawerStore, iteration_id: int, artifact_id: int
) -> tuple[dict[str, Any], bytes | None] | None:
    if not _positive(artifact_id):
        raise IterationArtifactError(
            "ARTIFACT_NOT_FOUND", "Artifact is unavailable for this iteration"
        )
    refs = _refs(store, iteration_id)
    reference = next((row for row in refs if row["artifact_id"] == artifact_id), None)
    if reference is None:
        return None
    row = store._conn.execute(
        "SELECT data FROM iteration_artifact_blobs WHERE artifact_id=?", (artifact_id,)
    ).fetchone()
    if _parent(store, iteration_id) != (reference["iteration_identity"], reference["wing"]):
        raise IterationArtifactError("ITERATION_UNAVAILABLE", "Iteration changed during access")
    return reference, None if row is None else row[0]


def _attach(
    store: DrawerStore, iteration_id: int, kind: str, label: str, data: bytes
) -> dict[str, Any]:
    _label(kind, label)
    if not isinstance(data, bytes) or not 0 < len(data) <= _MAX_BYTES:
        raise IterationArtifactError("UNSAFE_SOURCE", "Artifact bytes must be nonempty and bounded")
    if store._read_snapshot is not None:
        raise IterationArtifactError("STORE_UNAVAILABLE", "Attachment store is read-only")
    with store.transaction():
        identity, wing = _parent(store, iteration_id)
        refs = _refs(store, iteration_id)
        for row in refs:
            ref = _reference(row)
            if (ref.kind, ref.label) == (kind, label):
                existing = _blob(store, iteration_id, ref.artifact_id)
                if existing is None:
                    raise IterationArtifactError("ARTIFACT_MISSING", "Saved artifact is missing")
                saved = _verified(ref, existing[1])
                if saved.data != data:
                    raise IterationArtifactError(
                        "ATTACHMENT_CONFLICT", "Artifact label already has other bytes"
                    )
                return asdict(ref)
        store._conn.execute(
            "CREATE TABLE IF NOT EXISTS iteration_artifact_refs ("
            "artifact_id INTEGER PRIMARY KEY, "
            "iteration_id INTEGER NOT NULL REFERENCES drawers(id), "
            "iteration_identity TEXT NOT NULL, wing TEXT NOT NULL, kind TEXT NOT NULL, "
            "label TEXT NOT NULL, byte_count INTEGER NOT NULL, sha256 TEXT NOT NULL, "
            "created_at TEXT NOT NULL, UNIQUE(iteration_id, kind, label))"
        )
        store._conn.execute(
            "CREATE TABLE IF NOT EXISTS iteration_artifact_blobs ("
            "artifact_id INTEGER PRIMARY KEY REFERENCES iteration_artifact_refs(artifact_id), "
            "data BLOB NOT NULL)"
        )
        digest = hashlib.sha256(data).hexdigest()
        created = datetime.now(UTC).isoformat()
        cursor = store._conn.execute(
            "INSERT INTO iteration_artifact_refs "
            "(iteration_id, iteration_identity, wing, kind, label, byte_count, sha256, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (iteration_id, identity, wing, kind, label, len(data), digest, created),
        )
        artifact_id = cursor.lastrowid
        store._conn.execute(
            "INSERT INTO iteration_artifact_blobs (artifact_id, data) VALUES (?,?)",
            (artifact_id, data),
        )
        if artifact_id is None:
            raise IterationArtifactError(
                "STORE_UNAVAILABLE", "Artifact insert returned no identity"
            )
        stored = _blob(store, iteration_id, artifact_id)
        if stored is None:
            raise IterationArtifactError("STORE_UNAVAILABLE", "Artifact insert was not retained")
        ref = _reference(stored[0])
        verified = _verified(ref, stored[1])
        if verified.data != data or (ref.kind, ref.label) != (kind, label):
            raise IterationArtifactError("ARTIFACT_CORRUPT", "Artifact changed before commit")
        return asdict(ref)


def _store_operation(store: DrawerStore, operation: str, *args: Any) -> Any:
    try:
        if operation == "attach":
            return _attach(store, *args)
        if operation == "refs":
            return _refs(store, *args)
        return _blob(store, *args)
    except IterationArtifactError:
        raise
    except (sqlite3.Error, MemoryStoreError) as exc:
        raise IterationArtifactError(
            "STORE_UNAVAILABLE", "Attachment store is unavailable"
        ) from exc


class IterationArtifactBook:
    """Attach producer-supplied bytes and retrieve them under parent authority."""

    def __init__(self, store: DrawerStore | ScopedStore, *, max_bytes: int = _MAX_BYTES) -> None:
        """Bind a store and an explicit per-file size limit."""
        if not _positive(max_bytes) or max_bytes > _MAX_BYTES:
            raise IterationArtifactError(
                "UNSAFE_SOURCE", "Expected a positive maximum up to 64 MiB"
            )
        self._store = store
        self._max_bytes = max_bytes

    def attach(
        self, iteration_id: int, source: Path, *, kind: str, label: str | None = None
    ) -> ArtifactRef:
        """Save one atomic immutable reference and its complete verified bytes."""
        chosen, data = _source(source, kind, label, self._max_bytes)
        return _reference(self._store._iteration_artifact_attach(iteration_id, kind, chosen, data))

    def list_for_iteration(self, iteration_id: int) -> list[ArtifactRef]:
        """Read saved references without touching parent metadata or bytes."""
        return [_reference(row) for row in self._store._iteration_artifact_refs(iteration_id)]

    def read(self, iteration_id: int, artifact_id: int) -> ArtifactRead:
        """Return only bytes that still match the immutable reference."""
        stored = self._store._iteration_artifact_blob(iteration_id, artifact_id)
        if stored is None:
            raise IterationArtifactError(
                "ARTIFACT_NOT_FOUND", "Artifact is unavailable for this iteration"
            )
        return _verified(_reference(stored[0]), stored[1])
