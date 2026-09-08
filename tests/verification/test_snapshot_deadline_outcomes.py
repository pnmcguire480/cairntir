from __future__ import annotations

import sqlite3
from contextlib import closing
from types import SimpleNamespace

import pytest
from test_recovery_outcomes import contents

from cairntir.errors import MemoryStoreError
from cairntir.memory import store as storage
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.tasks import TaskBook


@pytest.mark.parametrize("complete", [True, False], ids=["committed", "incomplete"])
def test_snapshot_deadline_respects_sqlite_completion_and_rollback(
    seeded, tmp_path, monkeypatch, complete
):
    database, task, expected = seeded
    connect = sqlite3.connect
    with closing(connect(database)) as connection:
        connection.execute("CREATE TABLE padding (data BLOB)")
        connection.execute("INSERT INTO padding VALUES (zeroblob(2097152))")
        connection.commit()
    before = contents(database)
    clock = [0.0]
    observed = []

    class DelayedCallback(sqlite3.Connection):
        def backup(self, target, *, progress, **kwargs):
            def delayed(status, remaining, total):
                if (status == sqlite3.SQLITE_DONE) == complete:
                    observed.append((status, remaining, total))
                    clock[0] = 2.0
                progress(status, remaining, total)

            return super().backup(target, progress=delayed, **kwargs)

    snapshot = tmp_path / "snapshot.db"
    failure = None
    with monkeypatch.context() as patch:
        patch.setattr(storage, "time", SimpleNamespace(monotonic=lambda: clock[0]))
        patch.setattr(
            sqlite3, "connect", lambda *a, **kw: connect(*a, factory=DelayedCallback, **kw)
        )
        try:
            storage._backup_live_database(database, snapshot, deadline=1.0)
        except MemoryStoreError as exc:
            failure = exc

    assert contents(database) == before
    assert observed and observed[0][2] > 256
    if complete:
        assert observed[-1][:2] == (sqlite3.SQLITE_DONE, 0)
        assert contents(snapshot, standalone=True) == before
        assert failure is None, "RECOVERY: committed snapshot rejected after callback delay"
    else:
        assert observed[0][0] == sqlite3.SQLITE_OK and observed[0][1] > 0
        assert failure is not None and "timed out" in str(failure)
        with closing(connect(snapshot)) as connection:
            assert connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
            assert connection.execute("SELECT name FROM sqlite_master").fetchall() == []
        snapshot = tmp_path / "retry.db"
        storage._backup_live_database(database, snapshot, deadline=float("inf"))
        assert contents(snapshot, standalone=True) == before
    with storage.DrawerStore(snapshot, HashEmbeddingProvider(dimension=32)) as store:
        assert TaskBook(store).resume("recovery", task_id=task) == expected
