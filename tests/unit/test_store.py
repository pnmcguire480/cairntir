"""Unit tests for the sqlite-vec drawer store."""

from __future__ import annotations

import sqlite3
import struct
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import sqlite_vec

from cairntir.errors import (
    AnchorError,
    ContentIntegrityError,
    EmbeddingError,
    EmbeddingSpaceError,
    MemoryStoreError,
)
from cairntir.memory.embeddings import (
    PRODUCTION_CHAR_WINDOW,
    FastEmbedProvider,
    HashEmbeddingProvider,
    embedding_space_id,
)
from cairntir.memory.store import (
    SCHEMA_VERSION,
    DrawerStore,
    backup_database,
    inspect_embedding_space,
    reindex_database,
)
from cairntir.memory.taxonomy import Drawer, Layer


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[DrawerStore]:
    with DrawerStore(tmp_path / "cairntir.db", HashEmbeddingProvider(dimension=32)) as s:
        yield s


def _drawer(
    content: str, *, wing: str = "cairntir", room: str = "phase-1", layer: Layer = Layer.ON_DEMAND
) -> Drawer:
    return Drawer(wing=wing, room=room, content=content, layer=layer)


def test_add_assigns_id_and_roundtrips(store: DrawerStore) -> None:
    saved = store.add(_drawer("the cairn sees across time"))
    assert saved.id is not None and saved.id > 0
    fetched = store.get(saved.id)
    assert fetched is not None
    assert fetched.content == "the cairn sees across time"
    assert fetched.wing == "cairntir"


def test_get_returns_none_when_missing(store: DrawerStore) -> None:
    assert store.get(9999) is None


# The write-time guard (P2 of plans/2026-08-04-honest-and-whole.md). The
# leaked envelope below is the exact shape repaired by
# scripts/repair_leaked_metadata.py: real content, then a swallowed tool call.
_LEAKED_ENVELOPE_CONTENT = (
    "the real memory ends here.</content>\n"
    '<parameter name="metadata">{"anchors": [{"path": "src/cairntir/cli.py"}]}'
)


def test_add_rejects_tool_call_markup(store: DrawerStore) -> None:
    """The recurring 2026-04/05/08 damage shape must be refused at write time."""
    with pytest.raises(ContentIntegrityError, match="tool-call envelope"):
        store.add(_drawer(_LEAKED_ENVELOPE_CONTENT))
    assert store.get(1) is None  # nothing stored, no id consumed silently


def test_add_rejects_trailing_envelope_even_with_metadata(store: DrawerStore) -> None:
    drawer = Drawer(
        wing="cairntir",
        room="phase-1",
        content=_LEAKED_ENVELOPE_CONTENT,
        metadata={"note": "metadata arrived, but the tail is still a swallowed call"},
    )
    with pytest.raises(ContentIntegrityError, match="swallowed"):
        store.add(drawer)


def test_add_rejects_markup_mid_content_with_empty_metadata(store: DrawerStore) -> None:
    """check_store_health rule 3 parity: markers plus empty metadata is a leak."""
    marker = "<" + "/content>"
    with pytest.raises(ContentIntegrityError, match="fingerprint"):
        store.add(_drawer(f"a broken write left {marker} markup mid-content"))


def test_add_allows_quoted_markup_when_metadata_present(store: DrawerStore) -> None:
    """Documenting the damage pattern must stay writable — the guard's own
    history drawers quote these markers. Metadata is what tells a quote from
    a swallowed call."""
    marker = "<" + "/content>"
    drawer = Drawer(
        wing="cairntir",
        room="phase-1",
        content=f"the 2026-08-02 leaks serialized the envelope: {marker} markup in content",
        metadata={"note": "deliberate quote of the leak pattern"},
    )
    saved = store.add(drawer)
    assert saved.id is not None


def test_add_rejects_malformed_anchors(store: DrawerStore) -> None:
    """Legacy string-form anchors are rejected at write, not found at recall."""
    drawer = Drawer(
        wing="cairntir",
        room="phase-1",
        content="anchors written in the legacy bare-string shape",
        metadata={"anchors": ["src/cairntir/cli.py"]},
    )
    with pytest.raises(AnchorError, match="write rejected"):
        store.add(drawer)


def test_add_stores_well_formed_anchors(store: DrawerStore) -> None:
    drawer = Drawer(
        wing="cairntir",
        room="phase-1",
        content="anchors in the object shape recall_for_change reads",
        metadata={"anchors": [{"path": "src/cairntir/cli.py", "symbol": "app"}]},
    )
    saved = store.add(drawer)
    fetched = store.get(saved.id)
    assert fetched is not None
    assert fetched.metadata["anchors"] == [{"path": "src/cairntir/cli.py", "symbol": "app"}]


def test_list_by_filters_wing_room_layer(store: DrawerStore) -> None:
    store.add(_drawer("a", layer=Layer.IDENTITY))
    store.add(_drawer("b", layer=Layer.ESSENTIAL))
    store.add(_drawer("c", layer=Layer.ON_DEMAND))
    store.add(_drawer("d", wing="other", layer=Layer.ON_DEMAND))

    essentials = store.list_by(wing="cairntir", layer=Layer.ESSENTIAL)
    assert [d.content for d in essentials] == ["b"]

    on_demand = store.list_by(layer=Layer.ON_DEMAND)
    assert {d.content for d in on_demand} == {"c", "d"}


def test_search_returns_exact_match_first(store: DrawerStore) -> None:
    store.add(_drawer("kill cross-chat amnesia"))
    store.add(_drawer("3d printing post scarcity"))
    store.add(_drawer("sqlite vec backend"))

    results = store.search("kill cross-chat amnesia", limit=3)
    assert len(results) >= 1
    top_drawer, _distance = results[0]
    assert top_drawer.content == "kill cross-chat amnesia"


def test_search_scopes_to_wing(store: DrawerStore) -> None:
    store.add(_drawer("memory spike", wing="cairntir"))
    store.add(_drawer("memory spike", wing="other"))
    results = store.search("memory spike", wing="cairntir", limit=5)
    assert all(d.wing == "cairntir" for d, _ in results)
    assert len(results) == 1


def test_search_prefilters_wing_before_knn_limit(store: DrawerStore) -> None:
    """The only in-scope hit must survive even when outside global top-K."""
    for index in range(20):
        store.add(_drawer("identical crowded vector", wing=f"other-{index}"))
    store.add(_drawer("identical crowded vector", wing="wanted"))

    results = store.search("identical crowded vector", wing="wanted", limit=1)
    assert len(results) == 1
    assert results[0][0].wing == "wanted"


def test_search_prefilters_room_and_layer_before_knn_limit(store: DrawerStore) -> None:
    for index in range(20):
        store.add(
            _drawer(
                "identical scoped vector",
                room=f"other-{index}",
                layer=Layer.ESSENTIAL,
            )
        )
    store.add(
        _drawer(
            "identical scoped vector",
            room="wanted",
            layer=Layer.ON_DEMAND,
        )
    )

    results = store.search(
        "identical scoped vector",
        wing="cairntir",
        room="wanted",
        layer=Layer.ON_DEMAND,
        limit=1,
    )
    assert len(results) == 1
    assert results[0][0].room == "wanted"
    assert results[0][0].layer is Layer.ON_DEMAND


def test_prediction_fields_round_trip(store: DrawerStore) -> None:
    d = Drawer(
        wing="cairntir",
        room="v0-2",
        content="prediction-bound drawer",
        claim="migration will be forward-only",
        predicted_outcome="old rows load with None prediction fields",
        observed_outcome="old rows loaded with None prediction fields",
        delta="no surprise",
        supersedes_id=None,
    )
    saved = store.add(d)
    assert saved.id is not None
    fetched = store.get(saved.id)
    assert fetched is not None
    assert fetched.claim == "migration will be forward-only"
    assert fetched.predicted_outcome == "old rows load with None prediction fields"
    assert fetched.observed_outcome == "old rows loaded with None prediction fields"
    assert fetched.delta == "no surprise"
    assert fetched.supersedes_id is None


def test_supersedes_chain_round_trips(store: DrawerStore) -> None:
    first = store.add(_drawer("initial belief"))
    assert first.id is not None
    second = store.add(
        Drawer(
            wing="cairntir",
            room="phase-1",
            content="revised belief",
            supersedes_id=first.id,
        )
    )
    fetched = store.get(second.id or 0)
    assert fetched is not None
    assert fetched.supersedes_id == first.id


def test_migration_from_v1_database_preserves_old_rows(tmp_path: Path) -> None:
    """A pre-v2 database must open, upgrade, and keep its existing rows intact."""
    db_path = tmp_path / "legacy.db"

    # Hand-build a v1-shaped database (no prediction fields, no user_version).
    conn = sqlite3.connect(db_path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    with conn:
        conn.execute(
            """
            CREATE TABLE drawers (
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
        conn.execute(
            "CREATE VIRTUAL TABLE vec_drawers USING vec0("
            "drawer_id INTEGER PRIMARY KEY, embedding FLOAT[32])"
        )
        conn.execute(
            "INSERT INTO drawers (wing, room, content, layer, metadata, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                "cairntir",
                "legacy",
                "pre-v2 drawer",
                "on_demand",
                "{}",
                datetime.now(UTC).isoformat(),
            ),
        )
    conn.close()

    # Open through DrawerStore — migration should add the new columns
    # and the old row should deserialize cleanly with None prediction fields.
    with DrawerStore(db_path, HashEmbeddingProvider(dimension=32)) as s:
        legacy = s.list_by(wing="cairntir", room="legacy")
        assert len(legacy) == 1
        row = legacy[0]
        assert row.content == "pre-v2 drawer"
        assert row.claim is None
        assert row.predicted_outcome is None
        assert row.observed_outcome is None
        assert row.delta is None
        assert row.supersedes_id is None
        provenance = s.get_provenance(row.id or 0)
        assert provenance is not None
        assert provenance.host == "legacy"
        assert provenance.trust.value == "untrusted"

        # Legacy vectors have no provable provider identity. Raw access
        # survives migration, but semantic reads/writes fail closed.
        assert s.embedding_status().state == "unverified"
        with pytest.raises(EmbeddingSpaceError, match="reindex"):
            s.search("pre-v2 drawer")
        with pytest.raises(EmbeddingSpaceError, match="reindex"):
            s.add(_drawer("refused until verified"))

        # PRAGMA user_version is stamped even though semantic behavior remains
        # disabled pending the explicit offline index rebuild.
        version = s._conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == SCHEMA_VERSION

    migration_backups = list(tmp_path.glob("legacy.pre-v6-*.db"))
    assert len(migration_backups) == 1

    receipt = reindex_database(db_path, HashEmbeddingProvider(dimension=32))
    assert receipt.drawer_count == 1

    with DrawerStore(db_path, HashEmbeddingProvider(dimension=32)) as s:
        assert s.embedding_status().verified

        # New inserts work only after the explicit rebuild established the
        # embedding-space identity.
        saved = s.add(
            Drawer(
                wing="cairntir",
                room="legacy",
                content="post-migration drawer",
                claim="migration is idempotent",
                predicted_outcome="reopening does not re-alter",
            )
        )
        assert saved.id is not None
        got = s.get(saved.id)
        assert got is not None
        assert got.claim == "migration is idempotent"

    # Reopening the same DB is a no-op for migration (idempotency check).
    with DrawerStore(db_path, HashEmbeddingProvider(dimension=32)) as s2:
        assert len(s2.list_by(wing="cairntir", room="legacy")) == 2


def test_migration_from_v2_database_preserves_old_rows(tmp_path: Path) -> None:
    """A v2-shaped database must upgrade to v4 without losing prediction fields."""
    db_path = tmp_path / "v2.db"

    conn = sqlite3.connect(db_path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    with conn:
        conn.execute(
            """
            CREATE TABLE drawers (
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
                supersedes_id     INTEGER
            )
            """
        )
        conn.execute(
            "CREATE VIRTUAL TABLE vec_drawers USING vec0("
            "drawer_id INTEGER PRIMARY KEY, embedding FLOAT[32])"
        )
        conn.execute(
            "INSERT INTO drawers (wing, room, content, layer, metadata, created_at,"
            " claim, predicted_outcome) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "cairntir",
                "legacy",
                "v2 row",
                "on_demand",
                "{}",
                datetime.now(UTC).isoformat(),
                "v2 claim",
                "held",
            ),
        )
    conn.close()

    with DrawerStore(db_path, HashEmbeddingProvider(dimension=32)) as s:
        rows = s.list_by(wing="cairntir", room="legacy")
        assert len(rows) == 1
        row = rows[0]
        assert row.claim == "v2 claim"
        assert row.predicted_outcome == "held"
        assert row.belief_mass == pytest.approx(1.0)  # default backfilled by migration
        version = s._conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == SCHEMA_VERSION


def test_migration_from_v3_database_preserves_access_counters(tmp_path: Path) -> None:
    """A v3-shaped database must upgrade to v4 without losing access counters."""
    db_path = tmp_path / "v3.db"

    conn = sqlite3.connect(db_path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    now = datetime.now(UTC).isoformat()
    with conn:
        conn.execute(
            """
            CREATE TABLE drawers (
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
                access_count      INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            "CREATE VIRTUAL TABLE vec_drawers USING vec0("
            "drawer_id INTEGER PRIMARY KEY, embedding FLOAT[32])"
        )
        conn.execute(
            "INSERT INTO drawers (wing, room, content, layer, metadata, created_at,"
            " last_accessed_at, access_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("cairntir", "legacy", "v3 row", "on_demand", "{}", now, now, 5),
        )
    conn.close()

    with DrawerStore(db_path, HashEmbeddingProvider(dimension=32)) as s:
        rows = s.list_by(wing="cairntir", room="legacy")
        assert len(rows) == 1
        assert rows[0].belief_mass == pytest.approx(1.0)
        version = s._conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == SCHEMA_VERSION


def test_migration_from_v4_requires_explicit_embedding_verification(tmp_path: Path) -> None:
    """A v4 database remains readable but cannot guess which provider made its vectors."""
    db_path = tmp_path / "v4.db"
    provider = HashEmbeddingProvider(dimension=32)
    now = datetime.now(UTC).isoformat()
    conn = sqlite3.connect(db_path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    with conn:
        conn.execute(
            """
            CREATE TABLE drawers (
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
        conn.execute(
            "CREATE VIRTUAL TABLE vec_drawers USING vec0("
            "drawer_id INTEGER PRIMARY KEY, embedding FLOAT[32])"
        )
        cursor = conn.execute(
            "INSERT INTO drawers (wing, room, content, layer, metadata, created_at,"
            " last_accessed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("cairntir", "legacy", "v4 row", "on_demand", "{}", now, now),
        )
        drawer_id = int(cursor.lastrowid or 0)
        vector = provider.embed(["v4 row"])[0]
        conn.execute(
            "INSERT INTO vec_drawers(drawer_id, embedding) VALUES (?, ?)",
            (drawer_id, struct.pack(f"{len(vector)}f", *vector)),
        )
        conn.execute("PRAGMA user_version = 4")
    conn.close()

    with DrawerStore(db_path, provider) as store:
        assert store.list_by()[0].content == "v4 row"
        assert store.embedding_status().state == "unverified"
        with pytest.raises(EmbeddingSpaceError):
            store.search("v4 row")

    reindex_database(db_path, provider)
    with DrawerStore(db_path, provider) as store:
        assert store.embedding_status().verified
        assert store.search("v4 row")[0][0].content == "v4 row"
        assert store._conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_migration_from_v5_backfills_provenance_and_trust_filters(tmp_path: Path) -> None:
    db_path = tmp_path / "v5.db"
    provider = HashEmbeddingProvider(dimension=32)
    now = datetime.now(UTC).isoformat()
    conn = sqlite3.connect(db_path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    with conn:
        conn.execute(
            """
            CREATE TABLE drawers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wing TEXT NOT NULL,
                room TEXT NOT NULL,
                content TEXT NOT NULL,
                layer TEXT NOT NULL,
                metadata TEXT NOT NULL,
                created_at TEXT NOT NULL,
                claim TEXT,
                predicted_outcome TEXT,
                observed_outcome TEXT,
                delta TEXT,
                supersedes_id INTEGER,
                last_accessed_at TEXT,
                access_count INTEGER NOT NULL DEFAULT 0,
                belief_mass REAL NOT NULL DEFAULT 1.0
            )
            """
        )
        conn.execute(
            "CREATE VIRTUAL TABLE vec_drawers USING vec0("
            "drawer_id INTEGER PRIMARY KEY, embedding FLOAT[32], "
            "wing TEXT, room TEXT, layer TEXT)"
        )
        cursor = conn.execute(
            "INSERT INTO drawers("
            "wing, room, content, layer, metadata, created_at, last_accessed_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("cairntir", "legacy", "v5 row", "on_demand", "{}", now, now),
        )
        drawer_id = int(cursor.lastrowid or 0)
        vector = provider.embed(["v5 row"])[0]
        conn.execute(
            "INSERT INTO vec_drawers("
            "drawer_id, embedding, wing, room, layer) VALUES (?, ?, ?, ?, ?)",
            (
                drawer_id,
                struct.pack(f"{len(vector)}f", *vector),
                "cairntir",
                "legacy",
                "on_demand",
            ),
        )
        conn.execute("CREATE TABLE store_metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.executemany(
            "INSERT INTO store_metadata(key, value) VALUES (?, ?)",
            (
                ("embedding_space_id", embedding_space_id(provider)),
                ("embedding_dimension", "32"),
                ("embedding_generation", "v5-generation"),
                ("embedding_verified_at", now),
            ),
        )
        conn.execute("PRAGMA user_version = 5")
    conn.close()

    with DrawerStore(db_path, provider) as store:
        provenance = store.get_provenance(drawer_id)
        assert provenance is not None
        assert provenance.host == "legacy"
        assert store.embedding_status().state == "corrupt"

    reindex_database(db_path, provider)
    with DrawerStore(db_path, provider) as store:
        assert store.embedding_status().verified
        assert store.search("v5 row")[0][0].id == drawer_id


def test_touch_and_stale_ids_drive_forgetting_curve(store: DrawerStore) -> None:
    old = datetime.now(UTC) - timedelta(days=10)
    saved = store.add(Drawer(wing="cairntir", room="room-x", content="x", created_at=old))
    assert saved.id is not None
    cutoff = datetime.now(UTC) - timedelta(days=7)
    assert store.stale_ids(older_than=cutoff, layer=Layer.ON_DEMAND) == [saved.id]
    # A get() bumps last_accessed_at, so the drawer is no longer stale.
    store.get(saved.id)
    assert store.stale_ids(older_than=cutoff, layer=Layer.ON_DEMAND) == []


def test_update_layer_moves_drawer(store: DrawerStore) -> None:
    saved = store.add(_drawer("demote me", layer=Layer.ON_DEMAND))
    assert saved.id is not None
    store.update_layer(saved.id, Layer.DEEP)
    fetched = store.get(saved.id)
    assert fetched is not None
    assert fetched.layer == Layer.DEEP
    assert store.search("demote me", layer=Layer.ON_DEMAND) == []
    assert store.search("demote me", layer=Layer.DEEP)[0][0].id == saved.id


def test_metadata_is_preserved(store: DrawerStore) -> None:
    d = Drawer(
        wing="cairntir",
        room="phase-1",
        content="with meta",
        metadata={"k": "v", "n": 3},
    )
    saved = store.add(d)
    assert saved.id is not None
    fetched = store.get(saved.id)
    assert fetched is not None
    assert fetched.metadata == {"k": "v", "n": 3}


def test_new_store_stamps_verified_embedding_space(tmp_path: Path) -> None:
    provider = HashEmbeddingProvider(dimension=32)
    with DrawerStore(tmp_path / "verified.db", provider) as s:
        status = s.embedding_status()
        assert status.verified
        assert status.stored_space_id == embedding_space_id(provider)
        assert status.stored_dimension == 32
        assert status.vector_dimension == 32
        assert status.generation
        assert status.drawer_count == status.vector_count == 0


def test_mismatched_space_keeps_raw_drawers_readable_and_refuses_semantics(
    tmp_path: Path,
) -> None:
    path = tmp_path / "mismatch.db"
    with DrawerStore(path, HashEmbeddingProvider(dimension=32)) as original:
        saved = original.add(_drawer("one canonical semantic space"))
        assert saved.id is not None

    with DrawerStore(path, HashEmbeddingProvider(dimension=64)) as mismatched:
        status = mismatched.embedding_status()
        assert status.state == "mismatch"
        assert mismatched.list_by()[0].content == "one canonical semantic space"
        assert mismatched.get(saved.id) is not None
        with pytest.raises(EmbeddingSpaceError, match="mismatch"):
            mismatched.search("canonical")
        with pytest.raises(EmbeddingSpaceError, match="mismatch"):
            mismatched.add(_drawer("must not contaminate"))


class _AlternateSpaceProvider:
    dimension = 32
    embedding_space_id = "test/alternate-semantic-space-v1"

    def __init__(self) -> None:
        self._delegate = HashEmbeddingProvider(dimension=32)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return self._delegate.embed(texts)


def test_reindex_repairs_same_dimension_mismatch_and_changes_generation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "repair.db"
    with DrawerStore(path, HashEmbeddingProvider(dimension=32)) as original:
        original.add(_drawer("rebuild all semantic vectors"))
        old_generation = original.embedding_status().generation

    with DrawerStore(path, _AlternateSpaceProvider()) as replacement:
        receipt = replacement.reindex_embeddings(batch_size=1)
        status = replacement.embedding_status()
        assert status.verified
        assert receipt.dimension == 32
        assert receipt.generation != old_generation
        assert status.vector_dimension == 32
        assert replacement.search("rebuild all semantic vectors")[0][0].content == (
            "rebuild all semantic vectors"
        )


def test_offline_reindex_changes_dimension_via_verified_sidecar(tmp_path: Path) -> None:
    path = tmp_path / "dimension-change.db"
    with DrawerStore(path, HashEmbeddingProvider(dimension=32)) as original:
        original.add(_drawer("sidecar rebuild"))

    receipt = reindex_database(path, HashEmbeddingProvider(dimension=64), batch_size=1)
    assert receipt.dimension == 64
    report = inspect_embedding_space(path, HashEmbeddingProvider(dimension=64))
    assert report.verified
    assert report.vector_dimension == 64
    with DrawerStore(path, HashEmbeddingProvider(dimension=64)) as reopened:
        assert reopened.search("sidecar rebuild")[0][0].content == "sidecar rebuild"


class _WritingDuringReindexProvider:
    """Commits to the source database from a second connection mid-rebuild.

    This is the concurrent holder the guard exists to refuse, and it is the
    shape that actually happens: an MCP server that was idle at checkpoint
    time (so ``wal_checkpoint(TRUNCATE)`` reported not-busy) waking up and
    writing while a long rebuild runs in the sidecar.
    """

    dimension = 32
    embedding_space_id = "cairntir/hash-sha256-cyclic-v1/dimension=32"

    def __init__(self, source: Path) -> None:
        self._source = source
        self._written = False
        self._inner = HashEmbeddingProvider(dimension=32)
        self.intruder: sqlite3.Connection | None = None

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not self._written:
            self._written = True
            # Held open on purpose, and this is the whole point. A client
            # that connects, writes and *closes* becomes the last connection,
            # so SQLite checkpoints the WAL back into the main file on close
            # and the old mtime guard would notice. A real MCP server does
            # not close — it stays connected across the rebuild, its frames
            # stay in `-wal`, and the main file's size and mtime never move.
            # That is the case the old guard could not see.
            self.intruder = sqlite3.connect(self._source)
            self.intruder.execute(
                "UPDATE drawers SET content = content || ' (edited by another client)'"
            )
            self.intruder.commit()
        return self._inner.embed(texts)

    def close_intruder(self) -> None:
        if self.intruder is not None:
            self.intruder.close()
            self.intruder = None


def test_reindex_refuses_to_replace_a_database_written_during_the_rebuild(
    tmp_path: Path,
) -> None:
    """The WAL-mode concurrency guard, which had no test until 1.6.3.

    The previous guard compared ``(st_size, st_mtime_ns)`` on the *main*
    database file. In WAL mode a committing writer appends to ``<db>-wal``
    and leaves the main file untouched until checkpoint, so those two stats
    were identical across a window in which another connection had committed
    — the guard could not fire on the one condition it was written for.
    """
    path = tmp_path / "concurrent.db"
    with DrawerStore(path, HashEmbeddingProvider(dimension=32)) as store:
        store.add(_drawer("original content"))

    provider = _WritingDuringReindexProvider(path)
    try:
        with pytest.raises(MemoryStoreError, match="changed while reindex was running"):
            reindex_database(path, provider, batch_size=1)
        assert provider._written, "the test did not actually write during the window"
        # The write landed in the WAL and left the main file untouched — the
        # precondition that made the pre-1.6.3 stat comparison unable to fire.
        assert path.with_name(f"{path.name}-wal").exists()
    finally:
        provider.close_intruder()

    # The intruder's write survives; the rebuild is discarded, not half-applied.
    with DrawerStore(path, HashEmbeddingProvider(dimension=32)) as reopened:
        assert "edited by another client" in reopened.list_by()[0].content


def test_reindex_discards_stale_write_ahead_sidecars(tmp_path: Path) -> None:
    """A surviving ``-wal`` must never outlive the file it belonged to.

    A write-ahead log has no identity binding to its database. Left beside a
    swapped-in rebuild, its frames can be recovered onto the new file — old
    page images replayed over a store whose vec table may have a different
    vector dimension.
    """
    path = tmp_path / "sidecars.db"
    with DrawerStore(path, HashEmbeddingProvider(dimension=32)) as store:
        store.add(_drawer("sidecar hygiene"))

    wal, shm = path.with_name(f"{path.name}-wal"), path.with_name(f"{path.name}-shm")
    wal.write_bytes(b"stale frames from the pre-rebuild database")

    reindex_database(path, HashEmbeddingProvider(dimension=64), batch_size=1)

    assert not wal.exists(), "stale -wal survived the swap"
    assert not shm.exists(), "stale -shm survived the swap"
    with DrawerStore(path, HashEmbeddingProvider(dimension=64)) as reopened:
        assert reopened.list_by()[0].content == "sidecar hygiene"


def test_reindex_refuses_drawers_wider_than_the_embedder_window(tmp_path: Path) -> None:
    """A rebuild must not silently re-truncate what it cannot embed whole."""
    path = tmp_path / "oversized.db"
    with DrawerStore(path, HashEmbeddingProvider(dimension=32)) as store:
        store.add(_drawer("x" * (PRODUCTION_CHAR_WINDOW + 1)))

    with pytest.raises(EmbeddingSpaceError, match="exceed the embedder"):
        reindex_database(path, HashEmbeddingProvider(dimension=64), batch_size=1)


class _FailingReindexProvider:
    dimension = 32
    embedding_space_id = "cairntir/hash-sha256-cyclic-v1/dimension=32"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        raise EmbeddingError(f"intentional failure for {len(texts)} inputs")


def test_failed_reindex_preserves_verified_index(tmp_path: Path) -> None:
    path = tmp_path / "atomic.db"
    with DrawerStore(path, HashEmbeddingProvider(dimension=32)) as original:
        original.add(_drawer("old index survives"))
        old_generation = original.embedding_status().generation

    with DrawerStore(path, _FailingReindexProvider()) as failing:
        with pytest.raises(EmbeddingError, match="intentional failure"):
            failing.reindex_embeddings()
        assert failing.embedding_status().generation == old_generation

    with DrawerStore(path, HashEmbeddingProvider(dimension=32)) as reopened:
        assert reopened.embedding_status().verified
        assert reopened.embedding_status().generation == old_generation
        assert reopened.search("old index survives")[0][0].content == "old index survives"


def test_failed_index_swap_rolls_back_old_vectors_and_metadata(tmp_path: Path) -> None:
    path = tmp_path / "swap-rollback.db"
    with DrawerStore(path, HashEmbeddingProvider(dimension=32)) as original:
        original.add(_drawer("transactional old vector"))
        old_generation = original.embedding_status().generation

    with DrawerStore(path, _AlternateSpaceProvider()) as replacement:
        replacement._conn.execute(
            """
            CREATE TRIGGER reject_embedding_metadata_update
            BEFORE UPDATE ON store_metadata
            BEGIN
                SELECT RAISE(ABORT, 'intentional metadata failure');
            END
            """
        )
        with pytest.raises(MemoryStoreError, match="intentional metadata failure"):
            replacement.reindex_embeddings()
        replacement._conn.execute("DROP TRIGGER reject_embedding_metadata_update")
        status = replacement.embedding_status()
        assert status.state == "mismatch"
        assert status.vector_dimension == 32
        assert status.generation == old_generation

    with DrawerStore(path, HashEmbeddingProvider(dimension=32)) as reopened:
        assert reopened.embedding_status().verified
        assert reopened.search("transactional old vector")[0][0].content == (
            "transactional old vector"
        )


def test_future_schema_is_refused_without_mutation(tmp_path: Path) -> None:
    path = tmp_path / "future.db"
    conn = sqlite3.connect(path)
    with conn:
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    conn.close()

    with pytest.raises(MemoryStoreError, match="newer"):
        DrawerStore(path, HashEmbeddingProvider(dimension=32))

    check = sqlite3.connect(path)
    try:
        assert check.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION + 1
        assert (
            check.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='drawers'"
            ).fetchone()
            is None
        )
    finally:
        check.close()


def test_inspection_is_read_only_and_reports_unverified_legacy_index(
    tmp_path: Path,
) -> None:
    path = tmp_path / "inspect.db"
    with DrawerStore(path, HashEmbeddingProvider(dimension=32)):
        pass
    conn = sqlite3.connect(path)
    with conn:
        conn.execute("DELETE FROM store_metadata")
        conn.execute("PRAGMA user_version = 4")
    conn.close()

    report = inspect_embedding_space(path, HashEmbeddingProvider(dimension=32))
    assert report.state == "unverified"

    check = sqlite3.connect(path)
    try:
        assert check.execute("PRAGMA user_version").fetchone()[0] == 4
        assert check.execute("SELECT COUNT(*) FROM store_metadata").fetchone()[0] == 0
    finally:
        check.close()


def test_backup_database_creates_independent_verified_copy(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    destination = tmp_path / "backup.db"
    provider = HashEmbeddingProvider(dimension=32)
    with DrawerStore(source, provider) as original:
        original.add(_drawer("backup before rebuild"))

    assert backup_database(source, destination) == destination
    report = inspect_embedding_space(destination, provider)
    assert report.verified
    assert report.drawer_count == report.vector_count == 1


def test_provider_identity_distinguishes_algorithm_model_and_dimension() -> None:
    hash_32 = embedding_space_id(HashEmbeddingProvider(dimension=32))
    hash_64 = embedding_space_id(HashEmbeddingProvider(dimension=64))
    fastembed = embedding_space_id(FastEmbedProvider())
    assert len({hash_32, hash_64, fastembed}) == 3
