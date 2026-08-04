"""Repair drawers whose tool-call markup was serialized into `content`.

THE DAMAGE
Seven drawers (#74, #96, #209-#213) end with a literal::

    ...real content.</content>
    <parameter name="metadata">{"anchors": [...]}

The metadata payload never reached the `metadata` column -- it is `{}` on every
one of them -- because the whole tool-call envelope was written into the text.
Anchors on those rows are therefore invisible to `recall_for_change`.

WHY `repair_anchors` CANNOT DO THIS
`DrawerStore.repair_anchors` fixes a *different* defect: legacy anchors stored as
bare strings. It requires `metadata["anchors"]` to exist and raises
"has no anchors to repair" when metadata is `{}`. These seven have no metadata at
all, so it refuses them. Same reason `add_anchors` could not fix the legacy rows:
each tool is blocked by the shape of the damage it was not written for.

WHAT THIS DOES
Strips only an exact, end-anchored, JSON-parseable envelope and restores the
payload to the metadata column. Nothing is guessed. The stripped bytes are kept
under `metadata.repair.stripped_tail`, so the operation is reversible and nothing
is destroyed. Content shrinks only by bytes that were never authored.

Because content changes, vectors are rebuilt via the store's own atomic
`reindex_embeddings()`.

Idempotent -- a row with no envelope is skipped. Honours CAIRNTIR_HOME, so it can
be rehearsed against a copy before it touches the live store.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

# End-anchored so it can only ever match a trailing envelope, never mid-content.
ENVELOPE = re.compile(
    r"\s*</content>\s*<parameter\s+name=\"metadata\">\s*(?P<json>\{.*\})\s*\Z",
    re.DOTALL,
)


def split_envelope(content: str) -> tuple[str, dict, str] | None:
    """Return (clean_content, payload, stripped_tail), or None if undamaged."""
    m = ENVELOPE.search(content)
    if not m:
        return None
    try:
        payload = json.loads(m.group("json"))
    except json.JSONDecodeError:
        return None  # not parseable -> leave it for a human, loudly
    if not isinstance(payload, dict):
        return None
    return content[: m.start()].rstrip(), payload, content[m.start() :]


def main() -> int:
    """Strip leaked tool-call envelopes and restore metadata. Return an exit code."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write; otherwise dry run")
    args = ap.parse_args()

    print(f"CAIRNTIR_HOME = {os.environ.get('CAIRNTIR_HOME') or '(default = LIVE STORE)'}")

    from cairntir.config import db_path
    from cairntir.memory.embeddings import production_embedding_provider
    from cairntir.memory.store import DrawerStore

    print(f"target db     = {db_path()}")
    store = DrawerStore(db_path(), production_embedding_provider())
    conn = store._conn  # one-off maintenance; no public repair API exists for this shape

    rows = conn.execute(
        "SELECT id, wing, room, content, metadata FROM drawers ORDER BY id"
    ).fetchall()
    targets = []
    for r in rows:
        rid, wing, room, content, metadata = r[0], r[1], r[2], r[3], r[4]
        split = split_envelope(content)
        if split is None:
            continue
        clean, payload, tail = split
        try:
            existing = json.loads(metadata)
        except json.JSONDecodeError:
            existing = {}
        targets.append((rid, wing, room, clean, payload, tail, existing, len(content)))

    print(f"\ndamaged drawers found: {len(targets)}")
    for rid, wing, room, clean, payload, tail, existing, oldlen in targets:
        keys = ", ".join(sorted(payload))
        anchors = payload.get("anchors") or []
        print(
            f"  #{rid:3d} {wing}/{room}\n"
            f"       content {oldlen} -> {len(clean)} ch (strip {len(tail)})"
            f" | metadata {existing or '{}'} -> keys[{keys}]"
            f" | anchors recovered: {len(anchors)}"
        )

    if not targets:
        print("nothing to repair.")
        return 0

    if not args.apply:
        print("\n--- DRY RUN, nothing written ---")
        return 0

    for rid, _w, _r, clean, payload, tail, existing, _ol in targets:
        merged = {**existing, **payload}
        merged["repair"] = {
            "repaired_at": "2026-08-04",
            "by": "scripts/repair_leaked_metadata.py",
            "reason": "tool-call envelope was serialized into content; metadata column was empty",
            "stripped_tail": tail,  # kept verbatim -> reversible, nothing destroyed
        }
        conn.execute(
            "UPDATE drawers SET content = ?, metadata = ? WHERE id = ?",
            (clean, json.dumps(merged, ensure_ascii=False, sort_keys=True), rid),
        )
    conn.commit()
    print(f"\nrepaired {len(targets)} drawers")

    print("rebuilding vectors (content changed)...")
    result = store.reindex_embeddings()
    print(f"  reindex complete: {result}")
    store.checkpoint()
    return 0


if __name__ == "__main__":
    sys.exit(main())
