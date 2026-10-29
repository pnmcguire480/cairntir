"""Deterministic, source-bound planning calendars with immutable local revisions."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date, timedelta
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn, cast
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from cairntir import ideation_channels as channels
from cairntir.access import ScopedStore
from cairntir.errors import IdempotencyConflictError, ProjectionError
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.provenance import WriteProvenance

Store = DrawerStore | ScopedStore
PathLike = str | os.PathLike[str]
_ROOM = "ideation-calendars"
_REF_KEYS = {"drawer_id", "portable_identity", "content_sha256", "wing", "room"}
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_WING = re.compile(r"[a-z0-9][a-z0-9._:-]{0,62}[a-z0-9]\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_BEGIN = b"<!-- cairntir:calendar:begin -->"
_END = b"<!-- cairntir:calendar:end -->"
_NOTICE = (
    "Planning only. Historical and model-supplied claims, selection, availability and "
    "effectiveness remain unverified; human_confirmation=false. Nothing is published."
)


class CalendarError(ProjectionError):
    """A surfaced calendar failure with a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        """Retain the failure code and explanation."""
        self.code = code
        super().__init__(message)


def _fail(code: str, message: str) -> NoReturn:
    raise CalendarError(code, message)


def _canonical(value: Any, code: str = "INVALID_INPUT") -> bytes:
    try:
        raw = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise CalendarError(code, "value is not strict UTF-8 JSON") from exc
    if len(raw) > 2_097_152:
        _fail(code, "calendar artifact exceeds its byte limit")
    return raw


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json(raw: bytes | str, code: str = "INVALID_INPUT") -> Any:
    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                _fail(code, "JSON contains duplicate object keys")
            result[key] = value
        return result

    def constant(value: str) -> NoReturn:
        _fail(code, f"non-finite JSON value {value}")

    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise CalendarError(code, "invalid calendar JSON") from exc


def _object(value: Any, keys: set[str], code: str = "INVALID_INPUT") -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        _fail(code, "object fields do not match the calendar contract")
    return cast(dict[str, Any], value)


def _text(value: Any, limit: int, *, empty: bool = False) -> str:
    if (
        not isinstance(value, str)
        or len(value) > limit
        or (not empty and not value.strip())
        or "\x00" in value
    ):
        _fail("INVALID_INPUT", "invalid calendar text")
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise CalendarError("INVALID_INPUT", "text is not UTF-8") from exc
    return value


def _ident(value: Any, *, wing: bool = False) -> str:
    parsed = _text(value, 64)
    if not (_WING if wing else _ID).fullmatch(parsed):
        _fail("INVALID_INPUT", "invalid calendar identifier")
    return parsed


def _integer(value: Any, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        _fail("INVALID_INPUT", "invalid bounded integer")
    return value


def _hash(value: Any) -> str:
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        _fail("INVALID_INPUT", "invalid SHA256 digest")
    return value


def _date(value: Any) -> date:
    value = _text(value, 10)
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise CalendarError("INVALID_INPUT", "invalid calendar date") from exc
    if parsed.isoformat() != value:
        _fail("INVALID_INPUT", "dates must use YYYY-MM-DD")
    return parsed


def _list(value: Any, minimum: int, maximum: int) -> list[Any]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        _fail("INVALID_INPUT", "invalid bounded list")
    return value


def _safe(path: Path, *, directory: bool = False) -> Path:
    try:
        return channels._safe_path(path, directory=directory)
    except channels.ChannelError as exc:
        raise CalendarError("CONFLICT", str(exc)) from exc


def _historical(value: Any, source_root: PathLike | None) -> dict[str, Any]:
    row = _object(
        value,
        {
            "schema",
            "kind",
            "project",
            "attribution",
            "human_confirmation",
            "sources",
            "ideas",
            "constraints_refs",
            "withdrawn_date_refs",
            "claims_policy",
        },
    )
    if (
        row["schema"] != "cairntir.i04.historical-context.v1"
        or row["kind"] != "historical_provisional"
        or row["attribution"] != "historical_record_unverified"
        or row["human_confirmation"] is not False
    ):
        _fail("INVALID_INPUT", "historical context must retain its unverified attribution")
    _text(row["project"], 256)
    _text(row["claims_policy"], 4096)
    sources = _list(row["sources"], 1, 32)
    anchors: dict[tuple[str, str], dict[str, Any]] = {}
    source_ids: set[str] = set()
    source_paths: set[str] = set()
    total = 0
    for source in sources:
        source = _object(
            source, {"source_id", "path", "original_path", "bytes", "sha256", "anchors"}
        )
        sid, path = _ident(source["source_id"]), _text(source["path"], 1024)
        if (
            sid in source_ids
            or path.casefold() in source_paths
            or "\\" in path
            or ":" in path
            or PurePosixPath(path).is_absolute()
            or any(part in {"", ".", ".."} for part in path.split("/"))
        ):
            _fail("INVALID_INPUT", "source identities and safe relative paths must be unique")
        source_ids.add(sid)
        source_paths.add(path.casefold())
        _text(source["original_path"], 2048)
        size = _integer(source["bytes"], 1, 262_144)
        total += size
        if total > 1_048_576:
            _fail("INVALID_INPUT", "historical source byte limit exceeded")
        _hash(source["sha256"])
        seen_anchors: set[str] = set()
        for anchor in _list(source["anchors"], 1, 128):
            anchor = _object(
                anchor,
                {
                    "id",
                    "anchor",
                    "anchor_occurrences",
                    "excerpt",
                    "excerpt_sha256",
                    "byte_start",
                    "byte_length",
                },
            )
            aid, heading = _ident(anchor["id"]), _text(anchor["anchor"], 1024)
            excerpt = _text(anchor["excerpt"], 32_768).encode("utf-8")
            if (
                (sid, aid) in anchors
                or heading in seen_anchors
                or type(anchor["anchor_occurrences"]) is not int
                or anchor["anchor_occurrences"] != 1
                or _sha(excerpt) != _hash(anchor["excerpt_sha256"])
                or not anchor["excerpt"].startswith(heading)
            ):
                _fail("INVALID_INPUT", "source anchors and exact excerpts must be unique and bound")
            start = _integer(anchor["byte_start"], 0, size - 1)
            length = _integer(anchor["byte_length"], 1, size)
            if length != len(excerpt) or start + length > size:
                _fail("INVALID_INPUT", "source excerpt byte range does not match")
            seen_anchors.add(heading)
            anchors[sid, aid] = anchor

    def source_ref(value: Any) -> dict[str, Any]:
        ref = _object(value, {"source_id", "anchor_id"})
        key = (_ident(ref["source_id"]), _ident(ref["anchor_id"]))
        if key not in anchors:
            _fail("INVALID_INPUT", "source reference does not resolve")
        return anchors[key]

    idea_ids: set[str] = set()
    hook_ids: set[str] = set()
    for idea in _list(row["ideas"], 1, 128):
        idea = _object(idea, {"id", "title", "source_ref", "hooks"})
        ident, title = _ident(idea["id"]), _text(idea["title"], 512)
        if ident in idea_ids or title not in source_ref(idea["source_ref"])["excerpt"]:
            _fail("INVALID_INPUT", "idea identity or source attribution is invalid")
        idea_ids.add(ident)
        for hook in _list(idea["hooks"], 1, 64):
            hook = _object(hook, {"id", "channel", "format", "source_ref", "text"})
            hid = _ident(hook["id"])
            _text(hook["channel"], 128)
            _text(hook["format"], 128)
            wording = _text(hook["text"], 8192)
            if hid in hook_ids or wording not in source_ref(hook["source_ref"])["excerpt"]:
                _fail("INVALID_INPUT", "hook identity or source attribution is invalid")
            hook_ids.add(hid)
    for key in ("constraints_refs", "withdrawn_date_refs"):
        seen_refs: set[bytes] = set()
        for ref in _list(row[key], 0, 128):
            source_ref(ref)
            bound = _canonical(ref)
            if bound in seen_refs:
                _fail("INVALID_INPUT", "duplicate constraint source reference")
            seen_refs.add(bound)
    if source_root is not None:
        try:
            base = _safe(Path(source_root), directory=True)
            for source in sources:
                source_path = _safe(base / source["path"])
                if not source_path.is_relative_to(base) or not source_path.is_file():
                    _fail("INVALID_INPUT", "source is not a regular file beneath its root")
                with source_path.open("rb") as handle:
                    data = handle.read(262_145)
                if len(data) != source["bytes"] or _sha(data) != source["sha256"]:
                    _fail("INVALID_INPUT", "historical source bytes have changed")
                text = data.decode("utf-8")
                for anchor in source["anchors"]:
                    start, length = anchor["byte_start"], anchor["byte_length"]
                    if (
                        text.count(anchor["anchor"]) != 1
                        or data.find(anchor["anchor"].encode("utf-8")) != start
                        or data[start : start + length] != anchor["excerpt"].encode("utf-8")
                    ):
                        _fail("INVALID_INPUT", "historical anchor or exact excerpt has changed")
        except (OSError, UnicodeError, ValueError, TypeError, CalendarError) as exc:
            raise CalendarError(
                "INVALID_INPUT", "historical source files are unsafe or changed"
            ) from exc
    return cast(dict[str, Any], _json(_canonical(row)))


def _modern(store: Store, value: Any, source_root: PathLike | None) -> dict[str, Any]:
    row = _object(value, {"kind", "ref"})
    if row["kind"] != "i03":
        _fail("INVALID_INPUT", "unsupported calendar inlet")
    try:
        receipt = channels.get_channel_set(store, row["ref"], source_root=source_root)
        graph = channels._graph(store, row["ref"])
        selection = graph["origin"]["selection"]
        if source_root is not None:
            channels._sources(selection, source_root)
    except channels.ChannelError as exc:
        raise CalendarError(
            "INVALID_INPUT", "canonical I03 context is unavailable or invalid"
        ) from exc
    hooks = [
        {
            "id": adaptation["channel_id"],
            "channel": adaptation["channel_id"],
            "format": adaptation["format_id"],
            "source_ref": {
                "origin_ref": receipt["origin_ref"],
                "source_ids": adaptation["source_ids"],
            },
            "text": adaptation["hook"],
            "uncertainty_notice": adaptation["uncertainty_notice"],
        }
        for adaptation in receipt["adaptations"]
    ]
    return cast(
        dict[str, Any],
        _json(
            _canonical(
                {
                    "kind": "i03",
                    "ref": receipt["ref"],
                    "attribution": selection["attribution"],
                    "human_confirmation": False,
                    "selection": selection,
                    "ideas": [
                        {
                            "id": selection["idea_id"],
                            "title": selection["title"],
                            "source_ref": receipt["origin_ref"],
                            "hooks": hooks,
                        }
                    ],
                    "uncertainty_notice": _NOTICE,
                }
            )
        ),
    )


def _context(
    store: Store, value: Any, source_root: PathLike | None, *, retained: bool = False
) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("INVALID_INPUT", "calendar context must be an object")
    if value.get("kind") == "historical_provisional":
        return _historical(value, source_root)
    if value.get("kind") == "i03":
        raw = {"kind": "i03", "ref": value.get("ref")} if retained else value
        normalized = _modern(store, raw, source_root)
        if retained and normalized != value:
            _fail("CORRUPT_ARTIFACT", "retained I03 context differs from its canonical graph")
        return normalized
    _fail("INVALID_INPUT", "calendar requires a canonical I03 or historical provisional context")


def _hooks(context: dict[str, Any]) -> dict[str, tuple[dict[str, Any], dict[str, Any]]]:
    return {hook["id"]: (idea, hook) for idea in context["ideas"] for hook in idea["hooks"]}


def _policy(value: Any, context: dict[str, Any]) -> dict[str, Any]:
    row = _object(
        value,
        {
            "schema",
            "assumption_origin",
            "human_confirmation",
            "start_date",
            "days",
            "timezone",
            "daily_capacity",
            "collision_policy",
            "flex_weekdays",
            "blackouts",
            "existing_commitments",
            "weekly_slots",
            "repurposing_policy",
            "publication_policy",
            "historical_claims_policy",
        },
    )
    if (
        row["schema"] != "cairntir.i04.policy.v1"
        or row["human_confirmation"] is not False
        or type(row["days"]) is not int
        or row["days"] != 30
        or row["collision_policy"] != "retain_and_report"
        or row["publication_policy"] != "planning_only_no_external_publish"
    ):
        _fail("INVALID_INPUT", "calendar policy must remain a provisional 30-day planning policy")
    _text(row["assumption_origin"], 256)
    _text(row["historical_claims_policy"], 4096)
    _date(row["start_date"])
    timezone = _text(row["timezone"], 128)
    if timezone != "UTC":
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise CalendarError("INVALID_INPUT", "named timezone data is unavailable") from exc
    _integer(row["daily_capacity"], 1, 64)
    flex = [_integer(day, 0, 6) for day in _list(row["flex_weekdays"], 0, 7)]
    if len(set(flex)) != len(flex):
        _fail("INVALID_INPUT", "flex weekdays must be unique")
    dates: set[str] = set()
    for blackout in _list(row["blackouts"], 0, 366):
        blackout = _object(blackout, {"date", "reason"})
        _date(blackout["date"])
        _text(blackout["reason"], 1024)
        if blackout["date"] in dates:
            _fail("INVALID_INPUT", "blackout dates must be unique")
        dates.add(blackout["date"])
    commitments: set[str] = set()
    for item in _list(row["existing_commitments"], 0, 1024):
        item = _object(item, {"id", "date", "units", "title"})
        ident = _ident(item["id"])
        _date(item["date"])
        _integer(item["units"], 1, 64)
        _text(item["title"], 1024)
        if ident in commitments:
            _fail("INVALID_INPUT", "commitment IDs must be unique")
        commitments.add(ident)
    rules = _object(
        row["repurposing_policy"],
        {"require_same_idea", "require_different_channel", "require_source_before_target"},
    )
    if any(value is not True for value in rules.values()):
        _fail(
            "INVALID_INPUT", "repurposing must retain earlier same-idea, different-channel sources"
        )
    hooks = _hooks(context)
    slots: dict[str, dict[str, Any]] = {}
    for slot in _list(row["weekly_slots"], 1, 32):
        if not isinstance(slot, dict):
            _fail("INVALID_INPUT", "weekly slot must be an object")
        base = {"id", "weekday", "title_by_hook", "cta_by_hook"}
        repurpose = "repurpose_from_slot" in slot
        keys = (
            {"repurpose_from_slot", "source_offset_days", "hook_map"}
            if repurpose
            else {"hook_cycle"}
        )
        slot = _object(slot, base | keys)
        ident = _ident(slot["id"])
        _integer(slot["weekday"], 0, 6)
        if ident in slots:
            _fail("INVALID_INPUT", "weekly slot IDs must be unique")
        slots[ident] = slot
        if repurpose:
            _ident(slot["repurpose_from_slot"])
            _integer(slot["source_offset_days"], -29, -1)
            mapping = slot["hook_map"]
            if not isinstance(mapping, dict) or not mapping:
                _fail("INVALID_INPUT", "repurposing needs an explicit hook mapping")
            targets = list(mapping.values())
            if any(
                _ident(key) not in hooks or _ident(target) not in hooks
                for key, target in mapping.items()
            ):
                _fail("INVALID_INPUT", "repurposing references an unknown hook")
        else:
            targets = [_ident(hook) for hook in _list(slot["hook_cycle"], 1, 64)]
            if any(target not in hooks for target in targets):
                _fail("INVALID_INPUT", "weekly route references an unknown hook")
        for key in ("title_by_hook", "cta_by_hook"):
            mapping = slot[key]
            if not isinstance(mapping, dict) or set(mapping) != set(targets):
                _fail(
                    "INVALID_INPUT", "every routed hook needs an explicit title and call to action"
                )
            for text in mapping.values():
                _text(text, 2048)
    for slot in slots.values():
        if "repurpose_from_slot" in slot:
            parent = slots.get(slot["repurpose_from_slot"])
            if parent is None:
                _fail("INVALID_INPUT", "repurposing source slot does not exist")
            parent_hooks = set(parent.get("hook_cycle", parent.get("hook_map", {}).values()))
            if set(slot["hook_map"]) != parent_hooks:
                _fail("INVALID_INPUT", "repurpose hook mapping does not cover its source route")
            if (slot["weekday"] + slot["source_offset_days"]) % 7 != parent["weekday"]:
                _fail(
                    "CONSTRAINT_VIOLATION",
                    "repurpose offset does not resolve to its source weekday",
                )
    return cast(dict[str, Any], _json(_canonical(row)))


def _layout(
    entries: list[dict[str, Any]], policy: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    start = _date(policy["start_date"])
    horizon = [(start + timedelta(days=offset)).isoformat() for offset in range(30)]
    by_id = {entry["entry_id"]: entry for entry in entries}
    if len(by_id) != len(entries):
        _fail("CONSTRAINT_VIOLATION", "calendar entry IDs must be unique")
    for entry in entries:
        if entry["date"] not in horizon:
            _fail("CONSTRAINT_VIOLATION", "entry date is outside the calendar horizon")
        source_id = entry["repurpose_of"]
        if source_id is not None:
            source = by_id.get(source_id)
            if (
                source is None
                or source["date"] >= entry["date"]
                or source["idea_id"] != entry["idea_id"]
                or source["channel"] == entry["channel"]
            ):
                _fail(
                    "CONSTRAINT_VIOLATION",
                    "repurposing must resolve to an earlier same-idea entry on another channel",
                )
    blackouts = {item["date"] for item in policy["blackouts"]}
    days: list[dict[str, Any]] = []
    collisions: list[dict[str, Any]] = []
    for day in horizon:
        selected = sorted(
            (entry for entry in entries if entry["date"] == day), key=lambda item: item["entry_id"]
        )
        commitments = [item for item in policy["existing_commitments"] if item["date"] == day]
        is_flex = _date(day).weekday() in policy["flex_weekdays"]
        kind = (
            "blackout"
            if day in blackouts
            else "flex"
            if is_flex
            else "scheduled"
            if selected
            else "available"
        )
        days.append(
            {
                "date": day,
                "kind": kind,
                "entries": [
                    {key: value for key, value in entry.items() if key != "date"}
                    for entry in selected
                ],
            }
        )
        load = len(selected) + sum(item["units"] for item in commitments)
        kinds = []
        if load and day in blackouts:
            kinds.append("blackout")
        if load and is_flex:
            kinds.append("flex")
        if load > policy["daily_capacity"]:
            kinds.append("capacity")
        for collision in kinds:
            collisions.append(
                {
                    "kind": collision,
                    "date": day,
                    "entry_ids": [entry["entry_id"] for entry in selected],
                    "commitment_ids": [item["id"] for item in commitments],
                    "capacity": policy["daily_capacity"],
                    "load": load,
                }
            )
    return days, collisions


def _schedule(
    context: dict[str, Any], policy: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    hooks = _hooks(context)
    entries: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    slots = policy["weekly_slots"]
    start = _date(policy["start_date"])
    scheduled: dict[tuple[str, str], dict[str, Any]] = {}
    for offset in range(30):
        current = start + timedelta(days=offset)
        day = current.isoformat()
        for slot in slots:
            if slot["weekday"] != current.weekday():
                continue
            parent = None
            if "repurpose_from_slot" in slot:
                source_day = (current + timedelta(days=slot["source_offset_days"])).isoformat()
                parent = scheduled.get((source_day, slot["repurpose_from_slot"]))
                if parent is None:
                    _fail(
                        "CONSTRAINT_VIOLATION", "repurpose source is missing or outside the horizon"
                    )
                hook_id = slot["hook_map"][parent["hook_id"]]
            else:
                occurrence = counts.get(slot["id"], 0)
                hook_id = slot["hook_cycle"][occurrence % len(slot["hook_cycle"])]
                counts[slot["id"]] = occurrence + 1
            idea, hook = hooks[hook_id]
            entry = {
                "entry_id": f"{slot['id']}-{day}",
                "date": day,
                "title": slot["title_by_hook"][hook_id],
                "idea_id": idea["id"],
                "hook_id": hook_id,
                "channel": hook["channel"],
                "format": hook["format"],
                "cta": slot["cta_by_hook"][hook_id],
                "notes": "",
                "repurpose_of": None if parent is None else parent["entry_id"],
            }
            entries.append(entry)
            scheduled[day, slot["id"]] = entry
    if not entries:
        _fail("CONSTRAINT_VIOLATION", "calendar has no scheduled planning entries")
    return _layout(entries, policy)


def _edit(
    days: list[dict[str, Any]], policy: dict[str, Any], changes: Any
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    entries = [dict(entry, date=day["date"]) for day in days for entry in day["entries"]]
    by_id = {entry["entry_id"]: entry for entry in entries}
    seen: set[str] = set()
    for change in _list(changes, 1, max(len(entries), 1)):
        if (
            not isinstance(change, dict)
            or "entry_id" not in change
            or not 2 <= len(change) <= 4
            or not set(change) <= {"entry_id", "date", "cta", "notes"}
        ):
            _fail("INVALID_INPUT", "revision edits may only change date, CTA and notes")
        ident = _text(change["entry_id"], 128)
        if ident in seen or ident not in by_id:
            _fail("INVALID_INPUT", "edit target is unknown or repeated")
        seen.add(ident)
        for key, value in change.items():
            if key == "date":
                _date(value)
            elif key == "cta":
                _text(value, 2048)
            elif key == "notes":
                _text(value, 8192, empty=True)
            if key != "entry_id":
                by_id[ident][key] = value
    return _layout(entries, policy)


def _authority(
    store: Store, wing: str, capability: str = "read", drawer_id: int | None = None
) -> None:
    if isinstance(store, ScopedStore):
        store.authorize(capability, wing=wing, room=_ROOM, drawer_id=drawer_id)


def _ref(value: Any) -> dict[str, Any]:
    try:
        row = _object(value, _REF_KEYS)
        _integer(row["drawer_id"], 1, 2**63 - 1)
        _ident(row["wing"], wing=True)
        _hash(row["content_sha256"])
        if row["room"] != _ROOM or not isinstance(row["portable_identity"], str):
            _fail("CORRUPT_ARTIFACT", "invalid calendar reference scope")
        identity = UUID(row["portable_identity"])
        if str(identity) != row["portable_identity"]:
            _fail("CORRUPT_ARTIFACT", "calendar identity is not canonical")
    except (CalendarError, ValueError) as exc:
        raise CalendarError("CORRUPT_ARTIFACT", "invalid calendar artifact reference") from exc
    return dict(row)


def _read(store: Store, value: Any) -> tuple[dict[str, Any], Drawer, dict[str, Any]]:
    ref = _ref(value)
    _authority(store, ref["wing"], drawer_id=ref["drawer_id"])
    rows = store.list_by(wing=ref["wing"], room=_ROOM, limit=None, include_expired=True)
    drawer = next((row for row in rows if row.id == ref["drawer_id"]), None)
    if drawer is None or store.portable_identity(ref["drawer_id"]) != ref["portable_identity"]:
        _fail("CORRUPT_ARTIFACT", "calendar identity is unavailable or changed")
    if _sha(drawer.content.encode("utf-8")) != ref["content_sha256"]:
        _fail("CORRUPT_ARTIFACT", "calendar artifact bytes have changed")
    core = _json(drawer.content, "CORRUPT_ARTIFACT")
    if (
        not isinstance(core, dict)
        or _canonical(core, "CORRUPT_ARTIFACT").decode("utf-8") != drawer.content
    ):
        _fail("CORRUPT_ARTIFACT", "calendar artifact is not a canonical object")
    if store.get_provenance(ref["drawer_id"]) is None:
        _fail("CORRUPT_ARTIFACT", "calendar artifact has no retained provenance")
    return core, drawer, ref


def _metadata(
    drawer: Drawer, core: dict[str, Any], parents: list[int], previous: int | None = None
) -> None:
    if (
        drawer.metadata != {"kind": core["schema"], "derived_from": parents}
        or drawer.supersedes_id != previous
    ):
        _fail("CORRUPT_ARTIFACT", "calendar dependency metadata or lineage has changed")


def _upstream(store: Store, context: dict[str, Any], *, export: bool = False) -> list[int]:
    if context["kind"] != "i03":
        return []
    try:
        graph = channels._graph(store, context["ref"])
        channels._recheck(store, context["ref"], graph, export=export)
    except channels.ChannelError as exc:
        raise CalendarError("CORRUPT_ARTIFACT", "upstream I03 dependencies changed") from exc
    return [
        context["ref"]["drawer_id"],
        graph["result"]["origin_ref"]["drawer_id"],
        graph["result"]["prepared_ref"]["drawer_id"],
    ]


def _add(
    store: Store, wing: str, core: dict[str, Any], parents: list[int], previous: int | None = None
) -> dict[str, Any]:
    content = _canonical(core).decode("utf-8")
    drawer = store.add(
        Drawer(
            wing=wing,
            room=_ROOM,
            content=content,
            metadata={"kind": core["schema"], "derived_from": parents},
            supersedes_id=previous,
        ),
        provenance=WriteProvenance.create(host="library", capture_path="ideation_calendar"),
    )
    if drawer.id is None:
        _fail("CORRUPT_ARTIFACT", "calendar insert returned no identity")
    return {
        "drawer_id": drawer.id,
        "portable_identity": store.portable_identity(drawer.id),
        "content_sha256": _sha(content.encode("utf-8")),
        "wing": wing,
        "room": _ROOM,
    }


def _receipt(ref: dict[str, Any], core: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "cairntir.calendar-receipt.v1",
        "status": "committed_draft",
        "ref": dict(ref),
        "revision": core["revision"],
        "previous_ref": core["previous_ref"],
        "context": context,
        "policy": core["policy"],
        "days": core["days"],
        "collisions": core["collisions"],
        "replayed": False,
        "projection_status": "not_requested",
        "projection": None,
        "projection_error": None,
    }


def _load(store: Store, value: Any, source_root: PathLike | None) -> dict[str, Any]:
    selected = _ref(value)
    chain: list[tuple[dict[str, Any], Drawer, dict[str, Any]]] = []
    seen: set[int] = set()
    target: dict[str, Any] | None = selected
    keys = {
        "schema",
        "context_ref",
        "previous_ref",
        "revision",
        "policy",
        "changes",
        "days",
        "collisions",
    }
    while target is not None:
        core, drawer, target = _read(store, target)
        _object(core, keys, "CORRUPT_ARTIFACT")
        if (
            target["drawer_id"] in seen
            or target["wing"] != selected["wing"]
            or core["schema"] != "cairntir.calendar-version.v1"
        ):
            _fail("CORRUPT_ARTIFACT", "calendar lineage is cyclic or crosses scope")
        seen.add(target["drawer_id"])
        chain.append((core, drawer, target))
        target = None if core["previous_ref"] is None else _ref(core["previous_ref"])
    context_ref = _ref(chain[0][0]["context_ref"])
    if context_ref["wing"] != selected["wing"]:
        _fail("CORRUPT_ARTIFACT", "calendar context crosses wing scope")
    context_core, context_drawer, context_ref = _read(store, context_ref)
    _object(context_core, {"schema", "context"}, "CORRUPT_ARTIFACT")
    if context_core["schema"] != "cairntir.calendar-context.v1":
        _fail("CORRUPT_ARTIFACT", "calendar context schema is invalid")
    try:
        context = _context(store, context_core["context"], source_root, retained=True)
        parents = _upstream(store, context)
        _metadata(context_drawer, context_core, parents)
        previous_core = None
        previous_ref = None
        versions: list[dict[str, Any]] = []
        for core, drawer, ref in reversed(chain):
            if core["context_ref"] != context_ref:
                _fail("CORRUPT_ARTIFACT", "calendar context changed within its lineage")
            policy = _policy(core["policy"], context)
            _integer(core["revision"], 1, 2**31 - 1)
            if previous_core is None:
                if (
                    core["revision"] != 1
                    or core["previous_ref"] is not None
                    or core["changes"] != []
                ):
                    _fail("CORRUPT_ARTIFACT", "invalid initial calendar version")
                expected_days, expected_collisions = _schedule(context, policy)
            else:
                if (
                    core["revision"] != previous_core["revision"] + 1
                    or core["previous_ref"] != previous_ref
                    or core["policy"] != previous_core["policy"]
                ):
                    _fail("CORRUPT_ARTIFACT", "calendar revision chronology changed")
                expected_days, expected_collisions = _edit(
                    previous_core["days"], policy, core["changes"]
                )
            previous_id: int | None = None if previous_ref is None else previous_ref["drawer_id"]
            _metadata(
                drawer,
                core,
                [context_ref["drawer_id"]] + ([] if previous_id is None else [previous_id]),
                previous_id,
            )
            if core["days"] != expected_days or core["collisions"] != expected_collisions:
                _fail(
                    "CORRUPT_ARTIFACT", "retained calendar differs from its source-bound schedule"
                )
            versions.append({"ref": ref, "core": core})
            previous_core, previous_ref = core, ref
    except CalendarError as exc:
        if exc.code == "CORRUPT_ARTIFACT":
            raise
        raise CalendarError(
            "CORRUPT_ARTIFACT", "saved calendar context or revision is invalid"
        ) from exc
    graph = {
        "context_ref": context_ref,
        "context_core": context_core,
        "context": context,
        "versions": versions,
        "root_ref": versions[0]["ref"],
        "ref": selected,
    }
    _recheck(store, graph)
    return graph


def _recheck(
    store: Store, graph: dict[str, Any], *, export: bool = False, write: bool = False
) -> None:
    refs = [graph["context_ref"], *(version["ref"] for version in graph["versions"])]
    for ref in refs:
        _authority(store, ref["wing"], drawer_id=ref["drawer_id"])
        if export:
            _authority(store, ref["wing"], "export", ref["drawer_id"])
    if export and isinstance(store, ScopedStore):
        visible = {
            drawer.id
            for drawer in store.list_for_export(
                wing=graph["ref"]["wing"], room=_ROOM, limit=None, include_expired=True
            )
        }
        if any(ref["drawer_id"] not in visible for ref in refs):
            _fail("CONFLICT", "calendar dependencies are not exportable")
    if write:
        _authority(store, graph["ref"]["wing"], "write", graph["ref"]["drawer_id"])
    _upstream(store, graph["context"], export=export)


def get_calendar(
    store: Store, ref: dict[str, Any], *, source_root: PathLike | None = None
) -> dict[str, Any]:
    """Verify and return exactly the referenced immutable calendar version."""
    graph = _load(store, ref, source_root)
    return _receipt(graph["ref"], graph["versions"][-1]["core"], graph["context"])


def _key(wing: str, key: Any) -> str:
    key = _text(key, 128)
    if key != key.strip():
        _fail("INVALID_INPUT", "idempotency key has edge whitespace")
    return f"i04:{wing}:{_sha(key.encode('utf-8'))}"


def generate_calendar(
    store: Store,
    *,
    wing: str,
    context: dict[str, Any],
    policy: dict[str, Any],
    source_root: PathLike,
    idempotency_key: str,
) -> dict[str, Any]:
    """Atomically retain a deterministic 30-day draft and its attributed context."""
    if store.transaction_active:
        _fail("INVALID_INPUT", "calendar generation cannot join a caller-owned transaction")
    wing = _ident(wing, wing=True)
    _authority(store, wing)
    _authority(store, wing, "write")
    if source_root is None:
        _fail("INVALID_INPUT", "generation needs a trusted source root")
    context = _context(store, context, source_root)
    if context["kind"] == "i03" and context["ref"]["wing"] != wing:
        _fail("INVALID_INPUT", "I03 context belongs to another wing")
    policy = _policy(policy, context)
    days, collisions = _schedule(context, policy)
    key = _key(wing, idempotency_key)

    def action() -> dict[str, Any]:
        _authority(store, wing)
        _authority(store, wing, "write")
        current = _context(store, context, source_root, retained=True)
        parents = _upstream(store, current)
        context_ref = _add(
            store, wing, {"schema": "cairntir.calendar-context.v1", "context": current}, parents
        )
        ref = _add(
            store,
            wing,
            {
                "schema": "cairntir.calendar-version.v1",
                "context_ref": context_ref,
                "previous_ref": None,
                "revision": 1,
                "policy": policy,
                "changes": [],
                "days": days,
                "collisions": collisions,
            },
            [context_ref["drawer_id"]],
        )
        _recheck(store, _load(store, ref, source_root), write=True)
        return {"ref": ref}

    try:
        with store.transaction():
            execution = store.execute_once(
                idempotency_key=key,
                operation="i04.calendar.generate.v1",
                request={"wing": wing, "context": context, "policy": policy},
                action=action,
            )
            receipt = get_calendar(store, execution.result["ref"], source_root=source_root)
            _authority(store, wing, "write")
    except IdempotencyConflictError as exc:
        raise CalendarError(
            "CONFLICT", "idempotency key is bound to another calendar request"
        ) from exc
    receipt["replayed"] = execution.replayed
    return receipt


def revise_calendar(
    store: Store,
    ref: dict[str, Any],
    *,
    expected_revision: int,
    changes: list[dict[str, Any]],
    idempotency_key: str,
    source_root: PathLike | None = None,
) -> dict[str, Any]:
    """Append a serialized, stale-safe revision changing only dates, CTAs or notes."""
    if store.transaction_active:
        _fail("INVALID_INPUT", "calendar revision cannot join a caller-owned transaction")
    graph = _load(store, ref, source_root)
    ref = graph["ref"]
    core = graph["versions"][-1]["core"]
    _integer(expected_revision, 1, 2**31 - 1)
    if expected_revision != core["revision"]:
        _fail("CONFLICT", "expected revision does not match the selected calendar version")
    changes = cast(list[dict[str, Any]], _json(_canonical(changes)))
    days, collisions = _edit(core["days"], core["policy"], changes)
    _recheck(store, graph, write=True)
    key = _key(ref["wing"], idempotency_key)

    def action() -> dict[str, Any]:
        live = _load(store, ref, source_root)
        _recheck(store, live, write=True)
        if isinstance(store, ScopedStore):
            stale = store.has_direct_successor(ref["drawer_id"])
        else:
            stale = any(
                drawer.supersedes_id == ref["drawer_id"]
                for drawer in store.list_by(limit=None, include_expired=True)
            )
        if stale:
            _fail("CONFLICT", "selected calendar already has a successor")
        revision_ref = _add(
            store,
            ref["wing"],
            {
                "schema": "cairntir.calendar-version.v1",
                "context_ref": live["context_ref"],
                "previous_ref": ref,
                "revision": expected_revision + 1,
                "policy": core["policy"],
                "changes": changes,
                "days": days,
                "collisions": collisions,
            },
            [live["context_ref"]["drawer_id"], ref["drawer_id"]],
            ref["drawer_id"],
        )
        _recheck(store, _load(store, revision_ref, source_root), write=True)
        return {"ref": revision_ref}

    try:
        with store.transaction():
            execution = store.execute_once(
                idempotency_key=key,
                operation="i04.calendar.revise.v1",
                request={"ref": ref, "expected_revision": expected_revision, "changes": changes},
                action=action,
            )
            receipt = get_calendar(store, execution.result["ref"], source_root=source_root)
            _authority(store, ref["wing"], "write", ref["drawer_id"])
    except IdempotencyConflictError as exc:
        raise CalendarError(
            "CONFLICT", "idempotency key is bound to another calendar request"
        ) from exc
    receipt["replayed"] = execution.replayed
    return receipt


def _quoted(value: Any) -> str:
    return channels._note_json(value).replace("<", "\\u003c")


def _display(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("|", "\\|")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def _relative(graph: dict[str, Any]) -> str:
    return f"cairntir-sync/{graph['ref']['wing']}/calendars/{graph['root_ref']['content_sha256']}"


def _render(graph: dict[str, Any], version: dict[str, Any]) -> bytes:
    relative = _relative(graph)
    ref, core = version["ref"], version["core"]
    source = f"{relative}/sources/{graph['context_ref']['content_sha256']}"
    version_path = f"{relative}/versions/{ref['content_sha256']}"
    lines = [
        f"Calendar version: [[{version_path}]]",
        f"Revision: {core['revision']}",
        "",
        _NOTICE,
        "",
        f"Context: [[{source}]]",
        "",
        "| Date | Day | Plan | Format | Call to action | Origins | Repurpose |",
        "|---|---|---|---|---|---|---|",
    ]
    for day in core["days"]:
        if not day["entries"]:
            lines.append(f"| {day['date']} | {day['kind']} | — | — | — | — | — |")
        for entry in day["entries"]:
            origin = f"[[{source}#idea-{entry['idea_id']}]] / [[{source}#hook-{entry['hook_id']}]]"
            parent = (
                "—"
                if entry["repurpose_of"] is None
                else f"[[{version_path}#entry-{entry['repurpose_of']}]]"
            )
            lines.append(
                f"| {day['date']} | {day['kind']} | {_display(entry['title'])} | "
                f"{_display(entry['channel'])}: {_display(entry['format'])} | "
                f"{_display(entry['cta'])} | {origin} | {parent} |"
            )
    lines += ["", "## Collisions", "", _quoted(core["collisions"])]
    for day in core["days"]:
        for entry in day["entries"]:
            lines += [f"## entry-{entry['entry_id']}", "", _quoted(entry)]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _projection_files(graph: dict[str, Any]) -> tuple[dict[str, bytes], dict[str, Any]]:
    relative = _relative(graph)
    source_path = f"{relative}/sources/{graph['context_ref']['content_sha256']}.md"
    lines = ["# Calendar context — provisional", "", _NOTICE, "", _quoted(graph["context_core"])]
    for idea in graph["context"]["ideas"]:
        lines += [
            f"## idea-{idea['id']}",
            "",
            _quoted({key: value for key, value in idea.items() if key != "hooks"}),
        ]
        for hook in idea["hooks"]:
            lines += [f"## hook-{hook['id']}", "", _quoted(hook)]
    files = {source_path: ("\n".join(lines) + "\n").encode("utf-8")}
    for version in graph["versions"]:
        path = f"{relative}/versions/{version['ref']['content_sha256']}.md"
        previous = version["core"]["previous_ref"]
        link = (
            ""
            if previous is None
            else f"\nPrevious revision: [[{relative}/versions/{previous['content_sha256']}]]\n"
        )
        files[path] = (
            "# Calendar version — provisional\n\n".encode()
            + _render(graph, version)
            + link.encode("utf-8")
            + _quoted({"ref": version["ref"], "policy": version["core"]["policy"]}).encode("utf-8")
        )
    calendar_path = f"{relative}/calendar.md"
    selected_path = f"{relative}/versions/{graph['ref']['content_sha256']}.md"
    return files, {
        "calendar_path": calendar_path,
        "version_path": selected_path,
        "source_paths": [source_path],
        "paths": [*files, calendar_path],
    }


def _file(path: Path) -> bytes | None:
    try:
        return channels._file(path)
    except channels.ChannelError as exc:
        raise CalendarError("CONFLICT", str(exc)) from exc


def _current(
    store: Store, graph: dict[str, Any], before: bytes | None, source_root: PathLike | None
) -> bytes:
    rendered = _render(graph, graph["versions"][-1])
    block = _BEGIN + b"\n" + rendered + _END
    if before is None:
        return b"# Calendar\n\n" + block + b"\n\n## My Notes\n"
    if (
        before.count(_BEGIN) != 1
        or before.count(_END) != 1
        or before.index(_BEGIN) > before.index(_END)
    ):
        _fail("CONFLICT", "calendar note is unowned or has ambiguous markers")
    start, end = before.index(_BEGIN), before.index(_END) + len(_END)
    body = before[start + len(_BEGIN) + 1 : end - len(_END)]
    pattern = (
        rb"Calendar version: \[\["
        + re.escape((_relative(graph) + "/versions/").encode("utf-8"))
        + rb"([0-9a-f]{64})\]\]\nRevision: ([1-9][0-9]*)\n"
    )
    match = re.match(pattern, body)
    if match is None:
        _fail("CONFLICT", "calendar generated block is unrecognized or edited")
    digest = match.group(1).decode("ascii")
    ref = None
    for drawer in store.list_by(
        wing=graph["ref"]["wing"], room=_ROOM, limit=None, include_expired=True
    ):
        if drawer.id is not None and _sha(drawer.content.encode("utf-8")) == digest:
            ref = {
                "drawer_id": drawer.id,
                "portable_identity": store.portable_identity(drawer.id),
                "content_sha256": digest,
                "wing": drawer.wing,
                "room": drawer.room,
            }
            break
    if ref is None:
        _fail("CONFLICT", "projected calendar version is not retained")
    previous = _load(store, ref, source_root)
    _recheck(store, previous, export=True)
    old_version = previous["versions"][-1]
    if (
        previous["root_ref"] != graph["root_ref"]
        or old_version["core"]["revision"] > graph["versions"][-1]["core"]["revision"]
    ):
        _fail("CONFLICT", "projection would downgrade or change calendar lineage")
    if body != _render(previous, old_version) or before[start:end] != _BEGIN + b"\n" + body + _END:
        _fail("CONFLICT", "calendar generated block has changed")
    return before[:start] + block + before[end:]


def project_calendar(
    store: Store,
    ref: dict[str, Any],
    *,
    vault_path: PathLike,
    source_root: PathLike | None = None,
) -> dict[str, Any]:
    """Project a selected immutable calendar while preserving every human-owned byte."""
    if store.transaction_active:
        _fail("INVALID_INPUT", "calendar projection cannot join a caller-owned transaction")
    graph = _load(store, ref, source_root)
    _recheck(store, graph, export=True)
    receipt = _receipt(graph["ref"], graph["versions"][-1]["core"], graph["context"])
    try:
        vault = _safe(Path(vault_path), directory=True)
        immutable, projection = _projection_files(graph)
        before = {relative: _file(vault / relative) for relative in projection["paths"]}
        for relative, content in immutable.items():
            if before[relative] is not None and before[relative] != content:
                _fail("CONFLICT", "immutable calendar projection bytes have changed")
        calendar = _current(store, graph, before[projection["calendar_path"]], source_root)
        contents = {**immutable, projection["calendar_path"]: calendar}
        for relative in contents:
            parent = (vault / relative).parent
            for part in reversed((parent, *parent.parents)):
                if part == vault or not part.is_relative_to(vault):
                    continue
                if part.exists():
                    _safe(part, directory=True)
        _recheck(store, graph, export=True)
    except CalendarError:
        raise
    except (OSError, ValueError, TypeError) as exc:
        raise CalendarError("CONFLICT", "calendar projection preflight failed") from exc
    try:
        for relative, content in contents.items():
            path = vault / relative
            for part in reversed((path.parent, *path.parent.parents)):
                if part == vault or not part.is_relative_to(vault):
                    continue
                if not part.exists():
                    _recheck(store, graph, export=True)
                    part.mkdir()
                _safe(part, directory=True)
            _recheck(store, graph, export=True)
            try:
                channels._write(path, content, before[relative])
            except channels.ChannelError as exc:
                raise CalendarError("CONFLICT", str(exc)) from exc
        _recheck(store, graph, export=True)
    except CalendarError:
        raise
    except (OSError, ValueError, TypeError) as exc:
        receipt.update(projection_status="failed", projection_error=str(exc))
        return receipt
    receipt.update(projection_status="ready", projection=projection)
    return receipt
