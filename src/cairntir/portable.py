"""Portable signed drawer format — the v0.5 anti-capture lock.

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
import re
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from cairntir.errors import ExternalUrlError, PortableFormatError
from cairntir.memory.taxonomy import Drawer, Layer

FORMAT_VERSION: Final[int] = 1
"""The portable envelope format version. Bumped on incompatible changes."""

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
    return json.dumps(
        drawer_dict,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


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
    if version != FORMAT_VERSION:
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
            wing=str(drawer_dict["wing"]),
            room=str(drawer_dict["room"]),
            content=str(drawer_dict["content"]),
            layer=Layer(drawer_dict["layer"]),
            metadata=dict(drawer_dict.get("metadata") or {}),
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
        if not hmac.compare_digest(sig, expected_sig):
            raise PortableFormatError("signature mismatch: key does not match envelope")

    return drawer


# --------- JSONL transport ---------------------------------------------


def write_jsonl(envelopes: Iterable[dict[str, Any]], path: Path) -> int:
    """Write envelopes to ``path`` as JSON Lines. Returns the count written."""
    count = 0
    with path.open("w", encoding="utf-8") as fh:
        for env in envelopes:
            fh.write(json.dumps(env, ensure_ascii=False, sort_keys=True))
            fh.write("\n")
            count += 1
    return count


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read envelopes from a JSON Lines file. One envelope per non-empty line."""
    envelopes: list[dict[str, Any]] = []
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
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
