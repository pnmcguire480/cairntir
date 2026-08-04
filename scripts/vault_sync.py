"""Obsidian vault -> Cairntir import.

The missing half of ``cairntir-sync/sync-conventions.md``. ``obsidian.py``
projects Cairntir OUT to the vault; nothing ever read the vault back IN. This
does that, following the conventions already written in that document.

Idempotent: a (wing, room) pair that already exists is skipped, so re-running is safe.
Retroactive: created_at is taken from the walkthrough's own date, not today, so the
store gains real history rather than a wall of drawers all dated at import time.

The vault is named by ``--vault`` or ``$CAIRNTIR_VAULT``; there is no baked-in
path. The target store is chosen by ``$CAIRNTIR_HOME``, so a run can be
rehearsed against a copy before it touches the live store.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

# Vault folder -> Cairntir wing slug. Matches wings already in the store.
WING_MAP = {
    "GetKith": "getkith",
    "Ground Zero": "ground-zero",
    "IntakeForms": "intake-forms",
    "Triangulate": "triangulate",
    "examples": "codeglass",
}

DATED = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)$")


def parse_name(stem: str) -> tuple[datetime | None, str]:
    """Split '2026-03-30-pipeline-audit' into its date and task slug."""
    m = DATED.match(stem)
    if not m:
        return None, stem
    try:
        d = datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        return None, stem
    return d, m.group(2)


def collect(vault: Path) -> list[dict]:
    """Build the manifest of drawers this sync would write."""
    items: list[dict] = []
    for folder, wing in WING_MAP.items():
        base = vault / "walkthroughs" / folder
        if not base.is_dir():
            continue
        for path in sorted(base.glob("*.md")):
            text = path.read_text(encoding="utf-8", errors="replace").strip()
            if not text:
                continue
            when, slug = parse_name(path.stem)
            prefix = "example" if wing == "codeglass" else "walkthrough"
            # Rooms must satisfy ^[a-z0-9][a-z0-9._:-]{0,62}[a-z0-9]$ — lowercase, <=64.
            room = re.sub(r"[^a-z0-9._:-]+", "-", f"{prefix}-{path.stem}".lower())
            room = room.strip("-.:_")[:64].rstrip("-.:_")
            items.append(
                {
                    "wing": wing,
                    "room": room,
                    "content": text,
                    "created_at": when or datetime.fromtimestamp(path.stat().st_mtime, tz=UTC),
                    "metadata": {
                        "kind": "obsidian_walkthrough",
                        "source_path": str(path),
                        "vault_folder": folder,
                        "task_slug": slug,
                        "imported_at": "2026-08-04",
                        "importer": "scripts/vault_sync.py",
                        "note": (
                            "Retroactive import. Authored on created_at; "
                            "reached Cairntir 2026-08-04 because the vault->store "
                            "direction of sync-conventions.md was never built."
                        ),
                    },
                }
            )
    return items


def main() -> int:
    """Import vault walkthroughs into the Cairntir store. Return an exit code."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write; otherwise dry run")
    ap.add_argument(
        "--vault",
        type=Path,
        default=os.environ.get("CAIRNTIR_VAULT"),
        help="Path to the Obsidian vault. Defaults to $CAIRNTIR_VAULT.",
    )
    args = ap.parse_args()

    if args.vault is None:
        print("error: pass --vault or set CAIRNTIR_VAULT", file=sys.stderr)
        return 2
    vault: Path = args.vault.expanduser()
    if not (vault / ".obsidian").is_dir():
        print(f"error: {vault} is not an Obsidian vault (missing .obsidian)", file=sys.stderr)
        return 2

    home = os.environ.get("CAIRNTIR_HOME")
    print(f"vault         = {vault}")
    print(f"CAIRNTIR_HOME = {home or '(default user-data dir = LIVE STORE)'}")

    manifest = collect(vault)
    print(f"manifest: {len(manifest)} drawers")
    by_wing: dict[str, int] = {}
    for it in manifest:
        by_wing[it["wing"]] = by_wing.get(it["wing"], 0) + 1
    for w, n in sorted(by_wing.items()):
        print(f"   {w:16s} {n:3d}")

    from cairntir.config import db_path
    from cairntir.memory.embeddings import production_embedding_provider
    from cairntir.memory.store import DrawerStore
    from cairntir.memory.taxonomy import Drawer, Layer
    from cairntir.provenance import TrustLevel, WriteProvenance

    print(f"target db  = {db_path()}")
    store = DrawerStore(
        db_path(),
        production_embedding_provider(),
        provenance=WriteProvenance.create(
            host="cli",
            capture_path="vault-sync",
            trust=TrustLevel.USER_ASSERTED,
        ),
    )

    existing: set[tuple[str, str]] = set()
    for w in sorted({i["wing"] for i in manifest}):
        for r in store.list_by(wing=w, limit=100000):
            existing.add((r.wing, r.room))
    todo = [i for i in manifest if (i["wing"], i["room"]) not in existing]
    print(f"already present: {len(manifest) - len(todo)}   to write: {len(todo)}")

    if not args.apply:
        print("\n--- DRY RUN, nothing written ---")
        for i in todo[:5]:
            print(f"  {i['wing']}/{i['room']}  {i['created_at'].date()}  {len(i['content'])}ch")
        if len(todo) > 5:
            print(f"  ... and {len(todo) - 5} more")
        return 0

    written = 0
    for i in todo:
        d = Drawer(
            wing=i["wing"],
            room=i["room"],
            content=i["content"],
            layer=Layer.DEEP,
            metadata=i["metadata"],
            created_at=i["created_at"],
        )
        store.add(d)
        written += 1
        print(f"  + {i['wing']}/{i['room']}")
    store.checkpoint()
    print(f"\nwrote {written} drawers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
