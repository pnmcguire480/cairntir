"""Independent durable receipt and projection controls for the managed port."""

from __future__ import annotations

import importlib
import socket
import sqlite3
import subprocess
import sys
from contextlib import closing, contextmanager
from copy import deepcopy
from functools import partial
from types import SimpleNamespace
from uuid import uuid4

import pytest
import sqlite_vec
from cairntir.access import bind_grant, issue_grant
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.tasks import TaskBook

WING = "managed-durability"
ROOM = "requests"
ORIGINAL = "  Keep this exact original commitment café\r\n  "


@contextmanager
def observer(path):
    """Use an independent complete-schema reader, including SQLite vector tables."""
    with closing(sqlite3.connect(path, timeout=1)) as connection:
        connection.enable_load_extension(True)
        sqlite_vec.load(connection)
        connection.enable_load_extension(False)
        yield connection


def snapshot(connection):
    """Compare every physical table, preserving caller-owned uncommitted work."""
    names = [
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    ]
    result = {}
    for name in names:
        quoted = name.replace('"', '""')
        rows = connection.execute(f'SELECT * FROM "{quoted}"').fetchall()  # noqa: S608
        result[name] = tuple(sorted((tuple(row) for row in rows), key=repr))
    return result


@pytest.fixture
def durable(tmp_path, monkeypatch):
    """Prepare an inert synthetic store and trusted never-launched profile."""
    for name in ("CAIRNTIR_HOME", "XDG_CACHE_HOME", "HF_HOME", "TORCH_HOME", "TEMP", "TMP"):
        isolated = tmp_path / name.lower()
        isolated.mkdir()
        monkeypatch.setenv(name, str(isolated))
    monkeypatch.delenv("CAIRNTIR_GRANT_FILE", raising=False)
    monkeypatch.setenv("CAIRNTIR_DISABLE_AUTOREGISTER", "1")
    monkeypatch.setenv("CAIRNTIR_DISABLE_UPDATE_CHECK", "1")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")

    def denied(*_args, **_kwargs):
        pytest.fail("Managed durable-boundary fixture attempted network or external launch")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(subprocess, "Popen", denied)
    path = tmp_path / "managed.db"
    project = tmp_path / "project"
    project.mkdir()
    owner = DrawerStore(path, HashEmbeddingProvider(dimension=16))
    token = issue_grant(owner, scopes=[{"wing": WING}], capabilities=["read", "write"])
    config = {
        "schema": "cairntir.managed-config.v1",
        "wing": WING,
        "room": ROOM,
        "project_root": str(project),
        "brief_budget_chars": 16384,
        "profiles": {
            "inert": {
                "argv": [sys.executable, "-c", "raise SystemExit(97)"],
                "cwd": str(project),
                "timeout_seconds": 2,
                "output_limit_bytes": 128,
            }
        },
    }
    bundle = SimpleNamespace(
        owner=owner,
        token=token,
        path=path,
        project=project,
        config=config,
        api=importlib.import_module("cairntir.managed"),
        projection=importlib.import_module("cairntir.managed_projection"),
    )
    try:
        yield bundle
    finally:
        owner.close()


def actor(bundle, principal):
    """Use the owner or a currently authorized scoped facade."""
    return bundle.owner if principal == "owner" else bind_grant(bundle.owner, bundle.token)


def ready(bundle, principal):
    """Commit a first event and create the exact complete current brief."""
    store = actor(bundle, principal)
    session = str(uuid4())
    runtime = bundle.api.ManagedRuntime(store, config=deepcopy(bundle.config))
    runtime.start(session)
    event = {
        "schema": "cairntir.managed-event.v1",
        "event_id": str(uuid4()),
        "session_id": session,
        "sequence": 1,
        "task_id": None,
        "expected_revision": 0,
        "content": ORIGINAL,
    }
    receipt = runtime.capture(event)
    brief = runtime.brief()
    assert receipt["status"] == "committed"
    assert brief["status"] == "ready" and brief["complete"] is True
    return store, runtime, session, receipt, brief


def operation(bundle, principal, name):
    """Prepare one valid write boundary before entering its caller transaction."""
    store, runtime, session, captured, brief = ready(bundle, principal)
    if name == "start":
        runtime = bundle.api.ManagedRuntime(store, config=deepcopy(bundle.config))
        invoke = partial(runtime.start, session, task_id=captured["task_id"])
    elif name == "capture":
        event = {
            "schema": "cairntir.managed-event.v1",
            "event_id": str(uuid4()),
            "session_id": session,
            "sequence": 2,
            "task_id": captured["task_id"],
            "expected_revision": captured["revision"],
            "content": "  Preserve a second exact commitment café\r\n  ",
        }
        invoke = partial(runtime.capture, event)
    elif name == "brief":
        invoke = runtime.brief
    elif name == "acknowledge":
        request = {
            "schema": "cairntir.managed-ack.v1",
            "brief_id": brief["brief_id"],
            "brief_sha256": brief["brief_sha256"],
        }
        invoke = partial(runtime.acknowledge, request)
    else:
        assert name == "close"
        invoke = partial(runtime.close, last_sequence=1)
    return store, invoke


class CallerRollbackError(Exception):
    """Force rollback of the explicitly caller-owned transaction."""


@contextmanager
def caller_transaction(bundle, store, style):
    """Distinguish the public transaction API from an already-active raw writer."""
    if style == "explicit":
        with store.transaction():
            yield
    else:
        bundle.owner._conn.execute("BEGIN IMMEDIATE")
        try:
            yield
        finally:
            bundle.owner._conn.rollback()


@pytest.mark.parametrize("principal", ["owner", "scoped"])
@pytest.mark.parametrize("name", ["start", "capture", "brief", "acknowledge", "close"])
@pytest.mark.parametrize("style", ["explicit", "raw"])
def test_caller_transaction_cannot_issue_managed_durable_receipts(durable, principal, name, style):
    """Reject false durability without touching caller state; retry after rollback works."""
    bundle = durable
    store, invoke = operation(bundle, principal, name)
    with observer(bundle.path) as independent:
        baseline = snapshot(bundle.owner._conn)
        assert snapshot(independent) == baseline
        with pytest.raises(CallerRollbackError), caller_transaction(bundle, store, style):
            bundle.owner._conn.execute(
                "INSERT INTO store_metadata(key,value) VALUES (?,?)",
                ("managed_caller_work", "uncommitted caller-owned marker"),
            )
            inside = snapshot(bundle.owner._conn)
            assert inside != baseline and snapshot(independent) == baseline
            assert store.transaction_active is True
            with pytest.raises(bundle.api.ManagedRuntimeError):
                invoke()
            assert store.transaction_active is True
            assert snapshot(bundle.owner._conn) == inside
            assert snapshot(independent) == baseline
            raise CallerRollbackError
        assert store.transaction_active is False
        assert snapshot(bundle.owner._conn) == baseline
        assert snapshot(independent) == baseline
        committed = invoke()
        expected_status = (
            "ready" if name in {"start", "brief"} else "closed" if name == "close" else "committed"
        )
        assert committed["status"] == expected_status
        assert store.transaction_active is False
        after = snapshot(independent)
        assert after == snapshot(bundle.owner._conn) and after != baseline
        assert len(after["workflow_runs"]) > len(baseline["workflow_runs"])


@pytest.mark.parametrize("principal", ["owner", "scoped"])
@pytest.mark.parametrize("style", ["explicit", "raw"])
def test_projection_cannot_publish_caller_uncommitted_checkpoint(durable, principal, style):
    """Retain human bytes and durable view until pending checkpoint really commits."""
    bundle = durable
    store, _runtime, session, captured, brief = ready(bundle, principal)
    target = bundle.project / "Last Session.md"
    target.write_bytes(
        b"Human prefix\r\n<!-- cairntir:begin -->\nold generated\n"
        b"<!-- cairntir:end -->\r\nHuman suffix caf\xc3\xa9\r\n"
    )

    def project():
        return bundle.projection.project_last_session(
            store,
            root=bundle.project,
            path=target,
            wing=WING,
            session_id=session,
            epoch=brief["epoch"],
        )

    initial = project()
    assert initial["status"] == "complete"
    durable_bytes = target.read_bytes()
    with observer(bundle.path) as independent:
        baseline = snapshot(bundle.owner._conn)
        assert snapshot(independent) == baseline
        with pytest.raises(CallerRollbackError), caller_transaction(bundle, store, style):
            checkpoint = {
                "task_id": captured["task_id"],
                "expected_revision": captured["revision"],
                "idempotency_key": str(uuid4()),
                "status": "active",
                "completed": [],
                "outstanding": [ORIGINAL, "  caller-owned pending commitment café\r\n  "],
                "next_action": "Pending state has not physically committed",
                "evidence_ids": [captured["drawer_id"]],
            }
            TaskBook(store).checkpoint(WING, ROOM, "Uncommitted caller checkpoint", checkpoint)
            inside = snapshot(bundle.owner._conn)
            assert inside != baseline and snapshot(independent) == baseline
            result = project()
            assert result["status"] == "error" and result.get("error")
            assert "snapshot" not in result and "generated_sha256" not in result
            assert target.read_bytes() == durable_bytes
            assert store.transaction_active is True
            assert snapshot(bundle.owner._conn) == inside
            assert snapshot(independent) == baseline
            raise CallerRollbackError
        assert store.transaction_active is False
        assert snapshot(bundle.owner._conn) == baseline
        assert snapshot(independent) == baseline
        rebuilt = project()
        assert rebuilt["status"] == "complete"
        assert rebuilt["snapshot"] == initial["snapshot"]
        assert target.read_bytes() == durable_bytes
        assert snapshot(bundle.owner._conn) == baseline
        assert snapshot(independent) == baseline
