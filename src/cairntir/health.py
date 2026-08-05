"""Store-integrity rules, shared by every surface that guards the bank.

One implementation, two front-ends: ``scripts/check_store_health.py`` for CI
and hand runs, and ``cairntir doctor --gate`` for pre-commit and anywhere the
real store lives. A check that runs where its subject does not exist is worse
than no check, because it advertises protection it cannot provide — so the
rules live here, in the package both front-ends import, and neither is free
to drift away from the other.

The five rules, unchanged since the 2026-08-03/04 survey that found every one
of them live in the bank:

  1. No id gaps            -- drawers are never deleted.
  2. Full embedding cover  -- every drawer is reachable by recall.
  3. No leaked envelopes   -- markup in `content` AND an empty `metadata`
                              column; both conditions required.
  4. Well-formed anchors   -- `metadata.anchors` is a list of objects carrying
                              a non-empty string `path`.
  5. Embedding space intact-- the store declares a verified embedding space.

Read-only by construction: callers open the connection, this module never
writes.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StoreHealthReport:
    """What the five rules found. Empty ``failures`` means the bank is whole."""

    drawer_count: int
    first_id: int | None
    last_id: int | None
    anchored_count: int
    embedding_space_id: str | None
    embedding_dimension: str | None
    failures: tuple[str, ...]

    @property
    def healthy(self) -> bool:
        """True when none of the five rules fired."""
        return not self.failures


def store_health(conn: sqlite3.Connection) -> StoreHealthReport:
    """Run the five integrity rules over an open store connection.

    Args:
        conn: A connection to the store, read-only or not; this function
            never writes. The ``vec_drawers`` table is loaded on demand if
            the vec extension is not active yet.

    Returns:
        A :class:`StoreHealthReport` naming every offending drawer id.
    """
    rows = conn.execute(
        "SELECT id, wing, room, content, metadata FROM drawers ORDER BY id"
    ).fetchall()
    if not rows:
        return StoreHealthReport(
            drawer_count=0,
            first_id=None,
            last_id=None,
            anchored_count=0,
            embedding_space_id=None,
            embedding_dimension=None,
            failures=(),
        )

    failures: list[str] = []
    ids = [row[0] for row in rows]

    # 1. no gaps -- drawers are never deleted
    present = set(ids)
    gaps = [i for i in range(min(ids), max(ids) + 1) if i not in present]
    if gaps:
        failures.append(f"id gaps -- drawers vanished: {gaps}")

    # 2. embedding coverage -- an unembedded drawer is a stray
    try:
        embedded = {r[0] for r in conn.execute("SELECT drawer_id FROM vec_drawers")}
    except sqlite3.OperationalError:
        import sqlite_vec

        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        embedded = {r[0] for r in conn.execute("SELECT drawer_id FROM vec_drawers")}
    stray = sorted(present - embedded)
    if stray:
        failures.append(f"unembedded drawers -- unreachable by recall: {stray}")

    # 3. leaked tool-call envelopes (markup AND empty metadata -- both required)
    leaked = [
        row[0]
        for row in rows
        if ("</content>" in row[3] or "<parameter name=" in row[3]) and row[4].strip() in ("{}", "")
    ]
    if leaked:
        failures.append(
            f"tool-call envelope serialized into content, metadata lost: {leaked} "
            "-- run scripts/repair_leaked_metadata.py"
        )

    # 4. anchor shape
    malformed: list[int] = []
    anchored = 0
    for row in rows:
        meta_raw = row[4]
        try:
            meta = json.loads(meta_raw)
        except json.JSONDecodeError:
            malformed.append(row[0])
            continue
        if not isinstance(meta, dict) or "anchors" not in meta:
            continue
        anchored += 1
        anchors = meta["anchors"]
        if not isinstance(anchors, list) or not all(
            isinstance(entry, dict)
            and isinstance(entry.get("path"), str)
            and str(entry.get("path")).strip()
            for entry in anchors
        ):
            malformed.append(row[0])
    if malformed:
        failures.append(
            f"malformed metadata.anchors -- invisible to recall_for_change: {malformed} "
            "-- run DrawerStore.repair_anchors"
        )

    # 5. embedding space declared
    meta_rows: Sequence[tuple[str, str]] = conn.execute(
        "SELECT key, value FROM store_metadata"
    ).fetchall()
    meta_map = dict(meta_rows)
    space_id = meta_map.get("embedding_space_id")
    if not space_id:
        failures.append("store_metadata has no embedding_space_id")

    return StoreHealthReport(
        drawer_count=len(ids),
        first_id=min(ids),
        last_id=max(ids),
        anchored_count=anchored,
        embedding_space_id=space_id,
        embedding_dimension=meta_map.get("embedding_dimension"),
        failures=tuple(failures),
    )
