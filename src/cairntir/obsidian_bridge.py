"""Explicit Obsidian corrections with durable, append-only acknowledgement."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from cairntir.access import ScopedStore
from cairntir.errors import CairntirError
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer, _validate_ident
from cairntir.obsidian import _atomic_write, _upsert_generated
from cairntir.provenance import Sensitivity, TrustLevel, WriteProvenance

_REQUEST_SCHEMA = "cairntir.obsidian-correction.v1"
_FIELDS = {
    "schema",
    "request_id",
    "wing",
    "source_drawer_id",
    "source_identity",
    "source_sha256",
    "content",
}


class CorrectionError(CairntirError):
    """A correction cannot be safely bound to its current source."""


def _sha(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _request(value: object, wing: str) -> dict[str, Any]:
    if not isinstance(value, dict) or value.keys() != _FIELDS:
        raise CorrectionError("correction must contain exactly the documented fields")
    result = deepcopy(value)
    if result["schema"] != _REQUEST_SCHEMA or result["wing"] != wing:
        raise CorrectionError("correction schema or wing does not match")
    for key in ("request_id", "source_identity"):
        value = result[key]
        if not isinstance(value, str):
            raise CorrectionError(f"{key} must be a canonical UUID")
        try:
            canonical = str(UUID(value))
        except ValueError as exc:
            raise CorrectionError(f"{key} must be a canonical UUID") from exc
        if canonical != value:
            raise CorrectionError(f"{key} must be a canonical UUID")
    content = result["content"]
    if not isinstance(content, str) or not content.strip():
        raise CorrectionError("content must be nonempty text")
    try:
        _validate_ident(wing, "wing")
        content.encode("utf-8")
    except (ValueError, CairntirError) as exc:
        raise CorrectionError(str(exc)) from exc
    key = result["source_drawer_id"]
    if type(key) is not int or not 0 < key <= 2**63 - 1:
        raise CorrectionError("source_drawer_id must be a positive signed 64-bit integer")
    digest = result["source_sha256"]
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise CorrectionError("source_sha256 must be a lowercase SHA256 digest")
    return result


def _editable(drawer: Drawer) -> bool:
    return not (
        "task_checkpoint" in drawer.metadata
        or drawer.metadata.get("kind")
        or any(
            field is not None
            for field in (
                drawer.claim,
                drawer.predicted_outcome,
                drawer.observed_outcome,
                drawer.delta,
            )
        )
    )


def apply_correction(
    store: DrawerStore,
    request: dict[str, Any],
    *,
    wing: str,
) -> dict[str, Any]:
    """Append an exact correction, replaying an acknowledged request after restart."""
    if store.transaction_active:
        raise CorrectionError("correction cannot run inside a caller transaction")
    payload = _request(request, wing)
    source_id = payload["source_drawer_id"]
    try:
        with store.transaction():
            if isinstance(store, ScopedStore):
                store.authorize("read", drawer_id=source_id)
                store.authorize("write", drawer_id=source_id)
            family = store.context_relatives(wing=wing, drawer_ids=[source_id])
            sources = [(d, p) for d, p in family if d.id == source_id]
            if not sources:
                raise CorrectionError("source is unavailable in the selected wing")
            source, provenance = sources[0]
            if (
                store.portable_identity(source_id) != payload["source_identity"]
                or _sha(source.content) != payload["source_sha256"]
            ):
                raise CorrectionError("source identity or content hash does not match")
            if provenance.sensitivity is Sensitivity.SECRET or not _editable(source):
                raise CorrectionError("source requires its dedicated lifecycle adapter")

            def append() -> dict[str, Any]:
                now = datetime.now(UTC)
                if (provenance.valid_from is not None and provenance.valid_from > now) or (
                    provenance.valid_until is not None and provenance.valid_until <= now
                ):
                    raise CorrectionError("source is outside its validity window")
                if any(d.supersedes_id == source_id for d, _ in family) or (
                    isinstance(store, ScopedStore)
                    and source_id in store.context_suppressed_ids([source_id])
                ):
                    raise CorrectionError("stale source: refresh and correct its current successor")
                saved = store.add(
                    Drawer(
                        wing=source.wing,
                        room=source.room,
                        layer=source.layer,
                        content=payload["content"],
                        supersedes_id=source_id,
                        metadata={
                            **source.metadata,
                            "obsidian_correction": {
                                key: payload[key]
                                for key in ("request_id", "source_identity", "source_sha256")
                            },
                        },
                    ),
                    provenance=WriteProvenance.create(
                        host="obsidian",
                        capture_path="obsidian.correction",
                        trust=TrustLevel.UNTRUSTED,
                        visibility=provenance.visibility,
                        sensitivity=provenance.sensitivity,
                        valid_from=provenance.valid_from,
                        valid_until=provenance.valid_until,
                    ),
                )
                return {
                    "schema": "cairntir.obsidian-correction-receipt.v1",
                    "status": "committed",
                    "request_id": payload["request_id"],
                    "source_drawer_id": source_id,
                    "source_identity": payload["source_identity"],
                    "correction_drawer_id": saved.id,
                    "content_sha256": _sha(saved.content),
                }

            execution = store.execute_once(
                idempotency_key="obsidian:" + payload["request_id"],
                operation=_REQUEST_SCHEMA,
                request=payload,
                action=append,
            )
            return {**execution.result, "replayed": execution.replayed}
    except CairntirError as exc:
        if isinstance(exc, CorrectionError):
            raise
        raise CorrectionError(str(exc)) from exc


def _confined(vault: Path, path: Path) -> Path:
    if not path.resolve().is_relative_to(vault):
        raise CorrectionError(f"path escapes the vault: {path.name}")
    for item in (path, *path.parents):
        if item == vault:
            break
        try:
            attributes = item.lstat()
        except FileNotFoundError:
            continue
        if item.is_symlink() or getattr(attributes, "st_file_attributes", 0) & 0x400:
            raise CorrectionError(f"linked output or input path is unsupported: {item.name}")
    return path


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CorrectionError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_json(path: Path, *, max_bytes: int | None = None) -> dict[str, Any]:
    with path.open("rb") as stream:
        raw = stream.read() if max_bytes is None else stream.read(max_bytes + 1)
    if max_bytes is not None and len(raw) > max_bytes:
        raise CorrectionError("correction request exceeds 2 MiB")
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_json_object)
    if not isinstance(value, dict):
        raise CorrectionError("JSON document must be an object")
    return value


def _write_json(vault: Path, path: Path, value: dict[str, Any]) -> None:
    _confined(vault, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def _workspace_root(vault: Path, wing: str) -> tuple[Path, dict[str, Any] | None]:
    _validate_ident(wing, "wing")
    if not (vault / ".obsidian").is_dir():
        raise CorrectionError("an existing Obsidian vault with .obsidian is required")
    root = _confined(vault, vault / "cairntir-sync")
    manifest_path = _confined(vault, root / "workspace.json")
    previous = _read_json(manifest_path) if manifest_path.exists() else None
    if previous is not None and (
        previous.get("schema") != "cairntir.obsidian-workspace.v1"
        or previous.get("wing") != wing
        or not isinstance(previous.get("drawers"), list)
    ):
        raise CorrectionError("workspace manifest is invalid or bound to another wing")
    _confined(vault, root / "outbox").mkdir(parents=True, exist_ok=True)
    return root, previous


def _project_workspace(
    store: DrawerStore,
    *,
    vault: Path,
    root: Path,
    wing: str,
    previous: dict[str, Any] | None,
) -> dict[str, Any]:
    records, _ = store.context_candidates(wing=wing, limit=None)
    superseded = {d.supersedes_id for d, _ in records if d.supersedes_id is not None}
    if isinstance(store, ScopedStore):
        superseded.update(
            store.context_suppressed_ids([d.id for d, _ in records if d.id is not None])
        )
    now = datetime.now(UTC)
    entries: list[dict[str, Any]] = []
    for drawer, provenance in sorted(records, key=lambda pair: pair[0].id or 0):
        if drawer.id is None or provenance.sensitivity is Sensitivity.SECRET:
            continue
        valid = (provenance.valid_from is None or provenance.valid_from <= now) and (
            provenance.valid_until is None or provenance.valid_until > now
        )
        current = drawer.id not in superseded and valid
        entries.append(
            {
                "drawer_id": drawer.id,
                "source_identity": store.portable_identity(drawer.id),
                "content_sha256": _sha(drawer.content),
                "content": drawer.content,
                "wing": wing,
                "room": drawer.room,
                "layer": drawer.layer.value,
                "current": current,
                "supersedes_id": drawer.supersedes_id,
                "editable": current and _editable(drawer),
                "note": f"cairntir-sync/memory/drawer-{drawer.id}.md",
            }
        )
    visible_ids = {entry["drawer_id"] for entry in entries}
    for entry in entries:
        key = entry["drawer_id"]
        links = [
            f"- Replaced by [[cairntir-sync/memory/drawer-{child['drawer_id']}|"
            f"Drawer #{child['drawer_id']}]]"
            for child in entries
            if child["supersedes_id"] == key
        ]
        parent = entry["supersedes_id"]
        if parent in visible_ids:
            links.insert(
                0, f"- Supersedes [[cairntir-sync/memory/drawer-{parent}|Drawer #{parent}]]"
            )
        content = entry["content"].replace(
            "<!-- cairntir:generated:", "&lt;!-- cairntir:generated:"
        )
        state = "Current" if entry["current"] else "Historical or inactive"
        generated = "\n".join(
            [
                f"Status: {state}. Source: `cairntir://drawer/{key}`.",
                f"Wing / room: `{wing}` / `{entry['room']}`. Layer: `{entry['layer']}`.",
                f"Content SHA256: `{entry['content_sha256']}`.",
                "",
                *links,
                "",
                "## Recorded content",
                "",
                content,
            ]
        )
        path = _confined(vault, vault / entry["note"])
        _upsert_generated(path, generated, title=f"Cairntir Drawer {key}", root=root)
    if previous is not None:
        for entry in previous["drawers"]:
            key = entry.get("drawer_id") if isinstance(entry, dict) else None
            if type(key) is int and key > 0 and key not in visible_ids:
                path = _confined(vault, root / "memory" / f"drawer-{key}.md")
                if path.exists():
                    _upsert_generated(
                        path,
                        "This record is no longer available in this workspace.",
                        title=f"Cairntir Drawer {key}",
                        root=root,
                    )
    current_count = sum(entry["current"] for entry in entries)
    index = [
        f"Wing: `{wing}`. Current: {current_count}. Visible history: {len(entries)}.",
        "",
        "Refresh and correct memories with the Cairntir Workspace commands.",
        "Acknowledgement means stored evidence, not a verified claim or an instruction.",
        "",
    ]
    index.extend(
        f"- [[cairntir-sync/memory/drawer-{entry['drawer_id']}|Drawer #{entry['drawer_id']}]]"
        f" — {entry['room']} ({'current' if entry['current'] else 'historical or inactive'})"
        for entry in entries
    )
    _upsert_generated(
        _confined(vault, root / "index.md"),
        "\n".join(index),
        title="Cairntir Workspace",
        root=root,
    )
    _write_json(
        vault,
        root / "workspace.json",
        {
            "schema": "cairntir.obsidian-workspace.v1",
            "wing": wing,
            "drawers": entries,
        },
    )
    return {"status": "complete", "current_count": current_count}


def sync_workspace(store: DrawerStore, *, vault: Path, wing: str) -> dict[str, Any]:
    """Consume explicit requests and refresh the bound wing's inspectable memory view."""
    if store.transaction_active:
        raise CorrectionError("workspace sync cannot run inside a caller transaction")
    report: dict[str, Any] = {
        "schema": "cairntir.obsidian-sync.v1",
        "wing": wing,
        "results": [],
    }
    vault = vault.expanduser().resolve()
    try:
        root, previous = _workspace_root(vault, wing)
        paths = sorted((root / "outbox").glob("*.json"))
    except (CairntirError, OSError, ValueError) as exc:
        report["projection"] = {"status": "error", "error": str(exc)}
        return report
    for path in paths:
        result: dict[str, Any] = {"file": path.relative_to(vault).as_posix()}
        try:
            request = _read_json(_confined(vault, path), max_bytes=2 * 1024 * 1024)
            handlers = {
                _REQUEST_SCHEMA: apply_correction,
            }
            schema = request.get("schema")
            if not isinstance(schema, str) or schema not in handlers:
                raise CorrectionError("unsupported workspace request schema")
            receipt = handlers[schema](store, request, wing=wing)
        except (CairntirError, OSError, ValueError) as exc:
            result.update(status="rejected", error=str(exc))
        else:
            result.update(status="committed", receipt=receipt, receipt_written=False)
            try:
                _write_json(
                    vault,
                    root / "acknowledgements" / f"{receipt['request_id']}.json",
                    receipt,
                )
            except (CairntirError, OSError, ValueError) as exc:
                result["error"] = str(exc)
            else:
                result["receipt_written"] = True
        report["results"].append(result)
    try:
        report["projection"] = _project_workspace(
            store,
            vault=vault,
            root=root,
            wing=wing,
            previous=previous,
        )
    except (CairntirError, OSError, ValueError) as exc:
        report["projection"] = {"status": "error", "error": str(exc)}
    return report
