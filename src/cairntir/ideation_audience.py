"""Store-backed, immutable audience snapshots for an Obsidian workspace."""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sqlite3
import tempfile
import unicodedata
from collections.abc import Mapping
from contextlib import closing, suppress
from pathlib import Path
from typing import Any

from cairntir.errors import ProjectionError

_FIELDS = ("audience", "channels", "pain", "sophistication", "desired_outcome")
_KINDS = {"inferred", "user_statement", "user_confirmation"}
_IDENT = re.compile(r"[a-z0-9](?:[a-z0-9._:-]{0,62}[a-z0-9])?\Z")
_SOURCE_ID = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._:-]{0,126}[A-Za-z0-9])?\Z")
_BEGIN = "<!-- cairntir:audience:begin -->"
_END = "<!-- cairntir:audience:end -->"
_TABLE = """
CREATE TABLE IF NOT EXISTS cairntir_audience_revisions (
    wing TEXT NOT NULL,
    revision INTEGER NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_json TEXT NOT NULL,
    profile_json TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    status TEXT NOT NULL,
    vault_path TEXT NOT NULL,
    snapshot_sha256 TEXT NOT NULL,
    projection_status TEXT NOT NULL,
    PRIMARY KEY (wing, revision),
    UNIQUE (wing, idempotency_key)
)
"""


def _line(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProjectionError(f"{label} must be nonblank text")
    if any(unicodedata.category(char)[0] == "C" or char in "\u2028\u2029" for char in value):
        raise ProjectionError(f"{label} cannot contain line or control characters")
    if "<!--" in value or "-->" in value:
        raise ProjectionError(f"{label} cannot contain a generated marker")
    return value


def _source_id(value: object) -> str:
    if not isinstance(value, str) or _SOURCE_ID.fullmatch(value) is None:
        raise ProjectionError("source ID must be a safe, nonblank identifier")
    return value


def _evidence(value: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    if not isinstance(value, Mapping):
        raise ProjectionError("evidence must be a mapping")
    result: dict[str, dict[str, Any]] = {}
    for raw_id, raw_item in value.items():
        source_id = _source_id(raw_id)
        if not isinstance(raw_item, Mapping):
            raise ProjectionError(f"evidence {source_id} must be a mapping")
        kind = raw_item.get("kind")
        if not isinstance(kind, str) or kind not in _KINDS:
            raise ProjectionError(f"evidence {source_id} has an invalid kind")
        content = _line(raw_item.get("content"), f"evidence {source_id} content")
        raw_supports = raw_item.get("supports")
        if not isinstance(raw_supports, list) or not raw_supports:
            raise ProjectionError(f"evidence {source_id} needs supported dimensions")
        if any(field not in _FIELDS for field in raw_supports) or len(set(raw_supports)) != len(
            raw_supports
        ):
            raise ProjectionError(f"evidence {source_id} has invalid supported dimensions")
        item: dict[str, Any] = {"kind": kind, "content": content, "supports": raw_supports[:]}
        raw_values = raw_item.get("values")
        if kind != "inferred":
            if not isinstance(raw_values, Mapping) or set(raw_values) != set(raw_supports):
                raise ProjectionError(f"evidence {source_id} needs exact value bindings")
            item["values"] = {
                field: _line(raw_values[field], f"evidence {source_id} value")
                for field in raw_supports
            }
        elif raw_values is not None:
            raise ProjectionError(f"inferred evidence {source_id} cannot assert human values")
        result[source_id] = item
    return result


def _profile(
    value: Mapping[str, Any], evidence: Mapping[str, Mapping[str, Any]]
) -> dict[str, dict[str, Any]]:
    if not isinstance(value, Mapping) or set(value) != set(_FIELDS):
        raise ProjectionError("profile must contain exactly five audience dimensions")
    result: dict[str, dict[str, Any]] = {}
    for field in _FIELDS:
        raw_item = value[field]
        if not isinstance(raw_item, Mapping):
            raise ProjectionError(f"profile {field} must be a mapping")
        field_value = _line(raw_item.get("value"), f"profile {field} value")
        raw_ids = raw_item.get("source_ids")
        if not isinstance(raw_ids, list) or not raw_ids:
            raise ProjectionError(f"profile {field} needs source IDs")
        source_ids = [_source_id(item) for item in raw_ids]
        if len(set(source_ids)) != len(source_ids):
            raise ProjectionError(f"profile {field} repeats a source ID")
        for source_id in source_ids:
            if source_id not in evidence or field not in evidence[source_id]["supports"]:
                raise ProjectionError(f"profile {field} has an unsupported source ID")
        result[field] = {"value": field_value, "source_ids": source_ids}
    return result


def _validate_request(
    profile: Mapping[str, Any],
    evidence: Mapping[str, Any],
    status: str,
    confirmation_source_id: str | None,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], str]:
    checked_evidence = _evidence(evidence)
    checked_profile = _profile(profile, checked_evidence)
    if not isinstance(status, str) or status not in {"provisional", "confirmed"}:
        raise ProjectionError("audience status must be provisional or confirmed")
    if confirmation_source_id is not None:
        _source_id(confirmation_source_id)
        if status != "confirmed":
            raise ProjectionError("a confirmation source requires confirmed status")
    if status == "confirmed":
        raise ProjectionError(
            "audience confirmation requires an authenticated user-evidence issuer"
        )
    request = {
        "profile": checked_profile,
        "evidence": checked_evidence,
        "status": status,
        "confirmation_source_id": confirmation_source_id,
    }
    request_json = json.dumps(request, sort_keys=True, separators=(",", ":"))
    return checked_profile, checked_evidence, request_json


def _paths(
    store_path: str | os.PathLike[str], vault_path: str | os.PathLike[str], wing: str
) -> tuple[Path, Path]:
    if not isinstance(wing, str) or _IDENT.fullmatch(wing) is None:
        raise ProjectionError("invalid audience wing")
    try:
        vault_input = Path(vault_path).expanduser()
        if vault_input.is_symlink():
            raise ProjectionError("vault root cannot be a symlink")
        vault = vault_input.resolve(strict=True)
        if not vault.is_dir():
            raise ProjectionError("vault path must be a directory")
        store_input = Path(store_path).expanduser()
        if store_input.is_symlink():
            raise ProjectionError("store path cannot be a symlink")
        store = store_input.resolve(strict=False)
        if store == vault or store.is_relative_to(vault):
            raise ProjectionError("audience store must remain outside the vault")
        if not store.parent.is_dir():
            raise ProjectionError("audience store parent is missing")
    except (OSError, TypeError, ValueError) as exc:
        raise ProjectionError(f"invalid audience paths: {exc}") from exc
    return store, vault


def _versions(vault: Path, wing: str, *, create: bool) -> Path:
    current = vault
    for name in ("cairntir-sync", wing, "audience", "versions"):
        current = current / name
        if current.is_symlink():
            raise ProjectionError(f"generated audience path is a symlink: {current}")
        if create and not current.exists():
            with suppress(FileExistsError):
                current.mkdir()
        if current.exists() and not current.is_dir():
            raise ProjectionError(f"generated audience path is not a directory: {current}")
    return current


def _markdown(value: str) -> str:
    escaped = html.escape(value, quote=True)
    return re.sub(r"([\\`*_\[\]])", r"\\\1", escaped)


def _render(
    wing: str,
    revision: int,
    status: str,
    profile: Mapping[str, Mapping[str, Any]],
    evidence: Mapping[str, Mapping[str, Any]],
) -> bytes:
    lines = [
        "# Audience",
        "",
        f"wing: {wing}",
        f"revision: {revision}",
        f"status: {status}",
        "",
        "## Profile",
    ]
    for field in _FIELDS:
        item = profile[field]
        sources = ", ".join(item["source_ids"])
        lines.append(f"- {field}: {_markdown(item['value'])} [sources: {sources}]")
    lines += ["", "## Evidence"]
    for source_id, item in sorted(evidence.items()):
        lines.append(
            f"- {source_id} ({item['kind']}; supports: {', '.join(item['supports'])}): "
            f"{_markdown(item['content'])}"
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


def _target(vault: Path, wing: str, row: sqlite3.Row) -> Path:
    if (
        not isinstance(row["revision"], int)
        or row["revision"] < 1
        or not isinstance(row["snapshot_sha256"], str)
        or re.fullmatch(r"[0-9a-f]{64}", row["snapshot_sha256"]) is None
    ):
        raise ProjectionError("stored audience revision has invalid identity")
    return _versions(vault, wing, create=False) / (
        f"revision-{row['revision']}-{row['snapshot_sha256']}.md"
    )


def _snapshot_state(path: Path, digest: str) -> str:
    if path.is_symlink():
        return "conflict"
    try:
        content = path.read_bytes()
    except FileNotFoundError:
        return "missing"
    except (IsADirectoryError, OSError) as exc:
        raise ProjectionError(f"cannot read audience snapshot {path}: {exc}") from exc
    return "ready" if hashlib.sha256(content).hexdigest() == digest else "conflict"


def _materialize(vault: Path, wing: str, row: sqlite3.Row) -> Path:
    directory = _versions(vault, wing, create=True)
    target = directory / f"revision-{row['revision']}-{row['snapshot_sha256']}.md"
    content = _render(
        wing,
        row["revision"],
        row["status"],
        json.loads(row["profile_json"]),
        json.loads(row["evidence_json"]),
    )
    if hashlib.sha256(content).hexdigest() != row["snapshot_sha256"]:
        raise ProjectionError("stored audience revision does not match its snapshot digest")
    state = _snapshot_state(target, row["snapshot_sha256"])
    if state == "conflict":
        raise ProjectionError("audience snapshot was changed; original bytes preserved")
    if state == "missing":
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", prefix=".audience-", suffix=".tmp", dir=directory, delete=False
            ) as handle:
                temporary = Path(handle.name)
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, target)
            except FileExistsError:
                if _snapshot_state(target, row["snapshot_sha256"]) != "ready":
                    raise ProjectionError(
                        "audience snapshot conflicts with committed revision"
                    ) from None
        except OSError as exc:
            raise ProjectionError(f"cannot materialize audience snapshot: {exc}") from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return target


def _receipt(row: sqlite3.Row, vault: Path, wing: str, *, current_revision: int) -> dict[str, Any]:
    if row["status"] != "provisional":
        raise ProjectionError(
            "stored audience confirmation is unverified; publish a provisional revision"
        )
    path = _target(vault, wing, row)
    profile = json.loads(row["profile_json"])
    evidence = json.loads(row["evidence_json"])
    rendered = _render(wing, row["revision"], row["status"], profile, evidence)
    if hashlib.sha256(rendered).hexdigest() != row["snapshot_sha256"]:
        raise ProjectionError("stored audience evidence does not match its snapshot digest")
    state = _snapshot_state(path, row["snapshot_sha256"])
    return {
        "revision": row["revision"],
        "status": row["status"],
        "projection_status": state if state != "ready" else row["projection_status"],
        "snapshot_path": str(path),
        "snapshot_sha256": row["snapshot_sha256"],
        "currentness": "current" if row["revision"] == current_revision else "historical",
        "profile": profile,
        "evidence": evidence,
    }


def publish_audience_revision(
    store_path: str | os.PathLike[str],
    vault_path: str | os.PathLike[str],
    wing: str,
    profile: Mapping[str, Any],
    evidence: Mapping[str, Any],
    *,
    idempotency_key: str,
    status: str = "provisional",
    confirmation_source_id: str | None = None,
) -> dict[str, Any]:
    """Commit a value-bound revision, then materialize its immutable snapshot."""
    store, vault = _paths(store_path, vault_path, wing)
    key = _source_id(idempotency_key)
    checked_profile, checked_evidence, request_json = _validate_request(
        profile, evidence, status, confirmation_source_id
    )
    _versions(vault, wing, create=False)
    try:
        with closing(sqlite3.connect(store, timeout=20)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(_TABLE)
            row = conn.execute(
                "SELECT * FROM cairntir_audience_revisions WHERE wing=? AND idempotency_key=?",
                (wing, key),
            ).fetchone()
            if row is None:
                revision = conn.execute(
                    "SELECT COALESCE(MAX(revision), 0) + 1 "
                    "FROM cairntir_audience_revisions WHERE wing=?",
                    (wing,),
                ).fetchone()[0]
                snapshot = _render(wing, revision, status, checked_profile, checked_evidence)
                digest = hashlib.sha256(snapshot).hexdigest()
                conn.execute(
                    "INSERT INTO cairntir_audience_revisions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        wing,
                        revision,
                        key,
                        request_json,
                        json.dumps(checked_profile, sort_keys=True),
                        json.dumps(checked_evidence, sort_keys=True),
                        status,
                        str(vault),
                        digest,
                        "pending",
                    ),
                )
                row = conn.execute(
                    "SELECT * FROM cairntir_audience_revisions WHERE wing=? AND revision=?",
                    (wing, revision),
                ).fetchone()
            elif row["request_json"] != request_json or row["vault_path"] != str(vault):
                raise ProjectionError("idempotency key already binds a different audience request")
            conn.commit()
            if row is None:
                raise ProjectionError("audience revision was not committed")
            if row["projection_status"] == "ready":
                if _snapshot_state(_target(vault, wing, row), row["snapshot_sha256"]) != "ready":
                    raise ProjectionError("committed audience snapshot is missing or changed")
            else:
                _materialize(vault, wing, row)
                conn.execute(
                    "UPDATE cairntir_audience_revisions SET projection_status='ready' "
                    "WHERE wing=? AND revision=? AND projection_status='pending'",
                    (wing, row["revision"]),
                )
                conn.commit()
            refreshed = conn.execute(
                "SELECT * FROM cairntir_audience_revisions WHERE wing=? AND revision=?",
                (wing, row["revision"]),
            ).fetchone()
            latest = conn.execute(
                "SELECT MAX(revision) FROM cairntir_audience_revisions WHERE wing=?", (wing,)
            ).fetchone()[0]
            if refreshed is None:
                raise ProjectionError("committed audience revision disappeared")
            return _receipt(refreshed, vault, wing, current_revision=latest)
    except (sqlite3.Error, OSError, ValueError, KeyError, TypeError) as exc:
        raise ProjectionError(f"audience publication failed: {exc}") from exc


def get_audience_revision(
    store_path: str | os.PathLike[str], vault_path: str | os.PathLike[str], wing: str
) -> dict[str, Any]:
    """Return the latest committed revision and its verified projection state."""
    store, vault = _paths(store_path, vault_path, wing)
    if not store.is_file():
        raise ProjectionError("audience store does not exist")
    try:
        with closing(sqlite3.connect(store, timeout=20)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM cairntir_audience_revisions WHERE wing=? "
                "ORDER BY revision DESC LIMIT 1",
                (wing,),
            ).fetchone()
            if row is None:
                raise ProjectionError(f"no audience revision for wing {wing}")
            if row["vault_path"] != str(vault):
                raise ProjectionError("audience revision is bound to another vault")
            return _receipt(row, vault, wing, current_revision=row["revision"])
    except (sqlite3.Error, OSError, ValueError, KeyError, TypeError) as exc:
        raise ProjectionError(f"cannot read audience revision: {exc}") from exc


def scan_legacy_audience(spec_path: str | os.PathLike[str]) -> dict[str, str]:
    """Classify old inline audience markers without changing the human file."""
    try:
        path = Path(spec_path).expanduser()
    except (TypeError, ValueError) as exc:
        raise ProjectionError(f"invalid legacy audience path: {exc}") from exc
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"state": "absent", "spec_path": str(path)}
    except (OSError, UnicodeError) as exc:
        raise ProjectionError(f"cannot read legacy audience note: {exc}") from exc
    begins = [match.start() for match in re.finditer(re.escape(_BEGIN), content)]
    ends = [match.start() for match in re.finditer(re.escape(_END), content)]
    if not begins and not ends:
        state = "none"
    elif len(begins) == len(ends) == 1 and begins[0] < ends[0]:
        state = "legacy"
    else:
        state = "ambiguous"
    return {"state": state, "spec_path": str(path)}
