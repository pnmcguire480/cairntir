"""Independent acceptance for task handoff alongside real SQLite clients."""

from __future__ import annotations

import hashlib
import json
import os
import queue
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any

import pytest
import sqlite_vec

from cairntir import cli
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.provenance import TrustLevel, WriteProvenance

WING = "concurrent-read-proof"
TASK = "coordinate committed atlas evidence"
BUDGET = 65_536
ROOT = Path(__file__).resolve().parents[2]
UNCOMMITTED = "UNCOMMITTED-canary-61d4"


def _embedder() -> HashEmbeddingProvider:
    return HashEmbeddingProvider(dimension=32)


def _content(generation: int, slot: str) -> str:
    return f"{TASK}; generation={generation}; slot={slot}; " + (slot + " evidence. ") * 850


def _tree(root: Path, *, racing: bool = False) -> dict[str, tuple[int, str]]:
    result = {}
    for path in (root, *root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if relative == "cairntir.db-shm" or (
            racing and relative in {".", "cairntir.db", "cairntir.db-wal"}
        ):
            continue
        result[relative] = (
            path.stat().st_mtime_ns,
            hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "<directory>",
        )
    return result


def _state(connection: sqlite3.Connection, ids: list[int], *, racing: bool) -> str:
    schema = connection.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name"
    ).fetchall()
    tables = []
    for kind, name, _, _ in schema:
        if kind != "table":
            continue
        quoted = name.replace('"', '""')
        cursor = connection.execute(f'SELECT * FROM "{quoted}"')  # noqa: S608
        columns = [item[0] for item in cursor.description]
        rows = []
        for row in cursor.fetchall():
            values = list(row)
            if racing and name == "drawers" and values[columns.index("id")] in ids:
                values[columns.index("content")] = "<deliberate writer generation>"
            rows.append(tuple(values))
        tables.append((name, sorted(rows, key=repr)))
    payload = schema, tables, connection.execute("PRAGMA user_version").fetchone()
    return hashlib.sha256(repr(payload).encode()).hexdigest()


def _writer(database: Path, ids: list[int]) -> None:
    with DrawerStore(database, _embedder()) as store, closing(sqlite3.connect(database)) as conn:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        conn.execute("PRAGMA wal_autocheckpoint=0")
        stopped = threading.Event()
        started = threading.Event()
        progress = {"generation": 0, "checkpoints": 0}
        errors: list[str] = []
        thread = None

        def race() -> None:
            try:
                with closing(sqlite3.connect(database, timeout=0.05)) as writer:
                    writer.execute("PRAGMA wal_autocheckpoint=0")
                    generation = 0
                    while not stopped.is_set():
                        generation += 1
                        writer.execute("BEGIN IMMEDIATE")
                        for drawer_id, slot in zip(ids, ["A", "B"], strict=True):
                            writer.execute(
                                "UPDATE drawers SET content=? WHERE id=?",
                                (_content(generation, slot), drawer_id),
                            )
                        writer.commit()
                        progress["generation"] = generation
                        mode = "TRUNCATE" if generation % 2 else "PASSIVE"
                        writer.execute(f"PRAGMA wal_checkpoint({mode})").fetchone()
                        progress["checkpoints"] += 1
                        started.set()
                        stopped.wait(0.002)
            except (OSError, sqlite3.Error) as error:
                errors.append(repr(error))
                started.set()

        print(json.dumps({"ready": True}), flush=True)
        try:
            for line in sys.stdin:
                request = json.loads(line)
                op = request["op"]
                if op == "close":
                    break
                if op == "add":
                    saved = store.add(
                        Drawer(wing=WING, room="evidence", content=request["content"])
                    )
                    response = {"id": saved.id}
                elif op == "begin":
                    conn.execute("BEGIN IMMEDIATE")
                    conn.execute("UPDATE drawers SET content=? WHERE id=?", (UNCOMMITTED, ids[0]))
                    response = {"active": conn.in_transaction}
                elif op == "state":
                    response = {"sha256": _state(conn, ids, racing=request.get("racing", False))}
                elif op == "race":
                    thread = threading.Thread(target=race)
                    thread.start()
                    assert started.wait(10), "writer race did not start"
                    response = dict(progress)
                elif op == "stop":
                    stopped.set()
                    assert thread is not None
                    thread.join(10)
                    assert not thread.is_alive(), "writer race did not stop"
                    response = dict(progress)
                elif op == "status":
                    response = dict(progress)
                else:
                    raise AssertionError(f"Unknown writer operation: {op}")
                assert not errors, errors
                print(json.dumps(response), flush=True)
        finally:
            stopped.set()
            if thread is not None:
                thread.join(10)
            conn.rollback()


def _exclusive(database: Path) -> None:
    with closing(sqlite3.connect(database)) as conn:
        assert conn.execute("PRAGMA journal_mode=DELETE").fetchone()[0] == "delete"
        conn.execute("BEGIN EXCLUSIVE")
        print(json.dumps({"ready": True}), flush=True)
        sys.stdin.readline()
        conn.rollback()


def _cli_main() -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Concurrent task CLI attempted network or runtime hooks")

    socket.socket.connect = forbidden
    socket.create_connection = forbidden
    cli.production_embedding_provider = _embedder
    cli.ensure_registered = forbidden
    cli.maybe_check_in_background = forbidden
    cli.pending_update_banner = lambda: "forbidden-update-banner " * 1_000
    sys.argv = ["cairntir", "handoff", WING, "--task", TASK, "--budget", str(BUDGET)]
    Path(os.environ["CONCURRENCY_CLI_READY"]).write_text("ready", encoding="utf-8")
    cli.app()


class _Peer:
    def __init__(self, process: subprocess.Popen[str]) -> None:
        self.process = process
        self.lines: queue.Queue[str] = queue.Queue()
        assert process.stdout is not None

        def receive() -> None:
            assert process.stdout is not None
            for line in process.stdout:
                self.lines.put(line)

        self.thread = threading.Thread(target=receive, daemon=True)
        self.thread.start()
        assert self.response() == {"ready": True}

    def response(self) -> dict[str, Any]:
        try:
            return json.loads(self.lines.get(timeout=15))
        except queue.Empty:
            pytest.fail(f"CONCURRENCY_INFRASTRUCTURE: helper timed out; exit={self.process.poll()}")

    def request(self, op: str, **kwargs: Any) -> dict[str, Any]:
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps({"op": op, **kwargs}) + "\n")
        self.process.stdin.flush()
        return self.response()

    def close(self) -> None:
        if self.process.poll() is None:
            assert self.process.stdin is not None
            self.process.stdin.write('{"op":"close"}\n')
            self.process.stdin.flush()
            self.process.wait(timeout=15)
        assert self.process.stderr is not None
        assert self.process.returncode == 0, self.process.stderr.read()
        self.thread.join(2)


@contextmanager
def _owner(case: dict[str, Any], mode: str = "writer") -> Any:
    process = subprocess.Popen(  # noqa: S603 - fixed tester-owned helper and isolated paths
        [
            sys.executable,
            str(Path(__file__).resolve()),
            mode,
            str(case["database"]),
            *map(str, case["ids"]),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=case["env"],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        peer = _Peer(process)
        yield peer
        peer.close()
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        for pipe in (process.stdin, process.stdout, process.stderr):
            if pipe is not None:
                pipe.close()


@pytest.fixture
def case(tmp_path: Path) -> dict[str, Any]:
    home, scratch, profile = [tmp_path / name for name in ("source", "scratch", "profile")]
    for path in (home, scratch, profile, home / "cache"):
        path.mkdir()
    (home / "mcp.log").write_text("Preserved diagnostic evidence.\n", encoding="utf-8")
    (home / "cache" / "marker").write_text("Preserved cache.\n", encoding="utf-8")
    database = home / "cairntir.db"
    with DrawerStore(database, _embedder()) as store:
        provenance = WriteProvenance.create(
            host="independent tester",
            capture_path="explicit",
            session_id="concurrency",
            model="deterministic",
            trust=TrustLevel.SYSTEM,
        )
        drawers = [
            store.add(
                Drawer(wing=WING, room="evidence", content=_content(0, slot)), provenance=provenance
            )
            for slot in ("A", "B")
        ]
    env = {
        **os.environ,
        "CAIRNTIR_HOME": str(home),
        "HOME": str(profile),
        "USERPROFILE": str(profile),
        "TMP": str(scratch),
        "TEMP": str(scratch),
        "TMPDIR": str(scratch),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(ROOT / "src"),
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
    }
    env.pop("CAIRNTIR_DISABLE_AUTOREGISTER", None)
    env.pop("CAIRNTIR_DISABLE_UPDATE_CHECK", None)
    return {
        "home": home,
        "scratch": scratch,
        "profile": profile,
        "database": database,
        "env": env,
        "ids": [drawer.id for drawer in drawers],
    }


def _start_cli(case: dict[str, Any]) -> subprocess.Popen[str]:
    ready = case["home"].parent / "cli-ready"
    ready.unlink(missing_ok=True)
    process = subprocess.Popen(  # noqa: S603 - actual CLI with isolated test provider and home
        [sys.executable, str(Path(__file__).resolve()), "cli"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**case["env"], "CONCURRENCY_CLI_READY": str(ready)},
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    deadline = time.monotonic() + 15
    while not ready.exists():
        if process.poll() is not None or time.monotonic() > deadline:
            process.kill()
            _, stderr = process.communicate(timeout=5)
            pytest.fail(f"CONCURRENCY_INFRASTRUCTURE: CLI did not finish importing: {stderr}")
        time.sleep(0.01)
    return process


def _finish_cli(
    process: subprocess.Popen[str], case: dict[str, Any], *, success: bool = True
) -> dict[str, Any]:
    try:
        stdout, stderr = process.communicate(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate(timeout=5)
        pytest.fail("Task CLI exceeded the 15-second bounded completion contract")
    assert not list(case["scratch"].iterdir()), "task CLI leaked private snapshots"
    assert not list(case["profile"].iterdir()), "task CLI wrote user-home state"
    assert len(stdout) <= BUDGET
    assert "forbidden-update-banner" not in stdout + stderr
    if not success:
        assert process.returncode != 0
        assert "cairntir:" in stderr.lower() and any(
            word in stderr.lower() for word in ("lock", "busy", "timeout", "timed out")
        ), stderr
        return {}
    assert process.returncode == 0, stderr
    assert not stderr, stderr
    result = json.loads(stdout)
    assert result["status"] == "selected", result
    assert all(entry["instruction_authority"] == "none" for entry in result["evidence"])
    return result


@pytest.mark.parametrize("active", [False, True], ids=["idle-wal-owner", "uncommitted-wal-writer"])
def test_cli_reads_committed_wal_without_mutating_owner_state(
    case: dict[str, Any], active: bool
) -> None:
    with _owner(case) as owner:
        marker = TASK + ": newly committed WAL-only record 89ce."
        new_id = owner.request("add", content=marker)["id"]
        assert marker.encode() not in case["database"].read_bytes()
        assert marker.encode() in Path(str(case["database"]) + "-wal").read_bytes()
        if active:
            assert owner.request("begin")["active"]
        before = _tree(case["home"])
        state = owner.request("state")
        for _ in range(2):
            payload = _finish_cli(_start_cli(case), case)
            evidence = {entry["drawer_id"]: entry["content"] for entry in payload["evidence"]}
            assert evidence == {
                case["ids"][0]: _content(0, "A"),
                case["ids"][1]: _content(0, "B"),
                new_id: marker,
            }
            assert UNCOMMITTED not in json.dumps(payload)
            assert owner.request("state") == state, "task read changed persisted application state"
            assert _tree(case["home"]) == before, (
                "task read changed source beyond existing SHM bookkeeping"
            )


def test_cli_snapshot_is_coherent_during_atomic_commits_and_checkpoints(
    case: dict[str, Any],
) -> None:
    with _owner(case) as owner:
        baseline = owner.request("state", racing=True)
        files = _tree(case["home"], racing=True)
        owner.request("race")
        for _ in range(4):
            first = owner.request("status")["generation"]
            payload = _finish_cli(_start_cli(case), case)
            last = owner.request("status")["generation"]
            evidence = {entry["drawer_id"]: entry["content"] for entry in payload["evidence"]}
            assert set(evidence) == set(case["ids"])
            generations = {
                int(value.split("generation=", 1)[1].split(";", 1)[0])
                for value in evidence.values()
            }
            assert len(generations) == 1, "snapshot mixed evidence from different atomic commits"
            generation = generations.pop()
            assert first <= generation <= last
            assert evidence == {
                case["ids"][0]: _content(generation, "A"),
                case["ids"][1]: _content(generation, "B"),
            }
        progress = owner.request("stop")
        assert progress["generation"] > 1 and progress["checkpoints"] > 1
        assert owner.request("state", racing=True) == baseline
        assert _tree(case["home"], racing=True) == files


@pytest.mark.parametrize("close_delay", [0.0, 0.05])
def test_cli_retains_committed_evidence_when_wal_owner_closes(
    case: dict[str, Any], close_delay: float
) -> None:
    with _owner(case) as owner:
        marker = TASK + ": committed owner-close record 51aa."
        new_id = owner.request("add", content=marker)["id"]
        process = _start_cli(case)
        time.sleep(close_delay)
        owner.close()
        payload = _finish_cli(process, case)
        evidence = {entry["drawer_id"]: entry["content"] for entry in payload["evidence"]}
        assert evidence == {
            case["ids"][0]: _content(0, "A"),
            case["ids"][1]: _content(0, "B"),
            new_id: marker,
        }
    with _owner(case) as owner:
        state = owner.request("state")
        _finish_cli(_start_cli(case), case)
        assert owner.request("state") == state


def test_genuine_exclusive_rollback_lock_fails_with_bounded_cleanup(case: dict[str, Any]) -> None:
    with _owner(case, "exclusive"):
        before = _tree(case["home"])
        _finish_cli(_start_cli(case), case, success=False)
        assert _tree(case["home"]) == before


if __name__ == "__main__":
    if sys.argv[1] == "cli":
        _cli_main()
    elif sys.argv[1] == "exclusive":
        _exclusive(Path(sys.argv[2]))
    else:
        _writer(Path(sys.argv[2]), [int(value) for value in sys.argv[3:]])
