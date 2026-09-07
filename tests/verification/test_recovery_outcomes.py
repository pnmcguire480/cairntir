from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from contextlib import closing, contextmanager
from pathlib import Path

import pytest
import sqlite_vec

from cairntir import backups
from cairntir.errors import MemoryStoreError
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore, inspect_database_integrity
from cairntir.memory.taxonomy import Drawer
from cairntir.tasks import TaskBook

TEXT = "  The user's exact memory: café 日本語 🌲\nKeep both revisions.\t"


def contents(database: Path, *, standalone: bool = False) -> str:
    uri = database.resolve().as_uri() + ("?mode=ro&immutable=1" if standalone else "?mode=ro")
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        connection.enable_load_extension(True)
        sqlite_vec.load(connection)
        connection.enable_load_extension(False)
        assert connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        schema = connection.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"
        ).fetchall()
        tables = {}
        for kind, name, *_ in schema:
            if kind == "table":
                quoted = name.replace('"', '""')
                rows = connection.execute(f'SELECT * FROM "{quoted}"').fetchall()  # noqa: S608
                tables[name] = sorted(rows, key=repr)
        return repr((schema, tables, connection.execute("PRAGMA user_version").fetchone()))


def add(store: DrawerStore, text: str):
    return store.add(Drawer(wing="recovery", room="evidence", content=text), model="verification")


@pytest.fixture()
def seeded(tmp_cairntir_home: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CAIRNTIR_GRANT_FILE", raising=False)
    database = tmp_cairntir_home / "cairntir.db"
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        evidence = add(store, TEXT)
        state = {
            "expected_revision": 0,
            "idempotency_key": "create-recovery",
            "status": "active",
            "completed": [],
            "outstanding": ["restore and resume"],
            "next_action": "Verify restoration.",
            "evidence_ids": [evidence.id],
        }
        book = TaskBook(store)
        first = json.loads(
            book.checkpoint(
                wing="recovery", room="tasks", content=TEXT, model="verification", checkpoint=state
            )
        )
        state.update(
            task_id=first["task_id"],
            expected_revision=1,
            idempotency_key="advance-recovery",
            completed=["original evidence captured"],
        )
        second = json.loads(
            book.checkpoint(
                wing="recovery",
                room="tasks",
                content="Saved progress.",
                model="verification",
                checkpoint=state,
            )
        )
        expected = book.resume("recovery", task_id=second["task_id"])
    return database, second["task_id"], expected


def test_restored_backup_preserves_every_table_and_resumes_task(seeded, tmp_path: Path) -> None:
    database, task, expected = seeded
    before = contents(database)
    backups.configure(database, tmp_path / "snapshots")
    result = backups.run(database)
    assert result["status"] == "created"
    snapshot = Path(result["snapshot"]["path"])
    restored = tmp_path / "restored" / "cairntir.db"
    restored.parent.mkdir()
    shutil.copyfile(snapshot, restored)
    assert contents(restored, standalone=True) == before, "RECOVERY: restored tables differ"
    assert contents(database) == before
    with DrawerStore(restored, HashEmbeddingProvider(dimension=32)) as store:
        assert TaskBook(store).resume("recovery", task_id=task) == expected
        checkpoint = json.loads(expected)["checkpoint"]
        assert checkpoint["original_request"] == TEXT
        assert checkpoint["completed"] == ["original evidence captured"]
        assert checkpoint["outstanding"] == ["restore and resume"]
        matches = store.search(TEXT, wing="recovery", room="evidence", limit=1)
        assert matches[0][0].content == TEXT
    assert contents(snapshot, standalone=True) == before


def test_failed_write_after_vector_insert_rolls_back_every_table(seeded) -> None:
    database, task, expected = seeded
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        store._conn.execute(
            "CREATE TRIGGER reject_portable BEFORE INSERT ON portable_records "
            "BEGIN SELECT RAISE(ABORT, 'injected late write failure'); END"
        )
        before = contents(database)
        with pytest.raises(MemoryStoreError, match="injected late write failure"):
            add(store, "This drawer and its physical vector must both roll back.")
        assert contents(database) == before, "RECOVERY: failed write left partial data"
        assert TaskBook(store).resume("recovery", task_id=task) == expected
        store._conn.execute("DROP TRIGGER reject_portable")
        saved = add(store, "A subsequent valid write succeeds.")
        assert saved.id is not None
    assert "A subsequent valid write succeeds." in contents(database)


def test_commit_failure_rolls_back_drawers_vectors_and_deferred_rows(seeded) -> None:
    database, task, expected = seeded
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        store._conn.execute(
            "CREATE TABLE deferred_check (drawer_id INTEGER REFERENCES drawers(id) "
            "DEFERRABLE INITIALLY DEFERRED)"
        )
        before = contents(database)
        with (
            pytest.raises(MemoryStoreError, match="failed to commit transaction"),
            store.transaction(),
        ):
            add(store, "This insert succeeds before the deferred constraint fails.")
            store._conn.execute("INSERT INTO deferred_check VALUES (-99)")
        assert contents(database) == before, "RECOVERY: failed commit left partial data"
        assert TaskBook(store).resume("recovery", task_id=task) == expected
        add(store, "Writes recover after failed commit.")


def test_nested_rollback_preserves_outer_writes_and_original_task(seeded) -> None:
    database, task, expected = seeded
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        with store.transaction():
            add(store, "outer-before")
            with pytest.raises(RuntimeError, match="abort inner unit"), store.transaction():
                add(store, "inner-discarded")
                raise RuntimeError("abort inner unit")
            add(store, "outer-after")
        assert TaskBook(store).resume("recovery", task_id=task) == expected
    state = contents(database)
    assert "outer-before" in state and "outer-after" in state
    assert "inner-discarded" not in state, "RECOVERY: nested rollback retained discarded data"


@contextmanager
def child(code: str, database: Path, control: Path):
    process = subprocess.Popen(  # noqa: S603 - isolated test code and disposable database
        [sys.executable, "-c", code, str(database), str(control)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=os.environ | {"PYTHONUTF8": "1"},
    )
    try:
        deadline = time.monotonic() + 12
        while not control.exists():
            assert process.poll() is None, process.communicate(timeout=5)
            assert time.monotonic() < deadline, "test child did not reach its barrier"
            time.sleep(0.01)
        yield process
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=15)


def test_real_writer_contention_reports_failure_then_recovers(seeded, tmp_path: Path) -> None:
    database, task, expected = seeded
    code = (
        "import sqlite3,sys; from pathlib import Path; c=sqlite3.connect(sys.argv[1]); "
        "c.execute('BEGIN IMMEDIATE'); Path(sys.argv[2]).touch(); sys.stdin.readline(); "
        "c.rollback(); c.close()"
    )
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        store._conn.execute("PRAGMA busy_timeout=100")
        before = contents(database)
        with child(code, database, tmp_path / "locked") as process:
            with pytest.raises(MemoryStoreError, match="locked"):
                add(store, "A competing writer must not appear successful.")
            assert contents(database) == before
            assert TaskBook(store).resume("recovery", task_id=task) == expected
            process.communicate("release\n", timeout=5)
            assert process.returncode == 0
        add(store, "Writer recovered after contention.")
    assert "Writer recovered after contention." in contents(database)


def test_process_death_rolls_back_uncommitted_vectors_and_drawers(seeded, tmp_path: Path) -> None:
    database, _, _ = seeded
    before = contents(database)
    code = (
        "import sys; from pathlib import Path; from cairntir.memory.store import DrawerStore; "
        "from cairntir.memory.embeddings import HashEmbeddingProvider; "
        "from cairntir.memory.taxonomy import Drawer; "
        "s=DrawerStore(Path(sys.argv[1]),HashEmbeddingProvider(dimension=32)); "
        "t=s.transaction(); t.__enter__(); "
        "s.add(Drawer(wing='recovery',room='evidence',content='uncommitted child write')); "
        "Path(sys.argv[2]).touch(); sys.stdin.readline()"
    )
    with child(code, database, tmp_path / "uncommitted") as process:
        process.kill()
        process.wait(timeout=5)
    assert contents(database) == before, "RECOVERY: process death leaked uncommitted data"


def test_unavailable_destination_preserves_backup_and_writes_then_recovers(seeded, tmp_path: Path):
    database, _, _ = seeded
    destination = tmp_path / "removable-destination"
    backups.configure(database, destination)
    first = backups.run(database)["snapshot"]
    before = contents(Path(first["path"]), standalone=True)
    away = tmp_path / "disconnected-volume"
    destination.rename(away)
    destination.write_text("mount point unavailable", encoding="utf-8")
    backups.configure(database, destination, interval_hours=1e-12)
    with (
        pytest.warns(backups.BackupWarning, match="automatic backup failed"),
        DrawerStore(database, HashEmbeddingProvider(dimension=32), automatic_backups=True) as store,
    ):
        add(store, "Memory remains writable while the destination is unavailable.")
    state = backups.status(database)
    assert state["last_error"] and state["last_success_at"] == first["created_at"]
    assert "Memory remains writable" in contents(database)
    preserved = away / Path(first["path"]).relative_to(destination)
    assert contents(preserved, standalone=True) == before
    destination.unlink()
    away.rename(destination)
    result = backups.run(database)
    assert result["status"] == "created" and result["last_error"] is None
    assert contents(Path(result["snapshot"]["path"]), standalone=True) == contents(database)


def test_interrupted_backup_never_publishes_partial_and_next_attempt_restores(
    seeded, tmp_path: Path
):
    database, _, _ = seeded
    destination = tmp_path / "snapshots"
    backups.configure(database, destination)
    first = backups.run(database)["snapshot"]
    before = contents(database)
    code = """import sys,time
from pathlib import Path
from cairntir import backups
database, control = Path(sys.argv[1]), Path(sys.argv[2])
prepare = backups._prepare_snapshot
def pause(*args):
    prepare(*args)
    control.write_text(str(args[1]),encoding='utf-8')
    sys.stdin.readline()
backups._prepare_snapshot = pause
backups._publish_snapshot(database,backups._load(database),backups.utc_now(),time.monotonic()+30)
"""
    control = tmp_path / "copied-before-publication"
    with child(code, database, control) as process:
        staged = Path(control.read_text(encoding="utf-8"))
        assert contents(staged, standalone=True) == before
        process.kill()
        process.wait(timeout=5)
    assert backups.status(database)["snapshots"] == [first]
    assert contents(Path(first["path"]), standalone=True) == before
    result = backups.run(database)
    assert result["status"] == "created"
    assert not staged.exists()
    assert contents(Path(result["snapshot"]["path"]), standalone=True) == before
    assert contents(database) == before


@pytest.mark.parametrize("damage", ["header", "truncate"])
def test_damaged_snapshot_reports_error_and_keeps_usable_recovery_point(
    seeded, tmp_path: Path, damage
):
    database, _, _ = seeded
    backups.configure(database, tmp_path / "snapshots")
    snapshot = Path(backups.run(database)["snapshot"]["path"])
    before = contents(database)
    damaged = tmp_path / "damaged.db"
    raw = snapshot.read_bytes()
    damaged.write_bytes(b"BROKEN DATABASE!" + raw[16:] if damage == "header" else raw[:100])
    with pytest.raises(MemoryStoreError, match=r"integrity|malformed|database"):
        inspect_database_integrity(damaged)
    assert contents(database) == contents(snapshot, standalone=True) == before
    restored = tmp_path / "restored.db"
    shutil.copyfile(snapshot, restored)
    assert inspect_database_integrity(restored).ok
    assert contents(restored, standalone=True) == before
