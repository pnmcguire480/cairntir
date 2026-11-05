"""Origin-qualified references over existing immutable portable records."""

from __future__ import annotations

import hashlib
import json
import re
from typing import TYPE_CHECKING, Any, TypedDict
from uuid import UUID

from cairntir.errors import CairntirError

if TYPE_CHECKING:
    from cairntir.access import ScopedStore
    from cairntir.memory.store import DrawerStore
    from cairntir.memory.taxonomy import Drawer
    from cairntir.provenance import WriteProvenance


class OriginReferenceError(CairntirError):
    """An origin-qualified reference cannot be read or safely captured."""


class OriginReference(TypedDict):
    """Exact portable origin and currently authorized content fingerprint."""

    source_store_id: str
    source_drawer_id: int
    identity: str
    content_sha256: str


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise OriginReferenceError("origin must be a canonical UUID")
    try:
        canonical = str(UUID(value))
    except ValueError as exc:
        raise OriginReferenceError("origin must be a canonical UUID") from exc
    if canonical != value:
        raise OriginReferenceError("origin must be a canonical UUID")
    return canonical


def _reference(value: object) -> OriginReference:
    if not isinstance(value, dict) or value.keys() != {
        "source_store_id",
        "source_drawer_id",
        "identity",
        "content_sha256",
    }:
        raise OriginReferenceError("reference must contain exactly four origin fields")
    number = value["source_drawer_id"]
    digest = value["content_sha256"]
    if type(number) is not int or not 0 < number <= 2**63 - 1:
        raise OriginReferenceError("source drawer must be a positive signed 64-bit integer")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise OriginReferenceError("content fingerprint must be a lowercase SHA256 digest")
    return {
        "source_store_id": _uuid(value["source_store_id"]),
        "source_drawer_id": number,
        "identity": _uuid(value["identity"]),
        "content_sha256": digest,
    }


def read_reference_drawer(store: DrawerStore | ScopedStore, drawer_id: int) -> Drawer:
    """Read one permitted drawer without touching retrieval counters."""
    if type(drawer_id) is not int or not 0 < drawer_id <= 2**63 - 1:
        raise OriginReferenceError("drawer reference is unavailable")
    drawer = store.reference_drawer(drawer_id)
    if drawer is None:
        raise OriginReferenceError("drawer reference is unavailable")
    return drawer


def origin_reference(store: DrawerStore | ScopedStore, drawer_id: int) -> OriginReference:
    """Describe the original store/UUID and the exact authorized body, without writes."""
    drawer = read_reference_drawer(store, drawer_id)
    original = store.portable_source(drawer_id)
    return _reference(
        {
            "source_store_id": original["source_store_id"],
            "source_drawer_id": original["source_drawer_id"],
            "identity": store.portable_identity(drawer_id),
            "content_sha256": hashlib.sha256(drawer.content.encode("utf-8")).hexdigest(),
        }
    )


def resolve_reference(store: DrawerStore | ScopedStore, reference: object) -> dict[str, Any]:
    """Resolve exact portable mappings, returning one opaque unresolved shape otherwise."""
    try:
        expected = _reference(reference)
        local_id = store._portable_lookup(expected["identity"])
        if local_id is not None and origin_reference(store, local_id) == expected:
            return {"status": "resolved", "drawer_id": local_id, "reference": expected}
    except (CairntirError, KeyError, TypeError):
        return {"status": "unresolved"}
    return {"status": "unresolved"}


def reference_family(
    store: DrawerStore | ScopedStore, drawer_id: int
) -> list[tuple[Drawer, WriteProvenance]]:
    """Read the source and all direct successors under the caller's existing authority."""
    return store.reference_family(drawer_id)


def check_capture_origin(
    store: DrawerStore | ScopedStore,
    *,
    content: str,
    reference_origin: str | None,
    metadata: dict[str, Any] | None = None,
    claim: str | None = None,
    predicted_outcome: str | None = None,
    anchors: list[dict[str, Any]] | None = None,
    checkpoint: dict[str, Any] | None = None,
) -> None:
    """Refuse explicitly foreign numeric-URI capture before ordinary writes."""
    if reference_origin is None:
        return
    declared = _uuid(reference_origin)
    if declared != store.portable_store_identity():
        captured = json.dumps(
            {
                "content": content,
                "metadata": metadata,
                "claim": claim,
                "predicted_outcome": predicted_outcome,
                "anchors": anchors,
                "checkpoint": checkpoint,
            },
            ensure_ascii=False,
        )
        if re.search(r"cairntir://drawer/[0-9]+", captured, re.IGNORECASE):
            raise OriginReferenceError("foreign drawer references require portable bundle import")
