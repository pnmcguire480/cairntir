"""Temporal walks over the drawer supersedes chain — v1.1.

Pure query layer on top of :class:`~cairntir.memory.store.DrawerStore`.
Does not mutate. Does not introduce a schema change; every relation it
reads was already present in the v0.2 prediction-bound schema
(``supersedes_id``) and the v0.3 consolidation schema
(``created_at``).

Two functions:

* :func:`walk_supersedes` returns the chain of drawers from the root
  of a supersedes chain down to the leaf that currently holds
  ``drawer_id``. Useful when a caller wants to see the full history of
  a claim: first prediction, every revision, the current observation.
* :func:`as_of` returns the drawer that was the leaf of
  ``drawer_id``'s chain at timestamp ``when`` — the version of the
  thought that was live on that date.

A "chain" is defined solely by ``supersedes_id`` pointers: A supersedes
B supersedes C. The function walks *both* directions from the given
id — up by ``supersedes_id`` to find the root and down by scanning for
drawers whose ``supersedes_id`` points at the current leaf.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from cairntir.errors import MemoryStoreError

if TYPE_CHECKING:
    from cairntir.memory.store import DrawerStore
    from cairntir.memory.taxonomy import Drawer


def walk_supersedes(store: DrawerStore, drawer_id: int) -> list[Drawer]:
    """Return the full supersedes chain as a list from root → leaf.

    The returned list starts at the oldest drawer (the one nothing
    supersedes) and ends at the newest drawer (the one no other drawer
    supersedes). ``drawer_id`` may sit anywhere in the chain; the
    function walks both directions.

    Raises :class:`~cairntir.errors.MemoryStoreError` when ``drawer_id``
    does not exist. A chain of length 1 (a drawer that neither
    supersedes nor is superseded) is returned as a single-element list.

    Cycle guard: if the ``supersedes_id`` graph contains a cycle (it
    shouldn't — the schema is append-only) the walk stops as soon as it
    revisits an id and returns what it has so far. Better to return a
    truncated-but-honest chain than to loop forever.
    """
    current = store.get(drawer_id)
    if current is None:
        raise MemoryStoreError(f"no drawer with id {drawer_id}")

    # Walk up to the root.
    seen: set[int] = set()
    root = current
    while root.supersedes_id is not None and root.supersedes_id not in seen:
        seen.add(root.id if root.id is not None else -1)
        parent = store.get(root.supersedes_id)
        if parent is None:
            # Dangling pointer — treat the current node as the root so
            # the caller sees what actually exists rather than a crash.
            break
        root = parent

    # Walk down from the root by scanning for children.
    chain: list[Drawer] = [root]
    seen_ids: set[int] = {root.id} if root.id is not None else set()
    node = root
    while True:
        if node.id is None:
            break
        child = _find_child(store, node.id)
        if child is None or child.id is None:
            break
        if child.id in seen_ids:
            break  # cycle guard
        chain.append(child)
        seen_ids.add(child.id)
        node = child

    return chain


def as_of(store: DrawerStore, drawer_id: int, when: datetime) -> Drawer:
    """Return the chain member that was the leaf at timestamp ``when``.

    The "leaf at time T" is the drawer in ``drawer_id``'s chain with
    the latest ``created_at`` that is still ``<= when``. If ``when``
    precedes the root of the chain, the root is returned — that was
    the thought before any revision existed.

    Raises :class:`~cairntir.errors.MemoryStoreError` if the chain has
    no member with ``created_at <= when`` (should only happen when
    ``when`` predates the root, which the previous clause already
    handles, but kept as an explicit guard against empty chains).
    """
    chain = walk_supersedes(store, drawer_id)
    if not chain:
        raise MemoryStoreError(f"empty supersedes chain for drawer {drawer_id}")

    # Chain is root → leaf; pick the latest entry whose created_at <= when.
    # If all entries are after ``when``, fall back to the root — the
    # caller asked for the state at a time before any version existed,
    # which is best represented as the earliest known version.
    selected = chain[0]
    for entry in chain:
        if entry.created_at <= when:
            selected = entry
        else:
            break
    return selected


def _find_child(store: DrawerStore, parent_id: int) -> Drawer | None:
    """Return the drawer (if any) whose ``supersedes_id`` is ``parent_id``.

    The schema is append-only, so a parent should have at most one
    child. If somehow two drawers supersede the same parent (a bug in
    the caller that wrote them) we return the one with the lowest id —
    deterministic, so the walk is reproducible.
    """
    # list_by doesn't filter on supersedes_id, so fall through to raw SQL.
    # This is a tight read on an append-only column, no concurrency risk.
    import sqlite3

    try:
        rows = store._conn.execute(
            "SELECT * FROM drawers WHERE supersedes_id = ? ORDER BY id ASC LIMIT 1",
            (parent_id,),
        ).fetchall()
    except sqlite3.Error as exc:
        raise MemoryStoreError(f"failed to scan for child of {parent_id}: {exc}") from exc
    if not rows:
        return None
    from cairntir.memory.store import _row_to_drawer

    return _row_to_drawer(rows[0])
