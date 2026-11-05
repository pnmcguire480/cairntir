"""Currentness of explicit, portable derivation dependencies."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from cairntir.access import ScopedStore
from cairntir.errors import CairntirError, RetrievalError
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.origin import (
    OriginReference,
    origin_reference,
    read_reference_drawer,
    reference_family,
)
from cairntir.provenance import Sensitivity, WriteProvenance

_DEPENDENCY = re.compile(r"/metadata/derived_from/(?:0|[1-9][0-9]*)")
_Store = DrawerStore | ScopedStore


def _usable(receipt: WriteProvenance | None) -> bool:
    now = datetime.now(UTC)
    return (
        receipt is not None
        and receipt.sensitivity is not Sensitivity.SECRET
        and (receipt.valid_from is None or receipt.valid_from <= now)
        and (receipt.valid_until is None or receipt.valid_until > now)
    )


def _dependencies(store: _Store, drawer_id: int) -> list[int]:
    references = store.portable_source(drawer_id)["references"]
    selected = {
        reference["path"]: reference
        for reference in references
        if isinstance(reference.get("path"), str) and _DEPENDENCY.fullmatch(reference["path"])
    }
    if not selected:
        return []
    result = []
    for original in selected.values():
        identity = original["target_identity"]
        if original["kind"] != "source" or not isinstance(identity, str):
            raise RetrievalError("derivation source unavailable")
        key = store._portable_lookup(identity)
        if type(key) is not int or key <= 0 or store.portable_identity(key) != identity:
            raise RetrievalError("derivation source unavailable")
        result.append(key)
    return result


def derivation_status(store: _Store, drawer_id: int) -> dict[str, Any]:
    """Inspect explicit dependencies without touching or rewriting evidence."""
    sources: dict[str, OriginReference] = {}
    reasons: set[str] = set()
    active: set[int] = set()
    done: set[int] = set()
    visited: set[int] = set()

    def track(key: int) -> None:
        if key not in visited:
            if len(visited) >= 1024:
                raise RetrievalError("derivation source unavailable")
            visited.add(key)

    def available(key: int) -> Drawer:
        track(key)
        drawer = read_reference_drawer(store, key)
        if not _usable(store.get_provenance(key)):
            raise RetrievalError("derivation source unavailable")
        return drawer

    def remember_source(key: int) -> None:
        track(key)
        reference = origin_reference(store, key)
        sources[reference["identity"]] = reference

    def walk(key: int) -> None:
        if key in active or len(active) >= 256:
            raise RetrievalError("derivation source unavailable")
        if key in done:
            return
        active.add(key)
        available(key)
        for source_id in _dependencies(store, key):
            source = available(source_id)
            if isinstance(store, ScopedStore):
                store._authorize_complete_wing(source.wing)
            remember_source(source_id)
            family = reference_family(store, source_id)
            if not any(drawer.id == source_id for drawer, _ in family):
                raise RetrievalError("derivation source unavailable")
            successors = [
                drawer
                for drawer, _ in family
                if drawer.id != source_id and drawer.supersedes_id == source_id
            ]
            for drawer, receipt in family:
                if not _usable(receipt):
                    raise RetrievalError("derivation source unavailable")
                if drawer.id is not None and drawer.id != source_id:
                    remember_source(drawer.id)
            if successors:
                reasons.add("source_conflict" if len(successors) > 1 else "source_superseded")
            walk(source_id)
        active.remove(key)
        done.add(key)

    try:
        available(drawer_id)
        if not _dependencies(store, drawer_id):
            return {"status": "not_derived", "reasons": [], "sources": []}
        walk(drawer_id)
    except (CairntirError, KeyError, TypeError, ValueError):
        return {"status": "unknown", "reasons": ["source_unavailable"], "sources": []}
    return {
        "status": "needs_review" if reasons else "current",
        "reasons": sorted(reasons),
        "sources": sorted(sources.values(), key=lambda reference: reference["identity"]),
    }


def is_withheld(state: dict[str, Any]) -> bool:
    """Report whether derived evidence must stay out of working context."""
    return state["status"] in {"needs_review", "unknown"}


def evidence_fields(store: _Store, drawer: Drawer) -> dict[str, Any]:
    """Attach origin and derivation observations to visible evidence."""
    if drawer.id is None:
        raise RetrievalError("evidence has no persisted identity")
    return {
        "origin_reference": origin_reference(store, drawer.id),
        "derivation": derivation_status(store, drawer.id),
    }
