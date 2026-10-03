"""Whole-evidence recall bounded by its serialized MCP result envelope."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from mcp import types

from cairntir.errors import MCPError
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.prompt_safety import assess_memory_content


def _render(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _fits(payload: dict[str, Any], budget: int) -> bool:
    result = types.CallToolResult(
        content=[types.TextContent(type="text", text=_render(payload))],
        isError=False,
    )
    return len(result.model_dump_json()) <= budget


def _entry(store: DrawerStore, drawer: Drawer) -> dict[str, Any]:
    if drawer.id is None:
        raise MCPError("recall returned an unpersisted drawer")
    provenance = store.get_provenance(drawer.id)
    if provenance is None:
        raise MCPError(f"drawer {drawer.id} has no provenance")
    assessment = assess_memory_content(drawer.content)
    return {
        "drawer_id": drawer.id,
        "resource": f"cairntir://drawer/{drawer.id}",
        "wing": drawer.wing,
        "room": drawer.room,
        "layer": drawer.layer.value,
        "content": drawer.content,
        "content_sha256": hashlib.sha256(drawer.content.encode("utf-8")).hexdigest(),
        "supersedes_id": drawer.supersedes_id,
        "provenance": provenance.to_dict(),
        "instruction_authority": "none",
        "suspicious": assessment.suspicious,
        "security_signals": list(assessment.signals),
    }


def recall_bounded(
    store: DrawerStore,
    *,
    query: str,
    wing: str | None = None,
    room: str | None = None,
    limit: int = 10,
    full_content: int = 0,
    budget_chars: int,
) -> str:
    """Return complete records or explicit omissions within the full MCP envelope budget."""
    if type(budget_chars) is not int or not 1024 <= budget_chars <= 262144:
        raise MCPError("budget_chars must be an integer from 1024 through 262144")
    if not isinstance(query, str) or not query.strip():
        raise MCPError("recall requires a non-empty query")
    if type(limit) is not int or limit < 1:
        raise MCPError("limit must be a positive integer")
    if type(full_content) is not int or full_content < 0:
        raise MCPError("full_content must be a nonnegative integer")
    hits = store.search(query, wing=wing, room=room, limit=limit)
    evidence: list[dict[str, Any]] = []
    omitted: dict[str, Any] = {"count": len(hits), "drawer_ids": [], "ids_complete": not hits}
    payload: dict[str, Any] = {
        "schema": "cairntir.recall-budget.v1",
        "status": "omitted" if hits else "complete",
        "instruction_authority": "none",
        "notification_policy": "excluded",
        "budget": {"limit_chars": budget_chars},
        "evidence": evidence,
        "omitted": omitted,
    }

    def update_status() -> None:
        omitted["count"] = len(hits) - len(evidence)
        omitted["ids_complete"] = len(omitted["drawer_ids"]) == omitted["count"]
        payload["status"] = (
            "complete" if not omitted["count"] else "partial" if evidence else "omitted"
        )

    for drawer, _ in hits[:full_content]:
        evidence.append(_entry(store, drawer))
        update_status()
        if not _fits(payload, budget_chars):
            evidence.pop()
            update_status()
    included = {entry["drawer_id"] for entry in evidence}
    for drawer, _ in hits:
        if drawer.id is None:
            raise MCPError("recall returned an unpersisted drawer")
        if drawer.id in included:
            continue
        omitted["drawer_ids"].append(drawer.id)
        update_status()
        if not _fits(payload, budget_chars):
            omitted["drawer_ids"].pop()
            update_status()
            break
    if not _fits(payload, budget_chars):
        raise MCPError("recall result envelope could not satisfy its declared budget")
    return _render(payload)
