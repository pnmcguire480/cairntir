"""SQLite + sqlite-vec backed drawer store.

The store persists :class:`~cairntir.memory.taxonomy.Drawer` rows verbatim in
a regular SQLite table and mirrors their embeddings in a ``vec0`` virtual
table for fast k-nearest-neighbor search.

Every method raises :class:`~cairntir.errors.MemoryStoreError` on failure. Silent
swallowing of SQLite exceptions is explicitly banned.
"""

from __future__ import annotations

import json
import sqlite3
import struct
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import sqlite_vec

from cairntir.errors import MemoryStoreError
from cairntir.memory.belief import rerank_results
from cairntir.memory.taxonomy import Drawer, Layer

if TYPE_CHECKING:
    from cairntir.memory.embeddings import EmbeddingProvider


def _pack(vec: list[float]) -> bytes:
    """Pack a float vector into the little-endian float32 bytes sqlite-vec expects."""
    return struct.pack(f"{len(vec)}f", *vec)


SCHEMA_VERSION = 4
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
"""

_V2_COLUMNS: tuple[str, ...] = (
    "claim",
    "predicted_outcome",
    "observed_outcome",
    "delta",
    "supersedes_id",
)


class DrawerStore:
    """Persistent verbatim drawer store with semantic search."""

    def __init__(self, db_path: Path, embedder: EmbeddingProvider) -> None:
        """Open (or create) the store at ``db_path`` using ``embedder``."""
        self._path = db_path
        self._embedder = embedder
        self._dim = embedder.dimension
        self._conn = self._connect(db_path)
        self._init_schema()

    @staticmethod
    def _connect(path: Path) -> sqlite3.Connection:
        try:
            conn = sqlite3.connect(path)
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.enable_load_extension(False)
            conn.row_factory = sqlite3.Row
        except sqlite3.Error as exc:
            raise MemoryStoreError(f"failed to open sqlite-vec database at {path}: {exc}") from exc
        return conn

    def _init_schema(self) -> None:
        try:
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
                        belief_mass       REAL NOT NULL DEFAULT 1.0
                    )
                    """
                )
                self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_drawers_wing_room ON drawers(wing, room)"
                )
                self._conn.execute("CREATE INDEX IF NOT EXISTS idx_drawers_layer ON drawers(layer)")
                self._conn.execute(
                    f"""
                    CREATE VIRTUAL TABLE IF NOT EXISTS vec_drawers USING vec0(
                        drawer_id INTEGER PRIMARY KEY,
                        embedding FLOAT[{self._dim}]
                    )
                    """
                )
                self._migrate()
                self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        except sqlite3.Error as exc:
            raise MemoryStoreError(f"failed to initialize schema: {exc}") from exc

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

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()

    def __enter__(self) -> DrawerStore:
        """Enter context manager."""
        return self

    def __exit__(self, *_: object) -> None:
        """Close on context exit."""
        self.close()

    def add(self, drawer: Drawer) -> Drawer:
        """Insert a drawer and return a copy with its assigned id."""
        vector = self._embedder.embed([drawer.content])[0]
        if len(vector) != self._dim:
            raise MemoryStoreError(
                f"embedding dimension mismatch: expected {self._dim}, got {len(vector)}"
            )
        try:
            with self._conn:
                cur = self._conn.execute(
                    """
                    INSERT INTO drawers (
                        wing, room, content, layer, metadata, created_at,
                        claim, predicted_outcome, observed_outcome, delta, supersedes_id,
                        last_accessed_at, access_count, belief_mass
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
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
                    ),
                )
                drawer_id = int(cur.lastrowid or 0)
                self._conn.execute(
                    "INSERT INTO vec_drawers(drawer_id, embedding) VALUES (?, ?)",
                    (drawer_id, _pack(vector)),
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

    def _touch(self, drawer_id: int, *, now: datetime | None = None) -> None:
        """Bump access_count and stamp last_accessed_at for one drawer."""
        stamp = (now or datetime.now(UTC)).isoformat()
        try:
            with self._conn:
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
            with self._conn:
                cur = self._conn.execute(
                    "UPDATE drawers SET layer = ? WHERE id = ?",
                    (layer.value, drawer_id),
                )
                if cur.rowcount == 0:
                    raise MemoryStoreError(f"no drawer with id {drawer_id} to update_layer")
        except sqlite3.Error as exc:
            raise MemoryStoreError(f"failed to update layer for drawer {drawer_id}: {exc}") from exc

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
            with self._conn:
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
    ) -> list[Drawer]:
        """Return drawers filtered by wing/room/layer, most recent first."""
        clauses: list[str] = []
        params: list[Any] = []
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
        limit: int = 10,
        rerank_by_belief: bool = True,
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
        vector = self._embedder.embed([query])[0]
        try:
            rows = self._conn.execute(
                """
                SELECT d.*, v.distance AS distance
                FROM vec_drawers v
                JOIN drawers d ON d.id = v.drawer_id
                WHERE v.embedding MATCH ? AND k = ?
                ORDER BY v.distance
                """,
                (_pack(vector), limit * 4),
            ).fetchall()
        except sqlite3.Error as exc:
            raise MemoryStoreError(f"search failed: {exc}") from exc

        results: list[tuple[Drawer, float]] = []
        for row in rows:
            if wing is not None and row["wing"] != wing:
                continue
            if room is not None and row["room"] != room:
                continue
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
