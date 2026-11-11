"""Human confirmation of an audience revision and its transfer into a specification.

A revision stays immutable. Confirmation is a separate receipt bound to one
revision and its snapshot digest, so publishing a new revision returns the
project to provisional. Only a person at an interactive terminal typing a fresh
code can create that receipt; silence, a wrong answer or a script's piped input
cannot. This proves a deliberate terminal action on this computer, not who
typed it, and does not defend against a process that drives a real terminal.
"""

from __future__ import annotations

import os
import secrets
import sqlite3
import tempfile
import uuid
from collections.abc import Callable, Mapping
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cairntir import ideation_audience as audience
from cairntir.errors import ProjectionError

_METHOD = "interactive-terminal"
_TABLE = """
CREATE TABLE IF NOT EXISTS cairntir_audience_confirmations (
    wing TEXT NOT NULL,
    revision INTEGER NOT NULL,
    snapshot_sha256 TEXT NOT NULL,
    method TEXT NOT NULL,
    confirmed_at TEXT NOT NULL,
    PRIMARY KEY (wing, revision)
)
"""


def _confirmation(
    conn: sqlite3.Connection, receipt: dict[str, Any], wing: str
) -> dict[str, Any] | None:
    found = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='cairntir_audience_confirmations'"
    ).fetchone()
    if found is None:
        return None
    row = conn.execute(
        "SELECT method, confirmed_at FROM cairntir_audience_confirmations "
        "WHERE wing=? AND revision=? AND snapshot_sha256=?",
        (wing, receipt["revision"], receipt["snapshot_sha256"]),
    ).fetchone()
    return None if row is None else {"method": row[0], "confirmed_at": row[1]}


def audience_lock(
    store_path: str | os.PathLike[str], vault_path: str | os.PathLike[str], wing: str
) -> dict[str, Any]:
    """Return the current revision and whether a person has confirmed exactly it."""
    receipt = audience.get_audience_revision(store_path, vault_path, wing)
    try:
        with closing(sqlite3.connect(store_path, timeout=20)) as conn:
            confirmation = _confirmation(conn, receipt, wing)
    except sqlite3.Error as exc:
        raise ProjectionError(f"cannot read audience confirmation: {exc}") from exc
    if receipt["projection_status"] != "ready":
        confirmation = None
    return {
        **receipt,
        "lock": "confirmed" if confirmation is not None else "provisional",
        "confirmation": confirmation,
    }


def _summary(state: dict[str, Any]) -> str:
    evidence = state["evidence"]
    lines = [f"Audience revision {state['revision']}:"]
    for field, item in state["profile"].items():
        sources = ", ".join(f"{sid} ({evidence[sid]['kind']})" for sid in item["source_ids"])
        lines.append(f"  {field}: {item['value']}  [sources: {sources}]")
    return "\n".join(lines)


def confirm_audience(
    store_path: str | os.PathLike[str],
    vault_path: str | os.PathLike[str],
    wing: str,
    *,
    interactive: bool,
    ask: Callable[[str], str],
    show: Callable[[str], None],
) -> dict[str, Any]:
    """Record a person's confirmation of the current revision, or raise."""
    if not interactive:
        raise ProjectionError("audience confirmation needs an interactive terminal")
    state = audience_lock(store_path, vault_path, wing)
    if state["lock"] == "confirmed":
        return state
    if state["projection_status"] != "ready":
        raise ProjectionError("audience snapshot is missing or changed; publish a new revision")
    show(_summary(state))
    code = secrets.token_hex(3)
    try:
        answer = ask(f"Type {code} to confirm this audience, or anything else to cancel: ")
    except (EOFError, KeyboardInterrupt) as exc:
        raise ProjectionError("audience not confirmed: no answer was given") from exc
    if answer.strip() != code:
        raise ProjectionError("audience not confirmed: the code did not match")
    try:
        with closing(sqlite3.connect(store_path, timeout=20)) as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(_TABLE)
            latest = conn.execute(
                "SELECT revision, snapshot_sha256 FROM cairntir_audience_revisions "
                "WHERE wing=? ORDER BY revision DESC LIMIT 1",
                (wing,),
            ).fetchone()
            if latest != (state["revision"], state["snapshot_sha256"]):
                raise ProjectionError("audience changed during confirmation; review it again")
            conn.execute(
                "INSERT INTO cairntir_audience_confirmations VALUES (?, ?, ?, ?, ?)",
                (
                    wing,
                    state["revision"],
                    state["snapshot_sha256"],
                    _METHOD,
                    datetime.now(UTC).isoformat(timespec="seconds"),
                ),
            )
            conn.commit()
    except sqlite3.Error as exc:
        raise ProjectionError(f"cannot record audience confirmation: {exc}") from exc
    return audience_lock(store_path, vault_path, wing)


_CAPTURE_SOURCE = "cli-capture"


def capture_audience(
    store_path: str | os.PathLike[str],
    vault_path: str | os.PathLike[str],
    wing: str,
    values: Mapping[str, str],
) -> dict[str, Any]:
    """Store the five audience fields a person typed as a provisional revision.

    The source is a statement by the caller, so the revision is never confirmed
    here; only `confirm_audience` can do that. The same values as the current
    revision make no new revision.
    """
    fields = audience._FIELDS
    if not isinstance(values, Mapping):
        raise ProjectionError("audience values must be a mapping")
    missing = [f for f in fields if f not in values]
    unknown = sorted(str(k) for k in values if k not in fields)
    if missing:
        raise ProjectionError(f"audience capture is missing: {', '.join(missing)}")
    if unknown:
        raise ProjectionError(f"audience capture has unknown fields: {', '.join(unknown)}")
    profile = {f: {"value": values[f], "source_ids": [_CAPTURE_SOURCE]} for f in fields}
    evidence = {
        _CAPTURE_SOURCE: {
            "kind": "user_statement",
            "content": "Typed by the person running cairntir audience capture.",
            "supports": list(fields),
            "values": {f: values[f] for f in fields},
        }
    }
    if Path(store_path).expanduser().is_file():
        try:
            current = audience.get_audience_revision(store_path, vault_path, wing)
        except ProjectionError as exc:
            if "no audience revision" not in str(exc):
                raise
        else:
            if current["profile"] == profile and current["evidence"] == evidence:
                return current
    return audience.publish_audience_revision(
        store_path,
        vault_path,
        wing,
        profile,
        evidence,
        idempotency_key=f"capture-{uuid.uuid4().hex}",
    )


def _block(state: dict[str, Any], newline: bytes) -> bytes:
    evidence = state["evidence"]
    confirmation = state["confirmation"]
    note = (
        f"Status: confirmed by a person on {confirmation['confirmed_at']}"
        if confirmation is not None
        else "Status: provisional. This audience is not confirmed by a person."
    )
    lines = [
        audience._BEGIN,
        "## Audience",
        "",
        note,
        f"Revision {state['revision']}, snapshot {state['snapshot_sha256']}",
        "",
    ]
    for field, item in state["profile"].items():
        sources = ", ".join(f"{sid} ({evidence[sid]['kind']})" for sid in item["source_ids"])
        lines.append(f"- {field}: {audience._markdown(item['value'])} [sources: {sources}]")
    lines.append(audience._END)
    return newline.join(line.encode("utf-8") for line in lines)


def _read_spec(path: Path) -> tuple[bytes | None, int, int]:
    """Return the file bytes and its generated block's bounds, or refuse an unsafe file."""
    if path.is_symlink():
        raise ProjectionError("specification cannot be a symlink")
    state = audience.scan_legacy_audience(path)["state"]
    if state == "ambiguous":
        raise ProjectionError("specification has ambiguous audience markers")
    if state == "absent":
        return None, -1, -1
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise ProjectionError(f"cannot read specification: {exc}") from exc
    if state == "none":
        return content, -1, -1
    end = audience._END.encode("utf-8")
    return content, content.index(audience._BEGIN.encode("utf-8")), content.index(end) + len(end)


def _updated(content: bytes | None, start: int, end: int, state: dict[str, Any]) -> bytes:
    if content is None:
        return _block(state, b"\n") + b"\n"
    newline = b"\r\n" if b"\r\n" in content else b"\n"
    block = _block(state, newline)
    if start >= 0:
        return content[:start] + block + content[end:]
    prefix = content if not content or content.endswith(b"\n") else content + newline
    return prefix + (newline if prefix else b"") + block + newline


def spec_transfer_state(
    store_path: str | os.PathLike[str],
    vault_path: str | os.PathLike[str],
    wing: str,
    spec_path: str | os.PathLike[str],
) -> str:
    """Report whether the specification shows the current audience and lock."""
    state = audience_lock(store_path, vault_path, wing)
    content, start, end = _read_spec(Path(spec_path))
    if content is None or start < 0:
        return "absent"
    return "current" if _updated(content, start, end, state) == content else "stale"


def transfer_audience_to_spec(
    store_path: str | os.PathLike[str],
    vault_path: str | os.PathLike[str],
    wing: str,
    spec_path: str | os.PathLike[str],
) -> dict[str, Any]:
    """Write the current audience into its marked block, keeping all other bytes."""
    state = audience_lock(store_path, vault_path, wing)
    path = Path(spec_path)
    content, start, end = _read_spec(path)
    updated = _updated(content, start, end, state)
    summary = {"spec_path": str(path), "revision": state["revision"], "lock": state["lock"]}
    if updated == content:
        return {**summary, "changed": False}
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=".spec-", suffix=".tmp", dir=path.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(updated)
            handle.flush()
            os.fsync(handle.fileno())
        if _read_spec(path)[0] != content:
            raise ProjectionError("specification changed during transfer; try again")
        os.replace(temporary, path)
        temporary = None
    except OSError as exc:
        raise ProjectionError(f"cannot write specification: {exc}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {**summary, "changed": True}
