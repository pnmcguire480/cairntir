"""SQLite + sqlite-vec backed drawer store.

The store persists :class:`~cairntir.memory.taxonomy.Drawer` rows verbatim in
a regular SQLite table and mirrors their embeddings in a ``vec0`` virtual
table for fast k-nearest-neighbor search.

Every method raises :class:`~cairntir.errors.MemoryStoreError` on failure. Silent
swallowing of SQLite exceptions is explicitly banned.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import struct
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlite_vec

from cairntir.durability import (
    WorkflowExecution,
    WorkflowReceipt,
    WorkflowState,
    request_hash,
)
from cairntir.errors import (
    AnchorError,
    ContentIntegrityError,
    EmbeddingError,
    EmbeddingSpaceError,
    IdempotencyConflictError,
    MemoryStoreError,
    ProvenanceError,
    WorkflowError,
)
from cairntir.memory.anchors import parse_anchors
from cairntir.memory.belief import rerank_results
from cairntir.memory.embeddings import embedding_space_id
from cairntir.memory.taxonomy import Drawer, Layer
from cairntir.provenance import TrustLevel, WriteProvenance, legacy_provenance

if TYPE_CHECKING:
    from cairntir.memory.embeddings import EmbeddingProvider


def _pack(vec: list[float]) -> bytes:
    """Pack a float vector into the little-endian float32 bytes sqlite-vec expects."""
    return struct.pack(f"{len(vec)}f", *vec)


SCHEMA_VERSION = 6
"""Current drawer schema version.

v1 — initial: wing, room, content, layer, metadata, created_at.
v2 — prediction-bound drawers: claim, predicted_outcome, observed_outcome,
     delta, supersedes_id (all nullable). Forward-only ALTER TABLE migration.
v3 — consolidation substrate: last_accessed_at, access_count. Powers the
     replay-weighted forgetting curve and the consolidate pass. Backfilled
     from created_at / 0 for pre-v3 rows.
v4 — belief-as-distribution: belief_mass scalar (default 1.0). Raised by
     reinforce(), lowered by weaken(), clamped at 0. Combines with the
     optional ``delta`` field to steer search ranking without a training
     pipeline.
v5 — semantic-index integrity: store metadata records the embedding-space
     identity, vector dimension, verification time, and rebuild generation.
     Legacy non-empty indexes remain readable as raw drawers but semantic
     reads/writes fail closed until an explicit reindex.
v6 — trust and durability: immutable write provenance on every drawer,
     trust/validity vector prefilters, and durable idempotency receipts for
     crash-safe multi-drawer workflows.
"""

_V2_COLUMNS: tuple[str, ...] = (
    "claim",
    "predicted_outcome",
    "observed_outcome",
    "delta",
    "supersedes_id",
)

_META_EMBEDDING_SPACE = "embedding_space_id"
_META_EMBEDDING_DIMENSION = "embedding_dimension"
_META_EMBEDDING_GENERATION = "embedding_generation"
_META_EMBEDDING_VERIFIED_AT = "embedding_verified_at"
_VECTOR_DIMENSION_RE = re.compile(r"\bembedding\s+FLOAT\[(\d+)\]", re.IGNORECASE)
_VECTOR_FILTER_COLUMNS = frozenset({"wing", "room", "layer", "trust", "valid_until"})

_ENVELOPE_MARKERS: tuple[str, ...] = ("</content>", "<parameter name=")
"""Byte substrings identifying a host's serialized tool-call envelope.

The same shapes ``scripts/check_store_health.py`` rule 3 hunts for after the
fact. The write-time guard in :meth:`DrawerStore.add` uses them to refuse the
damage before it is stored.
"""

_TRAILING_ENVELOPE = re.compile(
    r"</content>\s*<parameter\s+name=\"[^\"]*\">\s*(?P<json>\{.*\})\s*\Z",
    re.DOTALL,
)
"""The exact end-anchored shape of a swallowed tool call.

Same silhouette as ``scripts/repair_leaked_metadata.py`` repairs, generalized
to any parameter name. A trailing envelope with a parseable JSON payload is
the fingerprint of a broken write in every observed case; no legitimate
content ends this way.
"""


@dataclass(frozen=True)
class EmbeddingSpaceStatus:
    """Read-only health report for a store's semantic index."""

    state: str
    current_space_id: str
    stored_space_id: str | None
    vector_dimension: int | None
    stored_dimension: int | None
    generation: str | None
    drawer_count: int
    vector_count: int
    detail: str

    @property
    def verified(self) -> bool:
        """Return whether semantic reads and writes are safe."""
        return self.state == "verified"


@dataclass(frozen=True)
class EmbeddingReindexResult:
    """Receipt returned after a complete semantic-index rebuild."""

    drawer_count: int
    dimension: int
    space_id: str
    generation: str


@dataclass(frozen=True)
class DatabaseIntegrityStatus:
    """Read-only SQLite and durable-workflow health receipt."""

    ok: bool
    quick_check: tuple[str, ...]
    foreign_key_violations: int
    started_workflows: int
    failed_workflows: int


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
            (name,),
        ).fetchone()
        is not None
    )


def _vector_dimension(conn: sqlite3.Connection) -> int | None:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='vec_drawers'"
    ).fetchone()
    if row is None or row[0] is None:
        return None
    match = _VECTOR_DIMENSION_RE.search(str(row[0]))
    return int(match.group(1)) if match is not None else None


def _vector_columns(conn: sqlite3.Connection) -> set[str]:
    if not _table_exists(conn, "vec_drawers"):
        return set()
    return {str(row[1]) for row in conn.execute("PRAGMA table_info(vec_drawers)").fetchall()}


def _create_vector_table(conn: sqlite3.Connection, dimension: int) -> None:
    conn.execute(
        "CREATE VIRTUAL TABLE vec_drawers USING vec0("
        "drawer_id INTEGER PRIMARY KEY, "
        f"embedding FLOAT[{dimension}], "
        "wing TEXT, room TEXT, layer TEXT, trust TEXT, valid_until TEXT)"
    )


def _metadata(conn: sqlite3.Connection) -> dict[str, str]:
    if not _table_exists(conn, "store_metadata"):
        return {}
    rows = conn.execute("SELECT key, value FROM store_metadata").fetchall()
    return {str(row[0]): str(row[1]) for row in rows}


def _embedding_status(
    conn: sqlite3.Connection,
    embedder: EmbeddingProvider,
) -> EmbeddingSpaceStatus:
    current_space = embedding_space_id(embedder)
    if not _table_exists(conn, "drawers"):
        return EmbeddingSpaceStatus(
            state="corrupt",
            current_space_id=current_space,
            stored_space_id=None,
            vector_dimension=None,
            stored_dimension=None,
            generation=None,
            drawer_count=0,
            vector_count=0,
            detail="drawers table is missing",
        )

    drawer_count = int(conn.execute("SELECT COUNT(*) FROM drawers").fetchone()[0])
    vector_dimension = _vector_dimension(conn)
    if _table_exists(conn, "vec_drawers"):
        vector_count = int(conn.execute("SELECT COUNT(*) FROM vec_drawers").fetchone()[0])
    else:
        vector_count = 0

    metadata = _metadata(conn)
    stored_space = metadata.get(_META_EMBEDDING_SPACE)
    raw_dimension = metadata.get(_META_EMBEDDING_DIMENSION)
    generation = metadata.get(_META_EMBEDDING_GENERATION)
    try:
        stored_dimension = int(raw_dimension) if raw_dimension is not None else None
    except ValueError:
        stored_dimension = None

    def _status(state: str, detail: str) -> EmbeddingSpaceStatus:
        return EmbeddingSpaceStatus(
            state=state,
            current_space_id=current_space,
            stored_space_id=stored_space,
            vector_dimension=vector_dimension,
            stored_dimension=stored_dimension,
            generation=generation,
            drawer_count=drawer_count,
            vector_count=vector_count,
            detail=detail,
        )

    if stored_space is None:
        return _status(
            "unverified",
            (
                "legacy semantic index has no embedding-space identity; "
                "raw drawers remain readable, but reindex is required"
            ),
        )
    if stored_space != current_space:
        return _status(
            "mismatch",
            (
                f"stored embedding space {stored_space!r} does not match "
                f"active space {current_space!r}"
            ),
        )
    if stored_dimension is None or generation is None:
        return _status(
            "corrupt",
            "embedding metadata is incomplete or has an invalid dimension",
        )
    if vector_dimension is None:
        return _status(
            "corrupt",
            "vec_drawers is missing or its dimension cannot be read",
        )
    missing_filter_columns = _VECTOR_FILTER_COLUMNS - _vector_columns(conn)
    if missing_filter_columns:
        return _status(
            "corrupt",
            "vec_drawers lacks required prefilter columns: "
            + ", ".join(sorted(missing_filter_columns)),
        )
    if vector_dimension != stored_dimension:
        return _status(
            "corrupt",
            (
                f"vec_drawers dimension {vector_dimension} does not match "
                f"recorded dimension {stored_dimension}"
            ),
        )
    if vector_count != drawer_count:
        return _status(
            "corrupt",
            f"semantic index contains {vector_count} vectors for {drawer_count} drawers",
        )
    return _status(
        "verified",
        "embedding space, dimension, generation, and row counts agree",
    )


def inspect_embedding_space(
    path: Path,
    embedder: EmbeddingProvider,
) -> EmbeddingSpaceStatus:
    """Inspect semantic-index health without migrating or modifying ``path``."""
    current_space = embedding_space_id(embedder)
    if not path.exists():
        return EmbeddingSpaceStatus(
            state="missing",
            current_space_id=current_space,
            stored_space_id=None,
            vector_dimension=None,
            stored_dimension=None,
            generation=None,
            drawer_count=0,
            vector_count=0,
            detail=f"database does not exist at {path}",
        )
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        try:
            version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            if version > SCHEMA_VERSION:
                return EmbeddingSpaceStatus(
                    state="future_schema",
                    current_space_id=current_space,
                    stored_space_id=None,
                    vector_dimension=None,
                    stored_dimension=None,
                    generation=None,
                    drawer_count=0,
                    vector_count=0,
                    detail=(
                        f"database schema v{version} is newer than library schema v{SCHEMA_VERSION}"
                    ),
                )
            return _embedding_status(conn, embedder)
        finally:
            conn.close()
    except sqlite3.Error as exc:
        raise MemoryStoreError(f"failed to inspect embedding space at {path}: {exc}") from exc


def inspect_database_integrity(path: Path) -> DatabaseIntegrityStatus:
    """Run SQLite integrity checks without migrating or writing the database."""
    if not path.exists():
        raise MemoryStoreError(f"database does not exist at {path}")
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
        try:
            quick = tuple(str(row[0]) for row in conn.execute("PRAGMA quick_check").fetchall())
            foreign_keys = len(conn.execute("PRAGMA foreign_key_check").fetchall())
            if _table_exists(conn, "workflow_runs"):
                rows = conn.execute(
                    "SELECT state, COUNT(*) FROM workflow_runs "
                    "WHERE state IN (?, ?) GROUP BY state",
                    (WorkflowState.STARTED.value, WorkflowState.FAILED.value),
                ).fetchall()
                counts = {str(row[0]): int(row[1]) for row in rows}
            else:
                counts = {}
        finally:
            conn.close()
    except sqlite3.Error as exc:
        raise MemoryStoreError(f"failed to inspect database integrity at {path}: {exc}") from exc
    started = counts.get(WorkflowState.STARTED.value, 0)
    failed = counts.get(WorkflowState.FAILED.value, 0)
    return DatabaseIntegrityStatus(
        ok=quick == ("ok",) and foreign_keys == 0,
        quick_check=quick,
        foreign_key_violations=foreign_keys,
        started_workflows=started,
        failed_workflows=failed,
    )


def backup_database(source: Path, destination: Path) -> Path:
    """Create a SQLite online backup without opening Cairntir's schema."""
    if not source.exists():
        raise MemoryStoreError(f"cannot back up missing database at {source}")
    if source.resolve() == destination.resolve():
        raise MemoryStoreError("backup destination must differ from source")
    if destination.exists():
        raise MemoryStoreError(f"refusing to overwrite existing backup at {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        source_conn = sqlite3.connect(source)
        destination_conn = sqlite3.connect(destination)
        try:
            source_conn.backup(destination_conn)
        finally:
            destination_conn.close()
            source_conn.close()
    except sqlite3.Error as exc:
        raise MemoryStoreError(
            f"failed to back up database from {source} to {destination}: {exc}"
        ) from exc
    return destination


def _checkpoint_database(path: Path) -> None:
    try:
        conn = sqlite3.connect(path)
        try:
            busy, _log, _checkpointed = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        raise MemoryStoreError(f"failed to checkpoint {path} before reindex: {exc}") from exc
    if int(busy) != 0:
        raise MemoryStoreError(
            "database checkpoint is busy; stop Cairntir clients before reindexing"
        )


def reindex_database(
    path: Path,
    embedder: EmbeddingProvider,
    *,
    batch_size: int = 64,
) -> EmbeddingReindexResult:
    """Rebuild in a sidecar database and atomically replace ``path``.

    The source file is unchanged until the sidecar has a complete, verified
    index. This is the recovery path when the provider changes vector
    dimension, because sqlite-vec virtual-table DDL is not transactionally
    reversible on every supported SQLite build.
    """
    if not path.exists():
        raise MemoryStoreError(f"cannot reindex missing database at {path}")
    _checkpoint_database(path)
    before = path.stat()
    temporary = path.with_name(f".{path.name}.reindex-{uuid4().hex}.tmp")
    try:
        backup_database(path, temporary)
        with DrawerStore(temporary, embedder, backup_migrations=False) as store:
            result = store.reindex_embeddings(
                batch_size=batch_size,
                _allow_dimension_change=True,
            )
            store.checkpoint()
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise MemoryStoreError(
                "database changed while reindex was running; refusing to replace it. "
                "Stop Cairntir clients and retry."
            )
        try:
            os.replace(temporary, path)
        except OSError as exc:
            raise MemoryStoreError(
                f"failed to atomically replace {path}; stop Cairntir clients and retry: {exc}"
            ) from exc
        return result
    finally:
        if temporary.exists():
            try:
                temporary.unlink()
            except OSError as exc:
                raise MemoryStoreError(
                    f"failed to remove temporary reindex database {temporary}: {exc}"
                ) from exc


def _guard_write_integrity(drawer: Drawer) -> None:
    """Reject damaged writes before they are stored.

    Two content rules, one per observed damage shape:

    * A trailing tool-call envelope with a parseable JSON payload is a
      swallowed write in every case ever observed — the real content ends
      where the envelope begins. Rejected regardless of metadata.
    * Envelope markers anywhere in the content plus an empty metadata column
      is exactly the fingerprint ``scripts/check_store_health.py`` rule 3
      reports as a leaked envelope. A swallowed tool call never carries
      metadata, because the metadata parameter was the thing that got
      swallowed; a deliberate quote of the pattern can be written with some
      metadata attached, which is what tells the two apart.

    The guard refuses; it never rewrites. Repairing rows that predate it is
    ``scripts/repair_leaked_metadata.py``'s job. Anchors are held to the same
    shape :func:`~cairntir.memory.anchors.recall_for_change` reads, on every
    write path, not only the MCP one.
    """
    content = drawer.content
    trailing = _TRAILING_ENVELOPE.search(content)
    if trailing is not None:
        try:
            json.loads(trailing.group("json"))
        except json.JSONDecodeError:
            pass  # unparseable tail: left to the marker-and-metadata rule below
        else:
            raise ContentIntegrityError(
                "write rejected: content ends with a serialized tool-call "
                "envelope (</content> + <parameter ...>). The host swallowed "
                "the tool call; retry the write with the real content."
            )
    if any(marker in content for marker in _ENVELOPE_MARKERS) and not drawer.metadata:
        raise ContentIntegrityError(
            "write rejected: content contains tool-call envelope markup and "
            "the write carries no metadata — the exact fingerprint of a "
            "swallowed tool call. If the markup is quoted deliberately, "
            "attach metadata so the store can tell the difference."
        )
    try:
        parse_anchors(drawer.metadata)
    except AnchorError as exc:
        raise AnchorError(f"write rejected: {exc}") from exc


class DrawerStore:
    """Persistent verbatim drawer store with semantic search."""

    def __init__(
        self,
        db_path: Path,
        embedder: EmbeddingProvider,
        *,
        provenance: WriteProvenance | None = None,
        backup_migrations: bool = True,
    ) -> None:
        """Open (or create) the store at ``db_path`` using ``embedder``.

        Does not touch ``embedder.dimension`` unless the ``vec_drawers``
        virtual table must be created. Opening an existing database skips
        the embedder entirely, so an MCP server answers the ``initialize``
        handshake without loading a model. Semantic work remains lazy and
        ``cairntir setup`` can pre-warm it in the foreground.
        """
        self._path = db_path
        self._embedder = embedder
        self._write_provenance = provenance or WriteProvenance.create(
            host="library",
            capture_path="direct",
        )
        self._dim: int | None = None  # lazy; populated by _init_schema or first add
        self._transaction_depth = 0
        self._savepoint_counter = 0
        self._conn = self._connect(db_path)
        try:
            if backup_migrations:
                self._backup_before_migration()
            self._init_schema()
        except (EmbeddingError, MemoryStoreError):
            self._conn.close()
            raise

    def _backup_before_migration(self) -> None:
        """Create a timestamped online backup before altering an older schema."""
        try:
            existing_version = int(self._conn.execute("PRAGMA user_version").fetchone()[0])
            has_drawers = _table_exists(self._conn, "drawers")
        except sqlite3.Error as exc:
            raise MemoryStoreError(f"failed to inspect schema before migration: {exc}") from exc
        if not has_drawers or existing_version >= SCHEMA_VERSION:
            return
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        destination = self._path.with_name(
            f"{self._path.stem}.pre-v{SCHEMA_VERSION}-{stamp}{self._path.suffix}"
        )
        backup_database(self._path, destination)

    @staticmethod
    def _connect(path: Path) -> sqlite3.Connection:
        try:
            conn = sqlite3.connect(path)
            conn.execute("PRAGMA busy_timeout = 5000")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.enable_load_extension(False)
            conn.row_factory = sqlite3.Row
        except sqlite3.Error as exc:
            raise MemoryStoreError(f"failed to open sqlite-vec database at {path}: {exc}") from exc
        return conn

    def _init_schema(self) -> None:
        try:
            existing_version = int(self._conn.execute("PRAGMA user_version").fetchone()[0])
            if existing_version > SCHEMA_VERSION:
                raise MemoryStoreError(
                    f"database schema v{existing_version} is newer than "
                    f"this library's schema v{SCHEMA_VERSION}; upgrade Cairntir"
                )
            with self._conn:
                self._conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS drawers (
                        id                INTEGER PRIMARY KEY AUTOINCREMENT,
                        wing              TEXT NOT NULL,
                        room              TEXT NOT NULL,
                        content           TEXT NOT NULL,
                        layer             TEXT NOT NULL,
                        metadata          TEXT NOT NULL,
                        created_at        TEXT NOT NULL,
                        claim             TEXT,
                        predicted_outcome TEXT,
                        observed_outcome  TEXT,
                        delta             TEXT,
                        supersedes_id     INTEGER,
                        last_accessed_at  TEXT,
                        access_count      INTEGER NOT NULL DEFAULT 0,
                        belief_mass       REAL NOT NULL DEFAULT 1.0,
                        trust             TEXT NOT NULL,
                        valid_until       TEXT NOT NULL,
                        provenance        TEXT NOT NULL
                    )
                    """
                )
                self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_drawers_wing_room ON drawers(wing, room)"
                )
                self._conn.execute("CREATE INDEX IF NOT EXISTS idx_drawers_layer ON drawers(layer)")
                self._conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS store_metadata (
                        key   TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                    """
                )
                self._conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS workflow_runs (
                        idempotency_key TEXT PRIMARY KEY,
                        operation       TEXT NOT NULL,
                        request_hash    TEXT NOT NULL,
                        state           TEXT NOT NULL,
                        attempt_count   INTEGER NOT NULL DEFAULT 1,
                        started_at      TEXT NOT NULL,
                        updated_at      TEXT NOT NULL,
                        result          TEXT,
                        error           TEXT
                    )
                    """
                )
                self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_workflow_runs_state ON workflow_runs(state)"
                )
                vec_exists = _table_exists(self._conn, "vec_drawers")
                if not vec_exists:
                    # First-time DB: creating the virtual table needs a concrete
                    # dimension, so the embedder loads here. Existing DBs skip
                    # this branch entirely — see __init__ docstring.
                    self._dim = self._embedder.dimension
                    _create_vector_table(self._conn, self._dim)
                self._migrate()
                self._initialize_embedding_metadata_if_safe()
                self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        except sqlite3.Error as exc:
            raise MemoryStoreError(f"failed to initialize schema: {exc}") from exc

    def _initialize_embedding_metadata_if_safe(self) -> None:
        """Stamp a brand-new/empty index; never guess the identity of legacy vectors."""
        metadata = _metadata(self._conn)
        drawer_count = int(self._conn.execute("SELECT COUNT(*) FROM drawers").fetchone()[0])
        vector_count = int(self._conn.execute("SELECT COUNT(*) FROM vec_drawers").fetchone()[0])
        if drawer_count != 0 or vector_count != 0:
            return

        desired_dimension = self._embedder.dimension
        actual_dimension = _vector_dimension(self._conn)
        has_filter_columns = _vector_columns(self._conn) >= _VECTOR_FILTER_COLUMNS
        requires_rebuild = actual_dimension != desired_dimension or not has_filter_columns
        if not requires_rebuild and _META_EMBEDDING_SPACE in metadata:
            return
        if requires_rebuild:
            self._conn.execute("DROP TABLE vec_drawers")
            _create_vector_table(self._conn, desired_dimension)
        self._dim = desired_dimension
        self._stamp_embedding_metadata(
            dimension=desired_dimension,
            generation=str(uuid4()),
        )

    def _stamp_embedding_metadata(self, *, dimension: int, generation: str) -> None:
        values = {
            _META_EMBEDDING_SPACE: embedding_space_id(self._embedder),
            _META_EMBEDDING_DIMENSION: str(dimension),
            _META_EMBEDDING_GENERATION: generation,
            _META_EMBEDDING_VERIFIED_AT: datetime.now(UTC).isoformat(),
        }
        self._conn.executemany(
            """
            INSERT INTO store_metadata(key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            values.items(),
        )

    def _migrate(self) -> None:
        """Forward-only schema migrations. Idempotent.

        Upgrades pre-v2 databases in place by adding the prediction-bound
        columns. Old rows keep ``NULL`` for every new field, so existing
        drawers continue to deserialize unchanged.
        """
        existing = {row[1] for row in self._conn.execute("PRAGMA table_info(drawers)").fetchall()}
        column_defs = {
            "claim": "TEXT",
            "predicted_outcome": "TEXT",
            "observed_outcome": "TEXT",
            "delta": "TEXT",
            "supersedes_id": "INTEGER",
            "last_accessed_at": "TEXT",
            "access_count": "INTEGER NOT NULL DEFAULT 0",
            "belief_mass": "REAL NOT NULL DEFAULT 1.0",
            "trust": "TEXT NOT NULL DEFAULT 'untrusted'",
            "valid_until": "TEXT NOT NULL DEFAULT '9999-12-31T23:59:59.999999+00:00'",
            "provenance": "TEXT NOT NULL DEFAULT '{}'",
        }
        for name, decl in column_defs.items():
            if name not in existing:
                # ALTER TABLE identifiers are trusted literals defined above;
                # no user input flows into this statement.
                self._conn.execute(f"ALTER TABLE drawers ADD COLUMN {name} {decl}")
        # Backfill last_accessed_at from created_at for pre-v3 rows. One-shot,
        # idempotent (WHERE last_accessed_at IS NULL).
        self._conn.execute(
            "UPDATE drawers SET last_accessed_at = created_at WHERE last_accessed_at IS NULL"
        )
        self._conn.execute(
            "UPDATE drawers SET provenance = ? WHERE provenance = '{}'",
            (legacy_provenance().to_json(),),
        )

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()

    def checkpoint(self) -> None:
        """Flush this connection's WAL into the main database file."""
        try:
            busy, _log, _checkpointed = self._conn.execute(
                "PRAGMA wal_checkpoint(TRUNCATE)"
            ).fetchone()
        except sqlite3.Error as exc:
            raise MemoryStoreError(f"failed to checkpoint database: {exc}") from exc
        if int(busy) != 0:
            raise MemoryStoreError("database checkpoint is busy; stop other Cairntir clients")

    def __enter__(self) -> DrawerStore:
        """Enter context manager."""
        return self

    def __exit__(self, *_: object) -> None:
        """Close on context exit."""
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Run writes atomically, using savepoints when workflows nest."""
        savepoint: str | None = None
        try:
            if self._transaction_depth == 0:
                self._conn.execute("BEGIN IMMEDIATE")
            else:
                self._savepoint_counter += 1
                savepoint = f"cairntir_sp_{self._savepoint_counter}"
                self._conn.execute(f"SAVEPOINT {savepoint}")
            self._transaction_depth += 1
        except sqlite3.Error as exc:
            raise MemoryStoreError(f"failed to begin transaction: {exc}") from exc

        try:
            yield
        except BaseException:
            self._transaction_depth -= 1
            try:
                if savepoint is None:
                    self._conn.rollback()
                else:
                    self._conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                    self._conn.execute(f"RELEASE SAVEPOINT {savepoint}")
            except sqlite3.Error as rollback_exc:
                raise MemoryStoreError(f"failed to roll back transaction: {rollback_exc}") from (
                    rollback_exc
                )
            raise
        else:
            self._transaction_depth -= 1
            try:
                if savepoint is None:
                    self._conn.commit()
                else:
                    self._conn.execute(f"RELEASE SAVEPOINT {savepoint}")
            except sqlite3.Error as exc:
                if savepoint is None:
                    self._conn.rollback()
                raise MemoryStoreError(f"failed to commit transaction: {exc}") from exc

    @contextmanager
    def _write_scope(self) -> Iterator[None]:
        """Join the active unit of work or create a new transaction."""
        if self._transaction_depth:
            yield
            return
        with self.transaction():
            yield

    def workflow_receipt(self, idempotency_key: str) -> WorkflowReceipt | None:
        """Return the durable state for an idempotent workflow invocation."""
        try:
            row = self._conn.execute(
                "SELECT * FROM workflow_runs WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise WorkflowError(f"failed to read workflow receipt: {exc}") from exc
        return _row_to_workflow_receipt(row) if row is not None else None

    def execute_once(
        self,
        *,
        idempotency_key: str,
        operation: str,
        request: dict[str, Any],
        action: Callable[[], dict[str, Any]],
    ) -> WorkflowExecution:
        """Execute ``action`` atomically and replay its result on safe retries.

        A ``started`` receipt is committed before the operation begins. The
        operation's writes and its ``committed`` receipt then share one
        transaction. A crash can therefore leave only ``started`` or the
        complete result—never half a multi-drawer workflow.
        """
        key = idempotency_key.strip()
        op = operation.strip()
        if not key:
            raise ValueError("idempotency_key must be non-empty")
        if not op:
            raise ValueError("operation must be non-empty")
        try:
            fingerprint = request_hash(request)
        except ValueError as exc:
            raise WorkflowError(str(exc)) from exc

        replay: WorkflowReceipt | None = None
        now = datetime.now(UTC).isoformat()
        try:
            with self.transaction():
                existing = self.workflow_receipt(key)
                if existing is None:
                    self._conn.execute(
                        """
                        INSERT INTO workflow_runs(
                            idempotency_key, operation, request_hash, state,
                            attempt_count, started_at, updated_at, result, error
                        ) VALUES (?, ?, ?, ?, 1, ?, ?, NULL, NULL)
                        """,
                        (key, op, fingerprint, WorkflowState.STARTED.value, now, now),
                    )
                else:
                    if existing.operation != op or existing.request_hash != fingerprint:
                        raise IdempotencyConflictError(
                            f"idempotency key {key!r} is already bound to a different request"
                        )
                    if existing.state is WorkflowState.COMMITTED:
                        replay = existing
                    else:
                        self._conn.execute(
                            """
                            UPDATE workflow_runs
                            SET state = ?, attempt_count = attempt_count + 1,
                                updated_at = ?, result = NULL, error = NULL
                            WHERE idempotency_key = ?
                            """,
                            (WorkflowState.STARTED.value, now, key),
                        )
        except sqlite3.Error as exc:
            raise WorkflowError(f"failed to prepare workflow {key!r}: {exc}") from exc

        if replay is not None:
            return WorkflowExecution(receipt=replay, replayed=True)

        try:
            with self.transaction():
                result = action()
                try:
                    result_json = json.dumps(
                        result,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                except (TypeError, ValueError) as exc:
                    raise WorkflowError(
                        f"workflow {key!r} returned a non-JSON result: {exc}"
                    ) from exc
                updated_at = datetime.now(UTC).isoformat()
                self._conn.execute(
                    """
                    UPDATE workflow_runs
                    SET state = ?, updated_at = ?, result = ?, error = NULL
                    WHERE idempotency_key = ?
                    """,
                    (WorkflowState.COMMITTED.value, updated_at, result_json, key),
                )
        except BaseException as exc:
            try:
                self._mark_workflow_failed(key, str(exc))
            except WorkflowError as mark_exc:
                raise WorkflowError(
                    f"workflow {key!r} failed and its failure state could not be recorded"
                ) from mark_exc
            raise

        receipt = self.workflow_receipt(key)
        if receipt is None or receipt.state is not WorkflowState.COMMITTED:
            raise WorkflowError(f"workflow {key!r} committed without a durable receipt")
        return WorkflowExecution(receipt=receipt, replayed=False)

    def _mark_workflow_failed(self, idempotency_key: str, error: str) -> None:
        try:
            with self.transaction():
                self._conn.execute(
                    """
                    UPDATE workflow_runs
                    SET state = ?, updated_at = ?, error = ?, result = NULL
                    WHERE idempotency_key = ?
                    """,
                    (
                        WorkflowState.FAILED.value,
                        datetime.now(UTC).isoformat(),
                        error[:4000],
                        idempotency_key,
                    ),
                )
        except sqlite3.Error as exc:
            raise WorkflowError(f"failed to record workflow failure: {exc}") from exc

    def embedding_status(self) -> EmbeddingSpaceStatus:
        """Return the current semantic-index integrity status."""
        try:
            return _embedding_status(self._conn, self._embedder)
        except sqlite3.Error as exc:
            raise MemoryStoreError(f"failed to inspect embedding space: {exc}") from exc

    def _require_embedding_space(self) -> EmbeddingSpaceStatus:
        status = self.embedding_status()
        if not status.verified:
            raise EmbeddingSpaceError(
                f"semantic index is {status.state}: {status.detail}. "
                "Run `cairntir doctor`, then `cairntir reindex`."
            )
        self._dim = status.stored_dimension
        return status

    def reindex_embeddings(
        self,
        *,
        batch_size: int = 64,
        _allow_dimension_change: bool = False,
    ) -> EmbeddingReindexResult:
        """Rebuild every vector, then atomically replace and identify the index."""
        if batch_size <= 0:
            raise ValueError(f"batch_size must be positive, got {batch_size}")
        declared_dimension = self._embedder.dimension
        existing_dimension = _vector_dimension(self._conn)
        existing_filters = _vector_columns(self._conn) >= _VECTOR_FILTER_COLUMNS
        requires_schema_rebuild = existing_dimension != declared_dimension or not existing_filters
        if requires_schema_rebuild and not _allow_dimension_change:
            raise EmbeddingSpaceError(
                "reindex must rebuild the sqlite-vec table for a dimension or "
                "prefilter-schema change; use the offline `cairntir reindex` command"
            )
        try:
            rows = self._conn.execute(
                "SELECT id, content, wing, room, layer, trust, valid_until, provenance "
                "FROM drawers ORDER BY id"
            ).fetchall()
            self._conn.execute("DROP TABLE IF EXISTS temp.cairntir_reindex_stage")
            self._conn.execute(
                "CREATE TEMP TABLE cairntir_reindex_stage ("
                "drawer_id INTEGER PRIMARY KEY, embedding BLOB NOT NULL, "
                "wing TEXT NOT NULL, room TEXT NOT NULL, layer TEXT NOT NULL, "
                "trust TEXT NOT NULL, valid_until TEXT NOT NULL)"
            )
        except sqlite3.Error as exc:
            raise MemoryStoreError(f"failed to prepare embedding reindex: {exc}") from exc

        try:
            for start in range(0, len(rows), batch_size):
                batch = rows[start : start + batch_size]
                vectors = self._embedder.embed([str(row["content"]) for row in batch])
                staged = self._validate_reindex_vectors(
                    batch,
                    vectors,
                    declared_dimension,
                )
                with self._write_scope():
                    self._conn.executemany(
                        "INSERT INTO cairntir_reindex_stage("
                        "drawer_id, embedding, wing, room, layer, trust, valid_until) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        staged,
                    )

            generation = str(uuid4())
            with self._write_scope():
                if requires_schema_rebuild:
                    self._conn.execute("DROP TABLE vec_drawers")
                    _create_vector_table(self._conn, declared_dimension)
                else:
                    self._conn.execute("DELETE FROM vec_drawers")
                self._conn.execute(
                    "INSERT INTO vec_drawers("
                    "drawer_id, embedding, wing, room, layer, trust, valid_until) "
                    "SELECT drawer_id, embedding, wing, room, layer, trust, valid_until "
                    "FROM cairntir_reindex_stage ORDER BY drawer_id"
                )
                self._stamp_embedding_metadata(
                    dimension=declared_dimension,
                    generation=generation,
                )
            self._dim = declared_dimension
            status = self.embedding_status()
            self._require_verified_reindex(status)
            result = EmbeddingReindexResult(
                drawer_count=len(rows),
                dimension=declared_dimension,
                space_id=embedding_space_id(self._embedder),
                generation=generation,
            )
        except sqlite3.Error as exc:
            self._drop_reindex_stage()
            raise MemoryStoreError(f"failed to rebuild embedding index: {exc}") from exc
        except (EmbeddingError, EmbeddingSpaceError, ProvenanceError, ValueError):
            self._drop_reindex_stage()
            raise
        self._drop_reindex_stage()
        return result

    def _drop_reindex_stage(self) -> None:
        try:
            self._conn.execute("DROP TABLE IF EXISTS temp.cairntir_reindex_stage")
        except sqlite3.Error as exc:
            raise MemoryStoreError(f"failed to clean up embedding reindex stage: {exc}") from exc

    @staticmethod
    def _validate_reindex_vectors(
        rows: list[sqlite3.Row],
        vectors: list[list[float]],
        declared_dimension: int,
    ) -> list[tuple[int, bytes, str, str, str, str, str]]:
        if len(vectors) != len(rows):
            raise EmbeddingSpaceError(
                f"embedder returned {len(vectors)} vectors for {len(rows)} inputs"
            )
        staged: list[tuple[int, bytes, str, str, str, str, str]] = []
        for row, vector in zip(rows, vectors, strict=True):
            if len(vector) != declared_dimension:
                raise EmbeddingSpaceError(
                    f"embedder declared dimension {declared_dimension} "
                    f"but produced {len(vector)} values"
                )
            try:
                provenance = WriteProvenance.from_json(str(row["provenance"]))
            except ValueError as exc:
                raise ProvenanceError(
                    f"drawer {int(row['id'])} has invalid provenance: {exc}"
                ) from exc
            if (
                str(row["trust"]) != provenance.trust.value
                or str(row["valid_until"]) != provenance.effective_valid_until
            ):
                raise ProvenanceError(
                    f"drawer {int(row['id'])} provenance does not match trust prefilters"
                )
            staged.append(
                (
                    int(row["id"]),
                    _pack(vector),
                    str(row["wing"]),
                    str(row["room"]),
                    str(row["layer"]),
                    str(row["trust"]),
                    str(row["valid_until"]),
                )
            )
        return staged

    @staticmethod
    def _require_verified_reindex(status: EmbeddingSpaceStatus) -> None:
        if not status.verified:
            raise EmbeddingSpaceError(f"reindex completed but verification failed: {status.detail}")

    def add(
        self,
        drawer: Drawer,
        *,
        provenance: WriteProvenance | None = None,
        model: str | None = None,
    ) -> Drawer:
        """Insert a drawer and return a copy with its assigned id.

        ``model`` records which model authored this specific drawer. It is a
        per-write argument because no host tells the MCP subprocess what it is
        running; the agent doing the writing is the only party that knows.
        Omitting it leaves the receipt's existing value, normally "unknown".

        Raises:
            ContentIntegrityError: when the content carries the fingerprint
                of a swallowed tool-call envelope. This is the write-time half
                of what ``scripts/check_store_health.py`` rule 3 detects after
                the fact; refusing here is what stops the recurrence instead
                of repairing it months later.
            AnchorError: when ``metadata.anchors`` is present but malformed.
                Every write path is held to the shape ``recall_for_change``
                reads, not only the MCP one.
        """
        _guard_write_integrity(drawer)
        status = self._require_embedding_space()
        vector = self._embedder.embed([drawer.content])[0]
        if len(vector) != status.stored_dimension:
            raise EmbeddingSpaceError(
                f"embedding dimension mismatch: expected {status.stored_dimension}, "
                f"got {len(vector)}"
            )
        receipt = (provenance or self._write_provenance).for_write(model=model)
        try:
            with self._write_scope():
                cur = self._conn.execute(
                    """
                    INSERT INTO drawers (
                        wing, room, content, layer, metadata, created_at,
                        claim, predicted_outcome, observed_outcome, delta, supersedes_id,
                        last_accessed_at, access_count, belief_mass, trust, valid_until,
                        provenance
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
                    """,
                    (
                        drawer.wing,
                        drawer.room,
                        drawer.content,
                        drawer.layer.value,
                        json.dumps(drawer.metadata, sort_keys=True),
                        drawer.created_at.isoformat(),
                        drawer.claim,
                        drawer.predicted_outcome,
                        drawer.observed_outcome,
                        drawer.delta,
                        drawer.supersedes_id,
                        drawer.created_at.isoformat(),
                        max(drawer.belief_mass, 0.0),
                        receipt.trust.value,
                        receipt.effective_valid_until,
                        receipt.to_json(),
                    ),
                )
                drawer_id = int(cur.lastrowid or 0)
                self._conn.execute(
                    "INSERT INTO vec_drawers("
                    "drawer_id, embedding, wing, room, layer, trust, valid_until) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        drawer_id,
                        _pack(vector),
                        drawer.wing,
                        drawer.room,
                        drawer.layer.value,
                        receipt.trust.value,
                        receipt.effective_valid_until,
                    ),
                )
        except sqlite3.Error as exc:
            raise MemoryStoreError(f"failed to add drawer: {exc}") from exc
        return drawer.model_copy(update={"id": drawer_id})

    def get(self, drawer_id: int) -> Drawer | None:
        """Return a drawer by id, or ``None`` if missing.

        A successful fetch bumps ``access_count`` and refreshes
        ``last_accessed_at``. This is the replay signal the v0.3 forgetting
        curve reads from; drawers that are never retrieved grow stale and
        drift to a cold layer.
        """
        try:
            row = self._conn.execute("SELECT * FROM drawers WHERE id = ?", (drawer_id,)).fetchone()
        except sqlite3.Error as exc:
            raise MemoryStoreError(f"failed to fetch drawer {drawer_id}: {exc}") from exc
        if row is None:
            return None
        self._touch(int(row["id"]))
        return _row_to_drawer(row)

    def get_provenance(self, drawer_id: int) -> WriteProvenance | None:
        """Return the immutable write receipt for one drawer."""
        try:
            row = self._conn.execute(
                "SELECT provenance FROM drawers WHERE id = ?",
                (drawer_id,),
            ).fetchone()
        except sqlite3.Error as exc:
            message = f"failed to fetch provenance for drawer {drawer_id}: {exc}"
            raise MemoryStoreError(message) from exc
        if row is None:
            return None
        try:
            return WriteProvenance.from_json(str(row["provenance"]))
        except ValueError as exc:
            raise ProvenanceError(f"drawer {drawer_id} has invalid provenance: {exc}") from exc

    def _touch(self, drawer_id: int, *, now: datetime | None = None) -> None:
        """Bump access_count and stamp last_accessed_at for one drawer."""
        stamp = (now or datetime.now(UTC)).isoformat()
        try:
            with self._write_scope():
                self._conn.execute(
                    "UPDATE drawers SET access_count = access_count + 1,"
                    " last_accessed_at = ? WHERE id = ?",
                    (stamp, drawer_id),
                )
        except sqlite3.Error as exc:
            raise MemoryStoreError(f"failed to touch drawer {drawer_id}: {exc}") from exc

    def update_layer(self, drawer_id: int, layer: Layer) -> None:
        """Move a drawer to a new retrieval layer. Never deletes."""
        try:
            with self._write_scope():
                cur = self._conn.execute(
                    "UPDATE drawers SET layer = ? WHERE id = ?",
                    (layer.value, drawer_id),
                )
                if cur.rowcount == 0:
                    raise MemoryStoreError(f"no drawer with id {drawer_id} to update_layer")
                self._conn.execute(
                    "UPDATE vec_drawers SET layer = ? WHERE drawer_id = ?",
                    (layer.value, drawer_id),
                )
        except sqlite3.Error as exc:
            raise MemoryStoreError(f"failed to update layer for drawer {drawer_id}: {exc}") from exc

    def add_anchors(
        self, drawer_id: int, anchors: Sequence[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Attach structural anchors to an existing drawer. Returns the merged list.

        Anchors point a drawer at a code location so
        :func:`cairntir.memory.anchors.recall_for_change` can surface it when
        that file changes. New drawers can carry anchors at write time; this
        exists for the retroactive case — a corpus written before anchors
        existed cannot otherwise participate at all.

        **Append-only, and content is never touched.** Existing anchors are
        preserved, duplicates are collapsed, and nothing is removed. This is
        the same controlled mutation :meth:`update_layer` already performs:
        retrieval routing changes, the verbatim floor does not.
        """
        drawer = self.get(drawer_id)
        if drawer is None:
            raise MemoryStoreError(f"no drawer with id {drawer_id} to add_anchors")

        merged: list[dict[str, Any]] = []
        seen: set[str] = set()
        existing = drawer.metadata.get("anchors")
        candidates: list[Any] = list(existing) if isinstance(existing, list) else []
        candidates.extend(anchors)
        for entry in candidates:
            if not isinstance(entry, dict):
                raise MemoryStoreError(
                    f"anchor entries must be objects, got {type(entry).__name__}"
                )
            path = entry.get("path")
            if not isinstance(path, str) or not path.strip():
                raise MemoryStoreError("each anchor requires a non-empty string 'path'")
            fingerprint = f"{path}\x00{entry.get('symbol') or ''}"
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            merged.append(entry)

        metadata = {**drawer.metadata, "anchors": merged}
        payload = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
        try:
            with self._write_scope():
                cur = self._conn.execute(
                    "UPDATE drawers SET metadata = ? WHERE id = ?",
                    (payload, drawer_id),
                )
                if cur.rowcount == 0:
                    raise MemoryStoreError(f"no drawer with id {drawer_id} to add_anchors")
        except sqlite3.Error as exc:
            raise MemoryStoreError(f"failed to add anchors to drawer {drawer_id}: {exc}") from exc
        return merged

    def repair_anchors(self, drawer_id: int) -> list[dict[str, Any]]:
        """Coerce a drawer's legacy string anchors into object form. Returns the list.

        Agents writing through ``cairntir_remember`` had no way to see the
        anchor contract -- the tool declared ``metadata`` as a bare object --
        so they guessed a list of plain paths, ``["a.rs", "b.toml"]``, where
        the reader requires ``[{"path": "a.rs"}]``. Those rows are invisible
        to :func:`cairntir.memory.anchors.recall_for_change`.

        :meth:`add_anchors` cannot fix them. It validates the *merged* list,
        so it reads the existing bad entries and refuses before it can append
        anything -- the repair tool was blocked by exactly the damage it
        needed to repair. Hence this method.

        Coercion is deliberately limited to the one case that is not a guess:
        a bare string could only ever have meant a path. An object with no
        recoverable ``path``, a number, a nested list -- those are left to a
        human, loudly. Repairing by guessing would be the same class of
        silent drift that caused the defect.

        Idempotent, metadata-only, and duplicate-collapsing on the same
        fingerprint as :meth:`add_anchors`. The verbatim content never moves,
        and nothing is written unless every entry validates first.
        """
        drawer = self.get(drawer_id)
        if drawer is None:
            raise MemoryStoreError(f"no drawer with id {drawer_id} to repair_anchors")

        raw = drawer.metadata.get("anchors")
        if raw is None:
            raise MemoryStoreError(f"drawer {drawer_id} has no anchors to repair")
        if not isinstance(raw, list):
            raise MemoryStoreError(
                f"drawer {drawer_id} metadata.anchors must be a list, got {type(raw).__name__}"
            )

        repaired: list[dict[str, Any]] = []
        seen: set[str] = set()
        for index, entry in enumerate(raw):
            if isinstance(entry, str):
                candidate: dict[str, Any] = {"path": entry}
            elif isinstance(entry, dict):
                candidate = entry
            else:
                raise MemoryStoreError(
                    f"drawer {drawer_id} metadata.anchors[{index}] cannot be repaired: "
                    f"expected an object or a path string, got {type(entry).__name__}"
                )
            path = candidate.get("path")
            if not isinstance(path, str) or not path.strip():
                raise MemoryStoreError(
                    f"drawer {drawer_id} metadata.anchors[{index}] cannot be repaired: "
                    "no non-empty string 'path' to recover"
                )
            fingerprint = f"{path}\x00{candidate.get('symbol') or ''}"
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            repaired.append(candidate)

        if repaired == raw:
            # Already healthy. A no-op must not churn the row or its metadata.
            return repaired

        metadata = {**drawer.metadata, "anchors": repaired}
        payload = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
        try:
            with self._write_scope():
                cur = self._conn.execute(
                    "UPDATE drawers SET metadata = ? WHERE id = ?",
                    (payload, drawer_id),
                )
                if cur.rowcount == 0:
                    raise MemoryStoreError(f"no drawer with id {drawer_id} to repair_anchors")
        except sqlite3.Error as exc:
            raise MemoryStoreError(
                f"failed to repair anchors on drawer {drawer_id}: {exc}"
            ) from exc
        return repaired

    def legacy_migration_drawer_ids(self) -> list[int]:
        """Return the ids of drawers still carrying the v6-migration ``untrusted`` stamp.

        Read-only. This is the dry-run surface for :meth:`reattest_legacy_trust`
        -- the same targeting, no writes.
        """
        return [drawer_id for drawer_id, _ in self._legacy_migration_receipts()]

    def _legacy_migration_receipts(self) -> list[tuple[int, WriteProvenance]]:
        rows = self._conn.execute(
            "SELECT id, provenance FROM drawers WHERE trust = ?",
            (TrustLevel.UNTRUSTED.value,),
        ).fetchall()
        targets: list[tuple[int, WriteProvenance]] = []
        for row in rows:
            try:
                receipt = WriteProvenance.from_json(str(row["provenance"]))
            except ValueError as exc:
                raise MemoryStoreError(
                    f"drawer {int(row['id'])} has invalid provenance: {exc}"
                ) from exc
            if receipt.host == "legacy" and receipt.capture_path == "pre-v6-migration":
                targets.append((int(row["id"]), receipt))
        return targets

    def reattest_legacy_trust(self) -> list[int]:
        """Re-attest the v6-migration drawers from ``untrusted`` to ``legacy_migrated``.

        The v6 migration (2026-07-29) stamped every pre-provenance row with
        :func:`legacy_provenance`, whose trust is ``UNTRUSTED`` -- a migration
        artifact, not a judgement. It renders a security banner over drawers
        that are simply old, training every agent to ignore the banner. This
        corrects the label on exactly those rows and no others: only receipts
        that are the migration stamp itself move (``UNTRUSTED`` is also the
        default for new writes, so genuinely untrusted drawers are not swept).

        Keeps all three trust copies consistent -- the ``drawers.trust``
        column, the ``provenance`` receipt, and the ``vec_drawers.trust``
        prefilter column. Metadata-only and idempotent; verbatim content never
        moves and no embedding is recomputed. Returns the re-attested ids.
        """
        targets = self._legacy_migration_receipts()
        reattested: list[int] = []
        if not targets:
            return reattested
        try:
            with self.transaction():
                for drawer_id, receipt in targets:
                    updated = receipt.with_trust(TrustLevel.LEGACY_MIGRATED)
                    self._conn.execute(
                        "UPDATE drawers SET trust = ?, provenance = ? WHERE id = ?",
                        (
                            TrustLevel.LEGACY_MIGRATED.value,
                            updated.to_json(),
                            drawer_id,
                        ),
                    )
                    self._conn.execute(
                        "UPDATE vec_drawers SET trust = ? WHERE drawer_id = ?",
                        (TrustLevel.LEGACY_MIGRATED.value, drawer_id),
                    )
                    reattested.append(drawer_id)
        except sqlite3.Error as exc:
            raise MemoryStoreError(f"failed to re-attest legacy trust: {exc}") from exc
        return reattested

    def reinforce(self, drawer_id: int, *, amount: float = 1.0) -> float:
        """Raise a drawer's ``belief_mass`` by ``amount``. Returns the new mass.

        Belief mass is a scalar, neutral at 1.0. Reinforcement is how the
        system records that a retrieval was actually useful in context.
        The retrieval distribution itself is the belief: no training loop,
        no loss function, just replay-weighted mass.
        """
        return self._adjust_mass(drawer_id, amount)

    def weaken(self, drawer_id: int, *, amount: float = 1.0) -> float:
        """Lower a drawer's ``belief_mass`` by ``amount``. Clamped at 0.

        Used when a retrieval was dead weight — irrelevant to the query
        the user actually cared about. Never deletes the drawer; the
        verbatim content is the floor.
        """
        return self._adjust_mass(drawer_id, -amount)

    def _adjust_mass(self, drawer_id: int, delta: float) -> float:
        try:
            with self._write_scope():
                cur = self._conn.execute(
                    "UPDATE drawers SET belief_mass = MAX(0.0, belief_mass + ?) WHERE id = ?",
                    (delta, drawer_id),
                )
                if cur.rowcount == 0:
                    raise MemoryStoreError(f"no drawer with id {drawer_id} to adjust mass")
                row = self._conn.execute(
                    "SELECT belief_mass FROM drawers WHERE id = ?", (drawer_id,)
                ).fetchone()
        except sqlite3.Error as exc:
            raise MemoryStoreError(f"failed to adjust belief_mass for {drawer_id}: {exc}") from exc
        return float(row["belief_mass"])

    def stale_ids(
        self,
        *,
        older_than: datetime,
        layer: Layer,
        wing: str | None = None,
    ) -> list[int]:
        """Return ids of drawers in ``layer`` untouched since ``older_than``.

        The forgetting curve reads this to decide which drawers to demote.
        Never includes drawers that have been accessed since the cutoff.
        """
        sql = (
            "SELECT id FROM drawers"
            " WHERE layer = ? AND last_accessed_at IS NOT NULL"
            " AND last_accessed_at < ?"
        )
        params: list[Any] = [layer.value, older_than.isoformat()]
        if wing is not None:
            sql += " AND wing = ?"
            params.append(wing)
        try:
            rows = self._conn.execute(sql, params).fetchall()
        except sqlite3.Error as exc:
            raise MemoryStoreError(f"stale_ids failed: {exc}") from exc
        return [int(r["id"]) for r in rows]

    def list_by(
        self,
        *,
        wing: str | None = None,
        room: str | None = None,
        layer: Layer | None = None,
        limit: int = 100,
        include_expired: bool = False,
    ) -> list[Drawer]:
        """Return drawers filtered by wing/room/layer, most recent first."""
        clauses: list[str] = []
        params: list[Any] = []
        if not include_expired:
            clauses.append("valid_until > ?")
            params.append(datetime.now(UTC).isoformat())
        if wing is not None:
            clauses.append("wing = ?")
            params.append(wing)
        if room is not None:
            clauses.append("room = ?")
            params.append(room)
        if layer is not None:
            clauses.append("layer = ?")
            params.append(layer.value)
        # clauses are static strings; user values are bound as parameters below.
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM drawers {where} ORDER BY id DESC LIMIT ?"  # noqa: S608
        params.append(limit)
        try:
            rows = self._conn.execute(sql, params).fetchall()
        except sqlite3.Error as exc:
            raise MemoryStoreError(f"list_by failed: {exc}") from exc
        return [_row_to_drawer(r) for r in rows]

    def search(
        self,
        query: str,
        *,
        wing: str | None = None,
        room: str | None = None,
        layer: Layer | None = None,
        limit: int = 10,
        rerank_by_belief: bool = True,
        trust: TrustLevel | None = None,
        include_expired: bool = False,
    ) -> list[tuple[Drawer, float]]:
        """Semantic-search drawers. Returns ``(drawer, distance)`` pairs, closest first.

        When ``rerank_by_belief`` is ``True`` (the default) the results are
        reordered by :mod:`cairntir.memory.belief`'s effective-distance
        scorer, which folds in each drawer's ``belief_mass`` and a boost
        for any recorded surprise in its ``delta`` field. The raw vector
        distance is still returned in the tuple so callers can inspect
        semantic closeness; only the ordering changes. Set
        ``rerank_by_belief=False`` to get pure vector order.
        """
        status = self._require_embedding_space()
        vector = self._embedder.embed([query])[0]
        if len(vector) != status.stored_dimension:
            raise EmbeddingSpaceError(
                f"embedding dimension mismatch: expected {status.stored_dimension}, "
                f"got {len(vector)}"
            )
        clauses = ["v.embedding MATCH ?", "k = ?"]
        search_params: list[Any] = [_pack(vector), limit * 4]
        if not include_expired:
            clauses.append("v.valid_until > ?")
            search_params.append(datetime.now(UTC).isoformat())
        if trust is not None:
            clauses.append("v.trust = ?")
            search_params.append(trust.value)
        if wing is not None:
            clauses.append("v.wing = ?")
            search_params.append(wing)
        if room is not None:
            clauses.append("v.room = ?")
            search_params.append(room)
        if layer is not None:
            clauses.append("v.layer = ?")
            search_params.append(layer.value)
        where = " AND ".join(clauses)
        try:
            rows = self._conn.execute(
                f"""
                SELECT d.*, v.distance AS distance
                FROM vec_drawers v
                JOIN drawers d ON d.id = v.drawer_id
                WHERE {where}
                ORDER BY v.distance
                """,  # noqa: S608 — clauses are static; values remain bound parameters
                search_params,
            ).fetchall()
        except sqlite3.Error as exc:
            raise MemoryStoreError(f"search failed: {exc}") from exc

        results: list[tuple[Drawer, float]] = []
        for row in rows:
            results.append((_row_to_drawer(row), float(row["distance"])))
            if len(results) >= limit:
                break
        # Touch hits so the forgetting curve treats them as fresh. Done
        # after scoring so the update doesn't perturb the ranking read.
        for drawer, _ in results:
            if drawer.id is not None:
                self._touch(drawer.id)
        if rerank_by_belief:
            results = rerank_results(results)
        return results


def _row_to_drawer(row: sqlite3.Row) -> Drawer:
    keys = row.keys()

    def _opt(name: str) -> Any:
        return row[name] if name in keys else None

    supersedes = _opt("supersedes_id")
    mass = _opt("belief_mass")
    return Drawer(
        id=int(row["id"]),
        wing=str(row["wing"]),
        room=str(row["room"]),
        content=str(row["content"]),
        layer=Layer(row["layer"]),
        metadata=json.loads(row["metadata"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        claim=_opt("claim"),
        predicted_outcome=_opt("predicted_outcome"),
        observed_outcome=_opt("observed_outcome"),
        delta=_opt("delta"),
        supersedes_id=int(supersedes) if supersedes is not None else None,
        belief_mass=float(mass) if mass is not None else 1.0,
    )


def _row_to_workflow_receipt(row: sqlite3.Row) -> WorkflowReceipt:
    raw_result = row["result"]
    try:
        result = json.loads(str(raw_result)) if raw_result is not None else None
    except json.JSONDecodeError as exc:
        raise WorkflowError(
            f"workflow {str(row['idempotency_key'])!r} has an invalid stored result"
        ) from exc
    if result is not None and not isinstance(result, dict):
        raise WorkflowError(f"workflow {str(row['idempotency_key'])!r} result is not an object")
    try:
        state = WorkflowState(str(row["state"]))
        started_at = datetime.fromisoformat(str(row["started_at"]))
        updated_at = datetime.fromisoformat(str(row["updated_at"]))
    except ValueError as exc:
        raise WorkflowError(
            f"workflow {str(row['idempotency_key'])!r} has invalid lifecycle data"
        ) from exc
    return WorkflowReceipt(
        idempotency_key=str(row["idempotency_key"]),
        operation=str(row["operation"]),
        request_hash=str(row["request_hash"]),
        state=state,
        attempt_count=int(row["attempt_count"]),
        started_at=started_at,
        updated_at=updated_at,
        result=result,
        error=str(row["error"]) if row["error"] is not None else None,
    )
