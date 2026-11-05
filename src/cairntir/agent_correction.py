"""Explicit, append-only corrections made through an agent-facing tool."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from cairntir.access import ScopedStore
from cairntir.errors import CairntirError
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer, _validate_ident
from cairntir.obsidian_bridge import CorrectionError
from cairntir.provenance import Sensitivity, TrustLevel, WriteProvenance

_OPERATION = "cairntir.agent-correction.v1"


def _digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _canonical_uuid(value: str, field: str) -> str:
    if not isinstance(value, str):
        raise CorrectionError(f"{field} must be a canonical UUID")
    try:
        parsed = UUID(value)
    except ValueError as exc:
        raise CorrectionError(f"{field} must be a canonical UUID") from exc
    if str(parsed) != value:
        raise CorrectionError(f"{field} must be a canonical UUID")
    return value


def _editable(drawer: Drawer) -> bool:
    return not (
        "task_checkpoint" in drawer.metadata
        or drawer.metadata.get("kind")
        or any(
            value is not None
            for value in (
                drawer.claim,
                drawer.predicted_outcome,
                drawer.observed_outcome,
                drawer.delta,
            )
        )
    )


def correct_agent(
    store: DrawerStore | ScopedStore,
    *,
    wing: str,
    source_drawer_id: int,
    source_identity: str,
    source_sha256: str,
    content: str,
    idempotency_key: str,
    model: str | None = None,
) -> dict[str, Any]:
    """Bind a correction to one exact source and atomically append its successor."""
    if store.transaction_active:
        raise CorrectionError("correction cannot run inside a caller transaction")
    try:
        _validate_ident(wing, "wing")
        content.encode("utf-8")
    except (ValueError, CairntirError, UnicodeError) as exc:
        raise CorrectionError(str(exc)) from exc
    if type(source_drawer_id) is not int or not 0 < source_drawer_id <= 2**63 - 1:
        raise CorrectionError("source_drawer_id must be a positive signed 64-bit integer")
    _canonical_uuid(source_identity, "source_identity")
    _canonical_uuid(idempotency_key, "idempotency_key")
    if not isinstance(source_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
        raise CorrectionError("source_sha256 must be a lowercase SHA256 digest")
    if not isinstance(content, str) or not content.strip():
        raise CorrectionError("content must be nonempty text")
    if model is not None and (not isinstance(model, str) or not model.strip()):
        raise CorrectionError("model must be nonempty text")

    request = {
        "wing": wing,
        "source_drawer_id": source_drawer_id,
        "source_identity": source_identity,
        "source_sha256": source_sha256,
        "content": content,
        "model": model,
    }
    slot = hashlib.sha256(
        json.dumps([wing, source_identity, idempotency_key], separators=(",", ":")).encode()
    ).hexdigest()
    try:
        with store.transaction():
            if isinstance(store, ScopedStore):
                store.authorize("read", drawer_id=source_drawer_id)
                store.authorize("write", drawer_id=source_drawer_id)
            family = store.context_relatives(wing=wing, drawer_ids=[source_drawer_id])
            sources = [
                (drawer, provenance)
                for drawer, provenance in family
                if drawer.id == source_drawer_id
            ]
            if not sources:
                raise CorrectionError("source is unavailable in the selected wing")
            source, provenance = sources[0]
            if (
                store.portable_identity(source_drawer_id) != source_identity
                or _digest(source.content) != source_sha256
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
                if any(drawer.supersedes_id == source_drawer_id for drawer, _ in family) or (
                    isinstance(store, ScopedStore) and store.has_direct_successor(source_drawer_id)
                ):
                    raise CorrectionError("stale source: refresh and correct its current successor")
                saved = store.add(
                    Drawer(
                        wing=source.wing,
                        room=source.room,
                        layer=source.layer,
                        content=content,
                        metadata={
                            **source.metadata,
                            "agent_correction": {
                                "source_identity": source_identity,
                                "source_sha256": source_sha256,
                            },
                        },
                        supersedes_id=source_drawer_id,
                    ),
                    provenance=WriteProvenance.create(
                        host="mcp",
                        capture_path="mcp.correct",
                        trust=TrustLevel.AGENT_GENERATED,
                        visibility=provenance.visibility,
                        sensitivity=provenance.sensitivity,
                        valid_from=provenance.valid_from,
                        valid_until=provenance.valid_until,
                    ),
                    model=model,
                )
                return {
                    "schema": "cairntir.agent-correction-receipt.v1",
                    "status": "committed",
                    "source_drawer_id": source_drawer_id,
                    "source_identity": source_identity,
                    "correction_drawer_id": saved.id,
                    "content_sha256": _digest(content),
                }

            execution = store.execute_once(
                idempotency_key=f"agent-correction:{slot}",
                operation=_OPERATION,
                request=request,
                action=append,
            )
            return {**execution.result, "replayed": execution.replayed}
    except CairntirError as exc:
        if isinstance(exc, CorrectionError):
            raise
        raise CorrectionError(str(exc)) from exc
