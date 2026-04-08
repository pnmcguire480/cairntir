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
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import sqlite_vec

from cairntir.errors import MemoryStoreError
from cairntir.memory.taxonomy import Drawer, Layer

if TYPE_CHECKING:
    from cairntir.memory.embeddings import EmbeddingProvider


def _pack(vec: list[float]) -> bytes:
    """Pack a float vector into the little-endian float32 bytes sqlite-vec expects."""
    return struct.pack(f"{len(vec)}f", *vec)


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
                        id         INTEGER PRIMARY KEY AUTOINCREMENT,
                        wing       TEXT NOT NULL,
                        room       TEXT NOT NULL,
                        content    TEXT NOT NULL,
                        layer      TEXT NOT NULL,
                        metadata   TEXT NOT NULL,
                        created_at TEXT NOT NULL
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
        except sqlite3.Error as exc:
            raise MemoryStoreError(f"failed to initialize schema: {exc}") from exc

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
                    INSERT INTO drawers (wing, room, content, layer, metadata, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        drawer.wing,
                        drawer.room,
                        drawer.content,
                        drawer.layer.value,
                        json.dumps(drawer.metadata, sort_keys=True),
                        drawer.created_at.isoformat(),
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
        """Return a drawer by id, or ``None`` if missing."""
        try:
            row = self._conn.execute("SELECT * FROM drawers WHERE id = ?", (drawer_id,)).fetchone()
        except sqlite3.Error as exc:
            raise MemoryStoreError(f"failed to fetch drawer {drawer_id}: {exc}") from exc
        return None if row is None else _row_to_drawer(row)

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
    ) -> list[tuple[Drawer, float]]:
        """Semantic-search drawers. Returns ``(drawer, distance)`` pairs, closest first."""
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
        return results


def _row_to_drawer(row: sqlite3.Row) -> Drawer:
    return Drawer(
        id=int(row["id"]),
        wing=str(row["wing"]),
        room=str(row["room"]),
        content=str(row["content"]),
        layer=Layer(row["layer"]),
        metadata=json.loads(row["metadata"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )
