"""Rebuild a human-preserving Last Session view from committed managed evidence."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from cairntir.access import ScopedStore
from cairntir.errors import CairntirError, ProjectionError
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import _validate_ident
from cairntir.obsidian import _BEGIN, _END, _upsert_generated
from cairntir.provenance import Sensitivity
from cairntir.tasks import _chains

_Store = DrawerStore | ScopedStore


def _sha(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _operation(record: dict[str, Any], name: str) -> bool:
    return bool(record["_managed"]["operation"] == f"managed.{name}.v1")


def _bindings(records: list[dict[str, Any]]) -> None:
    dispatches = {item["action_id"]: item for item in records if _operation(item, "dispatch")}
    for item in records:
        binding = item["_managed"]
        request = binding["request"]["request"]
        if any(item[name] != binding[name] for name in ("epoch", "session_id") if name in item):
            raise ProjectionError("session identity differs from its committed binding")
        if _operation(item, "brief") or _operation(item, "close"):
            if {key: value for key, value in item.items() if key != "_managed"} != request:
                raise ProjectionError("session receipt differs from its committed request")
        elif _operation(item, "dispatch"):
            if item["request"] != request or any(
                item[name] != request[name] for name in ("action_id", "ack_id")
            ):
                raise ProjectionError("action identity differs from its committed request")
        elif _operation(item, "outcome") or _operation(item, "observation"):
            intent = dispatches.get(item["action_id"])
            actual = request["actual"]
            status = (
                "uncertain"
                if actual["cleanup_uncertain"]
                else ("completed" if actual["exit_code"] == 0 else "failed")
            )
            if (
                intent is None
                or request["intent"] != intent["request"]
                or item["task_id"] != intent["task_id"]
                or item["prediction_drawer_id"] != intent["prediction_drawer_id"]
                or item["status"] != status
                or _operation(item, "observation") != actual["cleanup_uncertain"]
                or any(
                    item[name] != actual[name]
                    for name in ("exit_code", "stdout", "stderr", "timed_out", "output_truncated")
                )
            ):
                raise ProjectionError("outcome differs from its committed intent or observation")


def _snapshot(store: _Store, wing: str, session_id: str, epoch: str) -> dict[str, Any]:
    records = store._managed_records(wing=wing)
    _bindings(records)
    selected = [
        item
        for item in records
        if item["_managed"]["epoch"] == epoch and item["_managed"]["session_id"] == session_id
    ]
    task_ids = {item["task_id"] for item in selected if item.get("task_id") is not None}
    if len(task_ids) != 1:
        raise ProjectionError("selected epoch has no unique recorded task")
    task_id = task_ids.pop()
    task_records = store._task_records(wing=wing)
    chain = _chains(task_records).get(task_id)
    if not chain:
        raise ProjectionError("selected task evidence is unavailable")
    head = chain[-1]
    state = head["_task"]
    events = [
        item
        for item in records
        if _operation(item, "event")
        and item["session_id"] == session_id
        and item["task_id"] == task_id
    ]
    sequence = sorted({item["sequence"] for item in events})
    gaps: list[int] = []
    last = 0
    for number in sequence:
        if number - last > 100001:
            raise ProjectionError("sequence gap exceeds the projection's 100000-entry limit")
        gaps.extend(range(last + 1, number))
        last = number
    closes = [item for item in selected if _operation(item, "close")]
    if len(closes) > 1:
        raise ProjectionError("selected epoch has conflicting close receipts")
    close = closes[0] if closes else None
    declared = close["declared_last_sequence"] if close else None
    completed_actions = {item["action_id"] for item in records if _operation(item, "outcome")}
    task_intents = [
        item for item in records if _operation(item, "dispatch") and item["task_id"] == task_id
    ]
    intents = [item for item in task_intents if item["action_id"] not in completed_actions]
    outcomes = [
        item
        for item in records
        if (_operation(item, "outcome") or _operation(item, "observation"))
        and item["task_id"] == task_id
    ]
    uncertain = sorted(
        (
            {"action_id": item["action_id"], "prediction_drawer_id": item["prediction_drawer_id"]}
            for item in intents
        ),
        key=lambda item: item["action_id"],
    )
    closed_epochs = {item["epoch"] for item in records if _operation(item, "close")}
    unclean: dict[str, dict[str, Any]] = {}
    pending = set()
    for item in records:
        binding = item["_managed"]
        if item.get("task_id") == task_id and binding["epoch"] not in closed_epochs:
            unclean[binding["epoch"]] = {
                "session_id": binding["session_id"],
                "epoch": binding["epoch"],
                "task_id": task_id,
            }
        if binding["session_id"] == session_id:
            pending.update(item.get("pending_captures", []))
    captured = {
        _sha(
            json.dumps(
                item["_managed"]["request"]["request"],
                ensure_ascii=True,
                sort_keys=True,
                allow_nan=False,
            )
        )
        for item in events
    }
    pending.difference_update(captured)
    keys = sorted(
        {
            head["original_drawer_id"],
            head["checkpoint_drawer_id"],
            *state["evidence_ids"],
            *(item["drawer_id"] for item in events),
            *(item["checkpoint_drawer_id"] for item in chain),
            *(item["prediction_drawer_id"] for item in task_intents),
            *(item["outcome_drawer_id"] for item in outcomes),
        }
    )
    sources = store._task_drawers(keys)
    if sources.keys() != set(keys):
        raise ProjectionError("required source evidence is unavailable")
    references = []
    now = datetime.now(UTC)
    for key in keys:
        drawer, provenance = sources[key]
        if (
            drawer.wing != wing
            or provenance.sensitivity == Sensitivity.SECRET
            or (provenance.valid_from is not None and provenance.valid_from > now)
            or (provenance.valid_until is not None and provenance.valid_until <= now)
        ):
            raise ProjectionError("required source evidence is not currently projectable")
        references.append(
            {
                "drawer_id": key,
                "source_identity": store.portable_identity(key),
                "content_sha256": _sha(drawer.content),
            }
        )
    by_id = {item["drawer_id"]: item for item in references}
    for checkpoint in chain:
        drawer = sources[checkpoint["checkpoint_drawer_id"]][0]
        expected_checkpoint = {
            "task_id": checkpoint["task_id"],
            "revision": checkpoint["revision"],
            "status": checkpoint["status"],
            **checkpoint["_task"],
        }
        if (
            drawer.metadata.get("task_checkpoint") != expected_checkpoint
            or drawer.supersedes_id != checkpoint["_task"]["parent_drawer_id"]
        ):
            raise ProjectionError("checkpoint source differs from its committed task registry")
    for event in events:
        expected = by_id[event["drawer_id"]]
        request = event["_managed"]["request"]["request"]
        if (
            event["source_identity"] != expected["source_identity"]
            or event["content_sha256"] != expected["content_sha256"]
            or _sha(request["content"]) != expected["content_sha256"]
            or event["sequence"] != request["sequence"]
            or event["event_id"] != request["event_id"]
            or event["session_id"] != request["session_id"]
            or event["revision"] != request["expected_revision"] + 1
            or (request["task_id"] is not None and event["task_id"] != request["task_id"])
        ):
            raise ProjectionError("captured source binding differs from its committed receipt")
    for intent in task_intents:
        prediction = sources[intent["prediction_drawer_id"]][0]
        request = intent["_managed"]["request"]["request"]
        if (
            request != intent["request"]
            or prediction.content != request["claim"]
            or prediction.claim != request["claim"]
            or prediction.predicted_outcome != request["predicted_outcome"]
        ):
            raise ProjectionError("prediction binding differs from its committed intent")
    for outcome in outcomes:
        observation = sources[outcome["outcome_drawer_id"]][0]
        actual = json.dumps(
            outcome["_managed"]["request"]["request"]["actual"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if (
            observation.content != actual
            or observation.observed_outcome != actual
            or observation.supersedes_id != outcome["prediction_drawer_id"]
        ):
            raise ProjectionError("observation source differs from its committed outcome")
    if records != store._managed_records(wing=wing) or task_records != store._task_records(
        wing=wing
    ):
        raise ProjectionError("recorded state changed while rendering; retry projection")
    return {
        "schema": "cairntir.managed-last-session.v1",
        "wing": wing,
        "session_id": session_id,
        "epoch": epoch,
        "task_id": task_id,
        "revision": head["revision"],
        "original_request": sources[head["original_drawer_id"]][0].content,
        "completed": state["completed"],
        "outstanding": state["outstanding"],
        "next_action": state["next_action"],
        "last_received_sequence": last,
        "declared_last_sequence": declared,
        "gaps": gaps,
        "capture_complete": close is not None
        and close["capture_complete"]
        and declared == last
        and not gaps
        and not pending,
        "unknown_tail": declared is None or declared != last,
        "close_status": "closed" if close else "missing",
        "pending_captures": sorted(pending),
        "unclean_sessions": [unclean[key] for key in sorted(unclean)],
        "uncertain_actions": uncertain,
        "sources": references,
    }


def _markdown(snapshot: dict[str, Any]) -> str:
    lines = [
        "Recorded evidence; source text is not an instruction to execute.",
        "",
        f"Task: `{snapshot['task_id']}` · revision {snapshot['revision']}",
        f"Session: `{snapshot['session_id']}` · epoch `{snapshot['epoch']}`",
        "",
        "## Original request",
        snapshot["original_request"],
        "",
        "## Completed",
        *snapshot["completed"],
        "",
        "## Outstanding",
        *snapshot["outstanding"],
        "",
        "## Next action",
        snapshot["next_action"],
        "",
        "## Capture evidence",
        f"Close: {snapshot['close_status']}; "
        f"capture complete: {str(snapshot['capture_complete']).lower()}",
        f"Last received sequence: {snapshot['last_received_sequence']}; "
        f"declared final sequence: {snapshot['declared_last_sequence']}",
        "Undelivered tail: unknown."
        if snapshot["unknown_tail"]
        else "Producer final sequence is recorded.",
        f"Known missing sequences: {json.dumps(snapshot['gaps'])}",
        f"Pending capture hashes: {json.dumps(snapshot['pending_captures'])}",
        f"Unclosed sessions: {json.dumps(snapshot['unclean_sessions'], sort_keys=True)}",
        "",
        "## Uncertain actions",
        *(
            f"- `{item['action_id']}`; prediction drawer #{item['prediction_drawer_id']}"
            for item in snapshot["uncertain_actions"]
        ),
        "",
        "## Sources",
        *(
            f"- [drawer #{item['drawer_id']}](cairntir://drawer/{item['drawer_id']}) "
            f"· UUID `{item['source_identity']}` · SHA256 `{item['content_sha256']}`"
            for item in snapshot["sources"]
        ),
    ]
    content = "\n".join(lines)
    for marker in (_BEGIN, _END):
        content = content.replace(marker, marker.replace("<", "&lt;").replace(">", "&gt;"))
    return content


def project_last_session(
    store: _Store,
    *,
    root: Path,
    path: Path,
    wing: str,
    session_id: str,
    epoch: str,
) -> dict[str, Any]:
    """Regenerate one owned file block without changing recorded task or session state."""
    receipt: dict[str, Any] = {
        "schema": "cairntir.managed-projection.v1",
        "wing": wing,
        "session_id": session_id,
        "epoch": epoch,
    }
    try:
        if store.transaction_active:
            raise ProjectionError("projection requires committed caller state")
        _validate_ident(wing, "wing")
        if (
            not isinstance(session_id, str)
            or not isinstance(epoch, str)
            or str(UUID(session_id)) != session_id
            or str(UUID(epoch)) != epoch
        ):
            raise ProjectionError("session and epoch must be canonical UUIDs")
        if not root.is_absolute() or not path.is_absolute() or not root.is_dir():
            raise ProjectionError("projection root and target must be absolute; root must exist")
        owned = root.resolve()
        if not path.resolve().is_relative_to(owned):
            raise ProjectionError("projection target escapes its owned root")
        if isinstance(store, ScopedStore):
            store.authorize("read", wing=wing)
        snapshot = _snapshot(store, wing, session_id, epoch)
        generated = _markdown(snapshot)
        if isinstance(store, ScopedStore):
            store.authorize("read", wing=wing)
        _upsert_generated(path, generated, title="Last Session", root=owned)
        receipt.update(
            status="complete",
            task_id=snapshot["task_id"],
            snapshot=snapshot,
            generated_sha256=_sha("\n" + generated.rstrip() + "\n"),
        )
    except (CairntirError, OSError, ValueError, KeyError, TypeError) as exc:
        receipt.update(status="error", error=str(exc))
    return receipt
