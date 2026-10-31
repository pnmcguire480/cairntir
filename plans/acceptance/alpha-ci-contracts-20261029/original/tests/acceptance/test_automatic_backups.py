"""Independent automatic-backup contract; real stores, copies, locks and transports."""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import os
import queue
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from contextlib import closing, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import sqlite_vec

from cairntir.errors import CairntirError
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer

ROOT = Path(__file__).resolve().parents[2]
START = datetime(2026, 9, 7, 12, tzinfo=UTC)
WING = "backup-acceptance"


def _api() -> Any:
    try:
        api = importlib.import_module("cairntir.backups")
    except ModuleNotFoundError as exc:
        if exc.name != "cairntir.backups":
            raise
        pytest.fail("AUTOMATIC_BACKUPS_UNIMPLEMENTED: cairntir.backups", pytrace=False)
    for name in ("configure", "status", "run", "disable", "utc_now"):
        assert callable(getattr(api, name, None)), f"missing backup API: {name}"
    assert issubclass(api.BackupError, CairntirError)
    assert issubclass(api.BackupWarning, UserWarning)
    return api


def _provider() -> HashEmbeddingProvider:
    return HashEmbeddingProvider(dimension=32)


class NoEmbedding(HashEmbeddingProvider):
    def __init__(self) -> None:
        super().__init__(dimension=32)

    def embed(self, texts: Any) -> Any:
        raise AssertionError("backup attempted to re-embed preserved evidence")


def _add(store: DrawerStore, text: str) -> Any:
    return store.add(Drawer(wing=WING, room="evidence", content=text))


def _time(value: str) -> datetime:
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert instant.tzinfo is not None
    return instant.astimezone(UTC)


def _state(path: Path, *, standalone: bool = False) -> str:
    uri = path.resolve().as_uri() + ("?immutable=1" if standalone else "?mode=ro")
    with closing(sqlite3.connect(uri, uri=True)) as conn:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        assert conn.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        schema = conn.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"
        ).fetchall()
        tables = []
        for kind, name, _, _ in schema:
            if kind == "table":
                quoted = name.replace('"', '""')
                rows = conn.execute(f'SELECT * FROM "{quoted}"').fetchall()  # noqa: S608
                tables.append((name, sorted(rows, key=repr)))
        return repr((schema, tables, conn.execute("PRAGMA user_version").fetchone()))


def _tree(root: Path) -> dict[str, tuple[int, str]]:
    return {
        p.relative_to(root).as_posix(): (
            p.stat().st_mtime_ns,
            hashlib.sha256(p.read_bytes()).hexdigest(),
        )
        for p in root.rglob("*")
        if p.is_file()
    }


def _snapshot(receipt: dict[str, Any]) -> Path:
    assert receipt["status"] == "created", receipt
    item = receipt["snapshot"]
    path = Path(item["path"])
    assert path.is_file() and path.stat().st_size == item["size_bytes"] > 0
    assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
    _time(item["created_at"])
    assert any(
        p.is_file()
        and p != path
        and item["sha256"] in p.read_text(encoding="utf-8", errors="ignore")
        for p in path.parent.iterdir()
        if p.suffix != ".db"
    ), "published snapshot lacks a persisted checksum receipt"
    return path


@pytest.fixture()
def case(tmp_cairntir_home: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    clock = [START]
    monkeypatch.delenv("CAIRNTIR_GRANT_FILE", raising=False)
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    db = tmp_cairntir_home / "cairntir.db"
    with DrawerStore(db, _provider()) as store:
        _add(store, "Verbatim café 日本語 🌲 evidence with physical vectors.")
        store._conn.execute(
            "CREATE TABLE acceptance_pair(slot TEXT PRIMARY KEY, generation INTEGER)"
        )
        store._conn.executemany("INSERT INTO acceptance_pair VALUES (?,0)", [("A",), ("B",)])
        store._conn.commit()

    def parameters() -> Any:
        api = _api()
        monkeypatch.setattr(api, "utc_now", lambda: clock[0])
        yield from (api, db, tmp_cairntir_home.parent / "backups", clock)

    return parameters()


def test_disabled_default_and_missing_status_have_no_filesystem_effects(case: Any) -> None:
    api, db, destination, _ = case
    before = _tree(db.parent.parent)
    result = api.status(db)
    assert result["enabled"] is False and result["snapshots"] == []
    assert api.run(db, force=False)["status"] == "disabled"
    assert api.status(db.parent / "missing" / "other.db")["enabled"] is False
    assert _tree(db.parent.parent) == before
    assert not destination.exists()


def test_configuration_persists_default_interval_and_disable_preserves_backups(case: Any) -> None:
    api, db, destination, _ = case
    before = _state(db)
    result = api.configure(db, destination)
    assert result["enabled"] is True and result["interval_hours"] == 12
    assert Path(result["destination"]).resolve() == destination.resolve()
    assert api.status(db)["snapshots"] == []
    copied = _snapshot(api.run(db))
    disabled = api.disable(db)
    assert disabled["enabled"] is False and copied.exists()
    assert api.run(db, force=False)["status"] == "disabled"
    assert _state(db) == before
    other = db.with_name("scratch.db")
    with DrawerStore(other, _provider(), automatic_backups=True):
        assert api.status(other)["enabled"] is False
    assert len(api.status(db)["snapshots"]) == 1


@pytest.mark.parametrize("interval", [0, -1, float("nan"), float("inf"), True])
def test_invalid_interval_is_typed_and_preserves_configuration(case: Any, interval: Any) -> None:
    api, db, destination, _ = case
    api.configure(db, destination)
    before = _tree(db.parent.parent)
    with pytest.raises(api.BackupError):
        api.configure(db, destination, interval_hours=interval)
    assert _tree(db.parent.parent) == before


def test_source_database_cannot_be_backup_destination(case: Any) -> None:
    api, db, _, _ = case
    before = _tree(db.parent.parent)
    with pytest.raises(api.BackupError):
        api.configure(db, db)
    assert _tree(db.parent.parent) == before


def test_new_destination_gets_recovery_point_without_inheriting_old_cadence(case: Any) -> None:
    api, db, destination, _ = case
    api.configure(db, destination)
    old = _snapshot(api.run(db))
    replacement = destination.with_name("new-destination")
    api.configure(db, replacement)
    with DrawerStore(db, NoEmbedding(), automatic_backups=True):
        current = api.status(db)
    assert old.exists()
    assert len(current["snapshots"]) == 1
    assert Path(current["snapshots"][0]["path"]).is_relative_to(replacement)


def test_opted_in_startup_copies_once_without_embedding_and_cadence_persists(case: Any) -> None:
    api, db, destination, clock = case
    api.configure(db, destination)
    before = _state(db)
    with DrawerStore(db, NoEmbedding(), automatic_backups=True):
        first = api.status(db)
    assert len(first["snapshots"]) == 1
    assert _time(first["last_success_at"]) == clock[0]
    assert _time(first["next_due_at"]) == clock[0] + timedelta(hours=12)
    _run_child("open", db, clock[0] + timedelta(hours=11, minutes=59))
    assert api.status(db)["snapshots"] == first["snapshots"]
    _run_child("open", db, clock[0] + timedelta(hours=12))
    assert len(api.status(db)["snapshots"]) == 2
    assert _state(db) == before


def test_due_outer_write_backs_up_committed_state_before_nested_work(case: Any) -> None:
    api, db, destination, clock = case
    api.configure(db, destination)
    with DrawerStore(db, _provider(), automatic_backups=True) as store:
        before = _state(db)
        clock[0] += timedelta(hours=12)
        with store.transaction():
            _add(store, "New outer transaction evidence.")
            with store.transaction():
                _add(store, "Nested committed evidence.")
            assert len(api.status(db)["snapshots"]) == 2
        latest = max(api.status(db)["snapshots"], key=lambda item: _time(item["created_at"]))
        assert _state(Path(latest["path"]), standalone=True) == before
        assert _state(db) != before
        assert len(api.status(db)["snapshots"]) == 2


def test_read_only_and_unopted_store_never_activate_due_backups(case: Any) -> None:
    api, db, destination, _ = case
    api.configure(db, destination)
    before = _tree(db.parent.parent)
    with DrawerStore(db, _provider(), read_only=True, automatic_backups=True):
        assert api.status(db)["snapshots"] == []
    with DrawerStore(db, NoEmbedding()):
        assert api.status(db)["snapshots"] == []
    assert _tree(db.parent.parent) == before


@pytest.mark.parametrize("trigger", ["startup", "write"])
def test_unavailable_destination_warns_and_does_not_block_ordinary_writes(
    case: Any, trigger: str
) -> None:
    api, db, destination, clock = case
    api.configure(db, destination)
    store = None
    if trigger == "write":
        store = DrawerStore(db, _provider(), automatic_backups=True)
        shutil.rmtree(destination)
        clock[0] += timedelta(hours=12)
    destination.write_text("not a directory", encoding="utf-8")
    previous = api.status(db)["last_success_at"]
    try:
        with pytest.warns(api.BackupWarning, match=".+"):
            if store is None:
                store = DrawerStore(db, _provider(), automatic_backups=True)
            _add(store, "Write survived unavailable backup destination.")
        failed = api.status(db)
        assert failed["last_error"] and failed["last_success_at"] == previous
        assert "Write survived" in _state(db)
    finally:
        if store is not None:
            store.close()
    destination.unlink()
    _snapshot(api.run(db, force=False))
    assert not api.status(db)["last_error"]


def test_explicit_failure_is_typed_without_false_success_or_retention(case: Any) -> None:
    api, db, destination, clock = case
    api.configure(db, destination)
    good = _snapshot(api.run(db))
    original = good.read_bytes()
    clock[0] += timedelta(days=90)
    db.write_bytes(b"not a SQLite database")
    previous = api.status(db)["last_success_at"]
    with pytest.raises(api.BackupError):
        api.run(db)
    assert good.read_bytes() == original
    assert api.status(db)["last_success_at"] == previous
    assert len(api.status(db)["snapshots"]) == 1


def test_wal_snapshot_is_standalone_and_excludes_uncommitted_changes(case: Any) -> None:
    api, db, destination, _ = case
    api.configure(db, destination)
    with _peer("wal", db) as peer:
        peer.read("READY")
        before = _state(db)
        assert Path(str(db) + "-wal").stat().st_size > 0
        copied = _snapshot(api.run(db))
        assert _state(copied, standalone=True) == before
        assert "Committed in the owner WAL" in before
        assert "UNCOMMITTED" not in _state(copied, standalone=True)
        peer.process.kill()
        peer.process.wait(timeout=5)
    restored = db.parent / "restored.db"
    shutil.copyfile(copied, restored)
    assert _state(restored, standalone=True) == before
    with DrawerStore(restored, NoEmbedding()):
        assert _state(restored) == before
    assert _state(db) == before


def test_orphan_committed_wal_survives_backup_without_source_sidecars(case: Any) -> None:
    api, db, destination, _ = case
    api.configure(db, destination)
    with _peer("wal", db) as peer:
        peer.read("READY")
        before = _state(db)
        peer.process.kill()
        peer.process.wait(timeout=5)
    assert Path(str(db) + "-wal").stat().st_size > 0
    copied = _snapshot(api.run(db))
    restored = destination / "manual-restored.db"
    shutil.copyfile(copied, restored)
    assert _state(restored, standalone=True) == before
    assert "Committed in the owner WAL" in _state(restored, standalone=True)


def test_write_checkpoint_races_produce_coherent_verified_snapshots(case: Any) -> None:
    api, db, destination, clock = case
    api.configure(db, destination)
    with _peer("race", db) as peer:
        peer.read("READY")
        for _ in range(4):
            copied = _snapshot(api.run(db))
            with closing(sqlite3.connect(copied.as_uri() + "?immutable=1", uri=True)) as conn:
                rows = conn.execute("SELECT generation FROM acceptance_pair").fetchall()
            assert len(rows) == 2 and rows[0] == rows[1]
            clock[0] += timedelta(seconds=1)
        peer.send("STOP")
        result = json.loads(peer.read())
        assert result["commits"] > 0 and result["checkpoints"] > 0


def test_concurrent_due_processes_publish_exactly_one_snapshot(case: Any) -> None:
    api, db, destination, _ = case
    api.configure(db, destination)
    with _peer("gated-run", db) as left, _peer("gated-run", db) as right:
        left.read("READY")
        right.read("READY")
        left.send("GO")
        right.send("GO")
        outcomes = [json.loads(left.read(timeout=20)), json.loads(right.read(timeout=20))]
        assert sum(r["status"] == "created" for r in outcomes) == 1
        assert {r["status"] for r in outcomes} <= {"created", "busy", "not_due"}
    assert len(api.status(db)["snapshots"]) == 1


def test_contention_is_bounded_and_crashed_owner_can_be_replaced(case: Any) -> None:
    api, db, destination, _ = case
    api.configure(db, destination)
    with _peer("exclusive", db) as writer:
        writer.read("READY")
        with _peer("run", db) as worker:
            worker.read("READY")
            deadline = time.monotonic() + 6
            while not api.status(db)["in_progress"]:
                assert time.monotonic() < deadline, "backup claim never became observable"
                time.sleep(0.025)
            started = time.monotonic()
            assert api.run(db, force=False)["status"] == "busy"
            assert time.monotonic() - started < 2
            assert api.status(db)["snapshots"] == []
            worker.process.kill()
            worker.process.wait(timeout=5)
        writer.send("STOP")
        writer.read("STOPPED")
    started = time.monotonic()
    copied = _snapshot(api.run(db, force=False))
    assert time.monotonic() - started <= 20
    assert not api.status(db)["in_progress"]
    assert _state(copied, standalone=True) == _state(db)
    assert len(api.status(db)["snapshots"]) == 1


def test_locked_source_timeout_is_typed_and_never_published(case: Any) -> None:
    api, db, destination, _ = case
    api.configure(db, destination)
    with _peer("exclusive", db) as writer:
        writer.read("READY")
        started = time.monotonic()
        with pytest.raises(api.BackupError):
            api.run(db)
        assert time.monotonic() - started <= 20
        assert api.status(db)["snapshots"] == []
        assert not api.status(db)["last_success_at"]


def test_retention_keeps_recent_and_four_weekly_points_and_unmanaged_files(case: Any) -> None:
    api, db, destination, clock = case
    api.configure(db, destination)
    destination.mkdir(exist_ok=True)
    manual = destination / "manual-baseline.db"
    shutil.copyfile(db, manual)
    unknown = destination / "cairntir-backup-unrecognized.json"
    unknown.write_text('{"path":"manual-baseline.db"}', encoding="utf-8")
    keep = {p: p.read_bytes() for p in (manual, unknown)}
    all_items = []
    for days in [70, 63, 56, 49, 42, 35, 28, 21, 15, 14, 13, 9, 8, 7, 6, 2, 0]:
        clock[0] = START - timedelta(days=days)
        item = api.run(db)["snapshot"]
        _snapshot({"status": "created", "snapshot": item})
        all_items.append(item)
    recent = [r for r in all_items if START - _time(r["created_at"]) <= timedelta(days=7)]
    weeks = {}
    for item in all_items:
        instant = _time(item["created_at"])
        if START - instant > timedelta(days=7):
            weeks[instant.isocalendar()[:2]] = item
    expected = {r["path"] for r in recent}
    expected.update(weeks[key]["path"] for key in sorted(weeks, reverse=True)[:4])
    actual = {r["path"] for r in api.status(db)["snapshots"]}
    assert actual == expected
    for item in all_items:
        assert Path(item["path"]).exists() == (item["path"] in expected)
    assert all(path.read_bytes() == data for path, data in keep.items())


def test_retention_preserves_other_database_and_changed_managed_snapshot(case: Any) -> None:
    api, db, destination, clock = case
    api.configure(db, destination)
    original = _snapshot(api.run(db))
    original.write_bytes(b"externally changed; never eligible for deletion")
    other = db.with_name("other.db")
    with DrawerStore(other, _provider()) as store:
        _add(store, "Another source's recovery evidence.")
    api.configure(other, destination)
    foreign = _snapshot(api.run(other))
    foreign_bytes = foreign.read_bytes()
    for weeks in range(1, 8):
        clock[0] = START + timedelta(weeks=weeks)
        _snapshot(api.run(db))
    assert original.read_bytes() == b"externally changed; never eligible for deletion"
    assert foreign.read_bytes() == foreign_bytes


def test_cli_configuration_run_status_disable_are_real_and_status_is_pure(case: Any) -> None:
    api, db, destination, _ = case
    before = _tree(db.parent.parent)
    result = _cli("backup", "status")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["enabled"] is False
    assert _tree(db.parent.parent) == before
    configured = _cli("backup", "configure", str(destination))
    assert configured.returncode == 0, configured.stderr
    assert json.loads(configured.stdout)["interval_hours"] == 12
    run = _cli("backup", "run")
    assert run.returncode == 0, run.stderr
    copied = _snapshot(json.loads(run.stdout))
    assert _state(copied, standalone=True) == _state(db)
    disabled = _cli("backup", "disable")
    assert disabled.returncode == 0 and not json.loads(disabled.stdout)["enabled"]
    assert api.status(db)["enabled"] is False


@pytest.mark.parametrize("transport", ["cli", "mcp"])
def test_production_owner_startup_activates_backup_and_retains_transport_shape(
    case: Any, transport: str
) -> None:
    api, db, destination, _ = case
    api.configure(db, destination)
    before = _state(db)
    if transport == "cli":
        result = _cli("status")
        assert result.returncode == 0, result.stderr
    else:
        result = _run_child("mcp-probe", db, START)
        assert result["tools"] == 21 and not result["error"]
    assert len(api.status(db)["snapshots"]) == 1
    assert _state(Path(api.status(db)["snapshots"][0]["path"]), standalone=True) == before


@pytest.mark.parametrize("transport", ["cli", "mcp"])
def test_scoped_startup_cannot_trigger_owner_backups(case: Any, transport: str) -> None:
    from cairntir.access import issue_grant

    api, db, destination, _ = case
    with DrawerStore(db, _provider()) as owner:
        token = issue_grant(owner, scopes=[{"wing": WING}], capabilities=["read", "write"])
    grant = db.parent / "grant.txt"
    grant.write_text(token, encoding="utf-8")
    api.configure(db, destination)
    before = _tree(db.parent.parent)
    if transport == "cli":
        result = _cli("handoff", WING, "--task", "Verbatim café", grant=grant)
        assert result.returncode == 0, result.stderr
    else:
        result = _run_child("mcp-probe", db, START, grant=grant)
        assert result["tools"] == 21 and not result["error"]
    assert api.status(db)["snapshots"] == []
    assert _tree(db.parent.parent) == before


def test_scoped_cli_cannot_configure_or_force_whole_store_backup(case: Any) -> None:
    from cairntir.access import issue_grant

    api, db, destination, _ = case
    with DrawerStore(db, _provider()) as owner:
        token = issue_grant(owner, scopes=[{"wing": WING}], capabilities=["read", "write"])
    grant = db.parent / "grant.txt"
    grant.write_text(token, encoding="utf-8")
    api.configure(db, destination)
    before = _tree(db.parent.parent)
    for args in [("configure", str(destination)), ("run",), ("disable",)]:
        result = _cli("backup", *args, grant=grant)
        assert result.returncode != 0 and "access denied" in result.stderr.lower()
    assert _tree(db.parent.parent) == before


def _env(grant: Path | None = None) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["PYTHONIOENCODING"] = "utf-8"
    if grant is None:
        env.pop("CAIRNTIR_GRANT_FILE", None)
    else:
        env["CAIRNTIR_GRANT_FILE"] = str(grant)
    return env


def _command(mode: str, *args: Any) -> list[str]:
    return [sys.executable, str(Path(__file__).resolve()), mode, *(str(v) for v in args)]


def _cli(*args: str, grant: Path | None = None) -> Any:
    return subprocess.run(  # noqa: S603 - explicit isolated test entry point
        _command("cli", *args),
        cwd=ROOT,
        env=_env(grant),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=25,
        check=False,
    )


def _run_child(mode: str, db: Path, instant: datetime, *, grant: Path | None = None) -> Any:
    result = subprocess.run(  # noqa: S603 - explicit isolated test entry point
        _command(mode, db, instant.isoformat()),
        cwd=ROOT,
        env=_env(grant),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=25,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


class Peer:
    def __init__(self, mode: str, db: Path) -> None:
        self.process = subprocess.Popen(  # noqa: S603 - explicit isolated test entry point
            _command(mode, db, START.isoformat()),
            cwd=ROOT,
            env=_env(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        self.lines: queue.Queue[str] = queue.Queue()
        assert self.process.stdout is not None
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            self.lines.put(line.rstrip())

    def read(self, expected: str | None = None, timeout: float = 10) -> str:
        try:
            value = self.lines.get(timeout=timeout)
        except queue.Empty:
            pytest.fail("isolated backup helper failed to respond within deadline")
        if expected is not None:
            assert value == expected
        return value

    def send(self, text: str) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(text + "\n")
        self.process.stdin.flush()

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.kill()
        self.process.communicate(timeout=20)


@contextmanager
def _peer(mode: str, db: Path) -> Any:
    peer = Peer(mode, db)
    try:
        yield peer
    finally:
        peer.close()


def _child_main() -> None:
    mode = sys.argv[1]
    if mode in {"cli", "server", "mcp-probe"}:
        import cairntir.cli as cli
        import cairntir.mcp.server as server

        cli.production_embedding_provider = _provider
        server.production_embedding_provider = _provider
        connect = socket.socket.connect

        def local_only(sock: Any, address: Any) -> Any:
            if isinstance(address, tuple) and address[0] not in {"127.0.0.1", "::1"}:
                raise AssertionError("acceptance must not access external network")
            return connect(sock, address)

        socket.socket.connect = local_only
        if mode == "cli":
            sys.argv = [sys.argv[0], *sys.argv[2:]]
            cli.app()
            return
        if mode == "server":
            sys.argv = [sys.argv[0], "--host", "independent-backup-probe"]
            server.main()
            return
        asyncio.run(_mcp_probe())
        return
    db = Path(sys.argv[2])
    instant = datetime.fromisoformat(sys.argv[3])
    if mode in {"open", "run", "gated-run"}:
        api = _api()
        api.utc_now = lambda: instant
        if mode == "open":
            with DrawerStore(db, NoEmbedding(), automatic_backups=True):
                print(json.dumps(api.status(db)), flush=True)
        else:
            print("READY", flush=True)
            if mode == "gated-run":
                input()
            print(json.dumps(api.run(db, force=False)), flush=True)
        return
    if mode == "wal":
        with DrawerStore(db, _provider()) as store:
            store._conn.execute("PRAGMA wal_autocheckpoint=0")
            _add(store, "Committed in the owner WAL, including its vector.")
            store._conn.execute("BEGIN IMMEDIATE")
            store._conn.execute("UPDATE acceptance_pair SET generation=999")
            store._conn.execute("UPDATE drawers SET content='UNCOMMITTED'")
            print("READY", flush=True)
            input()
        return
    if mode == "exclusive":
        with closing(sqlite3.connect(db)) as conn:
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.execute("BEGIN EXCLUSIVE")
            print("READY", flush=True)
            input()
            conn.rollback()
            print("STOPPED", flush=True)
        return
    if mode == "race":
        stop = threading.Event()
        threading.Thread(target=lambda: (input(), stop.set()), daemon=True).start()
        commits = checkpoints = 0
        with closing(sqlite3.connect(db, timeout=1)) as conn:
            conn.execute("PRAGMA wal_autocheckpoint=0")
            print("READY", flush=True)
            while not stop.is_set():
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("UPDATE acceptance_pair SET generation=?", (commits + 1,))
                conn.commit()
                commits += 1
                conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
                checkpoints += 1
                time.sleep(0.002)
        print(json.dumps({"commits": commits, "checkpoints": checkpoints}), flush=True)


async def _mcp_probe() -> None:
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    parameters = StdioServerParameters(
        command=sys.executable, args=_command("server")[1:], env=dict(os.environ), cwd=ROOT
    )
    async with (
        stdio_client(parameters) as (reader, writer),
        ClientSession(reader, writer) as session,
    ):
        await session.initialize()
        tools = (await session.list_tools()).tools
        result = await session.call_tool(
            "cairntir_handoff", {"wing": WING, "task": "Verbatim café"}
        )
        print(json.dumps({"tools": len(tools), "error": result.isError}), flush=True)


if __name__ == "__main__":
    _child_main()
