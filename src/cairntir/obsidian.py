"""One-way, user-note-preserving projection into an Obsidian vault."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from uuid import uuid4

from cairntir.codeglass import CODEGLASS_ROOM
from cairntir.errors import ProjectionError
from cairntir.learning import Discovery, format_discoveries, list_discoveries
from cairntir.memory.store import DrawerStore
from cairntir.provenance import Sensitivity

_BEGIN: Final[str] = "<!-- cairntir:generated:begin -->"
_END: Final[str] = "<!-- cairntir:generated:end -->"
_USER_NOTES: Final[str] = """## My Notes

<!-- Write here. Cairntir never changes text outside its generated block. -->
"""


@dataclass(frozen=True, slots=True)
class ObsidianProjection:
    """Receipt for files created or refreshed in a vault."""

    vault: Path
    learning_log: Path
    codeglass_notes: tuple[Path, ...]
    receipt_notes: tuple[Path, ...]


def project_to_obsidian(
    store: DrawerStore,
    *,
    vault: Path,
    wing: str | None = None,
) -> ObsidianProjection:
    """Project the learning log and CodeGlass notes without ingesting edits."""
    if not (vault / ".obsidian").is_dir():
        raise ProjectionError(f"{vault} is not an Obsidian vault (missing .obsidian)")
    root = vault / "cairntir-sync"
    discoveries = list_discoveries(store, wing=wing, limit=10_000)
    visible_discoveries = [
        item
        for item in discoveries
        if _is_projectable(store, item.drawer_id)
        and item.state in {"candidate", "corroborated", "promoted"}
    ]
    learning_log = root / "learning-log.md"
    _upsert_generated(
        learning_log,
        _learning_log_markdown(visible_discoveries),
        title="Cairntir Human Learning Log",
    )

    codeglass_notes: list[Path] = []
    receipt_ids: set[int] = set()
    walkthroughs = [
        drawer
        for drawer in store.list_by(wing=wing, room=CODEGLASS_ROOM, limit=100_000)
        if drawer.id is not None
        and drawer.metadata.get("kind") == "codeglass.walkthrough"
        and _is_projectable(store, drawer.id)
    ]
    for drawer in walkthroughs:
        drawer_id = drawer.id
        if drawer_id is None:
            raise ProjectionError("stored CodeGlass walkthrough is missing its id")
        target = str(drawer.metadata.get("target", "walkthrough"))
        note = root / "codeglass" / drawer.wing / f"{drawer_id}-{_slug(target)}.md"
        evidence_ids = _evidence_ids(drawer.metadata.get("evidence_drawer_ids"))
        receipt_ids.update(evidence_ids)
        generated = (
            f"Source: [[cairntir-sync/receipts/drawer-{drawer_id}|Drawer #{drawer_id}]]\n\n"
            + drawer.content
            + "\n\n## Evidence receipts\n"
            + "\n".join(
                f"- [[cairntir-sync/receipts/drawer-{item}|Drawer #{item}]]"
                for item in evidence_ids
            )
        )
        _upsert_generated(note, generated, title=f"CodeGlass — {target}")
        codeglass_notes.append(note)
        receipt_ids.add(drawer_id)

    for discovery in visible_discoveries:
        receipt_ids.add(discovery.drawer_id)
        receipt_ids.update(discovery.evidence_ids)
    receipt_notes = tuple(
        _write_receipt(store, root=root, drawer_id=drawer_id)
        for drawer_id in sorted(receipt_ids)
        if _is_projectable(store, drawer_id)
    )
    return ObsidianProjection(
        vault=vault,
        learning_log=learning_log,
        codeglass_notes=tuple(codeglass_notes),
        receipt_notes=receipt_notes,
    )


def _learning_log_markdown(discoveries: list[Discovery]) -> str:
    rendered = format_discoveries(discoveries, heading="Cairntir Human Learning Log")
    for item in discoveries:
        rendered = rendered.replace(
            f"cairntir://drawer/{item.drawer_id}",
            f"[[cairntir-sync/receipts/drawer-{item.drawer_id}|Drawer #{item.drawer_id}]]",
        )
        for evidence_id in item.evidence_ids:
            rendered = rendered.replace(
                f"#{evidence_id}",
                f"[[cairntir-sync/receipts/drawer-{evidence_id}|#{evidence_id}]]",
            )
    return rendered


def _write_receipt(store: DrawerStore, *, root: Path, drawer_id: int) -> Path:
    drawer = store.get(drawer_id)
    if drawer is None:
        raise ProjectionError(f"cannot project missing drawer #{drawer_id}")
    provenance = store.get_provenance(drawer_id)
    if provenance is None:
        raise ProjectionError(f"cannot project drawer #{drawer_id} without provenance")
    note = root / "receipts" / f"drawer-{drawer_id}.md"
    content_hash = hashlib.sha256(drawer.content.encode()).hexdigest()
    generated = "\n".join(
        (
            f"- resource: `cairntir://drawer/{drawer_id}`",
            f"- wing / room: `{drawer.wing}` / `{drawer.room}`",
            f"- layer: `{drawer.layer.value}`",
            f"- created: `{drawer.created_at.isoformat()}`",
            f"- content sha256: `{content_hash}`",
            f"- origin: `{provenance.host}` / `{provenance.model}`",
            f"- trust: `{provenance.trust.value}`",
            "",
            "Full verbatim content remains in SQLite. Use `cairntir get "
            f"{drawer_id}` or `cairntir_get` to inspect it.",
        )
    )
    _upsert_generated(note, generated, title=f"Cairntir Drawer {drawer_id}")
    return note


def _is_projectable(store: DrawerStore, drawer_id: int) -> bool:
    provenance = store.get_provenance(drawer_id)
    return provenance is not None and provenance.sensitivity is not Sensitivity.SECRET


def _evidence_ids(value: object) -> tuple[int, ...]:
    if not isinstance(value, list) or not all(
        isinstance(item, int) and not isinstance(item, bool) and item > 0 for item in value
    ):
        raise ProjectionError("CodeGlass walkthrough has invalid evidence ids")
    return tuple(value)


def _slug(value: str) -> str:
    cleaned = "-".join(re.findall(r"[a-z0-9]+", value.lower()))
    return cleaned[:80] or "walkthrough"


def _upsert_generated(path: Path, generated: str, *, title: str) -> None:
    block = f"{_BEGIN}\n{generated.rstrip()}\n{_END}\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        _atomic_write(path, f"# {title}\n\n{block}\n{_USER_NOTES}")
        return
    try:
        existing = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProjectionError(f"could not read projection {path}: {exc}") from exc
    begin = existing.find(_BEGIN)
    end = existing.find(_END)
    if begin == -1 or end == -1 or end < begin:
        raise ProjectionError(
            f"refusing to overwrite user-owned Obsidian note without complete markers: {path}"
        )
    end += len(_END)
    replacement = existing[:begin] + block.rstrip("\n") + existing[end:]
    if replacement != existing:
        _atomic_write(path, replacement)


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, path)
    except OSError as exc:
        raise ProjectionError(f"could not write projection {path}: {exc}") from exc
    finally:
        if temporary.exists():
            try:
                temporary.unlink()
            except OSError as exc:
                raise ProjectionError(
                    f"could not remove temporary projection {temporary}: {exc}"
                ) from exc
