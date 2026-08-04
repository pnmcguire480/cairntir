"""Typed write provenance and trust metadata.

Provenance is stored beside every drawer by :class:`DrawerStore`; callers
cannot smuggle it through arbitrary drawer metadata.  It records where a
write entered Cairntir without changing the drawer's retrieval identity.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Final
from uuid import uuid4

_NEVER_EXPIRES: Final[str] = "9999-12-31T23:59:59.999999+00:00"
TOOL_SURFACE_VERSION: Final[str] = "20"
"""How many MCP tools the surface exposes, recorded on every write receipt.

Hand-maintained because deriving it would make :mod:`cairntir.provenance`
import the server, and the server already imports this. The number is pinned
by ``test_tool_surface_version_matches_the_server`` instead -- an unchecked
constant that describes the code is the exact drift this project keeps finding.
"""


class TrustLevel(StrEnum):
    """How strongly Cairntir may rely on a drawer's asserted content."""

    UNTRUSTED = "untrusted"
    USER_ASSERTED = "user_asserted"
    AGENT_GENERATED = "agent_generated"
    SYSTEM = "system"


class Visibility(StrEnum):
    """Intended sharing boundary for a drawer."""

    PRIVATE = "private"
    PROJECT = "project"
    PORTABLE = "portable"


class Sensitivity(StrEnum):
    """Human-declared sensitivity of drawer content."""

    NORMAL = "normal"
    SENSITIVE = "sensitive"
    SECRET = "secret"  # noqa: S105 - classification label, not a credential


@dataclass(frozen=True, slots=True)
class WriteProvenance:
    """Immutable receipt describing one write path into Cairntir."""

    host: str
    capture_path: str
    session_id: str
    trust: TrustLevel = TrustLevel.UNTRUSTED
    visibility: Visibility = Visibility.PRIVATE
    sensitivity: Sensitivity = Sensitivity.NORMAL
    client_name: str | None = None
    client_version: str | None = None
    model: str | None = None
    tool_surface_version: str = TOOL_SURFACE_VERSION
    recorded_at: datetime | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None

    def __post_init__(self) -> None:
        """Validate fields once so serialized receipts are trustworthy."""
        if not self.host.strip():
            raise ValueError("provenance host must be non-empty")
        if not self.capture_path.strip():
            raise ValueError("provenance capture_path must be non-empty")
        if not self.session_id.strip():
            raise ValueError("provenance session_id must be non-empty")
        if (
            self.valid_from is not None
            and self.valid_until is not None
            and _as_utc(self.valid_until) <= _as_utc(self.valid_from)
        ):
            raise ValueError("provenance valid_until must be later than valid_from")

    @classmethod
    def create(
        cls,
        *,
        host: str,
        capture_path: str,
        trust: TrustLevel = TrustLevel.UNTRUSTED,
        visibility: Visibility = Visibility.PRIVATE,
        sensitivity: Sensitivity = Sensitivity.NORMAL,
        client_name: str | None = None,
        client_version: str | None = None,
        model: str | None = None,
        session_id: str | None = None,
        valid_from: datetime | None = None,
        valid_until: datetime | None = None,
    ) -> WriteProvenance:
        """Construct a receipt with a stable per-process/session identifier."""
        return cls(
            host=host,
            capture_path=capture_path,
            session_id=session_id or str(uuid4()),
            trust=trust,
            visibility=visibility,
            sensitivity=sensitivity,
            client_name=client_name or host,
            client_version=client_version,
            model=model or "unknown",
            recorded_at=datetime.now(UTC),
            valid_from=valid_from,
            valid_until=valid_until,
        )

    def for_write(
        self,
        *,
        trust: TrustLevel | None = None,
        visibility: Visibility | None = None,
        sensitivity: Sensitivity | None = None,
        valid_from: datetime | None = None,
        valid_until: datetime | None = None,
        model: str | None = None,
    ) -> WriteProvenance:
        """Return a per-drawer receipt while retaining host/session identity.

        ``model`` is per-write rather than per-process on purpose. The host
        never discloses which model is running to the MCP subprocess, so a
        value fixed at startup would keep asserting the first model after the
        user switched to another. The writing agent knows its own identity and
        can state it on each write; the process-level default stays "unknown",
        which is honest, rather than a stale guess that looks like data.
        """
        return replace(
            self,
            trust=trust or self.trust,
            visibility=visibility or self.visibility,
            sensitivity=sensitivity or self.sensitivity,
            model=model.strip() if model and model.strip() else self.model,
            recorded_at=datetime.now(UTC),
            valid_from=valid_from if valid_from is not None else self.valid_from,
            valid_until=valid_until if valid_until is not None else self.valid_until,
        )

    @property
    def effective_valid_until(self) -> str:
        """Sortable timestamp used by sqlite-vec's validity prefilter."""
        if self.valid_until is None:
            return _NEVER_EXPIRES
        return _as_utc(self.valid_until).isoformat()

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        payload = asdict(self)
        payload["trust"] = self.trust.value
        payload["visibility"] = self.visibility.value
        payload["sensitivity"] = self.sensitivity.value
        for key in ("recorded_at", "valid_from", "valid_until"):
            value = payload[key]
            payload[key] = _as_utc(value).isoformat() if value is not None else None
        return payload

    def to_json(self) -> str:
        """Return deterministic JSON for SQLite storage."""
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, raw: str) -> WriteProvenance:
        """Parse and validate a stored receipt."""
        try:
            payload = _json_object(raw)
            return cls(
                host=str(payload["host"]),
                capture_path=str(payload["capture_path"]),
                session_id=str(payload["session_id"]),
                trust=TrustLevel(payload["trust"]),
                visibility=Visibility(payload["visibility"]),
                sensitivity=Sensitivity(payload["sensitivity"]),
                client_name=_optional_text(payload.get("client_name")),
                client_version=_optional_text(payload.get("client_version")),
                model=_optional_text(payload.get("model")),
                tool_surface_version=str(payload.get("tool_surface_version", TOOL_SURFACE_VERSION)),
                recorded_at=_optional_datetime(payload.get("recorded_at")),
                valid_from=_optional_datetime(payload.get("valid_from")),
                valid_until=_optional_datetime(payload.get("valid_until")),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid stored provenance receipt: {exc}") from exc


def legacy_provenance() -> WriteProvenance:
    """Receipt used when migrating drawers written before provenance existed."""
    return WriteProvenance.create(
        host="legacy",
        capture_path="pre-v6-migration",
        trust=TrustLevel.UNTRUSTED,
    )


def _optional_text(value: object) -> str | None:
    return None if value is None else str(value)


def _json_object(raw: str) -> dict[str, Any]:
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise TypeError("receipt is not an object")
    return payload


def _optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(str(value))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
