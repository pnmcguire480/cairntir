"""Turn a stored I02 angle into channel drafts and keep the link back to that angle.

The channel inlet in ``ideation_channels`` only accepts a selection backed by a
source file. This route writes that source file from a stored angle set, so the
draft, its vault note and the stored selection all quote the angle and name the
set revision and angle id it came from.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from cairntir import ideation_channels as channels
from cairntir.errors import ProjectionError
from cairntir.ideation_angles import get_angle_set

_IDEA = re.compile(r"s(\d+)-(.+)\Z")
_SOURCE_ID = "angle"
_RESULT = "cairntir.channel-result.v1"
_ORIGIN = "cairntir.channel-selection.v1"


def _bytes_cut(text: str, limit: int) -> str:
    """Return ``text`` cut on a character boundary to at most ``limit`` UTF-8 bytes."""
    if len(text.encode("utf-8")) <= limit:
        return text
    return text.encode("utf-8")[: limit - 3].decode("utf-8", errors="ignore").rstrip() + "..."


def default_profiles() -> list[dict[str, Any]]:
    """Return the three declared channel profiles, copied so callers cannot alter them."""
    copy: list[dict[str, Any]] = json.loads(json.dumps(channels._PROFILES))
    return copy


def source_root(vault: Path, wing: str) -> Path:
    """Return the folder that holds the angle source files for ``wing``."""
    return vault / "cairntir-sync" / wing / "channel-sources"


def pick_angle(angle_set: dict[str, Any], angle_id: str | None) -> tuple[dict[str, Any], str, str]:
    """Choose the angle and say who chose it.

    An explicit id wins, then the person's latest recorded pick, then the
    automatic top choice, which is labelled as the model's ranking.
    """
    by_id = {item["id"]: item for item in angle_set["candidates"]}
    if angle_id is not None:
        if angle_id not in by_id:
            raise ProjectionError(f"angle {angle_id!r} is not in angle set {angle_set['revision']}")
        return by_id[angle_id], "person_pick", f"Angle {angle_id} named on the command line."
    history = angle_set.get("selection_history") or []
    if history:
        last = history[-1]
        picked = by_id.get(last["candidate_id"])
        if picked is None:
            raise ProjectionError("the recorded pick is not in the stored angle set")
        return picked, "person_pick", f"Person's pick #{last['selection_id']}: {last['reason']}"
    top = by_id[angle_set["automatic_choice"]]
    return top, "automatic_top_choice", "No person's pick recorded; the model's top-ranked angle."


_BRIEF = (
    " Channel brief: write three different hooks, one per channel, never the same sentence. "
    "Community post: a question a developer would answer. Newsletter: a plain line stating "
    "the benefit. Short video: a spoken line that can be said in one breath. Keep every "
    "field short and inside its limit; use the angle's own subject in each."
)


def _excerpt(angle: dict[str, Any]) -> str:
    # The angle's own hook is left out on purpose: real models copy a hook they are shown
    # into every channel and the validator then refuses the draft. The hook stays linked
    # through the angle id.
    return f"{angle['angle']}\nWhy it fits: {angle['relevance']}"


def write_source(
    root: Path, angle_set: dict[str, Any], angle: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Write (or confirm) the immutable source file for this angle and return its entry."""
    revision, angle_id = angle_set["revision"], angle["id"]
    anchor = f"## Angle {angle_id} from angle set {revision}"
    excerpt = _excerpt(angle)
    body = (
        f"# Idea source (angle set {revision})\n\n"
        "Stored model-generated angle; provisional. Set and angle ids below link the "
        "channel drafts back to this idea.\n\n"
        f"{anchor}\n\n{excerpt}\n"
    ).encode()
    root.mkdir(parents=True, exist_ok=True)
    name = f"angle-s{revision}-{angle_id}.md"
    path = root / name
    if path.exists():
        if path.read_bytes() != body:
            raise ProjectionError(f"{path} already exists with different bytes; not overwritten")
    else:
        path.write_bytes(body)
    entry = {
        "source_id": _SOURCE_ID,
        "path": name,
        "sha256": hashlib.sha256(body).hexdigest(),
        "anchor": anchor,
        "excerpt": excerpt,
        "excerpt_sha256": hashlib.sha256(excerpt.encode()).hexdigest(),
    }
    return name, entry


def build_selection(
    angle_set: dict[str, Any], angle: dict[str, Any], reason: str, entry: dict[str, Any]
) -> dict[str, Any]:
    """Build the channel inlet's selection for a stored angle."""
    return {
        "kind": "manual_provisional",
        "idea_id": f"s{angle_set['revision']}-{angle['id']}",
        "title": _bytes_cut(angle["angle"], 240),
        "selected_text": entry["excerpt"],
        "selection_reason": _bytes_cut(reason, 1024 - len(_BRIEF.encode())) + _BRIEF,
        "attribution": "caller_supplied",
        "human_confirmation": False,
        "sources": [entry],
    }


def idea_link(angle_set: dict[str, Any], angle: dict[str, Any], chosen_by: str) -> dict[str, Any]:
    """Describe the angle a draft came from, for printing and for tests."""
    return {
        "angle_set_revision": angle_set["revision"],
        "angle_id": angle["id"],
        "angle": angle["angle"],
        "hook": angle["hook"],
        "chosen_by": chosen_by,
        "angle_set_note": angle_set["snapshot_path"],
    }


def request_key(wing: str, selection: dict[str, Any], identity: dict[str, Any]) -> str:
    """Return a key from the whole input, so a changed input never reuses an old key."""
    digest = hashlib.sha256(
        json.dumps(
            [wing, selection, identity, channels._PROFILES],
            sort_keys=True,
        ).encode()
    ).hexdigest()
    return "cli-ch-" + digest[:32]


def generate(
    store: Any,
    store_path: Path,
    vault: Path,
    wing: str,
    *,
    adapter: Any,
    angle_id: str | None = None,
    set_revision: int | None = None,
    key: str | None = None,
) -> dict[str, Any]:
    """Generate, keep and project channel drafts for one stored angle."""
    angle_set = get_angle_set(store_path, vault, wing, revision=set_revision)
    angle, chosen_by, reason = pick_angle(angle_set, angle_id)
    root = source_root(vault, wing)
    _, entry = write_source(root, angle_set, angle)
    profiles = default_profiles()
    selection = build_selection(angle_set, angle, reason, entry)
    receipt = channels.generate_channel_set(
        store,
        wing=wing,
        selection=selection,
        profiles=profiles,
        source_root=root,
        idempotency_key=key or request_key(wing, selection, dict(adapter.identity)),
        adapter=adapter,
    )
    replayed = bool(receipt.get("replayed"))
    projected = channels.project_channel_set(
        store, receipt["ref"], vault_path=vault, source_root=root, current_profiles=profiles
    )
    projected["replayed"] = replayed
    projected["idea"] = idea_link(angle_set, angle, chosen_by)
    return projected


def latest_ref(store: Any, wing: str) -> dict[str, Any]:
    """Return the reference of the newest stored channel draft for ``wing``."""
    rows = store.list_by(wing=wing, room=channels._ROOM, limit=None)
    found: list[Any] = []
    for row in rows:
        try:
            content = json.loads(row.content)
        except ValueError:
            continue
        if isinstance(content, dict) and content.get("schema") == _RESULT:
            found.append(row)
    if not found:
        raise ProjectionError(f"no channel draft is stored for wing {wing!r}")
    row = max(found, key=lambda item: int(item.id))
    return {
        "drawer_id": row.id,
        "portable_identity": store.portable_identity(row.id),
        "content_sha256": hashlib.sha256(row.content.encode("utf-8")).hexdigest(),
        "wing": wing,
        "room": channels._ROOM,
    }


def _origin_selection(store: Any, receipt: dict[str, Any]) -> dict[str, Any]:
    wing = receipt["origin_ref"]["wing"]
    for row in store.list_by(wing=wing, room=channels._ROOM, limit=None):
        if row.id == receipt["origin_ref"]["drawer_id"]:
            content = json.loads(row.content)
            if content.get("schema") == _ORIGIN:
                return dict(content["selection"])
    raise ProjectionError("the draft's origin record is missing")


def show(store: Any, store_path: Path, vault: Path, wing: str) -> dict[str, Any]:
    """Reopen the newest draft and the angle it links to, without calling a model."""
    root = source_root(vault, wing)
    ref = latest_ref(store, wing)
    receipt = channels.get_channel_set(
        store, ref, source_root=root, current_profiles=default_profiles()
    )
    selection = _origin_selection(store, receipt)
    match = _IDEA.fullmatch(selection["idea_id"])
    if match is None:
        raise ProjectionError("the draft was not made from a stored angle")
    revision, angle_id = int(match.group(1)), match.group(2)
    angle_set = get_angle_set(store_path, vault, wing, revision=revision)
    angle = next((a for a in angle_set["candidates"] if a["id"] == angle_id), None)
    if angle is None or _excerpt(angle) != selection["selected_text"]:
        raise ProjectionError("the stored angle no longer matches the draft's quoted idea")
    chosen_by = (
        "person_pick"
        if selection["selection_reason"].startswith(("Person", "Angle"))
        else ("automatic_top_choice")
    )
    base = vault / "cairntir-sync" / wing / "channels"
    notes = {
        "version_note": base / "versions" / f"{ref['content_sha256']}.md",
        "selection_note": base / "sources" / f"{receipt['origin_ref']['content_sha256']}.md",
        "current_note": base / "current.md",
    }
    receipt["projection"] = {name: str(path) for name, path in notes.items()}
    receipt["projection_status"] = (
        "ready" if all(path.is_file() for path in notes.values()) else "missing"
    )
    receipt["idea"] = idea_link(angle_set, angle, chosen_by)
    receipt["selection_reason"] = selection["selection_reason"]
    return receipt
