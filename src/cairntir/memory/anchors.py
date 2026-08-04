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

import re
from dataclasses import dataclass
from pathlib import Path
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

_CANDIDATE_RE = re.compile(r"[A-Za-z0-9_.\-/\\]*[A-Za-z0-9_\-][/\\.][A-Za-z0-9_.\-/\\]*")
"""Loose prefilter for path-like tokens in prose.

Deliberately permissive. Extraction is *not* the safety mechanism —
:class:`RepoIndex` is. A candidate that does not resolve to a real file on
disk is discarded, so a sloppy regex costs a wasted lookup, never a bad anchor.
"""

_EXTENSION_RE = re.compile(r"\.[A-Za-z][A-Za-z0-9]{0,4}$")
"""A trailing extension must contain a letter, so ``v1.2.0`` is not a filename."""

_IGNORED_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "venv",
        "__pycache__",
        "node_modules",
        "dist",
        "build",
        "target",
        "htmlcov",
        ".next",
        ".gradle",
        ".idea",
    }
)
"""Directories excluded from the repo index. Build output is not source."""

_AMBIGUOUS_BASENAMES = frozenset(
    {
        "__init__.py",
        "index.js",
        "index.ts",
        "index.tsx",
        "main.py",
        "main.rs",
        "main.ts",
        "mod.rs",
        "lib.rs",
        "readme.md",
        "license.md",
        "package.json",
        "tsconfig.json",
        "setup.py",
        "conftest.py",
    }
)
"""Basenames too generic to anchor from a bare mention.

A drawer that says "package.json" is usually talking *about* the concept, not
pointing at one file. These are only anchored when the drawer spells out a path
containing a separator, where the intent is unambiguous.
"""


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


@dataclass(frozen=True)
class AnchorProposal:
    """Anchors extracted from prose and verified against a real working tree.

    Attributes:
        anchors: Candidates that resolved to exactly one file on disk, carrying
            the **repo-relative path of the resolved file** rather than the raw
            token the prose happened to use.
        rejected: Candidates that looked like paths and did not resolve. Kept so
            a human can see what was skipped; a backfill that silently drops
            them teaches nobody anything.
    """

    anchors: tuple[Anchor, ...]
    rejected: tuple[str, ...]


class RepoIndex:
    """A filename index over one working tree, used to verify anchor candidates.

    This exists to enforce the rule that made the 2026-08-02 damage expensive:
    **never write an unverified anchor.** A wrong path does not fail loudly — it
    silently poisons :func:`recall_for_change`, surfacing the wrong memory for a
    change or, worse, nothing at all. A missing anchor costs one lost recall; a
    wrong one costs trust in every recall.

    So resolution is deliberately conservative. A candidate is accepted only
    when it names exactly one file:

    * an exact repo-relative hit, or
    * a segment-boundary suffix matching exactly one indexed file (prose often
      writes ``src/tech.rs`` for ``sim-core/src/tech.rs``), or
    * a bare filename matching exactly one indexed file, unless the basename is
      in :data:`_AMBIGUOUS_BASENAMES`.

    Two matches is not a near-miss, it is a guess, and it is rejected. No
    parser, no new dependency — a directory walk and a dict, consistent with
    this module's standing refusal to take on tree-sitter.
    """

    def __init__(self, root: Path) -> None:
        """Index every file under ``root``, skipping build output."""
        self._root = Path(root).resolve()
        self._by_relpath: set[str] = set()
        self._by_basename: dict[str, list[str]] = {}
        for absolute in self._walk(self._root):
            relative = normalize_path(str(absolute.relative_to(self._root)))
            self._by_relpath.add(relative)
            self._by_basename.setdefault(absolute.name.lower(), []).append(relative)

    @property
    def root(self) -> Path:
        """The working tree this index was built from."""
        return self._root

    def __len__(self) -> int:
        """Number of indexed files."""
        return len(self._by_relpath)

    @staticmethod
    def _walk(root: Path) -> Iterable[Path]:
        stack = [root]
        while stack:
            current = stack.pop()
            try:
                entries = list(current.iterdir())
            except (OSError, PermissionError):
                # An unreadable directory is a fact about the filesystem, not a
                # defect worth aborting an entire backfill over. Skip it.
                continue
            for entry in entries:
                if entry.is_dir():
                    if entry.name not in _IGNORED_DIRS:
                        stack.append(entry)
                elif entry.is_file():
                    yield entry

    def _strip_root_prefix(self, text: str) -> str:
        r"""Drop an absolute prefix up to and including this repo's own directory name.

        Drawers routinely write ``C:\Dev\MinnieSweets\catering.html`` where the
        index holds ``catering.html``. That prefix is the only one that can be
        removed without inferring: it names the very tree being searched. Any
        other leading component is an assertion by the author, and dropping it
        would turn ``vendor/package.json`` into a match for the root
        ``package.json`` — a guess, and exactly the kind this refuses to make.
        """
        segments = text.split("/")
        lowered = [s.lower() for s in segments[:-1]]
        root_name = self._root.name.lower()
        if root_name in lowered:
            return "/".join(segments[lowered.index(root_name) + 1 :])
        return text

    def resolve(self, candidate: str) -> str | None:
        """Return the repo-relative path a candidate unambiguously names, or ``None``."""
        text = self._strip_root_prefix(normalize_path(candidate).strip("/"))
        basename = text.rsplit("/", 1)[-1]
        if not text or not _EXTENSION_RE.search(basename):
            return None
        # Checked before the exact-path branch on purpose: a root-level
        # ``package.json`` makes the bare mention and the exact path the same
        # string, and the bare mention is still almost always conceptual.
        if "/" not in text and text.lower() in _AMBIGUOUS_BASENAMES:
            return None
        pool = self._by_basename.get(basename.lower(), [])
        if not pool:
            return None
        if text in self._by_relpath:
            return text
        if "/" in text:
            suffixed = [p for p in pool if p.endswith("/" + text)]
            return suffixed[0] if len(suffixed) == 1 else None
        return pool[0] if len(pool) == 1 else None


def extract_path_candidates(text: str) -> tuple[str, ...]:
    """Return path-like tokens from prose, in first-seen order, deduplicated.

    Loose on purpose: :meth:`RepoIndex.resolve` is what decides truth. Trailing
    prose punctuation is stripped so ``see src/cli.py.`` yields ``src/cli.py``.

    Tokens with no plausible file extension are dropped here rather than left
    for the resolver. Numbered-list markers and ordinary words ("1.", "it.",
    "N/A") would otherwise dominate the rejected list and bury the near-misses
    a human actually needs to look at.
    """
    seen: dict[str, None] = {}
    for raw in _CANDIDATE_RE.findall(text):
        token = raw.strip(".,;:!?()[]{}<>\"'`*").strip()
        if not token or token in seen:
            continue
        if _EXTENSION_RE.search(normalize_path(token).rsplit("/", 1)[-1]):
            seen[token] = None
    return tuple(seen)


def propose_anchors(text: str, index: RepoIndex) -> AnchorProposal:
    """Extract path candidates from ``text`` and verify each against ``index``.

    The one entry point a backfill should use. Every returned anchor has been
    proven to name a real file; everything else is reported, never written.
    """
    anchors: dict[str, None] = {}
    rejected: dict[str, None] = {}
    for candidate in extract_path_candidates(text):
        resolved = index.resolve(candidate)
        if resolved is None:
            rejected[candidate] = None
        else:
            anchors[resolved] = None
    return AnchorProposal(
        anchors=tuple(Anchor(path=path) for path in anchors),
        rejected=tuple(rejected),
    )
