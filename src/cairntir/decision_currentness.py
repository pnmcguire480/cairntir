"""Read-time decision currentness from explicit same-wing relationships."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from cairntir.access import AccessDenied, ScopedStore
from cairntir.errors import RetrievalError
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer

_DECISION = re.compile(r"^\s*decision(?:\s+reversed)?\s*:", re.IGNORECASE)
_DATASTORE = re.compile(r"\b(?:datastore|database)\b", re.IGNORECASE)


@dataclass(slots=True)
class CurrentnessIndex:
    """One fresh, wing-scoped classification with an explicit completeness signal."""

    _store: DrawerStore | ScopedStore
    wing: str
    _labels: dict[int, str]
    scan_complete: bool
    reason: str | None

    def fields(self, drawer: Drawer) -> dict[str, Any]:
        """Add stable identity, saved date and a conservative currentness label."""
        if drawer.id is None or drawer.wing != self.wing:
            raise RetrievalError("decision evidence is outside the currentness index")
        return {
            "saved_at": drawer.created_at.isoformat(),
            "portable_identity": self._store.portable_identity(drawer.id),
            "currentness": self._labels.get(drawer.id, "unresolved"),
            "supersedes_id": drawer.supersedes_id,
        }


def currentness_index(
    store: DrawerStore | ScopedStore, *, wing: str, allow_current: bool = True
) -> CurrentnessIndex:
    """Classify only witnessed ancestors and a complete, unopposed datastore leaf."""
    complete = allow_current
    reason = None if allow_current else "incomplete currentness scan: candidate limit"
    if isinstance(store, ScopedStore):
        try:
            store._authorize_complete_wing(wing)
        except AccessDenied:
            complete = False
            reason = "incomplete currentness scan: wing is not fully visible"

    drawers = store.list_by(wing=wing, limit=None, include_expired=True)
    by_id = {drawer.id: drawer for drawer in drawers if drawer.id is not None}
    descendants = {
        drawer.supersedes_id
        for drawer in drawers
        if drawer.supersedes_id is not None and drawer.supersedes_id in by_id
    }
    labels = {key: "historical" for key in descendants if _DECISION.match(by_id[key].content)}
    datastore_leaves = [
        drawer.id
        for drawer in drawers
        if drawer.id is not None
        and drawer.id not in descendants
        and _DECISION.match(drawer.content)
        and _DATASTORE.search(drawer.content)
    ]
    if complete and len(datastore_leaves) == 1:
        leaf = datastore_leaves[0]
        provenance = store.get_provenance(leaf)
        now = datetime.now(UTC)
        if (
            provenance is not None
            and (provenance.valid_from is None or provenance.valid_from <= now)
            and (provenance.valid_until is None or provenance.valid_until > now)
        ):
            labels[leaf] = "current"
    return CurrentnessIndex(store, wing, labels, complete, reason)
