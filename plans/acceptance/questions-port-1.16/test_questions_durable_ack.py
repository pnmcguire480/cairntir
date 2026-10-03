"""Independent inherited durable-acknowledgement controls for the R08 port."""

from __future__ import annotations

import hashlib
import importlib
import json
import socket
import sqlite3
import subprocess
from contextlib import closing, contextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
import sqlite_vec

from cairntir.access import bind_grant, issue_grant
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer

WING = "durable-question-fixture"


@contextmanager
def _observer(path):
    with closing(sqlite3.connect(path, timeout=1)) as connection:
        connection.enable_load_extension(True)
        sqlite_vec.load(connection)
        connection.enable_load_extension(False)
        yield connection


def _snapshot(connection):
    names = [
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    ]
    result = {}
    for name in names:
        quoted = name.replace('"', '""')
        # Disposable schema-derived names; quote embedded identifier delimiters.
        rows = connection.execute(f'SELECT * FROM "{quoted}"').fetchall()  # noqa: S608
        result[name] = tuple(sorted((tuple(row) for row in rows), key=repr))
    return result


@pytest.fixture
def durable(tmp_path, monkeypatch):
    for name in ("CAIRNTIR_HOME", "XDG_CACHE_HOME", "HF_HOME", "TORCH_HOME", "TEMP", "TMP"):
        home = tmp_path / name.lower()
        home.mkdir()
        monkeypatch.setenv(name, str(home))
    monkeypatch.delenv("CAIRNTIR_GRANT_FILE", raising=False)
    monkeypatch.setenv("CAIRNTIR_DISABLE_AUTOREGISTER", "1")
    monkeypatch.setenv("CAIRNTIR_DISABLE_UPDATE_CHECK", "1")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")

    def deny(*_args, **_kwargs):
        pytest.fail("Durable question fixture attempted network or an external process")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(subprocess, "Popen", deny)
    path = tmp_path / "questions.db"
    owner = DrawerStore(path, HashEmbeddingProvider(dimension=16))
    support = owner.add(Drawer(wing=WING, room="work", content="Exact evidence café\r\n  "))
    token = issue_grant(owner, scopes=[{"wing": WING}], capabilities=["read", "write"])
    reference = {
        "drawer_id": support.id,
        "source_identity": owner.portable_identity(support.id),
        "content_sha256": hashlib.sha256(support.content.encode()).hexdigest(),
    }
    bundle = SimpleNamespace(
        owner=owner,
        path=path,
        token=token,
        reference=reference,
        api=importlib.import_module("cairntir.questions"),
    )
    try:
        yield bundle
    finally:
        bundle.owner.close()


def _actor(bundle, principal):
    return bundle.owner if principal == "owner" else bind_grant(bundle.owner, bundle.token)


def _operation(bundle, principal, operation):
    actor = _actor(bundle, principal)
    opening = {
        "schema": "cairntir.question-open.v1",
        "request_id": str(uuid4()),
        "wing": WING,
        "room": "work",
        "content": "  Exact question café\r\n  ",
        "owner": " Attribution only ",
        "evidence": [bundle.reference],
    }
    if operation == "open":
        return actor, bundle.api.open_question, opening
    opened = bundle.api.open_question(actor, opening, wing=WING)
    return (
        actor,
        bundle.api.resolve_question,
        {
            "schema": "cairntir.question-resolve.v1",
            "request_id": str(uuid4()),
            "wing": WING,
            "question_id": opened["question_id"],
            "question_drawer_id": opened["question_drawer_id"],
            "question_sha256": opened["question_sha256"],
            "content": "  Declared resolution café\r\n  ",
            "evidence": [bundle.reference],
        },
    )


class _CallerRollback(Exception):
    pass


@contextmanager
def _caller_transaction(bundle, actor, style):
    if style == "explicit":
        with actor.transaction():
            yield
    else:
        bundle.owner._conn.execute("BEGIN IMMEDIATE")
        try:
            yield
        finally:
            bundle.owner._conn.rollback()


@pytest.mark.parametrize("principal", ["owner", "scoped"])
@pytest.mark.parametrize("operation", ["open", "resolve"])
@pytest.mark.parametrize("style", ["explicit", "raw"])
def test_caller_transaction_cannot_acknowledge_a_durable_question(
    durable, principal, operation, style
):
    b = durable
    actor, invoke, request = _operation(b, principal, operation)
    with _observer(b.path) as observer:
        baseline = _snapshot(b.owner._conn)
        assert _snapshot(observer) == baseline
        with pytest.raises(_CallerRollback):
            with _caller_transaction(b, actor, style):
                b.owner._conn.execute(
                    "INSERT INTO store_metadata(key, value) VALUES (?, ?)",
                    ("question_acceptance_caller_write", "uncommitted caller work"),
                )
                inside = _snapshot(b.owner._conn)
                assert inside != baseline and _snapshot(observer) == baseline
                assert actor.transaction_active is True
                with pytest.raises(b.api.QuestionError):
                    invoke(actor, request, wing=WING)
                assert actor.transaction_active is True
                assert _snapshot(b.owner._conn) == inside
                assert _snapshot(observer) == baseline
                raise _CallerRollback
        assert actor.transaction_active is False
        assert _snapshot(b.owner._conn) == baseline
        assert _snapshot(observer) == baseline


@pytest.mark.parametrize("principal", ["owner", "scoped"])
@pytest.mark.parametrize("operation", ["open", "resolve"])
def test_question_commit_is_visible_independently_and_replays_after_restart(
    durable, principal, operation
):
    b = durable
    actor, invoke, request = _operation(b, principal, operation)
    with _observer(b.path) as observer:
        before = _snapshot(observer)
        receipt = invoke(actor, request, wing=WING)
        assert receipt["status"] == "committed" and receipt["replayed"] is False
        assert actor.transaction_active is False
        after = _snapshot(observer)
        assert after == _snapshot(b.owner._conn) and after != before
        results = [
            json.loads(row[0])
            for row in observer.execute("SELECT result FROM workflow_runs WHERE state='committed'")
        ]
        stored = [result for result in results if result.get("request_id") == request["request_id"]]
        assert len(stored) == 1
        assert {key: stored[0][key] for key in receipt if key != "replayed"} == {
            key: value for key, value in receipt.items() if key != "replayed"
        }
        result_id = (
            receipt["question_drawer_id"]
            if operation == "open"
            else receipt["resolution_drawer_id"]
        )
        assert observer.execute(
            "SELECT content FROM drawers WHERE id=?", (result_id,)
        ).fetchone() == (request["content"],)
        assert observer.execute(
            "SELECT identity FROM portable_records WHERE drawer_id=?",
            (receipt["question_drawer_id"],),
        ).fetchone() == (receipt["question_id"],)
        b.owner.close()
        b.owner = DrawerStore(b.path, HashEmbeddingProvider(dimension=16))
        replay_actor = _actor(b, principal)
        replay = getattr(b.api, operation + "_question")(replay_actor, request, wing=WING)
        assert replay == {**receipt, "replayed": True}
        assert _snapshot(observer) == after
        assert _snapshot(b.owner._conn) == after
