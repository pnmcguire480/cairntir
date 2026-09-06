"""Pure, task-aware selection of whole memory evidence under a transport budget."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from mcp import types

from cairntir.errors import AnchorError, RetrievalError
from cairntir.memory.anchors import parse_anchors, paths_intersect
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.prompt_safety import assess_memory_content
from cairntir.provenance import Sensitivity, WriteProvenance

_MIN_COSINE = 0.75
_Record = tuple[Drawer, WriteProvenance]


def _identifier(record: _Record) -> int:
    if record[0].id is None:
        raise RetrievalError("task candidate is missing its persisted drawer id")
    return record[0].id


def _exclusions(record: _Record, now: datetime) -> list[str]:
    drawer, receipt = record
    reasons = []
    if receipt.valid_until is not None and _utc(receipt.valid_until) <= now:
        reasons.append("expired")
    if receipt.valid_from is not None and _utc(receipt.valid_from) > now:
        reasons.append("future_valid")
    if receipt.sensitivity is Sensitivity.SECRET:
        reasons.append("secret")
    if assess_memory_content(drawer.content).suspicious:
        reasons.append("suspicious")
    try:
        parse_anchors(drawer.metadata)
    except AnchorError:
        reasons.append("malformed_anchor")
    return reasons


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _match(drawer: Drawer, task: str, files: Sequence[str], similarity: float) -> list[str]:
    reasons = []
    query = task.strip().casefold()
    words = set(re.findall(r"\w+", query))
    content = drawer.content.casefold()
    if re.search(r"(?<!\w)" + re.escape(query) + r"(?!\w)", content) or (
        words and words <= set(re.findall(r"\w+", content))
    ):
        reasons.append("exact")
    if similarity >= _MIN_COSINE:
        reasons.append("semantic")
    if files and any(
        paths_intersect(anchor.path, path)
        for anchor in parse_anchors(drawer.metadata)
        for path in files
    ):
        reasons.append("anchor")
    return reasons


def _render(payload: dict[str, Any]) -> str:
    budget = payload["budget"]
    while True:
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        size = len(raw)
        if budget["rendered_chars"] == size and budget["estimated_tokens"] == size // 4:
            return raw
        budget.update(rendered_chars=size, estimated_tokens=size // 4)


def _fits(payload: dict[str, Any], limit: int) -> bool:
    raw = _render(payload)
    envelope = types.CallToolResult(
        content=[types.TextContent(type="text", text=raw)], isError=False
    )
    return max(len(raw) + 1, len(envelope.model_dump_json())) <= limit


def _families(records: dict[int, _Record]) -> list[set[int]]:
    adjacency: dict[int, set[int]] = {key: set() for key in records}
    for key, (drawer, _) in records.items():
        parent = drawer.supersedes_id
        if parent in records:
            adjacency[key].add(parent)
            adjacency[parent].add(key)
    remaining = set(records)
    groups = []
    while remaining:
        pending = [min(remaining)]
        group: set[int] = set()
        while pending:
            key = pending.pop()
            if key not in group:
                group.add(key)
                pending.extend(adjacency[key] - group)
        remaining -= group
        groups.append(group)
    return groups


def _superseded(records: dict[int, _Record], current: set[int]) -> set[int]:
    replaced: set[int] = set()
    for key in current:
        seen = {key}
        parent = records[key][0].supersedes_id
        while parent in records:
            if parent in seen:
                raise RetrievalError("task candidate supersession relationships contain a cycle")
            seen.add(parent)
            if parent in current:
                replaced.add(parent)
            parent = records[parent][0].supersedes_id
    return replaced


def compose_task_context(
    store: DrawerStore,
    *,
    wing: str,
    task: str,
    budget_chars: int,
    files: Sequence[str] | None = None,
    candidate_limit: int | None = None,
) -> str:
    """Select original evidence, recording abstention, exclusions, conflicts and scan bounds.

    The character ceiling includes CLI's newline and the serialized MCP tool
    result. Token figures are estimates. No memory state is updated.
    """
    if type(budget_chars) is not int or budget_chars <= 0:
        raise RetrievalError("task budget_chars must be a positive integer")
    if not isinstance(task, str) or not task.strip():
        raise RetrievalError("task must be a non-empty string")
    if not isinstance(wing, str) or not wing.strip():
        raise RetrievalError("task wing must be a non-empty string")
    if candidate_limit is not None and (type(candidate_limit) is not int or candidate_limit <= 0):
        raise RetrievalError("task candidate_limit must be a positive integer")
    if files is not None and (
        isinstance(files, str)
        or not isinstance(files, Sequence)
        or any(not isinstance(path, str) or not path.strip() for path in files)
    ):
        raise RetrievalError("task files must be a sequence of non-empty paths")
    payload: dict[str, Any] = {
        "wing": wing,
        "task": task,
        "status": "abstained",
        "evidence": [],
        "excluded": [],
        "omitted": [],
        "omitted_count": 0,
        "conflicts": [],
        "scan": {"limit": candidate_limit, "scanned": 0, "complete": True},
        "budget": {
            "limit_chars": budget_chars,
            "rendered_chars": 0,
            "estimated_tokens": 0,
            "token_basis": "estimate: rendered characters divided by four; not billed tokens",
        },
        "abstention_reason": "no_matching_evidence",
    }
    if not _fits(payload, budget_chars):
        raise RetrievalError("task budget is too small for the request and response envelope")

    candidates, total = store.context_candidates(wing=wing, limit=candidate_limit)
    payload["scan"].update(scanned=len(candidates), complete=len(candidates) == total)
    now = datetime.now(UTC)
    excluded = {_identifier(record): _exclusions(record, now) for record in candidates}
    eligible = [record for record in candidates if not excluded[_identifier(record)]]
    scores = store.context_similarities(task, [_identifier(record) for record in eligible])
    matched: dict[int, list[str]] = {}
    for drawer, receipt in eligible:
        key = _identifier((drawer, receipt))
        try:
            reasons = _match(drawer, task, files or (), scores[key])
        except AnchorError:
            excluded[key] = ["malformed_anchor"]
            continue
        if reasons:
            matched[key] = reasons

    records = {
        _identifier(record): record
        for record in store.context_relatives(wing=wing, drawer_ids=sorted(matched))
    }
    for key, record in records.items():
        excluded[key] = _exclusions(record, now)
    current = {
        key for key in records if not {"expired", "future_valid"}.intersection(excluded[key])
    }
    replaced = _superseded(records, current)
    for key in replaced:
        excluded[key].append("superseded")

    groups = []
    for family in _families(records):
        leaves = sorted((family & current) - replaced)
        if any(not excluded[key] for key in leaves) and family & matched.keys():
            groups.append(leaves)
    groups.sort(
        key=lambda group: (
            -max(len(matched.get(key, ())) for key in group),
            -max(scores.get(key, 0.0) for key in group),
            -max(group),
        )
    )

    payload["omitted_count"] = sum(not excluded[key] for group in groups for key in group)
    if groups:
        payload["abstention_reason"] = "budget_exhausted"
    if not _fits(payload, budget_chars):
        raise RetrievalError("task budget is too small for the selection receipts")
    omitted = []
    deferred_conflicts = []
    for group in groups:
        available = [key for key in group if not excluded[key]]
        entries = [
            {
                "drawer_id": key,
                "resource": f"cairntir://drawer/{key}",
                "content": records[key][0].content,
                "provenance": records[key][1].to_dict(),
                "instruction_authority": "none",
                "reasons": matched.get(key, ["successor"]),
            }
            for key in available
        ]
        conflict = {"drawer_ids": group, "status": "unresolved"} if len(group) > 1 else None
        payload["evidence"].extend(entries)
        if conflict:
            payload["conflicts"].append(conflict)
        payload["status"] = "selected"
        payload.pop("abstention_reason", None)
        payload["omitted_count"] -= len(available)
        if _fits(payload, budget_chars):
            continue
        del payload["evidence"][-len(entries) :]
        payload["omitted_count"] += len(available)
        omitted.extend(available)
        if conflict:
            payload["conflicts"].pop()
            deferred_conflicts.append(conflict)
        if not payload["evidence"]:
            payload["status"] = "abstained"
            payload["abstention_reason"] = "budget_exhausted"

    for conflict in deferred_conflicts:
        payload["conflicts"].append(conflict)
        if not _fits(payload, budget_chars):
            payload["conflicts"].pop()
    for field, receipts in (
        ("excluded", [(key, reasons) for key, reasons in sorted(excluded.items()) if reasons]),
        ("omitted", [(key, ["budget"]) for key in omitted]),
    ):
        for key, reasons in receipts:
            payload[field].append({"drawer_id": key, "reasons": reasons})
            if not _fits(payload, budget_chars):
                payload[field].pop()
    return _render(payload)
