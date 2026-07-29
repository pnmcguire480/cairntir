"""Workflow durability value types and deterministic request hashing."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable


class WorkflowState(StrEnum):
    """Persisted lifecycle of one idempotent workflow invocation."""

    STARTED = "started"
    COMMITTED = "committed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class WorkflowReceipt:
    """Read-only workflow state returned by the store."""

    idempotency_key: str
    operation: str
    request_hash: str
    state: WorkflowState
    attempt_count: int
    started_at: datetime
    updated_at: datetime
    result: dict[str, Any] | None
    error: str | None


@dataclass(frozen=True, slots=True)
class WorkflowExecution:
    """Result of executing or replaying one idempotent operation."""

    receipt: WorkflowReceipt
    replayed: bool

    @property
    def result(self) -> dict[str, Any]:
        """Return the committed result, failing loudly if it is absent."""
        if self.receipt.result is None:
            raise RuntimeError("committed workflow receipt has no result")
        return self.receipt.result


@runtime_checkable
class DurableStore(Protocol):
    """Concrete-store extension used by production workflow adapters."""

    def transaction(self) -> AbstractContextManager[None]:
        """Return a nestable atomic unit of work."""
        ...

    def execute_once(
        self,
        *,
        idempotency_key: str,
        operation: str,
        request: dict[str, Any],
        action: Callable[[], dict[str, Any]],
    ) -> WorkflowExecution:
        """Execute and durably replay one idempotent operation."""
        ...


def request_hash(payload: dict[str, Any]) -> str:
    """Return a deterministic SHA-256 hash for an idempotent request."""
    try:
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"workflow request is not JSON-serializable: {exc}") from exc
    return hashlib.sha256(canonical).hexdigest()
