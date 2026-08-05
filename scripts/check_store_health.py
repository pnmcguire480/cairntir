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

The rules themselves live in `cairntir.health`, shared with `cairntir doctor
--gate` so this script and the gate agree by construction. This script is the
CI front-end; be honest about its reach — a hosted runner carries no store, so
here it skips. The gate runs where the data lives.
"""

from __future__ import annotations

import sqlite3
import sys


def main() -> int:
    """Check the live store for silent degradation. Return a process exit code."""
    from cairntir.config import db_path
    from cairntir.health import store_health

    path = db_path()
    print(f"store: {path}")
    if not path.exists():
        print("SKIP: no store at this location (fresh environment)")
        return 0

    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    report = store_health(conn)
    conn.close()

    if report.drawer_count == 0:
        print("SKIP: store is empty")
        return 0

    print(f"drawers: {report.drawer_count} (ids {report.first_id}-{report.last_id})")
    print(f"drawers carrying anchors: {report.anchored_count}")
    if report.embedding_space_id:
        print(f"embedding space: {report.embedding_space_id} dim={report.embedding_dimension}")

    if report.failures:
        print(f"\nFAIL: {len(report.failures)} store-integrity problem(s)")
        for failure in report.failures:
            print(f"  - {failure}")
        return 1
    print("\nok: store is whole -- no gaps, no strays, no leaked envelopes, anchors well-formed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
