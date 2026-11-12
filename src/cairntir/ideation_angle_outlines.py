"""Expand a person's selected I02 angle into source-bound outlines (I05 route).

The outline engine in :mod:`cairntir.ideation_outlines` already validates complete
outlines, stores them with their planned next actions, replays identical requests
and projects owned vault notes. It accepts a provisional source-bound context:
source files on disk whose exact byte ranges and hashes are checked on every use.

This module supplies that context from the immutable I02 angle-set snapshot note.
The selected angle (the person's latest recorded pick, or one named explicitly)
becomes the idea, its hook becomes the hook, and the note's header and objectives
become constraint evidence. The snapshot holds model-generated, unverified angles,
so the context keeps ``historical_record_unverified`` attribution and
``human_confirmation=false``: it is a stored record, not confirmed truth.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from cairntir import ideation_angles as angles
from cairntir import ideation_outlines as outlines
from cairntir.audience_lock import audience_lock
from cairntir.errors import ProjectionError

PathLike = str | os.PathLike[str]

_SET_KIND = "cairntir.outline-set.v1"
_ROOM = "ideation-outlines"
_HEADER = "# Ideation — provisional"
_OBJECTIVES = "## Objectives"
_CLAIMS_POLICY = (
    "The source is a stored I02 angle set: angles, hooks, scores and reasons are a local "
    "model's unverified judgments, ranked by Cairntir. Quote it only as recorded text. "
    "Do not present any result, number, tool, price or availability as fact; make each "
    "such claim an assumption with a verification action. Examples are hypothetical."
)
DEFAULT_FORMATS = (
    "written-post:words:600:900",
    "short-video:seconds:60:90",
)
_FORMAT_CONSTRAINTS = {
    "words": (
        "Written post in plain paragraphs: each key point is developed in two or three "
        "sentences with one concrete hypothetical example the reader can picture."
    ),
    "seconds": (
        "Spoken short video: opening, points and close are lines a person can say aloud; "
        "production notes give per-section timing in seconds and what is on screen."
    ),
}
_COMMON_CONSTRAINT = (
    "Every bridge is a full written sentence that leads from one section into the next; "
    "planned actions are preparation steps for this piece, never publication."
)


def parse_format(value: str) -> dict[str, Any]:
    """Parse ``id:unit:minimum:maximum`` into an intended output format."""
    parts = value.split(":")
    if len(parts) != 4 or not all(part.strip() for part in parts):
        raise ValueError(f"format must look like id:unit:minimum:maximum, got {value!r}")
    ident, unit, low, high = (part.strip() for part in parts)
    if unit not in _FORMAT_CONSTRAINTS:
        raise ValueError(f"format unit must be words or seconds, got {unit!r}")
    if not (low.isdigit() and high.isdigit()) or int(low) < 1 or int(high) < int(low):
        raise ValueError(f"format length range is invalid in {value!r}")
    return {"format_id": ident, "unit": unit, "minimum": int(low), "maximum": int(high)}


def _selected(receipt: dict[str, Any], angle_id: str | None) -> tuple[dict[str, Any], str]:
    by_id = {item["id"]: item for item in receipt["candidates"]}
    if angle_id is not None:
        if angle_id not in by_id:
            raise ProjectionError(f"angle {angle_id!r} is not in angle set {receipt['revision']}")
        return by_id[angle_id], "named"
    history = receipt["selection_history"]
    if not history:
        raise ProjectionError(
            "no selected angle: record one with `cairntir angles choose` or pass --angle"
        )
    latest = max(history, key=lambda item: item["selection_id"])
    return by_id[latest["candidate_id"]], "person_pick"


def _anchor(data: bytes, start: int, end: int, ident: str) -> dict[str, Any]:
    excerpt = data[start:end]
    heading = excerpt.split(b"\n", 1)[0].decode("utf-8")
    if data.decode("utf-8").count(heading) != 1:
        raise ProjectionError(f"snapshot heading for {ident!r} is not unique")
    return {
        "id": ident,
        "anchor": heading,
        "anchor_occurrences": 1,
        "excerpt": excerpt.decode("utf-8"),
        "excerpt_sha256": hashlib.sha256(excerpt).hexdigest(),
        "byte_start": start,
        "byte_length": end - start,
    }


def _section_end(data: bytes, start: int) -> int:
    following = data.find(b"\n## ", start + 1)
    return len(data) if following < 0 else following + 1


def _audience_text(lock: dict[str, Any]) -> str:
    text = "; ".join(f"{field}: {item['value']}" for field, item in lock["profile"].items())
    return text[:500].strip() or "unspecified audience"


def angle_context(
    store_path: PathLike,
    vault_path: PathLike,
    wing: str,
    *,
    revision: int | None = None,
    angle_id: str | None = None,
) -> dict[str, Any]:
    """Bind the selected angle in its immutable snapshot note as outline context."""
    receipt = angles.get_angle_set(store_path, vault_path, wing, revision=revision)
    if receipt["projection_status"] == "conflict":
        raise ProjectionError("angle snapshot note conflicts with the stored set")
    snapshot = Path(receipt["snapshot_path"])
    try:
        data = snapshot.read_bytes()
    except FileNotFoundError as exc:
        raise ProjectionError(
            "angle snapshot note is missing: run `cairntir angles choose` to write it"
        ) from exc
    angle, selection = _selected(receipt, angle_id)
    prefix = f"## {angle['rank']}. {angle['id']}: ".encode()
    start = data.find(b"\n" + prefix)
    if start < 0:
        raise ProjectionError("selected angle is missing from its snapshot note")
    start += 1
    end = _section_end(data, start)
    section = data[start:end].decode("utf-8")
    title = section.split("\n", 1)[0][len(prefix.decode("utf-8")) :]
    hooks = [line[len("Hook: ") :] for line in section.split("\n") if line.startswith("Hook: ")]
    if len(hooks) != 1 or not title.strip() or not hooks[0].strip():
        raise ProjectionError("selected angle has no single title and hook in its note")
    objectives = data.find(b"\n" + _OBJECTIVES.encode()) + 1
    if objectives <= 0 or not data.startswith(_HEADER.encode()):
        raise ProjectionError("angle snapshot note has an unexpected layout")
    anchors = [
        _anchor(data, 0, objectives, "set-header"),
        _anchor(data, objectives, _section_end(data, objectives), "objectives"),
        _anchor(data, start, end, "selected-angle"),
    ]
    source_id = f"I02-SET-{receipt['revision']}"
    ref = {"source_id": source_id, "anchor_id": "selected-angle"}
    hook_id = f"{angle['id']}.hook"
    context = {
        "schema": "cairntir.i04.historical-context.v1",
        "kind": "historical_provisional",
        "project": f"I02 angle set {receipt['revision']}, wing {wing}",
        "attribution": "historical_record_unverified",
        "human_confirmation": False,
        "sources": [
            {
                "source_id": source_id,
                "path": snapshot.name,
                "original_path": str(snapshot),
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "anchors": anchors,
            }
        ],
        "ideas": [
            {
                "id": angle["id"],
                "title": title[:512],
                "source_ref": ref,
                "hooks": [
                    {
                        "id": hook_id,
                        "channel": "angle-hook",
                        "format": "i02-hook",
                        "source_ref": ref,
                        "text": hooks[0],
                    }
                ],
            }
        ],
        "constraints_refs": [
            {"source_id": source_id, "anchor_id": "set-header"},
            {"source_id": source_id, "anchor_id": "objectives"},
        ],
        "withdrawn_date_refs": [],
        "claims_policy": _CLAIMS_POLICY,
    }
    return {
        "context": context,
        "source_root": str(snapshot.parent),
        "set_revision": receipt["revision"],
        "angle_id": angle["id"],
        "hook_id": hook_id,
        "selection": selection,
        "audience": _audience_text(audience_lock(store_path, vault_path, wing)),
    }


def outline_requests(
    bound: dict[str, Any], formats: Sequence[dict[str, Any]], constraints: Sequence[str] = ()
) -> list[dict[str, Any]]:
    """Make one engine request per intended format for the selected angle."""
    if not formats:
        raise ProjectionError("at least one intended output format is required")
    requests = []
    for item in formats:
        requests.append(
            {
                "request_id": item["format_id"],
                "idea_id": bound["angle_id"],
                "hook_id": bound["hook_id"],
                "format_id": item["format_id"],
                "audience": bound["audience"],
                "finished_length": {
                    "unit": item["unit"],
                    "minimum": item["minimum"],
                    "maximum": item["maximum"],
                },
                "production_constraints": [
                    _FORMAT_CONSTRAINTS[item["unit"]],
                    _COMMON_CONSTRAINT,
                    *constraints,
                ],
            }
        )
    return requests


def generate_angle_outlines(
    store: outlines.Store,
    store_path: PathLike,
    vault_path: PathLike,
    wing: str,
    *,
    formats: Sequence[dict[str, Any]],
    adapter: outlines.OutlineAdapter,
    idempotency_key: str,
    constraints: Sequence[str] = (),
    revision: int | None = None,
    angle_id: str | None = None,
    bound: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate, accept atomically and project outlines for the selected angle.

    ``bound`` reuses a context already returned by :func:`angle_context`.
    """
    if bound is None:
        bound = angle_context(store_path, vault_path, wing, revision=revision, angle_id=angle_id)
    receipt = outlines.generate_outline_set(
        store,
        wing=wing,
        context=bound["context"],
        requests=outline_requests(bound, formats, constraints),
        source_root=bound["source_root"],
        adapter=adapter,
        idempotency_key=idempotency_key,
    )
    replayed = receipt["replayed"]
    projected = outlines.project_outline_set(
        store, receipt["ref"], vault_path=vault_path, source_root=bound["source_root"]
    )
    projected["replayed"] = replayed
    return _summary(projected, bound, vault_path)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def latest_outline_ref(
    store: outlines.Store, wing: str, set_id: int | None = None
) -> dict[str, Any]:
    """Return the reference of the newest (or the named) accepted outline set."""
    rows = [
        drawer
        for drawer in store.list_by(wing=wing, room=_ROOM, limit=None, include_expired=True)
        if drawer.id is not None
        and isinstance(drawer.metadata, dict)
        and drawer.metadata.get("kind") == _SET_KIND
        and (set_id is None or drawer.id == set_id)
    ]
    if not rows:
        raise ProjectionError("no accepted outline set for this wing")
    drawer = max(rows, key=lambda row: cast(int, row.id))
    drawer_id = cast(int, drawer.id)
    return {
        "drawer_id": drawer_id,
        "portable_identity": store.portable_identity(drawer_id),
        "content_sha256": _sha(drawer.content),
        "wing": wing,
        "room": _ROOM,
    }


def show_angle_outlines(
    store: outlines.Store, vault_path: PathLike, wing: str, *, set_id: int | None = None
) -> dict[str, Any]:
    """Reopen and verify a stored outline set, its actions and its source note."""
    ref = latest_outline_ref(store, wing, set_id)
    unchecked = outlines.get_outline_set(store, ref)
    source = unchecked["context"]["sources"][0]
    root = str(Path(source["original_path"]).parent)
    receipt = outlines.get_outline_set(store, ref, source_root=root)
    receipt["replayed"] = False
    angle = receipt["context"]["ideas"][0]
    bound = {
        "angle_id": angle["id"],
        "hook_id": angle["hooks"][0]["id"],
        "set_revision": int(source["source_id"].rsplit("-", 1)[1]),
        "selection": None,
    }
    return _summary(receipt, bound, vault_path)


def _summary(receipt: dict[str, Any], bound: dict[str, Any], vault: PathLike) -> dict[str, Any]:
    base = Path(vault) / "cairntir-sync" / receipt["ref"]["wing"] / "outlines"
    set_note = base / receipt["ref"]["content_sha256"] / "set.md"
    return {
        **receipt,
        "angle_id": bound["angle_id"],
        "hook_id": bound["hook_id"],
        "angle_set_revision": bound["set_revision"],
        "selection": bound["selection"],
        "set_note_path": str(set_note),
        "set_note_exists": set_note.is_file(),
    }
