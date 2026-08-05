"""Obsidian vault -> Cairntir ingest: the other half of the sync.

``obsidian.py`` projects Cairntir OUT to a vault. Nothing ever read the vault
back IN, and nothing noticed for four months while 36 walkthroughs sat outside
the store. This module is that missing direction, and it lives here — not in a
loose script — so it has a CLI command, a ``--check`` mode, and tests. A script
nobody runs drifts back out of sync exactly as its predecessor did.

Two operations, deliberately separate:

* :func:`plan_sync` reads only. It answers "which vault walkthroughs have no
  drawer?" and is what ``--check`` reports on.
* :func:`apply_sync` writes the missing ones and nothing else.

Idempotent: a ``(wing, room)`` pair already in the store is skipped, so
re-running is safe. Retroactive: ``created_at`` comes from the walkthrough's own
filename date, not today, so the store gains real history rather than a wall of
drawers all stamped at import time.

The vault is named by the caller — ``--vault`` or ``$CAIRNTIR_VAULT``. There is
no baked-in path. The target store is whatever ``$CAIRNTIR_HOME`` selects, so a
run can be rehearsed against a copy before it touches the live store.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from cairntir.errors import CairntirError
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer, Layer

# Vault folder -> Cairntir wing slug. Matches wings already in the store.
# A folder absent from this map is not synced: guessing a wing would mint a
# duplicate corpus under a near-miss name, which is worse than not importing.
WING_MAP: Final[dict[str, str]] = {
    "GetKith": "getkith",
    "Ground Zero": "ground-zero",
    "IntakeForms": "intake-forms",
    "Triangulate": "triangulate",
    "examples": "codeglass",
}

WALKTHROUGH_KIND: Final[str] = "obsidian_walkthrough"
IMPORTER: Final[str] = "cairntir.vault"

_DATED = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)$")


class VaultSyncError(CairntirError):
    """Raised when a vault cannot be located or is not an Obsidian vault.

    Typed and surfaced rather than a bare ``SystemExit`` so the CLI, the tests,
    and any future caller all fail the same way with the same message.
    """


@dataclass(frozen=True, slots=True)
class VaultWalkthrough:
    """One vault note, and the drawer it would become."""

    source: Path
    vault_folder: str
    wing: str
    room: str
    content: str
    created_at: datetime
    task_slug: str

    def metadata(self, *, imported_at: str) -> dict[str, Any]:
        """Build the drawer metadata recording where this note came from."""
        return {
            "kind": WALKTHROUGH_KIND,
            "source_path": str(self.source),
            "vault_folder": self.vault_folder,
            "task_slug": self.task_slug,
            "imported_at": imported_at,
            "importer": IMPORTER,
            "note": (
                "Retroactive import. Authored on created_at; reached Cairntir later "
                "because the vault->store direction of sync-conventions.md was never built."
            ),
        }

    def to_drawer(self, *, imported_at: str) -> Drawer:
        """Render this walkthrough as an unsaved :class:`Drawer`."""
        return Drawer(
            wing=self.wing,
            room=self.room,
            content=self.content,
            layer=Layer.DEEP,
            metadata=self.metadata(imported_at=imported_at),
            created_at=self.created_at,
        )


@dataclass(frozen=True, slots=True)
class VaultSyncPlan:
    """What a sync would do. Read-only; produced by :func:`plan_sync`."""

    vault: Path
    found: tuple[VaultWalkthrough, ...]
    missing: tuple[VaultWalkthrough, ...]

    @property
    def present(self) -> int:
        """How many vault walkthroughs already have a drawer."""
        return len(self.found) - len(self.missing)

    @property
    def has_drift(self) -> bool:
        """True when a vault note exists with no corresponding drawer."""
        return bool(self.missing)

    def counts_by_wing(self) -> dict[str, int]:
        """Total walkthroughs found, per wing, wing-sorted."""
        counts: dict[str, int] = {}
        for item in self.found:
            counts[item.wing] = counts.get(item.wing, 0) + 1
        return dict(sorted(counts.items()))


def resolve_vault(value: Path | str | None) -> Path:
    """Expand and validate a vault path, or raise :class:`VaultSyncError`.

    Args:
        value: The path given by ``--vault`` or ``$CAIRNTIR_VAULT``. ``None``
            means neither was supplied.

    Returns:
        The expanded vault path, confirmed to carry an ``.obsidian`` marker.

    Raises:
        VaultSyncError: No path was given, or the path is not an Obsidian vault.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        raise VaultSyncError("no vault given: pass --vault or set CAIRNTIR_VAULT")
    vault = Path(value).expanduser()
    if not vault.is_dir():
        raise VaultSyncError(f"{vault} is not a directory")
    if not (vault / ".obsidian").is_dir():
        raise VaultSyncError(f"{vault} is not an Obsidian vault (missing .obsidian)")
    return vault


def parse_name(stem: str) -> tuple[datetime | None, str]:
    """Split ``'2026-03-30-pipeline-audit'`` into its date and task slug."""
    match = _DATED.match(stem)
    if match is None:
        return None, stem
    try:
        when = datetime.strptime(match.group(1), "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        # A well-shaped but impossible date (2026-02-31). Fall back to the
        # file's mtime rather than guessing a nearby day.
        return None, stem
    return when, match.group(2)


def room_for(stem: str, *, wing: str) -> str:
    """Derive a valid room identifier from a vault filename stem.

    Rooms must match ``^[a-z0-9][a-z0-9._:-]{0,62}[a-z0-9]$`` — lowercase and
    at most 64 characters — so the stem is lowercased, non-conforming runs are
    collapsed to ``-``, and the result is trimmed at both ends.
    """
    prefix = "example" if wing == "codeglass" else "walkthrough"
    room = re.sub(r"[^a-z0-9._:-]+", "-", f"{prefix}-{stem}".lower())
    return room.strip("-.:_")[:64].rstrip("-.:_")


def collect(vault: Path) -> list[VaultWalkthrough]:
    """Read every mapped walkthrough out of the vault, sorted deterministically.

    Empty notes are skipped: a drawer with no content is noise, and the store
    rejects whitespace content anyway.
    """
    items: list[VaultWalkthrough] = []
    for folder, wing in sorted(WING_MAP.items()):
        base = vault / "walkthroughs" / folder
        if not base.is_dir():
            continue
        for path in sorted(base.glob("*.md")):
            try:
                text = path.read_text(encoding="utf-8", errors="replace").strip()
                mtime = path.stat().st_mtime
            except OSError as exc:
                raise VaultSyncError(f"could not read vault note {path}: {exc}") from exc
            if not text:
                continue
            when, slug = parse_name(path.stem)
            items.append(
                VaultWalkthrough(
                    source=path,
                    vault_folder=folder,
                    wing=wing,
                    room=room_for(path.stem, wing=wing),
                    content=text,
                    created_at=when or datetime.fromtimestamp(mtime, tz=UTC),
                    task_slug=slug,
                )
            )
    return items


def plan_sync(store: DrawerStore, vault: Path) -> VaultSyncPlan:
    """Compare the vault against the store. Reads only; writes nothing."""
    found = collect(vault)
    existing: set[tuple[str, str]] = set()
    for wing in sorted({item.wing for item in found}):
        for drawer in store.list_by(wing=wing, limit=100_000):
            existing.add((drawer.wing, drawer.room))
    missing = tuple(item for item in found if (item.wing, item.room) not in existing)
    return VaultSyncPlan(vault=vault, found=tuple(found), missing=missing)


def apply_sync(
    store: DrawerStore,
    plan: VaultSyncPlan,
    *,
    model: str | None = None,
) -> tuple[Drawer, ...]:
    """Write the drawers named by ``plan.missing`` and return them, saved.

    ``model`` records which model ran the import, per the per-write provenance
    contract. Nothing else in the plan is touched — walkthroughs already in the
    store are never rewritten.
    """
    imported_at = datetime.now(UTC).date().isoformat()
    written = [
        store.add(item.to_drawer(imported_at=imported_at), model=model) for item in plan.missing
    ]
    if written:
        store.checkpoint()
    return tuple(written)


def render_plan(plan: VaultSyncPlan, *, check: bool, sample: int = 5) -> str:
    """Render a plan as the text the CLI prints.

    Args:
        plan: The comparison to describe.
        check: True when rendering for ``--check``, which frames unimported
            walkthroughs as drift rather than as pending work.
        sample: How many missing walkthroughs to name before summarising.
    """
    lines = [
        f"vault: {plan.vault}",
        f"walkthroughs found: {len(plan.found)}",
    ]
    lines.extend(f"   {wing:16s} {count:3d}" for wing, count in plan.counts_by_wing().items())
    lines.append(f"already in the store: {plan.present}   without a drawer: {len(plan.missing)}")

    if plan.missing:
        for item in plan.missing[:sample]:
            lines.append(
                f"  {item.wing}/{item.room}  {item.created_at.date()}  {len(item.content)}ch"
            )
        if len(plan.missing) > sample:
            lines.append(f"  ... and {len(plan.missing) - sample} more")

    if check:
        if plan.missing:
            lines.append(
                f"\nDRIFT: {len(plan.missing)} vault walkthrough(s) have no drawer. "
                "Run `cairntir vault-sync --apply` to import them."
            )
        else:
            lines.append("\nok: every vault walkthrough has a drawer.")
    return "\n".join(lines)
