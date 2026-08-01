"""Structural anchors and recall-for-change — Tier 1.

The borrowed idea, credited in :doc:`../../docs/lineage/code-review-graph`:
**memory should be reachable by what you are changing, not only by what you
thought to ask.** Cairntir already had semantic recall and exact recall. It had
no answer to "surface what I need without me knowing to ask."

An *anchor* is an optional entry in a drawer's ``metadata["anchors"]`` list::

    {"path": "src/cairntir/memory/embeddings.py",
     "symbol": "SentenceTransformerProvider",
     "symbol_source_hash": "9f86d081..."}

Only ``path`` is required. The store's ``metadata`` column is already
arbitrary JSON, so anchors need **no schema change and no migration**.

What this module deliberately is not
------------------------------------

* **No parser.** No tree-sitter, no grammars, no new dependency. Cairntir
  refused ChromaDB over roughly fifteen transitive dependencies
  (``docs/lineage/mempalace.md``); accepting thirty tree-sitter grammars
  afterwards would make that decision incoherent. Anchors are written by
  whoever writes the drawer.
* **No index.** There is no derived table, no cache to invalidate, and
  nothing to rebuild. Anchors live on the drawer they describe. The verbatim
  floor does not move.
* **No staleness flagging.** ``symbol_source_hash`` is *stored* and never
  *compared*. Gate A2 measured the naive file-scoped design at 40.3%
  precision — a 2.48x noise factor — and while the corrected symbol-scoped
  design is sound in principle, rename survival is untested: Cairntir's own
  history contains zero renames, so its corpus cannot answer the question. A
  staleness signal that floods false positives on someone's first big
  refactor loses trust permanently and does not get a second chance. The
  hold lifts only when rename survival is tested against a corpus that has
  renames.

Opt-in by construction
----------------------

Gate A1 measured anchorability at 33.3% permissive / 28.9% strict against a
pre-registered 30% bar — marginal, not a clean pass — and found the split is
per-room: code-facing rooms anchor, collaboration-facing rooms anchor at 0%
and structurally should. There is no configuration switch for this and does
not need to be one. A drawer with no anchors never matches, so a room whose
drawers carry no anchors is silently and correctly absent from every result.
The optional ``rooms`` argument narrows further when a caller already knows
which rooms are code-facing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from cairntir.errors import AnchorError

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from cairntir.memory.store import DrawerStore
    from cairntir.memory.taxonomy import Drawer

ANCHORS_KEY = "anchors"
"""Key under which anchors live in a drawer's metadata."""

_SCAN_LIMIT = 10_000
"""Upper bound on drawers examined in one call. Tier 1 does a scan, not an index."""


@dataclass(frozen=True)
class Anchor:
    """A pointer from a drawer to a location in the codebase.

    Attributes:
        path: Repository-relative path, normalized to forward slashes.
        symbol: Optional function/class name the drawer is about.
        symbol_source_hash: Optional hash of the anchored symbol's source
            segment. Stored for a future staleness signal; **never compared
            here**. Note this is the hash of the *symbol*, never the file —
            the file-scoped reading is the 40.3%-precision design A2 rejected.
    """

    path: str
    symbol: str | None = None
    symbol_source_hash: str | None = None


@dataclass(frozen=True)
class AnchorMatch:
    """A drawer surfaced because one of its anchors intersects a changed file.

    Attributes:
        drawer: The matched drawer, verbatim and unmodified.
        anchors: The anchors that actually matched — not every anchor on the
            drawer. Callers show these so a user can see *why* it surfaced.
        files: The changed files that caused the match, as supplied.
    """

    drawer: Drawer
    anchors: tuple[Anchor, ...]
    files: tuple[str, ...]


@dataclass(frozen=True)
class ChangeRecall:
    """The result of :func:`recall_for_change`.

    Attributes:
        matches: Matched drawers, most recent first.
        malformed_drawer_ids: Drawers whose ``metadata.anchors`` could not be
            parsed. Surfaced rather than swallowed — a bad anchor is a data
            problem that must be visible, but must not abort an entire recall.
        scanned: How many drawers carried an ``anchors`` key and were examined.
    """

    matches: tuple[AnchorMatch, ...]
    malformed_drawer_ids: tuple[int, ...]
    scanned: int


def normalize_path(raw: str) -> str:
    """Normalize a path for comparison: forward slashes, no ``./``, no trailing slash.

    Windows and POSIX callers must be able to compare the same file. Case is
    deliberately preserved — POSIX filesystems are case-sensitive and folding
    it would create false matches there to paper over a Windows convenience.
    """
    text = raw.strip().replace("\\", "/")
    while "//" in text:
        text = text.replace("//", "/")
    while text.startswith("./"):
        text = text[2:]
    if len(text) > 1 and text.endswith("/"):
        text = text[:-1]
    return text


def paths_intersect(anchor_path: str, changed_path: str) -> bool:
    """Return whether an anchor path refers to the same file as a changed path.

    Matches when the two are equal after normalization, or when one is a
    **segment-boundary suffix** of the other. The suffix rule is what lets a
    repo-relative anchor (``src/cairntir/cli.py``) match an absolute changed
    path (``C:/Dev/Cairntir/src/cairntir/cli.py``) without a repo root being
    threaded through every call.

    The boundary requirement is load-bearing: ``cli.py`` must not match
    ``fastcli.py``. Only a match starting immediately after a ``/`` counts.
    """
    anchor = normalize_path(anchor_path)
    changed = normalize_path(changed_path)
    if not anchor or not changed:
        return False
    if anchor == changed:
        return True
    return changed.endswith("/" + anchor) or anchor.endswith("/" + changed)


def parse_anchors(metadata: dict[str, Any]) -> tuple[Anchor, ...]:
    """Parse ``metadata["anchors"]`` into :class:`Anchor` values.

    Returns an empty tuple when the key is absent — the overwhelmingly common
    case, and not an error. Raises :class:`~cairntir.errors.AnchorError` when
    the key is present but malformed, so the failure is loud for any caller
    that wants strictness.
    """
    raw = metadata.get(ANCHORS_KEY)
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise AnchorError(f"metadata.{ANCHORS_KEY} must be a list, got {type(raw).__name__}")

    anchors: list[Anchor] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise AnchorError(
                f"metadata.{ANCHORS_KEY}[{index}] must be an object, got {type(entry).__name__}"
            )
        path = entry.get("path")
        if not isinstance(path, str) or not path.strip():
            raise AnchorError(f"metadata.{ANCHORS_KEY}[{index}] requires a non-empty string 'path'")
        symbol = entry.get("symbol")
        if symbol is not None and not isinstance(symbol, str):
            raise AnchorError(f"metadata.{ANCHORS_KEY}[{index}].symbol must be a string or absent")
        digest = entry.get("symbol_source_hash")
        if digest is not None and not isinstance(digest, str):
            raise AnchorError(
                f"metadata.{ANCHORS_KEY}[{index}].symbol_source_hash must be a string or absent"
            )
        anchors.append(Anchor(path=normalize_path(path), symbol=symbol, symbol_source_hash=digest))
    return tuple(anchors)


def recall_for_change(
    store: DrawerStore,
    files: Iterable[str],
    *,
    wing: str | None = None,
    rooms: Sequence[str] | None = None,
    limit: int = 20,
) -> ChangeRecall:
    """Return drawers whose anchors intersect ``files``.

    This is structural recall: given the files a change touches, surface the
    memory attached to them without anyone having to ask the right question.

    Args:
        store: The drawer store to read. Read-only — nothing is written,
            mutated, or demoted.
        files: Changed file paths. Separator style and absolute-vs-relative
            do not matter; see :func:`paths_intersect`.
        wing: Restrict to one wing. ``None`` searches every wing.
        rooms: Restrict to specific rooms. ``None`` searches every room; a
            room whose drawers carry no anchors contributes nothing either
            way, so this is a narrowing convenience, not a correctness gate.
        limit: Maximum matches returned, most recent drawer first.

    Returns:
        A :class:`ChangeRecall`. Drawers with unparseable anchors are
        reported in ``malformed_drawer_ids`` rather than raising, so one bad
        entry cannot blind the whole recall.
    """
    wanted = [normalize_path(f) for f in files if f and f.strip()]
    if not wanted or limit <= 0:
        return ChangeRecall(matches=(), malformed_drawer_ids=(), scanned=0)

    room_filter = set(rooms) if rooms is not None else None
    matches: list[AnchorMatch] = []
    malformed: list[int] = []
    scanned = 0

    for drawer in _candidates(store, wing=wing):
        if room_filter is not None and drawer.room not in room_filter:
            continue
        scanned += 1
        try:
            anchors = parse_anchors(drawer.metadata)
        except AnchorError:
            # Surfaced on the result, never swallowed. A malformed anchor is a
            # data defect in one drawer; it must not abort recall for the rest.
            if drawer.id is not None:
                malformed.append(drawer.id)
            continue

        hit_anchors: list[Anchor] = []
        hit_files: list[str] = []
        for anchor in anchors:
            intersecting = [f for f in wanted if paths_intersect(anchor.path, f)]
            if intersecting:
                hit_anchors.append(anchor)
                hit_files.extend(f for f in intersecting if f not in hit_files)
        if hit_anchors:
            matches.append(
                AnchorMatch(
                    drawer=drawer,
                    anchors=tuple(hit_anchors),
                    files=tuple(hit_files),
                )
            )
        if len(matches) >= limit:
            break

    return ChangeRecall(
        matches=tuple(matches),
        malformed_drawer_ids=tuple(malformed),
        scanned=scanned,
    )


def _candidates(store: DrawerStore, *, wing: str | None) -> list[Drawer]:
    """Return drawers that plausibly carry anchors, newest first.

    Tier 1 scans rather than indexing. The scan is narrowed by a substring
    prefilter on the metadata JSON, which is a cheap superset — every drawer
    with a real anchors list contains the key, and the exact parse in
    :func:`recall_for_change` rejects anything the prefilter lets through.
    """
    return [
        drawer
        for drawer in store.list_by(wing=wing, limit=_SCAN_LIMIT)
        if ANCHORS_KEY in drawer.metadata
    ]
