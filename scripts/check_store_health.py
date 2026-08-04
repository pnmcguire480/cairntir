"""Store-integrity gate: fail CI when the memory bank silently degrades.

WHY THIS EXISTS
`check_landed_commitments.py` verifies that things we *said* we would build got
built. It cannot see the other half of the failure mode: infrastructure that was
built correctly and then quietly stopped being true. Every defect found in the
2026-08-03/04 survey was of that second kind, and every one of them was
invisible until a human went looking with a SQL prompt:

  * 7 drawers had their tool-call envelope serialized into `content`, leaving
    `metadata` empty and 15 code anchors unreachable. Undetected ~3 months.
  * 5 drawers carried anchors as bare strings, invisible to `recall_for_change`.
  * The Obsidian->Cairntir ingest never existed, so 36 walkthroughs sat outside
    the store for 4 months while the export half ran fine.

None of these would fail a unit test. They are data-shape truths about a live
store, so they need a check that runs against a live store.

WHAT IT ASSERTS
  1. No id gaps            -- drawers are never deleted.
  2. Full embedding cover  -- every drawer is reachable by recall. An unembedded
                              drawer is a stray: present, findable only by luck.
  3. No leaked envelopes   -- markup in `content` AND an empty `metadata` column.
                              Both conditions required; a drawer that merely
                              *quotes* the pattern while documenting it is fine.
  4. Well-formed anchors   -- `metadata.anchors` is a list of objects carrying a
                              non-empty string `path`.
  5. Embedding space intact-- the store declares a verified embedding space.

Exit 0 = healthy. Exit 1 = a real regression, with the offending ids named.
Honours CAIRNTIR_HOME. Read-only: it never writes.
"""

from __future__ import annotations

import json
import sqlite3
import sys


def main() -> int:
    """Check the live store for silent degradation. Return a process exit code."""
    from cairntir.config import db_path

    path = db_path()
    print(f"store: {path}")
    if not path.exists():
        print("SKIP: no store at this location (fresh environment)")
        return 0

    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    failures: list[str] = []

    rows = conn.execute(
        "SELECT id, wing, room, content, metadata FROM drawers ORDER BY id"
    ).fetchall()
    if not rows:
        print("SKIP: store is empty")
        return 0
    ids = [r[0] for r in rows]
    print(f"drawers: {len(ids)} (ids {min(ids)}-{max(ids)})")

    # 1. no gaps
    gaps = [i for i in range(min(ids), max(ids) + 1) if i not in set(ids)]
    if gaps:
        failures.append(f"id gaps -- drawers vanished: {gaps}")

    # 2. embedding coverage
    try:
        embedded = {r[0] for r in conn.execute("SELECT drawer_id FROM vec_drawers")}
    except sqlite3.OperationalError:
        import sqlite_vec

        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        embedded = {r[0] for r in conn.execute("SELECT drawer_id FROM vec_drawers")}
    stray = sorted(set(ids) - embedded)
    if stray:
        failures.append(f"unembedded drawers -- unreachable by recall: {stray}")

    # 3. leaked tool-call envelopes (markup AND empty metadata -- both required)
    leaked = [
        r[0]
        for r in rows
        if ("</content>" in r[3] or "<parameter name=" in r[3]) and r[4].strip() in ("{}", "")
    ]
    if leaked:
        failures.append(
            f"tool-call envelope serialized into content, metadata lost: {leaked} "
            "-- run scripts/repair_leaked_metadata.py"
        )

    # 4. anchor shape
    malformed: list[int] = []
    anchored = 0
    for rid, _w, _r, _c, meta in rows:
        try:
            m = json.loads(meta)
        except json.JSONDecodeError:
            malformed.append(rid)
            continue
        if not isinstance(m, dict) or "anchors" not in m:
            continue
        anchored += 1
        a = m["anchors"]
        if not isinstance(a, list) or not all(
            isinstance(x, dict) and isinstance(x.get("path"), str) and x["path"].strip() for x in a
        ):
            malformed.append(rid)
    if malformed:
        failures.append(
            f"malformed metadata.anchors -- invisible to recall_for_change: {malformed} "
            "-- run DrawerStore.repair_anchors"
        )
    print(f"drawers carrying anchors: {anchored}")

    # 5. embedding space declared and verified
    meta = dict(conn.execute("SELECT key, value FROM store_metadata").fetchall())
    if not meta.get("embedding_space_id"):
        failures.append("store_metadata has no embedding_space_id")
    else:
        print(
            f"embedding space: {meta['embedding_space_id']} dim={meta.get('embedding_dimension')}"
        )

    conn.close()

    if failures:
        print(f"\nFAIL: {len(failures)} store-integrity problem(s)")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nok: store is whole -- no gaps, no strays, no leaked envelopes, anchors well-formed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
