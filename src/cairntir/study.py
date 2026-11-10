"""Deterministic local study snapshots with explicit export authority."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn
from uuid import UUID, uuid4

from cairntir.access import ScopedStore
from cairntir.errors import CairntirError
from cairntir.memory.store import DrawerStore
from cairntir.provenance import Sensitivity, WriteProvenance

_CATEGORIES = ("patterns", "rules", "walkthroughs", "projects")
_MARKDOWN_LIMIT = 8 * 1024 * 1024
_MANIFEST_LIMIT = 1024 * 1024


class StudyExportError(CairntirError):
    """A study source, snapshot or publication is unavailable or invalid."""


def _refuse(message: str) -> NoReturn:
    raise StudyExportError(message)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _uuid(value: Any) -> str:
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise StudyExportError("study source requires a canonical portable UUID")
    return value


def _name(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 1024:
        raise StudyExportError("study export requires an explicit wing and notebook key")
    return value


def _selection(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict) or set(value) != set(_CATEGORIES):
        raise StudyExportError("study selection requires exactly four categories")
    selected: dict[str, list[str]] = {}
    seen: set[str] = set()
    for category in _CATEGORIES:
        entries = value[category]
        if not isinstance(entries, list) or len(entries) > 1000:
            raise StudyExportError("study category selection must be a UUID list")
        members = [_uuid(entry) for entry in entries]
        if len(set(members)) != len(members) or seen.intersection(members):
            raise StudyExportError("study sources cannot be assigned more than once")
        seen.update(members)
        if len(seen) > 1000:
            raise StudyExportError("study selection exceeds 1000 sources")
        selected[category] = sorted(members)
    return selected


def _safe(path: Path, *, missing: bool = False) -> None:
    for part in (*reversed(path.parents), path):
        try:
            info = part.lstat()
        except FileNotFoundError:
            if missing:
                continue
            raise StudyExportError("study snapshot path is missing") from None
        if (
            part.is_symlink()
            or stat.S_ISLNK(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
            or (stat.S_ISREG(info.st_mode) and info.st_nlink != 1)
        ):
            raise StudyExportError("study paths cannot use links or reparse redirects")
        if part != path and not stat.S_ISDIR(info.st_mode):
            raise StudyExportError("study path parent is not a directory")


def _bytes(path: Path, limit: int) -> bytes:
    _safe(path)
    if not path.is_file() or path.stat().st_size > limit:
        raise StudyExportError("study snapshot file is invalid or exceeds its bound")
    data = path.read_bytes()
    if len(data) > limit:
        raise StudyExportError("study snapshot file exceeds its bound")
    return data


def _json(path: Path) -> dict[str, Any]:
    raw = _bytes(path, _MANIFEST_LIMIT)
    value = json.loads(raw)
    if not isinstance(value, dict) or _canonical(value) != raw:
        raise StudyExportError("study snapshot JSON is not canonical")
    return value


def _source_id(notebook_key: str, wing: str, category: str) -> str:
    return _digest(_canonical(["cairntir.study-source.v1", notebook_key, wing, category]))


def _generation(root: Path, generation: str) -> dict[str, Any]:
    if not isinstance(generation, str) or re.fullmatch(r"[0-9a-f]{64}", generation) is None:
        raise StudyExportError("study generation identity is invalid")
    directory = root / "generations" / generation
    _safe(directory)
    if not directory.is_dir() or {p.name for p in directory.iterdir()} != {
        "manifest.json",
        *(f"{category}.md" for category in _CATEGORIES),
    }:
        raise StudyExportError("study generation must contain exactly five files")
    manifest = _json(directory / "manifest.json")
    if (
        set(manifest) != {"schema", "notebook_key", "wing", "sources"}
        or manifest["schema"] != "cairntir.study-sources.v1"
        or _digest(_canonical(manifest)) != generation
    ):
        raise StudyExportError("study generation manifest identity is invalid")
    wing = _name(manifest["wing"])
    notebook_key = _name(manifest["notebook_key"])
    sources = manifest["sources"]
    if not isinstance(sources, list) or len(sources) != 4:
        raise StudyExportError("study manifest requires four ordered sources")
    paths: dict[str, str] = {}
    selected: dict[str, list[str]] = {}
    total = 0
    for category, source in zip(_CATEGORIES, sources, strict=True):
        if not isinstance(source, dict) or set(source) != {
            "category",
            "source_id",
            "revision",
            "bytes",
            "path",
            "selected",
            "cited",
        }:
            raise StudyExportError("study source manifest entry is invalid")
        if (
            source["category"] != category
            or source["path"] != f"{category}.md"
            or source["source_id"] != _source_id(notebook_key, wing, category)
            or type(source["bytes"]) is not int
            or source["bytes"] < 0
        ):
            raise StudyExportError("study source identity or path is invalid")
        for key in ("selected", "cited"):
            entries = source[key]
            if not isinstance(entries, list) or entries != sorted({_uuid(v) for v in entries}):
                raise StudyExportError("study manifest UUIDs are not sorted and unique")
        if set(source["selected"]).intersection(source["cited"]):
            raise StudyExportError("selected evidence cannot also be cited history")
        selected[category] = source["selected"]
        path = directory / source["path"]
        body = _bytes(path, _MARKDOWN_LIMIT)
        total += len(body)
        if (
            len(body) != source["bytes"]
            or _digest(body) != source["revision"]
            or total > _MARKDOWN_LIMIT
        ):
            raise StudyExportError("study source revision or size is invalid")
        paths[category] = str(path)
    _selection(selected)
    if len({v for row in sources for v in (*row["selected"], *row["cited"])}) > 4000:
        raise StudyExportError("study closure exceeds 4000 records")
    return {"manifest": manifest, "paths": paths}


def _read(root: Path) -> dict[str, Any]:
    _safe(root)
    if not root.is_dir() or {p.name for p in root.iterdir()} - {
        "CURRENT.json",
        "generations",
        ".study.lock",
    }:
        raise StudyExportError("study output contains unowned contents")
    pointer = _json(root / "CURRENT.json")
    if set(pointer) != {"schema", "generation"} or pointer["schema"] != (
        "cairntir.study-current.v1"
    ):
        raise StudyExportError("study pointer is invalid")
    return _generation(root, pointer["generation"])


def read_study_sources(output: Path) -> dict[str, Any]:
    """Validate a stored snapshot, without claiming live store authority."""
    try:
        return _read(Path(output).absolute())
    except StudyExportError:
        raise
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise StudyExportError(f"study snapshot unavailable: {exc}") from exc


def _collect(
    store: DrawerStore | ScopedStore, wing: str, selection: dict[str, list[str]]
) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    records: dict[str, dict[str, Any]] = {}
    local: dict[str, int] = {}
    cited: dict[str, list[str]] = {}

    def source(identity: str, drawer_id: int | None = None) -> dict[str, Any]:
        if identity in records:
            return records[identity]
        if len(records) >= 4000:
            raise StudyExportError("study closure exceeds 4000 records")
        key = store._portable_lookup(identity) if drawer_id is None else drawer_id
        if key is None or store.portable_identity(key) != identity:
            raise StudyExportError("study source unavailable")
        record: dict[str, Any] = json.loads(_canonical(store.portable_source(key)))
        if (
            record["identity"] != identity
            or record["drawer"]["wing"] != wing
            or not isinstance(record["drawer"]["content"], str)
        ):
            raise StudyExportError("study source identity or wing is invalid")
        provenance = WriteProvenance.from_json(json.dumps(record["provenance"]))
        if provenance.sensitivity is Sensitivity.SECRET:
            raise StudyExportError("study source unavailable")
        records[identity] = record
        local[identity] = key
        return record

    for category in _CATEGORIES:
        visited: set[str] = set()
        pending = list(selection[category])
        while pending:
            identity = pending.pop()
            if identity in visited:
                continue
            record = source(identity)
            visited.add(identity)
            relations = store.portable_relations(local[identity])
            if {v["target_identity"] for v in relations} != {
                v["target_identity"] for v in record["references"]
            }:
                raise StudyExportError("study source references changed")
            for relation in relations:
                target = _uuid(relation["target_identity"])
                source(target, relation["target_drawer_id"])
                pending.append(target)
        cited[category] = sorted(visited - set(selection[category]))
    now = datetime.now(UTC)
    for identity in (v for values in selection.values() for v in values):
        provenance = WriteProvenance.from_json(json.dumps(records[identity]["provenance"]))
        if (
            (provenance.valid_from is not None and provenance.valid_from > now)
            or (provenance.valid_until is not None and provenance.valid_until <= now)
            or store.has_export_successor(local[identity])
        ):
            raise StudyExportError("selected study source is not current")
    return records, cited


def _render(
    category: str,
    source_id: str,
    wing: str,
    selected: list[str],
    cited: list[str],
    records: dict[str, dict[str, Any]],
) -> bytes:
    parts = [f"# Study source: {category}\n\nSource ID: {source_id}\nWing: {wing}\n"]
    for label, identities in (("Selected current evidence", selected), ("Cited history", cited)):
        parts.append(f"\n## {label}\n")
        for identity in identities:
            record = records[identity]
            body = record["drawer"]["content"]
            fence = "`" * max(3, max((len(v) + 1 for v in re.findall(r"`+", body)), default=3))
            attribution = {
                "identity": identity,
                "source_store_id": record["source_store_id"],
                "source_drawer_id": record["source_drawer_id"],
                "created_at": record["drawer"]["created_at"],
                "provenance": record["provenance"],
                "references": record["references"],
            }
            parts.append(
                f"\n### {identity}\n\nAuthored date: unknown\n\n"
                f"Attribution: {_canonical(attribution).decode('utf-8')}\n\n"
                f"{fence}text\n{body}\n{fence}\n"
            )
    return "".join(parts).encode("utf-8")


def export_study_sources(
    store: DrawerStore | ScopedStore,
    *,
    wing: str,
    notebook_key: str,
    selection: dict[str, list[str]],
    output: Path,
) -> dict[str, Any]:
    """Publish four local, versioned sources under live export authority."""
    lock: Path | None = None
    temporary: Path | None = None
    descriptor: int | None = None
    try:
        wing, notebook_key = _name(wing), _name(notebook_key)
        selected = _selection(selection)
        root = Path(output).absolute()
        _safe(root, missing=True)
        prior = _read(root) if root.exists() and any(root.iterdir()) else None
        if prior is not None and (
            prior["manifest"]["wing"] != wing or prior["manifest"]["notebook_key"] != notebook_key
        ):
            _refuse("study output belongs to another notebook or wing")
        root.mkdir(parents=True, exist_ok=True)
        _safe(root)
        lock_path = root / ".study.lock"
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        lock = lock_path
        context = store._portable_export() if isinstance(store, ScopedStore) else nullcontext()
        with context:
            records, cited = _collect(store, wing, selected)
            sources: list[dict[str, Any]] = []
            payloads: dict[str, bytes] = {}
            total = 0
            for category in _CATEGORIES:
                source_id = _source_id(notebook_key, wing, category)
                body = _render(
                    category, source_id, wing, selected[category], cited[category], records
                )
                total += len(body)
                if total > _MARKDOWN_LIMIT:
                    _refuse("study Markdown exceeds 8MiB")
                filename = f"{category}.md"
                payloads[filename] = body
                sources.append(
                    {
                        "category": category,
                        "source_id": source_id,
                        "revision": _digest(body),
                        "bytes": len(body),
                        "path": filename,
                        "selected": selected[category],
                        "cited": cited[category],
                    }
                )
            manifest = {
                "schema": "cairntir.study-sources.v1",
                "notebook_key": notebook_key,
                "wing": wing,
                "sources": sources,
            }
            manifest_bytes = _canonical(manifest)
            if len(manifest_bytes) > _MANIFEST_LIMIT:
                _refuse("study manifest exceeds 1MiB")
            generation = _digest(manifest_bytes)
            directory = root / "generations" / generation
            _safe(directory, missing=True)
            if directory.exists():
                _generation(root, generation)
            else:
                directory.parent.mkdir(exist_ok=True)
                stage = directory.parent / f".stage-{uuid4()}"
                stage.mkdir()
                for filename, data in {**payloads, "manifest.json": manifest_bytes}.items():
                    with (stage / filename).open("xb") as handle:
                        handle.write(data)
                        handle.flush()
                        os.fsync(handle.fileno())
                os.rename(stage, directory)
                _generation(root, generation)
            if _collect(store, wing, selected) != (records, cited):
                _refuse("study sources changed before publication")
        _safe(root)
        current = _read(root) if prior is not None else None
        if current != prior:
            _refuse("study pointer changed during publication")
        unchanged = prior is not None and prior["manifest"] == manifest
        if not unchanged:
            temporary = root / f".current-{uuid4()}.json"
            temporary.write_bytes(
                _canonical({"schema": "cairntir.study-current.v1", "generation": generation})
            )
            os.replace(temporary, root / "CURRENT.json")
        paths = {category: str(directory / f"{category}.md") for category in _CATEGORIES}
        previous = (
            {row["category"]: row["revision"] for row in prior["manifest"]["sources"]}
            if prior is not None
            else {}
        )
        return {
            "schema": "cairntir.study-export-receipt.v1",
            "status": "UNCHANGED" if unchanged else "PUBLISHED",
            "generation": generation,
            "sources": [{**row, "path": paths[row["category"]]} for row in sources],
            "changes": {
                row["category"]: (
                    "added"
                    if row["category"] not in previous
                    else "unchanged"
                    if previous[row["category"]] == row["revision"]
                    else "updated"
                )
                for row in sources
            },
            "validated_at": datetime.now(UTC).isoformat(),
            "notebooklm": {"status": "UNVERIFIED"},
        }
    except StudyExportError:
        raise
    except (CairntirError, OSError, ValueError, TypeError, KeyError) as exc:
        raise StudyExportError(f"study export refused: {exc}") from exc
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
        if descriptor is not None:
            os.close(descriptor)
        if lock is not None:
            lock.unlink()
