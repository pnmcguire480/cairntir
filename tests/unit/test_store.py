"""Unit tests for the sqlite-vec drawer store."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import sqlite_vec

from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import SCHEMA_VERSION, DrawerStore
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

        # New inserts alongside legacy rows must still work and carry
        # their prediction fields through.
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

        # PRAGMA user_version is stamped to the current schema version.
        version = s._conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == SCHEMA_VERSION

    # Reopening the same DB is a no-op for migration (idempotency check).
    with DrawerStore(db_path, HashEmbeddingProvider(dimension=32)) as s2:
        assert len(s2.list_by(wing="cairntir", room="legacy")) == 2


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
