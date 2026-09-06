"""Portable v1 envelopes and v2 evidence bundles.

The v1 envelope contract below remains compatible. V2 adds stable identities,
atomic graph interchange and immutable source records; it preserves URL text as
inert evidence and never activates imported approval or execution metadata.

The round table's fourth theme was blunt: **format is the product**. A
SaaS can be captured. A file format on a USB stick cannot. Cairntir's
portable format is the artifact a future contributor can still read
ten years after every server, company, and maintainer is gone, and the
cryptographic substrate that lets any memory be gossiped, torrented,
emailed, or stuck on a thumb drive without trusting a central service.

## Envelope shape

A portable envelope is a plain JSON object with five keys::

    {
      "format_version": 1,
      "content_hash":   "sha256:<64 hex chars>",
      "signature":      "hmac-sha256:<64 hex chars>"  or null,
      "provenance": {
        "origin":         "cairntir@localhost",
        "exported_at":    "2026-04-08T12:34:56+00:00",
        "schema_version": 4
      },
      "drawer": { ... all taxonomy fields except id and access counters ... }
    }

Only the ``drawer`` sub-object feeds the content hash. Local state —
``id``, ``access_count``, ``last_accessed_at`` — is deliberately dropped:
it is not portable and it is not part of the memory the drawer asserts.
The hash is sha256 over the canonical (sorted-keys, UTF-8) JSON of the
drawer. The optional signature is HMAC-SHA256 of the hash plus the
serialized provenance, using a symmetric key the operator holds.

## Structural prohibition: no external URLs

The ethos is that **drawers reference other drawers, not external
systems**. Export fails closed (:class:`~cairntir.errors.ExternalUrlError`)
if any drawer's ``content`` or ``metadata`` contains an ``http://``,
``https://``, ``ftp://``, ``file://``, or ``ssh://`` URL. Only
``cairntir://`` references are permitted. A memory that depends on a
URL that will 404 is not portable — it is a ticking bomb.

## What this module is not

It is **not** a cryptographic guarantee of authorship. HMAC verifies
"someone with the symmetric key produced this envelope", not "Patrick
McGuire did". A future version may add ed25519 public-key signing. It
is **not** a wire protocol: transport is left entirely to the caller —
file, pipe, git, torrent, USB, it doesn't matter. The format carries
itself.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import tempfile
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from cairntir.errors import ExternalUrlError, PortableFormatError
from cairntir.memory.taxonomy import Drawer, Layer
from cairntir.provenance import TrustLevel, Visibility, WriteProvenance

if TYPE_CHECKING:
    from cairntir.memory.store import DrawerStore

FORMAT_VERSION: Final[int] = 1
"""The legacy JSONL envelope version; v2 bundles have a separate entry point."""

_EXTERNAL_URL_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:https?|ftp|file|ssh)://",
    re.IGNORECASE,
)
"""Matches any scheme that would pin a drawer to a rot-prone external system."""

_HASH_PREFIX: Final[str] = "sha256:"
_SIG_PREFIX: Final[str] = "hmac-sha256:"

# Drawer fields that ride in portable envelopes. Local-only fields
# (``id``, ``access_count``, ``last_accessed_at``) are intentionally
# excluded — they are not portable and must never influence the hash.
_PORTABLE_FIELDS: Final[tuple[str, ...]] = (
    "wing",
    "room",
    "content",
    "layer",
    "metadata",
    "created_at",
    "claim",
    "predicted_outcome",
    "observed_outcome",
    "delta",
    "supersedes_id",
    "belief_mass",
)


# --------- URL prohibition ---------------------------------------------


def ensure_no_external_urls(drawer: Drawer) -> None:
    """Raise :class:`ExternalUrlError` if the drawer references anything external.

    Scans both ``content`` and the JSON representation of ``metadata``.
    ``cairntir://`` references are explicitly allowed — they are the
    one legal way for a drawer to point elsewhere.
    """
    haystack_parts = [drawer.content, json.dumps(drawer.metadata, sort_keys=True)]
    for part in haystack_parts:
        match = _EXTERNAL_URL_RE.search(part)
        if match is not None:
            raise ExternalUrlError(
                f"drawer references an external URL ({match.group(0)!r}); "
                "cairntir's portable format only permits cairntir:// references"
            )


# --------- canonical bytes + hash --------------------------------------


def _drawer_to_portable_dict(drawer: Drawer) -> dict[str, Any]:
    """Project a Drawer onto the subset of fields the portable format carries."""
    return {
        "wing": drawer.wing,
        "room": drawer.room,
        "content": drawer.content,
        "layer": drawer.layer.value,
        "metadata": drawer.metadata,
        "created_at": drawer.created_at.isoformat(),
        "claim": drawer.claim,
        "predicted_outcome": drawer.predicted_outcome,
        "observed_outcome": drawer.observed_outcome,
        "delta": drawer.delta,
        "supersedes_id": drawer.supersedes_id,
        "belief_mass": drawer.belief_mass,
    }


def canonical_bytes(drawer_dict: dict[str, Any]) -> bytes:
    """Return the canonical JSON bytes of a drawer dict.

    Canonical = sorted keys, no whitespace, UTF-8 encoded. Two drawers
    that are semantically identical produce byte-identical canonical
    forms, which is what makes content hashing deterministic across
    platforms and Python versions.
    """
    try:
        return json.dumps(
            drawer_dict,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (ValueError, TypeError) as exc:
        raise PortableFormatError(
            f"payload cannot be encoded as canonical UTF-8 JSON: {exc}"
        ) from exc


def content_hash(drawer: Drawer) -> str:
    """Return ``sha256:<hex>`` for the drawer's canonical portable form."""
    digest = hashlib.sha256(canonical_bytes(_drawer_to_portable_dict(drawer))).hexdigest()
    return f"{_HASH_PREFIX}{digest}"


def _sign(payload: bytes, key: bytes) -> str:
    mac = hmac.new(key, payload, hashlib.sha256).hexdigest()
    return f"{_SIG_PREFIX}{mac}"


# --------- encode / decode ----------------------------------------------


def encode_drawer(
    drawer: Drawer,
    *,
    origin: str = "cairntir@localhost",
    schema_version: int = 4,
    signing_key: bytes | None = None,
    exported_at: datetime | None = None,
) -> dict[str, Any]:
    """Serialize ``drawer`` into a portable envelope.

    Validates the external-URL prohibition before anything is hashed.
    If ``signing_key`` is provided, an HMAC-SHA256 signature of the
    content hash plus canonical provenance is included.
    """
    ensure_no_external_urls(drawer)
    portable = _drawer_to_portable_dict(drawer)
    hash_value = content_hash(drawer)
    provenance = {
        "origin": origin,
        "exported_at": (exported_at or datetime.now(UTC)).isoformat(),
        "schema_version": schema_version,
    }
    envelope: dict[str, Any] = {
        "format_version": FORMAT_VERSION,
        "content_hash": hash_value,
        "signature": None,
        "provenance": provenance,
        "drawer": portable,
    }
    if signing_key is not None:
        signed_bytes = hash_value.encode("utf-8") + canonical_bytes(provenance)
        envelope["signature"] = _sign(signed_bytes, signing_key)
    return envelope


def decode_drawer(
    envelope: dict[str, Any],
    *,
    verify_key: bytes | None = None,
) -> Drawer:
    """Parse an envelope back into a :class:`Drawer`, verifying hash + signature.

    Always verifies the content hash. If ``verify_key`` is given, also
    verifies the HMAC signature; an envelope without a signature fails
    closed under verification, rather than silently trusting. A
    format_version newer than this module understands is rejected.
    """
    if not isinstance(envelope, dict):
        raise PortableFormatError("envelope is not a JSON object")
    version = envelope.get("format_version")
    if type(version) is not int or version != FORMAT_VERSION:
        raise PortableFormatError(
            f"unsupported format_version {version!r}; this module speaks v{FORMAT_VERSION}"
        )
    drawer_dict = envelope.get("drawer")
    if not isinstance(drawer_dict, dict):
        raise PortableFormatError("envelope is missing a drawer payload")
    for field in _PORTABLE_FIELDS:
        if field not in drawer_dict:
            raise PortableFormatError(f"drawer payload missing required field {field!r}")

    # Rebuild the Drawer first so hash verification runs against the
    # same canonical projection encode_drawer used.
    try:
        drawer = Drawer(
            wing=drawer_dict["wing"],
            room=drawer_dict["room"],
            content=drawer_dict["content"],
            layer=Layer(drawer_dict["layer"]),
            metadata=drawer_dict["metadata"],
            created_at=datetime.fromisoformat(str(drawer_dict["created_at"])),
            claim=drawer_dict["claim"],
            predicted_outcome=drawer_dict["predicted_outcome"],
            observed_outcome=drawer_dict["observed_outcome"],
            delta=drawer_dict["delta"],
            supersedes_id=drawer_dict["supersedes_id"],
            belief_mass=float(drawer_dict["belief_mass"]),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise PortableFormatError(f"drawer payload has invalid shape: {exc}") from exc

    expected = envelope.get("content_hash")
    actual = content_hash(drawer)
    if expected != actual:
        raise PortableFormatError(
            f"content hash mismatch: envelope claims {expected}, recomputed {actual}"
        )

    if verify_key is not None:
        sig = envelope.get("signature")
        if not isinstance(sig, str):
            raise PortableFormatError("verification requested but envelope is unsigned")
        provenance = envelope.get("provenance")
        if not isinstance(provenance, dict):
            raise PortableFormatError("signed envelope missing provenance")
        signed_bytes = actual.encode("utf-8") + canonical_bytes(provenance)
        expected_sig = _sign(signed_bytes, verify_key)
        if not sig.isascii() or not hmac.compare_digest(sig, expected_sig):
            raise PortableFormatError("signature mismatch: key does not match envelope")

    ensure_no_external_urls(drawer)
    _reject_local_references(drawer)
    return drawer


# --------- JSONL transport ---------------------------------------------


def write_jsonl(envelopes: Iterable[dict[str, Any]], path: Path) -> int:
    """Atomically replace ``path`` with JSON Lines; preserve it on failure."""
    count = 0
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as fh:
            temporary = Path(fh.name)
            for env in envelopes:
                fh.write(json.dumps(env, ensure_ascii=False, sort_keys=True))
                fh.write("\n")
                count += 1
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temporary, path)
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        raise PortableFormatError(f"cannot write portable file {path}: {exc}") from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError as exc:
                raise PortableFormatError(
                    f"cannot remove temporary export {temporary}: {exc}"
                ) from exc
    return count


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read envelopes from a JSON Lines file. One envelope per non-empty line."""
    envelopes: list[dict[str, Any]] = []
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise PortableFormatError(f"cannot read portable file {path}: {exc}") from exc
    for lineno, line in enumerate(raw.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            env = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise PortableFormatError(f"{path}:{lineno}: invalid JSON: {exc}") from exc
        if not isinstance(env, dict):
            raise PortableFormatError(f"{path}:{lineno}: envelope is not a JSON object")
        envelopes.append(env)
    return envelopes


# --------- bulk export / import over a DrawerStore ---------------------


def export_drawers(
    drawers: Iterable[Drawer],
    path: Path,
    *,
    origin: str = "cairntir@localhost",
    schema_version: int = 4,
    signing_key: bytes | None = None,
) -> int:
    """Encode an iterable of drawers and write them as JSONL. Returns the count.

    Fails closed on the first drawer that violates the external-URL
    prohibition: the file is not created, partial exports never happen.
    """
    envelopes = [
        encode_drawer(
            d,
            origin=origin,
            schema_version=schema_version,
            signing_key=signing_key,
        )
        for d in drawers
    ]
    return write_jsonl(envelopes, path)


def import_drawers(
    path: Path,
    *,
    verify_key: bytes | None = None,
) -> list[Drawer]:
    """Read envelopes from ``path`` and return verified :class:`Drawer` values.

    The caller decides what to do with the result — most commonly,
    feeding them into ``store.add()``. This module deliberately does
    not touch the store; it only speaks the format. That keeps the
    portable layer transport-free and unit-testable without sqlite.
    """
    envelopes = read_jsonl(path)
    return [decode_drawer(env, verify_key=verify_key) for env in envelopes]


def _reject_local_references(drawer: Drawer) -> None:
    # V1 drops source ids: neither a signature nor a matching destination id
    # provides the mapping needed to preserve relationships across stores.
    local_keys = {
        "evidence_drawer_ids",
        "counterexample_drawer_ids",
        "walkthrough_id",
        "derived_from",
        "evidence_ids",
        "parent_drawer_id",
    }

    def contains_local_reference(value: object) -> bool:
        if isinstance(value, dict):
            return any(
                (key in local_keys and item is not None and item != [])
                or contains_local_reference(item)
                for key, item in value.items()
            )
        if isinstance(value, list):
            return any(contains_local_reference(item) for item in value)
        return False

    payload = _drawer_to_portable_dict(drawer)
    if (
        drawer.supersedes_id is not None
        or contains_local_reference(drawer.metadata)
        or re.search(r"cairntir://drawer/[0-9]+", json.dumps(payload), re.IGNORECASE)
    ):
        raise PortableFormatError(
            "portable v1 cannot import source-local drawer references without an id map; "
            "use a database backup to preserve linked history"
        )


def _reference_specs(drawer: dict[str, Any]) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    kinds = {
        "supersedes_id": "supersedes",
        "evidence_drawer_ids": "evidence",
        "counterexample_drawer_ids": "counterexample",
        "walkthrough_id": "source",
        "derived_from": "source",
        "evidence_ids": "evidence",
        "parent_drawer_id": "source",
    }

    def add(kind: str, path: str, value: object) -> None:
        if type(value) is int and value > 0:
            reference = {"kind": kind, "path": path, "source_target_id": value}
            if reference not in references:
                references.append(reference)

    def walk(value: object, path: str, kind: str | None = None) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                escaped = str(key).replace("~", "~0").replace("/", "~1")
                walk(item, f"{path}/{escaped}", kinds.get(key))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}/{index}", kind)
        elif isinstance(value, str):
            for match in re.finditer(r"cairntir://drawer/([0-9]+)", value, re.IGNORECASE):
                add("source", path, int(match[1]))
        elif kind is not None:
            add(kind, path, value)

    walk(drawer, "")
    return references


def _make_source_record(
    store: DrawerStore, drawer: Drawer, provenance: WriteProvenance
) -> dict[str, Any]:
    payload = _drawer_to_portable_dict(drawer)
    references = _reference_specs(payload)
    for reference in references:
        target = store._conn.execute(
            "SELECT identity FROM portable_records WHERE drawer_id=?",
            (reference["source_target_id"],),
        ).fetchone()
        reference["target_identity"] = str(target[0]) if target is not None else None
    return {
        "identity": store.portable_identity(drawer.id or 0),
        "source_store_id": str(
            store._conn.execute(
                "SELECT value FROM store_metadata WHERE key='portable_store_id'"
            ).fetchone()[0]
        ),
        "source_drawer_id": drawer.id,
        "drawer": payload,
        "provenance": provenance.to_dict(),
        "references": references,
    }


def _bundle_bytes(payload: dict[str, Any]) -> bytes:
    try:
        return json.dumps(
            payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (ValueError, TypeError, UnicodeError) as exc:
        raise PortableFormatError(f"invalid portable JSON: {exc}") from exc


def _bundle_payload(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    return {"format_version": 2, "records": sorted(records, key=lambda item: item["identity"])}


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise PortableFormatError("portable identity must be a UUID string")
    try:
        parsed = UUID(value)
    except ValueError as exc:
        raise PortableFormatError("invalid portable UUID") from exc
    if str(parsed) != value:
        raise PortableFormatError("portable UUID must use canonical lowercase notation")
    return value


def _original_drawer(record: dict[str, Any]) -> Drawer:
    raw = record.get("drawer")
    if not isinstance(raw, dict) or not all(key in raw for key in _PORTABLE_FIELDS):
        raise PortableFormatError("portable record is missing original drawer fields")
    try:
        drawer = Drawer(**raw)
    except (TypeError, ValueError) as exc:
        raise PortableFormatError(f"invalid original drawer: {exc}") from exc
    if _bundle_bytes(_drawer_to_portable_dict(drawer)) != _bundle_bytes(raw):
        raise PortableFormatError("original drawer fields must not require coercion")
    return drawer


def _validate_record(record: object) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise PortableFormatError("portable record must be an object")
    _uuid(record.get("identity"))
    _uuid(record.get("source_store_id"))
    if type(record.get("source_drawer_id")) is not int or record["source_drawer_id"] <= 0:
        raise PortableFormatError("portable record needs its positive original drawer id")
    drawer = _original_drawer(record)
    if not isinstance(record.get("provenance"), dict):
        raise PortableFormatError("portable record needs original provenance")
    try:
        WriteProvenance.from_json(json.dumps(record["provenance"]))
    except (ValueError, TypeError) as exc:
        raise PortableFormatError(f"invalid original provenance: {exc}") from exc
    references = record.get("references")
    if not isinstance(references, list):
        raise PortableFormatError("portable record needs its reference map")
    actual = []
    for reference in references:
        if not isinstance(reference, dict):
            raise PortableFormatError("portable reference must be an object")
        _uuid(reference.get("target_identity"))
        if type(reference.get("source_target_id")) is not int:
            raise PortableFormatError("portable reference needs an integer source target")
        actual.append({key: reference.get(key) for key in ("kind", "path", "source_target_id")})
    expected = _reference_specs(_drawer_to_portable_dict(drawer))
    if sorted(actual, key=repr) != sorted(expected, key=repr):
        raise PortableFormatError("portable reference map does not match original evidence")
    return record


def _validate_graph(store: DrawerStore, records: dict[str, dict[str, Any]]) -> None:
    for record in records.values():
        for reference in record["references"]:
            target = records.get(reference["target_identity"])
            if target is None:
                target_id = store._portable_lookup(reference["target_identity"])
                if target_id is None:
                    raise PortableFormatError("portable reference target is missing")
                target = store.portable_source(target_id)
            if (
                record["source_store_id"] == target["source_store_id"]
                and reference["source_target_id"] != target["source_drawer_id"]
            ):
                raise PortableFormatError(
                    "portable reference is rebound within its source namespace"
                )


def export_bundle(
    store: DrawerStore,
    path: Path,
    *,
    drawer_ids: Sequence[int] | None = None,
    wing: str | None = None,
    room: str | None = None,
    signing_key: bytes | None = None,
) -> dict[str, Any]:
    """Export complete original evidence and required relationships as an atomic v2 bundle."""
    from cairntir.access import ScopedStore

    if isinstance(store, ScopedStore) and not store._export_depth:
        with store._portable_export():
            return export_bundle(
                store, path, drawer_ids=drawer_ids, wing=wing, room=room, signing_key=signing_key
            )
    list_drawers = store.list_for_export if isinstance(store, ScopedStore) else store.list_by
    selected = (
        list(drawer_ids)
        if drawer_ids is not None
        else [
            item.id
            for item in list_drawers(wing=wing, room=room, limit=None, include_expired=True)
            if item.id is not None
        ]
    )
    records: dict[str, dict[str, Any]] = {}
    pending = list(selected)
    visited: set[int] = set()
    while pending:
        drawer_id = pending.pop()
        if drawer_id in visited:
            continue
        visited.add(drawer_id)
        record = _validate_record(store.portable_source(drawer_id))
        if (wing is not None and record["drawer"]["wing"] != wing) or (
            room is not None and record["drawer"]["room"] != room
        ):
            raise PortableFormatError("portable relationship closure exceeds the explicit scope")
        records[record["identity"]] = record
        pending.extend(item["target_drawer_id"] for item in store.portable_relations(drawer_id))
    _validate_graph(store, records)
    payload = _bundle_payload(records.values())
    raw = _bundle_bytes(payload)
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    bundle = {
        **payload,
        "bundle_hash": digest,
        "signature": _sign(raw, signing_key) if signing_key is not None else None,
    }
    if isinstance(store, ScopedStore):
        store.authorize("export")
    write_jsonl([bundle], path)
    return {"count": len(records), "complete": True, "bundle_hash": digest}


def import_bundle(
    store: DrawerStore,
    path: Path,
    *,
    verify_key: bytes | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Atomically import verified originals as inert evidence, deduplicating by UUID."""
    try:
        bundle = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise PortableFormatError(f"cannot read portable bundle: {exc}") from exc
    if (
        not isinstance(bundle, dict)
        or type(bundle.get("format_version")) is not int
        or bundle["format_version"] != 2
    ):
        raise PortableFormatError("unsupported portable bundle format")
    if not isinstance(bundle.get("records"), list):
        raise PortableFormatError("portable bundle needs a record array")
    records = {}
    for value in bundle["records"]:
        record = _validate_record(value)
        identity = record["identity"]
        if identity in records:
            raise PortableFormatError("duplicate portable identity inside bundle")
        records[identity] = record
    raw = _bundle_bytes(_bundle_payload(records.values()))
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    if digest != bundle.get("bundle_hash"):
        raise PortableFormatError("portable bundle hash mismatch")
    if verify_key is not None:
        signature = bundle.get("signature")
        if (
            not isinstance(signature, str)
            or not signature.isascii()
            or not hmac.compare_digest(signature, _sign(raw, verify_key))
        ):
            raise PortableFormatError("portable bundle signature mismatch or unsigned input")

    def apply() -> dict[str, Any]:
        _validate_graph(store, records)
        identity_map: dict[str, int] = {}
        new = []
        for identity, record in records.items():
            local_id = store._portable_lookup(identity)
            if local_id is not None:
                if store.portable_source(local_id) != record:
                    raise PortableFormatError(
                        "portable identity conflicts with its immutable original"
                    )
                identity_map[identity] = local_id
            else:
                new.append(record)
        for record in new:
            original = _original_drawer(record)
            source = WriteProvenance.from_json(json.dumps(record["provenance"]))
            provenance = WriteProvenance.create(
                host="portable-v2",
                capture_path="portable.import",
                trust=TrustLevel.UNTRUSTED,
                sensitivity=source.sensitivity,
                visibility=Visibility.PRIVATE,
                valid_from=source.valid_from,
                valid_until=source.valid_until,
            )
            projection = original.model_copy(
                update={
                    "supersedes_id": None,
                    "metadata": {
                        "kind": "cairntir.imported-evidence",
                        "portable_identity": record["identity"],
                    },
                }
            )
            saved = store.add(projection, provenance=provenance)
            if saved.id is None:
                raise PortableFormatError("portable import produced no drawer id")
            identity_map[record["identity"]] = saved.id
            store._portable_replace(saved.id, record["identity"], record)
        for record in new:
            for reference in record["references"]:
                if reference["kind"] != "supersedes" or reference["path"] != "/supersedes_id":
                    continue
                target_id = identity_map.get(reference["target_identity"])
                if target_id is None:
                    target_id = store._portable_lookup(reference["target_identity"])
                if target_id is None:
                    raise PortableFormatError("portable supersession target is missing")
                store._portable_supersedes(identity_map[record["identity"]], target_id)
        return {
            "count": len(records),
            "imported": len(new),
            "existing": len(records) - len(new),
            "identity_map": identity_map,
            "bundle_hash": digest,
        }

    execution = store.execute_once(
        idempotency_key=idempotency_key or f"portable-v2:{digest}",
        operation="portable.import.v2",
        request={"bundle_hash": digest},
        action=apply,
    )
    if execution.receipt.result is None:
        raise PortableFormatError("portable import committed without a result")
    return execution.receipt.result
