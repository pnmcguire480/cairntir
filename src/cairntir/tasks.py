"""Durable, versioned task checkpoints with explicit, read-only resumption."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any
from uuid import uuid4

from mcp import types

from cairntir.access import ScopedStore
from cairntir.errors import WorkflowError
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer, _validate_ident

_OPERATION = "task.checkpoint.v1"
_WRITE_SCHEMA = "cairntir.task-checkpoint.v1"
_FIELDS = {
    "expected_revision",
    "idempotency_key",
    "status",
    "completed",
    "outstanding",
    "next_action",
    "evidence_ids",
}
_RECEIPT_FIELDS = (
    "schema",
    "task_id",
    "revision",
    "status",
    "original_drawer_id",
    "checkpoint_drawer_id",
)


class TaskError(WorkflowError):
    """A checkpoint or resume request cannot satisfy the durable task contract."""


def _text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise TaskError(f"{name} must be a nonempty string")


def _checkpoint(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or not value.keys() >= _FIELDS:
        raise TaskError("checkpoint must contain every required field")
    if value.keys() - (_FIELDS | {"task_id"}):
        raise TaskError("checkpoint contains unsupported fields")
    result = deepcopy(value)
    revision = result["expected_revision"]
    if type(revision) is not int or revision < 0:
        raise TaskError("expected_revision must be a nonnegative integer")
    _text(result["idempotency_key"], "idempotency_key")
    if "task_id" in result:
        _text(result["task_id"], "task_id")
    if (revision == 0) != ("task_id" not in result):
        raise TaskError("creation requires revision zero and no task_id")
    for name in ("completed", "outstanding"):
        items = result[name]
        if not isinstance(items, list):
            raise TaskError(f"{name} must be a list of nonempty strings")
        for item in items:
            _text(item, name)
    evidence = result["evidence_ids"]
    if (
        not isinstance(evidence, list)
        or any(type(key) is not int or key <= 0 for key in evidence)
        or len(set(evidence)) != len(evidence)
    ):
        raise TaskError("evidence_ids must be unique positive integers")
    status = result["status"]
    if not isinstance(status, str) or status not in {"active", "completed", "cancelled"}:
        raise TaskError("status must be active, completed, or cancelled")
    if status == "active":
        _text(result["next_action"], "next_action")
    elif result["outstanding"] or result["next_action"] != "":
        raise TaskError("terminal checkpoints require empty outstanding and next_action")
    if revision == 0 and status != "active":
        raise TaskError("a new task must be active")
    return result


def _chains(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    chains: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        chains.setdefault(record["task_id"], []).append(record)
    for chain in chains.values():
        chain.sort(key=lambda item: item["revision"])
        original = chain[0]
        parent = None
        for revision, record in enumerate(chain, 1):
            state = record["_task"]
            if (
                record["revision"] != revision
                or record["original_drawer_id"] != original["checkpoint_drawer_id"]
                or state["parent_drawer_id"] != parent
                or state["wing"] != original["_task"]["wing"]
                or state["room"] != original["_task"]["room"]
                or (revision < len(chain) and record["status"] != "active")
            ):
                raise TaskError("task registry contains an incomplete or conflicting chain")
            parent = record["checkpoint_drawer_id"]
    return chains


def _render(payload: dict[str, Any]) -> str:
    while True:
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if payload["budget"]["rendered_chars"] == len(raw):
            return raw
        payload["budget"]["rendered_chars"] = len(raw)


def _required(raw: str) -> int:
    envelope = types.CallToolResult(
        content=[types.TextContent(type="text", text=raw)], isError=False
    )
    return max(len(raw) + 1, len(envelope.model_dump_json()))


class TaskBook:
    """Append complete checkpoints and resume locally registered tasks."""

    def __init__(self, store: DrawerStore) -> None:
        """Use the supplied store and its existing scope and durability boundaries."""
        self._store = store

    def _authorize(self, capability: str, *, wing: str, room: str) -> None:
        if isinstance(self._store, ScopedStore):
            self._store.authorize(capability, wing=wing, room=room)

    def _evidence(self, ids: list[int]) -> None:
        if self._store._task_drawers(ids).keys() != set(ids):
            raise TaskError("task evidence is unavailable")

    def checkpoint(
        self,
        wing: str,
        room: str,
        content: str,
        checkpoint: dict[str, Any],
        model: str | None = None,
    ) -> str:
        """Atomically append a complete task state, or replay its committed receipt."""
        _validate_ident(wing, "wing")
        _validate_ident(room, "room")
        _text(content, "content")
        if model is not None:
            _text(model, "model")
        state = _checkpoint(checkpoint)
        request = {
            "wing": wing,
            "room": room,
            "content": content,
            "checkpoint": state,
            "model": model,
        }
        key = "task:" + hashlib.sha256(state["idempotency_key"].encode("utf-8")).hexdigest()

        def append() -> dict[str, Any]:
            chains = _chains(self._store._task_records(wing=wing))
            task_id = state.get("task_id")
            head = None
            if task_id is not None:
                chain = chains.get(task_id)
                if chain is None or chain[0]["_task"]["room"] != room:
                    raise TaskError("task is unavailable")
                head = chain[-1]
                if head["revision"] != state["expected_revision"]:
                    raise TaskError("task revision conflict: checkpoint is stale")
                if head["status"] != "active":
                    raise TaskError("terminal tasks cannot receive another checkpoint")
            else:
                task_id = str(uuid4())
            revision = state["expected_revision"] + 1
            parent = head["checkpoint_drawer_id"] if head is not None else None
            payload = {
                "wing": wing,
                "room": room,
                "parent_drawer_id": parent,
                **{
                    name: state[name]
                    for name in ("completed", "outstanding", "next_action", "evidence_ids")
                },
            }
            saved = self._store.add(
                Drawer(
                    wing=wing,
                    room=room,
                    content=content,
                    supersedes_id=parent,
                    metadata={
                        "task_checkpoint": {
                            "task_id": task_id,
                            "revision": revision,
                            "status": state["status"],
                            **payload,
                        }
                    },
                ),
                model=model,
            )
            if saved.id is None:
                raise TaskError("checkpoint append returned no persisted drawer")
            return {
                "schema": _WRITE_SCHEMA,
                "task_id": task_id,
                "revision": revision,
                "status": state["status"],
                "original_drawer_id": head["original_drawer_id"] if head is not None else saved.id,
                "checkpoint_drawer_id": saved.id,
                "_task": payload,
            }

        # Enclose execute_once's preparation and failure receipt as well as its action.
        with self._store.transaction():
            self._authorize("read", wing=wing, room=room)
            self._authorize("write", wing=wing, room=room)
            self._evidence(state["evidence_ids"])
            execution = self._store.execute_once(
                idempotency_key=key, operation=_OPERATION, request=request, action=append
            )
            result = execution.result
            chains = _chains(self._store._task_records(wing=wing))
            if result["task_id"] not in chains:
                raise TaskError("task is unavailable")
            self._authorize("write", wing=wing, room=room)
            public = {name: result[name] for name in _RECEIPT_FIELDS}
            public["replayed"] = execution.replayed
        return json.dumps(public, ensure_ascii=False, separators=(",", ":"))

    def resume(self, wing: str, task_id: str | None = None, budget_chars: int = 8192) -> str:
        """Read a complete visible task, explicitly abstaining on ambiguity or overflow."""
        _validate_ident(wing, "wing")
        if task_id is not None:
            _text(task_id, "task_id")
        if type(budget_chars) is not int or budget_chars < 1024:
            raise TaskError("resume budget_chars must be an integer of at least 1024")
        chains = _chains(self._store._task_records(wing=wing))
        payload: dict[str, Any] = {
            "schema": "cairntir.task-resume.v1",
            "status": "none",
            "task_id": None,
            "revision": None,
            "checkpoint": None,
            "candidates": [],
            "instruction_authority": "none",
            "budget": {"limit_chars": budget_chars, "rendered_chars": 0},
        }
        if task_id is not None:
            chain = chains.get(task_id)
            if chain is None:
                payload["status"] = "unavailable"
                return _render(payload)
        else:
            active = [chain for chain in chains.values() if chain[-1]["status"] == "active"]
            if not active:
                return _render(payload)
            if len(active) > 1:
                payload.update(status="ambiguous", omitted_candidates=len(active))
                for chain in sorted(active, key=lambda item: item[0]["task_id"]):
                    payload["candidates"].append(
                        {"task_id": chain[-1]["task_id"], "revision": chain[-1]["revision"]}
                    )
                    payload["omitted_candidates"] -= 1
                    if _required(_render(payload)) > budget_chars:
                        payload["candidates"].pop()
                        payload["omitted_candidates"] += 1
                        break
                return _render(payload)
            chain = active[0]
        head = chain[-1]
        payload.update(task_id=head["task_id"], revision=head["revision"])
        if head["status"] != "active":
            payload["status"] = "terminal"
            return _render(payload)
        ids = [head["original_drawer_id"], head["checkpoint_drawer_id"]]
        records = self._store._task_drawers(ids)
        if not set(ids) <= records.keys():
            raise TaskError("task checkpoint evidence is unavailable")
        original, original_provenance = records[ids[0]]
        current, current_provenance = records[ids[1]]
        payload.update(
            status="ready",
            checkpoint={
                "original_request": original.content,
                "summary": current.content,
                **{
                    name: head["_task"][name]
                    for name in ("completed", "outstanding", "next_action", "evidence_ids")
                },
                "original_drawer_id": ids[0],
                "checkpoint_drawer_id": ids[1],
                "provenance": {
                    "original": original_provenance.to_dict(),
                    "checkpoint": current_provenance.to_dict(),
                },
            },
        )
        required = _required(_render(payload))
        if required > budget_chars:
            while True:
                payload["budget"]["limit_chars"] = required
                measured = _required(_render(payload))
                if measured == required:
                    break
                required = measured
            payload["budget"]["limit_chars"] = budget_chars
            payload.update(
                status="omitted",
                checkpoint=None,
                required_chars=required,
                original_drawer_id=ids[0],
                checkpoint_drawer_id=ids[1],
            )
        return _render(payload)
