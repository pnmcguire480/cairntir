r"""Backfill structural anchors onto drawers that name real files in prose.

WHY
`recall_for_change` is the only retrieval path that needs no good question from
the reader: it fires from the files being edited. That is the mechanism behind
the stated goal -- a weak model should be able to follow the pieces to the whole
without knowing what to ask. It covers ~11% of the store, and 19 of 22 wings
have zero anchors, so for most of the bank the mechanism is dark.

Most drawers already name their files in prose. This reads that prose, resolves
each candidate against the real working tree, and writes anchors only for the
ones that provably name exactly one file.

THE RULE THIS ENFORCES
Never write an unverified anchor. A missing anchor costs one lost recall; a
wrong one silently poisons every recall for that path, which is worse than
having none. Verification lives in `cairntir.memory.anchors.RepoIndex` and is
covered by tests -- see test_backfilled_anchors_are_verified_against_disk.

USAGE
Nothing is baked in; every wing is mapped to a working tree explicitly::

    python scripts/backfill_anchors.py --map cairntir=C:\\Dev\\Cairntir
    python scripts/backfill_anchors.py --map cairntir=C:\\Dev\\Cairntir --apply

Dry run by default. Honours CAIRNTIR_HOME, so it can be rehearsed against a
copy of the store before it touches the live one. Drawers that already carry
anchors are skipped -- this only ever adds coverage where there was none.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path


def parse_mapping(raw: list[str]) -> dict[str, Path]:
    """Turn ``wing=path`` arguments into a mapping, rejecting anything unusable."""
    mapping: dict[str, Path] = {}
    for item in raw:
        wing, sep, path = item.partition("=")
        if not sep or not wing.strip() or not path.strip():
            raise ValueError(f"--map expects wing=path, got {item!r}")
        root = Path(path.strip()).expanduser()
        if not root.is_dir():
            raise ValueError(f"--map {wing.strip()}: {root} is not a directory")
        mapping[wing.strip()] = root
    return mapping


def main() -> int:
    """Propose (and optionally write) verified anchors. Return an exit code."""
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--map",
        action="append",
        default=[],
        metavar="WING=PATH",
        help="Map a wing to its working tree. Repeat for several.",
    )
    ap.add_argument("--apply", action="store_true", help="write; otherwise dry run")
    ap.add_argument("--out", type=Path, help="write the full proposal to this JSON file")
    ap.add_argument(
        "--show-rejected",
        type=int,
        default=8,
        help="How many unresolved candidates to print per wing (0 to hide).",
    )
    args = ap.parse_args()

    if not args.map:
        print("error: pass at least one --map WING=PATH", file=sys.stderr)
        return 2
    try:
        mapping = parse_mapping(args.map)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    from cairntir.config import db_path
    from cairntir.memory.anchors import ANCHORS_KEY, RepoIndex, propose_anchors
    from cairntir.memory.embeddings import production_embedding_provider
    from cairntir.memory.store import DrawerStore

    print(f"CAIRNTIR_HOME = {os.environ.get('CAIRNTIR_HOME') or '(default = LIVE STORE)'}")
    print(f"target db     = {db_path()}")
    print(f"mode          = {'APPLY' if args.apply else 'DRY RUN'}\n")

    store = DrawerStore(db_path(), production_embedding_provider())
    proposal: dict[str, list[dict[str, object]]] = {}
    grand_drawers = 0
    grand_anchors = 0

    for wing, root in sorted(mapping.items()):
        index = RepoIndex(root)
        drawers = [
            d for d in store.list_by(wing=wing, limit=100000) if ANCHORS_KEY not in d.metadata
        ]
        hits: list[dict[str, object]] = []
        rejected: Counter[str] = Counter()

        for drawer in drawers:
            if drawer.id is None:
                continue
            result = propose_anchors(drawer.content, index)
            rejected.update(result.rejected)
            if result.anchors:
                hits.append(
                    {
                        "drawer_id": drawer.id,
                        "room": drawer.room,
                        "anchors": [{"path": a.path} for a in result.anchors],
                    }
                )

        anchors_total = sum(len(h["anchors"]) for h in hits)  # type: ignore[arg-type]
        grand_drawers += len(hits)
        grand_anchors += anchors_total
        proposal[wing] = hits

        print(f"{wing}")
        print(f"   working tree      {root}  ({len(index)} files indexed)")
        print(f"   unanchored        {len(drawers)}")
        print(f"   would gain        {len(hits)} drawer(s), {anchors_total} anchor(s)")
        if args.show_rejected and rejected:
            top = ", ".join(f"{c}x {t}" for t, c in rejected.most_common(args.show_rejected))
            print(f"   unresolved        {top}")
        print()

    print(f"TOTAL: {grand_drawers} drawer(s) would gain {grand_anchors} verified anchor(s)")

    if args.out:
        args.out.write_text(json.dumps(proposal, indent=2, sort_keys=True), encoding="utf-8")
        print(f"proposal written to {args.out}")

    if not args.apply:
        print("\n--- DRY RUN, nothing written ---")
        return 0

    written = 0
    for wing, hits in sorted(proposal.items()):
        for hit in hits:
            store.add_anchors(int(hit["drawer_id"]), hit["anchors"])  # type: ignore[arg-type]
            written += 1
        if hits:
            print(f"  {wing}: anchored {len(hits)} drawer(s)")
    store.checkpoint()
    print(f"\nanchored {written} drawer(s) with {grand_anchors} anchor(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
