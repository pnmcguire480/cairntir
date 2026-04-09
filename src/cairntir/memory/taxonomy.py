"""Wing / Room / Drawer taxonomy.

Cairntir organizes verbatim memory into three nested concepts:

* **Wing** — a project or top-level context (e.g. ``"cairntir"``).
* **Room** — a topic inside a wing (e.g. ``"phase-1-memory-spike"``).
* **Drawer** — a single verbatim entry with content, metadata, and a
  retrieval layer. Drawers are never summarized, truncated, or rewritten.

Identifiers are validated at construction time; invalid inputs raise
:class:`cairntir.errors.TaxonomyError` rather than producing silent garbage.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cairntir.errors import TaxonomyError

_IDENT_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,62}[a-z0-9]$")


class Layer(StrEnum):
    """Retrieval layer for a drawer.

    * ``IDENTITY`` — user/agent identity, always loaded.
    * ``ESSENTIAL`` — current wing state, loaded for any session in that wing.
    * ``ON_DEMAND`` — loaded when relevant to a query (semantic match).
    * ``DEEP`` — deep archive, only loaded on explicit request.
    """

    IDENTITY = "identity"
    ESSENTIAL = "essential"
    ON_DEMAND = "on_demand"
    DEEP = "deep"


def _validate_ident(value: str, kind: str) -> str:
    """Validate a wing or room identifier, raising :class:`TaxonomyError` on failure."""
    if not isinstance(value, str) or not _IDENT_RE.match(value):
        raise TaxonomyError(f"invalid {kind} identifier {value!r}: must match {_IDENT_RE.pattern}")
    return value


class Drawer(BaseModel):
    """A single verbatim memory entry.

    Attributes:
        id: Database row id. ``None`` before insert.
        wing: Wing identifier.
        room: Room identifier.
        content: Verbatim content, never summarized.
        layer: Retrieval layer.
        metadata: Arbitrary JSON-serializable metadata.
        created_at: UTC timestamp of creation.
        claim: Optional falsifiable claim this drawer makes.
        predicted_outcome: Optional prediction the claim commits to, before
            evidence arrives.
        observed_outcome: Optional observation recorded after the fact.
        delta: Optional free-form surprise signal — how the observation
            diverged from the prediction. Load-bearing in v0.4.
        supersedes_id: Optional drawer id this entry replaces. Append-only
            history; nothing is mutated in place.
    """

    model_config = ConfigDict(frozen=True)

    id: int | None = None
    wing: str
    room: str
    content: str
    layer: Layer = Layer.ON_DEMAND
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # v0.2 — prediction-bound drawer fields (all optional, append-only).
    claim: str | None = None
    predicted_outcome: str | None = None
    observed_outcome: str | None = None
    delta: str | None = None
    supersedes_id: int | None = None

    @field_validator("wing")
    @classmethod
    def _check_wing(cls, v: str) -> str:
        return _validate_ident(v, "wing")

    @field_validator("room")
    @classmethod
    def _check_room(cls, v: str) -> str:
        return _validate_ident(v, "room")

    @field_validator("content")
    @classmethod
    def _check_content(cls, v: str) -> str:
        if not v or not v.strip():
            raise TaxonomyError("drawer content must be non-empty")
        return v
