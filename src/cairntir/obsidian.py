"""One-way, user-note-preserving projection into an Obsidian vault."""

from __future__ import annotations

import hashlib
import html
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final
from uuid import uuid4

from cairntir.access import AccessDenied
from cairntir.codeglass import (
    CHECK_REPORT_SCHEMA,
    CODEGLASS_ROOM,
    HUMANFLOW_SCHEMA,
    PracticeRegisterSnapshot,
    build_practice_register,
)
from cairntir.errors import CairntirError, ProjectionError
from cairntir.learning import Discovery, format_discoveries, list_discoveries
from cairntir.memory.store import DrawerStore
from cairntir.procedures import ProcedureBook, practice_read_view
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
    learning_log: Path | None
    codeglass_notes: tuple[Path, ...]
    receipt_notes: tuple[Path, ...]
    practice_register_note: Path | None = None
    practice_history_notes: tuple[Path, ...] = ()
    practice_register_status: str | None = None


def project_to_obsidian(
    store: DrawerStore,
    *,
    vault: Path,
    wing: str | None = None,
    practice_register: bool = False,
    as_of: str | None = None,
) -> ObsidianProjection:
    """Project the learning log and CodeGlass notes without ingesting edits."""
    if not (vault / ".obsidian").is_dir():
        raise ProjectionError(f"{vault} is not an Obsidian vault (missing .obsidian)")
    root = vault.resolve() / "cairntir-sync"
    if practice_register:
        if not isinstance(wing, str) or not wing.strip():
            raise ProjectionError("practice register requires an explicit wing")
        return _project_practice_workspace(
            store,
            vault=vault,
            root=root,
            wing=wing,
            as_of=as_of if as_of is not None else datetime.now(UTC).date().isoformat(),
        )
    discoveries = list_discoveries(store, wing=wing, limit=None)
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
        root=root,
    )

    codeglass_notes: list[Path] = []
    receipt_ids: set[int] = set()
    walkthroughs = [
        drawer
        for drawer in store.list_by(wing=wing, room=CODEGLASS_ROOM, limit=None)
        if drawer.id is not None
        and drawer.metadata.get("kind") == "codeglass.walkthrough"
        and (
            (
                drawer.metadata.get("check_report_schema") == CHECK_REPORT_SCHEMA
                or drawer.metadata.get("humanflow_schema") == HUMANFLOW_SCHEMA
            )
            or _is_projectable(store, drawer.id)
        )
    ]
    current_ids = {drawer.id for drawer in walkthroughs}
    walkthroughs.extend(
        drawer
        for drawer in store.list_by(
            wing=wing, room=CODEGLASS_ROOM, limit=None, include_expired=True
        )
        if drawer.id is not None
        and drawer.id not in current_ids
        and drawer.metadata.get("kind") == "codeglass.walkthrough"
        and (
            drawer.metadata.get("check_report_schema") == CHECK_REPORT_SCHEMA
            or drawer.metadata.get("humanflow_schema") == HUMANFLOW_SCHEMA
        )
    )
    for drawer in walkthroughs:
        drawer_id = drawer.id
        if drawer_id is None:
            raise ProjectionError("stored CodeGlass walkthrough is missing its id")
        target = str(drawer.metadata.get("target", "walkthrough"))
        note = root / "codeglass" / _slug(drawer.wing) / f"{drawer_id}-{_slug(target)}.md"
        evidence_ids = _evidence_ids(drawer.metadata.get("evidence_drawer_ids"))
        if (
            drawer.metadata.get("check_report_schema") == CHECK_REPORT_SCHEMA
            or drawer.metadata.get("humanflow_schema") == HUMANFLOW_SCHEMA
        ) and (
            not _check_source_projectable(store, drawer_id, drawer.wing)
            or not all(_check_source_projectable(store, item, drawer.wing) for item in evidence_ids)
        ):
            _upsert_generated(
                note,
                "Check report unavailable: source evidence can no longer be projected.",
                title="CodeGlass — unavailable check report",
                root=root,
            )
            codeglass_notes.append(note)
            continue
        generated = (
            f"Source: [[cairntir-sync/receipts/drawer-{drawer_id}|Drawer #{drawer_id}]]\n\n"
            + drawer.content
            + "\n\n## Evidence receipts\n"
            + "\n".join(
                f"- [[cairntir-sync/receipts/drawer-{item}|Drawer #{item}]]"
                for item in evidence_ids
            )
        )
        if drawer.metadata.get("humanflow_schema") == HUMANFLOW_SCHEMA and (
            not _check_source_projectable(store, drawer_id, drawer.wing)
            or not all(_check_source_projectable(store, item, drawer.wing) for item in evidence_ids)
        ):
            _upsert_generated(
                note,
                "Check report unavailable: source evidence can no longer be projected.",
                title="CodeGlass — unavailable check report",
                root=root,
            )
            codeglass_notes.append(note)
            continue
        _upsert_generated(note, generated, title=f"CodeGlass — {target}", root=root)
        receipt_ids.update(evidence_ids)
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
    ids = {str(item.drawer_id) for item in discoveries}
    ids.update(str(evidence_id) for item in discoveries for evidence_id in item.evidence_ids)

    def link(match: re.Match[str]) -> str:
        drawer_id = match.group(1) or match.group(2)
        if drawer_id not in ids:
            return match.group(0)
        label = f"Drawer #{drawer_id}" if match.group(1) else f"#{drawer_id}"
        return f"[[cairntir-sync/receipts/drawer-{drawer_id}|{label}]]"

    return re.sub(r"cairntir://drawer/(\d+)\b|#(\d+)\b", link, rendered)


def _write_receipt(
    store: DrawerStore, *, root: Path, drawer_id: int, publisher: str | None = None
) -> Path:
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
    if publisher is not None:
        if note.exists() and not _practice_receipt_owned(note, root=root, publisher=publisher):
            raise ProjectionError("practice receipt path is already owned by another publication")
        generated = f"- publisher: practice-register:{publisher}\n" + generated
    _upsert_generated(
        note,
        generated,
        title="Cairntir evidence receipt" if publisher else f"Cairntir Drawer {drawer_id}",
        root=root,
    )
    return note


def _is_projectable(store: DrawerStore, drawer_id: int) -> bool:
    provenance = store.get_provenance(drawer_id)
    return provenance is not None and provenance.sensitivity is not Sensitivity.SECRET


def _check_source_projectable(store: DrawerStore, drawer_id: int, wing: str) -> bool:
    try:
        drawer = store.get(drawer_id)
        provenance = store.get_provenance(drawer_id)
    except AccessDenied:
        return False
    now = datetime.now(UTC)
    return (
        drawer is not None
        and drawer.wing == wing
        and provenance is not None
        and provenance.sensitivity is not Sensitivity.SECRET
        and (provenance.valid_from is None or provenance.valid_from <= now)
        and (provenance.valid_until is None or provenance.valid_until > now)
    )


def _evidence_ids(value: object) -> tuple[int, ...]:
    if not isinstance(value, list) or not all(
        isinstance(item, int) and not isinstance(item, bool) and item > 0 for item in value
    ):
        raise ProjectionError("CodeGlass walkthrough has invalid evidence ids")
    return tuple(value)


def _slug(value: str) -> str:
    cleaned = "-".join(re.findall(r"[a-z0-9]+", value.lower()))
    return cleaned[:80] or "walkthrough"


def _upsert_generated(path: Path, generated: str, *, title: str, root: Path) -> None:
    if not path.resolve().is_relative_to(root):
        raise ProjectionError(f"projection path escapes the owned output tree: {path}")
    if _BEGIN in generated or _END in generated or _BEGIN in title or _END in title:
        raise ProjectionError(f"projection content contains reserved generated markers: {path}")
    block = f"{_BEGIN}\n{generated.rstrip()}\n{_END}\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        _atomic_write(path, f"# {title}\n\n{block}\n{_USER_NOTES}")
        return
    try:
        with path.open(encoding="utf-8", newline="") as stream:
            existing = stream.read()
    except (OSError, UnicodeError) as exc:
        raise ProjectionError(f"could not read projection {path}: {exc}") from exc
    begin = existing.find(_BEGIN)
    end = existing.find(_END)
    if existing.count(_BEGIN) != 1 or existing.count(_END) != 1 or end < begin:
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
        temporary.write_text(content, encoding="utf-8", newline="")
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


def _practice_directory(root: Path, wing: str) -> Path:
    directory = root / "codeglass" / "practices" / hashlib.sha256(wing.encode("utf-8")).hexdigest()
    if not directory.resolve().is_relative_to(root):
        raise ProjectionError("practice projection path escapes the owned output tree")
    return directory


def _practice_generated(path: Path, *, root: Path) -> str:
    if not path.resolve().is_relative_to(root):
        raise ProjectionError("practice projection path escapes the owned output tree")
    text = path.read_text(encoding="utf-8")
    begin, end = text.find(_BEGIN), text.find(_END)
    if text.count(_BEGIN) != 1 or text.count(_END) != 1 or end < begin:
        raise ProjectionError("practice note has incomplete generated markers")
    return text[begin + len(_BEGIN) : end]


def _practice_receipt_owned(path: Path, *, root: Path, publisher: str) -> bool:
    generated = _practice_generated(path, root=root)
    return f"- publisher: practice-register:{publisher}" in generated.splitlines()


def _practice_receipt_paths(directory: Path, *, root: Path) -> set[Path]:
    register = directory / "register.md"
    if not register.exists():
        return set()
    generated = _practice_generated(register, root=root)
    return {
        root / "receipts" / f"drawer-{drawer_id}.md"
        for drawer_id in re.findall(
            r"\[\[cairntir-sync/receipts/drawer-(\d+)(?:\||\]\])", generated
        )
    }


def _invalidate_practice_receipts(paths: set[Path], *, directory: Path, root: Path) -> None:
    for path in sorted(paths):
        if path.exists() and _practice_receipt_owned(path, root=root, publisher=directory.name):
            _upsert_generated(
                path,
                f"- publisher: practice-register:{directory.name}\n"
                "Practice evidence unavailable in the current snapshot.",
                title="Cairntir evidence receipt",
                root=root,
            )


def _invalidate_practice_notes(directory: Path, *, root: Path, receipt_paths: set[Path]) -> None:
    receipt_paths = receipt_paths | _practice_receipt_paths(directory, root=root)
    _invalidate_practice_receipts(receipt_paths, directory=directory, root=root)
    paths = {directory / "register.md", *directory.glob("revision-*.md")}
    for path in sorted(paths):
        _upsert_generated(
            path,
            "Practice register unavailable: source evidence cannot be projected.",
            title="CodeGlass practice evidence",
            root=root,
        )


def _practice_register_markdown(
    snapshot: PracticeRegisterSnapshot, directory: Path, vault: Path
) -> str:
    def cell(value: object) -> str:
        text = html.escape("UNKNOWN" if value is None else str(value), quote=True)
        for character in "|`[]()":
            text = text.replace(character, f"&#{ord(character)};")
        return text.replace("\r", "").replace("\n", "<br>")

    def link(path: Path, label: str) -> str:
        return f"[[{path.relative_to(vault.resolve()).with_suffix('').as_posix()}|{label}]]"

    lines = [
        "# CodeGlass practice register",
        f"Wing: {cell(snapshot.wing)}; snapshot date: {snapshot.as_of}.",
        "SQLite is authoritative. This snapshot neither changes practices nor completes reviews.",
        "Attributed owners are labels, not proof of identity or approval.",
        "",
        "| Practice | Status | Attributed owner | Version | Change rationale | "
        "Review due | Review evidence | History |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in snapshot.rows:
        history = ", ".join(
            link(directory / f"revision-{rev.drawer_id}.md", f"#{rev.drawer_id}")
            for rev in row.history
        )
        review = (
            f"[[cairntir-sync/receipts/drawer-{row.review_id}|Recorded review]]"
            if row.review_id is not None
            else "No completed review recorded"
        )
        deadline = cell(row.review_due)
        if row.due is not None:
            deadline += " (due)" if row.due else " (not due)"
        lines.append(
            f"| {cell(row.title)} | `{row.status}` | {cell(row.owner)} | {cell(row.version)} | "
            f"{cell(row.rationale)} | {deadline} | {review} | {history} |"
        )
    if any(row.status == "active_governance_incomplete" for row in snapshot.rows):
        lines.extend(
            (
                "",
                "Governance incomplete. Opt in through ProcedureBook.revise, evaluate and "
                "operator-approved promote; missing values are not inferred.",
            )
        )
    elif any(row.status == "active" for row in snapshot.rows):
        lines.extend(
            (
                "",
                "Every active practice in this snapshot has governance; "
                "a due date alone is not evidence of revalidation.",
            )
        )
    else:
        lines.extend(("", "No current promoted practices."))
    if snapshot.conflicts:
        lines.extend(
            (
                "",
                "## Practice conflicts",
                "Severity precedes context specificity. Unresolved ties require a developer ADR; "
                "an attributed comparison is not human approval. "
                "Stale comparisons select no current winner.",
                "",
                "| First rule | Severity / context | Second rule | Severity / context | "
                "Situation | Status | Winner / basis | Origin | "
                "Conflict receipt | Source evidence |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            )
        )
        for conflict in snapshot.conflicts:
            first = link(directory / f"revision-{conflict.first_id}.md", cell(conflict.first_title))
            second = link(
                directory / f"revision-{conflict.second_id}.md", cell(conflict.second_title)
            )
            evidence = ", ".join(
                f"[[cairntir-sync/receipts/drawer-{key}|#{key}]]" for key in conflict.source_ids
            )
            winner = (
                f"#{conflict.winner_id} / {cell(conflict.basis)}"
                if conflict.winner_id is not None
                else "None / developer ADR required"
                if conflict.status == "adr_required"
                else "None / stale comparison"
            )
            lines.append(
                f"| {first} | {conflict.first_severity} / "
                f"{cell(', '.join(conflict.first_context))} | "
                f"{second} | {conflict.second_severity} / "
                f"{cell(', '.join(conflict.second_context))} | "
                f"{cell(', '.join(conflict.situation))} | {conflict.status} | {winner} | "
                f"{cell(conflict.origin)} | "
                f"[[cairntir-sync/receipts/drawer-{conflict.conflict_id}|Recorded comparison]] | "
                f"{evidence} |"
            )
    if any(row.lifecycle for row in snapshot.rows):
        lines.extend(
            (
                "",
                "## Practice lifecycle",
                "Experimental practices inform at P3. Validation is evidence, not activation. "
                "Active practices require governance and the existing operator-approved promotion. "
                "Deprecated practices only inform; retired practices leave active scans.",
                "",
                "| Practice | Phase | Assigned tier | Effective tier | Mode | "
                "Original phase history | Evidence |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            )
        )
        for row in snapshot.rows:
            if not row.lifecycle:
                continue
            phases = ", ".join(
                f"[[cairntir-sync/receipts/drawer-{event.drawer_id}|{event.state} "
                f"at {cell(event.recorded_at)}]]"
                for event in row.lifecycle
            )
            evidence = ", ".join(
                f"[[cairntir-sync/receipts/drawer-{key}|#{key}]]"
                for key in sorted({key for event in row.lifecycle for key in event.evidence_ids})
            )
            lines.append(
                f"| {cell(row.title)} | {cell(row.status)} | {cell(row.assigned_tier)} | "
                f"{cell(row.effective_tier)} | {cell(row.mode)} | {phases} | {evidence} |"
            )
    if snapshot.supersessions:
        lines.extend(
            (
                "",
                "## Contextual replacements",
                "Original wording, applicability, reasons and sources remain in revision history. "
                "A replacement masks the older rule only in the declared context; "
                "a restoration appends new evidence without deleting either rule.",
                "",
                "| Original rule | Successor | Context | Status | Recorded at | "
                "Reason | Evidence |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            )
        )
        for event in snapshot.supersessions:
            evidence = ", ".join(
                f"[[cairntir-sync/receipts/drawer-{key}|#{key}]]" for key in event.evidence_ids
            )
            older = link(directory / f"revision-{event.older_id}.md", f"#{event.older_id}")
            successor = link(
                directory / f"revision-{event.replacement_id}.md", f"#{event.replacement_id}"
            )
            lines.append(
                f"| {older} | {successor} | "
                f"{cell(', '.join(event.context))} | "
                f"[[cairntir-sync/receipts/drawer-{event.drawer_id}|{event.status}]] | "
                f"{cell(event.recorded_at)} | {cell(event.rationale)} | {evidence} |"
            )
    return "\n".join(lines)


def _project_practice_workspace(
    store: DrawerStore,
    *,
    vault: Path,
    root: Path,
    wing: str,
    as_of: str,
) -> ObsidianProjection:
    directory = _practice_directory(root, wing)
    register = directory / "register.md"
    view = practice_read_view(store)
    receipt_paths: set[Path] = set()
    try:
        previous_receipts = _practice_receipt_paths(directory, root=root)
        with ProcedureBook(view, {}).complete_history(wing=wing):
            snapshot = build_practice_register(view, wing=wing, as_of=as_of)
            receipt_paths = {
                root / "receipts" / f"drawer-{row.review_id}.md"
                for row in snapshot.rows
                if row.review_id is not None
            }
            conflict_receipts = {
                key
                for conflict in snapshot.conflicts
                for key in (conflict.conflict_id, *conflict.source_ids)
            }
            lifecycle_receipts = {
                key
                for row in snapshot.rows
                for event in row.lifecycle
                for key in (event.drawer_id, *event.evidence_ids)
            }
            supersession_receipts = {
                key
                for event in snapshot.supersessions
                for key in (event.drawer_id, *event.evidence_ids)
            }
            conflict_receipts.update(lifecycle_receipts | supersession_receipts)
            receipt_paths.update(
                root / "receipts" / f"drawer-{key}.md" for key in conflict_receipts
            )
            for key in sorted(conflict_receipts):
                _write_receipt(view, root=root, drawer_id=key, publisher=directory.name)
            history_notes: list[Path] = []
            for row in snapshot.rows:
                for revision in row.history:
                    note = directory / f"revision-{revision.drawer_id}.md"
                    longest = max(
                        (len(match.group()) for match in re.finditer(r"`+", revision.content)),
                        default=0,
                    )
                    fence = "`" * max(3, longest + 1)
                    fields = (
                        ("Attributed owner", revision.owner),
                        ("Version", revision.version),
                        ("Change rationale", revision.rationale),
                        ("Review due", revision.review_due),
                    )
                    governance = [
                        f"{label}: {html.escape('UNKNOWN' if value is None else value)}"
                        for label, value in fields
                    ]
                    generated = "\n".join(
                        (
                            f"Recorded state: {revision.state}",
                            f"Drawer: cairntir://drawer/{revision.drawer_id}",
                            f"Predecessor: {revision.supersedes_id}",
                            f"Revision SHA256: {revision.revision_sha256}",
                            f"Content SHA256: {revision.content_sha256}",
                            f"Metadata SHA256: {revision.metadata_sha256}",
                            *governance,
                            "",
                            "Complete original content:",
                            fence + "text",
                            revision.content,
                            fence,
                        )
                    )
                    _upsert_generated(
                        note, generated, title="CodeGlass practice revision", root=root
                    )
                    history_notes.append(note)
                if row.review_id is not None:
                    _write_receipt(
                        view, root=root, drawer_id=row.review_id, publisher=directory.name
                    )
            current_notes = set(history_notes)
            for stale in directory.glob("revision-*.md"):
                if stale not in current_notes:
                    _upsert_generated(
                        stale,
                        "Practice evidence unavailable in the current snapshot.",
                        title="CodeGlass practice revision",
                        root=root,
                    )
            _invalidate_practice_receipts(
                previous_receipts - receipt_paths, directory=directory, root=root
            )
            _upsert_generated(
                register,
                _practice_register_markdown(snapshot, directory, vault),
                title="CodeGlass practice register",
                root=root,
            )
        return ObsidianProjection(
            vault=vault,
            learning_log=None,
            codeglass_notes=(),
            receipt_notes=tuple(sorted(receipt_paths)),
            practice_register_note=register,
            practice_history_notes=tuple(history_notes),
            practice_register_status="published",
        )
    except (CairntirError, OSError, ValueError):
        try:
            _invalidate_practice_notes(directory, root=root, receipt_paths=receipt_paths)
        except (CairntirError, OSError, ValueError):
            raise ProjectionError(
                "practice register unavailable; owned notes could not be invalidated"
            ) from None
        return ObsidianProjection(
            vault=vault,
            learning_log=None,
            codeglass_notes=(),
            receipt_notes=(),
            practice_register_note=register,
            practice_register_status="unavailable",
        )
