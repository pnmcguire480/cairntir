import json
import sys
from copy import deepcopy
from uuid import uuid4

import pytest

from cairntir.access import AccessDenied, bind_grant, issue_grant, revoke_grant
from cairntir.managed import ManagedRuntime, ManagedRuntimeError
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.tasks import TaskBook

WING = "managed_authority_edges"
ROOM = "requests"


def _config(root):
    return {
        "schema": "cairntir.managed-config.v1",
        "wing": WING,
        "room": ROOM,
        "project_root": str(root),
        "brief_budget_chars": 65536,
        "profiles": {
            "check": {
                "argv": [sys.executable, "-c", "raise SystemExit(0)"],
                "cwd": str(root),
                "timeout_seconds": 10,
                "output_limit_bytes": 4096,
            }
        },
    }


def _state(store):
    return (
        tuple(map(tuple, store._conn.execute("SELECT * FROM drawers ORDER BY id"))),
        tuple(
            map(tuple, store._conn.execute("SELECT * FROM workflow_runs ORDER BY idempotency_key"))
        ),
        tuple(
            map(tuple, store._conn.execute("SELECT * FROM procedure_records ORDER BY drawer_id"))
        ),
        tuple(
            map(
                tuple, store._conn.execute("SELECT * FROM procedure_evaluations ORDER BY drawer_id")
            )
        ),
    )


def _event(session, *, task_id=None, revision=0, sequence=1):
    return {
        "schema": "cairntir.managed-event.v1",
        "event_id": str(uuid4()),
        "session_id": session,
        "sequence": sequence,
        "task_id": task_id,
        "expected_revision": revision,
        "content": "Review the restore before closing the task.",
    }


@pytest.mark.parametrize(
    "change",
    ["outer_shape", "payload_shape", "operation", "key", "schema", "room"],
)
def test_forged_scoped_managed_request_never_invokes_callback_or_commits(tmp_path, change):
    path = tmp_path / "memory.db"
    with DrawerStore(path, HashEmbeddingProvider(32)) as store:
        token = issue_grant(
            store, scopes=[{"wing": WING, "rooms": [ROOM]}], capabilities=["read", "write"]
        )
        scoped = bind_grant(store, token)
        event_id = str(uuid4())
        request = {
            "wing": WING,
            "room": ROOM,
            "request": {"schema": "cairntir.managed-event.v1", "event_id": event_id},
        }
        operation = "managed.event.v1"
        key = f"managed:event:{event_id}"
        if change == "outer_shape":
            request["grant"] = token
        elif change == "payload_shape":
            request["request"] = [request["request"]]
        elif change == "operation":
            operation = "managed.close.v1"
        elif change == "key":
            key = f"managed:event:{uuid4()}"
        elif change == "schema":
            request["request"]["schema"] = "cairntir.managed-reconcile.v1"
        else:
            request["room"] = "private"
        calls = []
        before = _state(store)
        with pytest.raises(AccessDenied):
            scoped._managed_shared_once(
                idempotency_key=key,
                operation=operation,
                request=request,
                action=lambda: calls.append("invoked"),
            )
        assert calls == []
        assert _state(store) == before
        assert not store.workflow_receipt(key)
    with DrawerStore(path, HashEmbeddingProvider(32)) as reopened:
        assert _state(reopened) == before


@pytest.mark.parametrize("hidden", ["event", "evidence"])
def test_scoped_reconciliation_cannot_use_hidden_drawer_proof(tmp_path, hidden):
    path = tmp_path / "memory.db"
    with DrawerStore(path, HashEmbeddingProvider(32)) as store:
        event = store.add(
            Drawer(wing=WING, room="private" if hidden == "event" else ROOM, content="event")
        )
        evidence = store.add(
            Drawer(wing=WING, room="private" if hidden == "evidence" else ROOM, content="proof")
        )
        token = issue_grant(
            store, scopes=[{"wing": WING, "rooms": [ROOM]}], capabilities=["read", "write"]
        )
        scoped = bind_grant(store, token)
        reconciliation_id = str(uuid4())
        request = {
            "wing": WING,
            "room": ROOM,
            "request": {
                "schema": "cairntir.managed-reconcile.v1",
                "reconciliation_id": reconciliation_id,
                "event_drawer_id": event.id,
                "evidence_ids": [evidence.id],
            },
        }
        calls = []
        before = _state(store)
        key = f"managed:reconcile:{reconciliation_id}"
        with pytest.raises(AccessDenied):
            scoped._managed_shared_once(
                idempotency_key=key,
                operation="managed.reconcile.v1",
                request=request,
                action=lambda: calls.append("invoked"),
            )
        assert calls == []
        assert _state(store) == before
        assert not store.workflow_receipt(key)
    with DrawerStore(path, HashEmbeddingProvider(32)) as reopened:
        assert _state(reopened) == before


def test_mid_transaction_grant_revocation_rolls_back_managed_result(tmp_path):
    path = tmp_path / "memory.db"
    with DrawerStore(path, HashEmbeddingProvider(32)) as store:
        token = issue_grant(
            store, scopes=[{"wing": WING, "rooms": [ROOM]}], capabilities=["read", "write"]
        )
        scoped = bind_grant(store, token)
        event_id = str(uuid4())
        request = {
            "wing": WING,
            "room": ROOM,
            "request": {"schema": "cairntir.managed-event.v1", "event_id": event_id},
        }
        key = f"managed:event:{event_id}"
        calls = []

        def append():
            calls.append("invoked")
            saved = store.add(Drawer(wing=WING, room=ROOM, content="uncommitted"))
            revoke_grant(store, token)
            return {"_managed": {"evidence_ids": [saved.id]}}

        before = _state(store)
        with pytest.raises(AccessDenied):
            scoped._managed_shared_once(
                idempotency_key=key,
                operation="managed.event.v1",
                request=request,
                action=append,
            )
        assert calls == ["invoked"]
        assert _state(store) == before
        assert not store.workflow_receipt(key)
        bind_grant(store, token)
    with DrawerStore(path, HashEmbeddingProvider(32)) as reopened:
        assert _state(reopened) == before


def test_scoped_managed_result_cannot_commit_hidden_evidence(tmp_path):
    path = tmp_path / "memory.db"
    with DrawerStore(path, HashEmbeddingProvider(32)) as store:
        hidden = store.add(Drawer(wing=WING, room="private", content="withheld"))
        token = issue_grant(
            store, scopes=[{"wing": WING, "rooms": [ROOM]}], capabilities=["read", "write"]
        )
        scoped = bind_grant(store, token)
        event_id = str(uuid4())
        request = {
            "wing": WING,
            "room": ROOM,
            "request": {"schema": "cairntir.managed-event.v1", "event_id": event_id},
        }
        key = f"managed:event:{event_id}"
        calls = []

        def append():
            calls.append("invoked")
            store.add(Drawer(wing=WING, room=ROOM, content="uncommitted"))
            return {"_managed": {"evidence_ids": [hidden.id]}}

        before = _state(store)
        with pytest.raises(AccessDenied):
            scoped._managed_shared_once(
                idempotency_key=key,
                operation="managed.event.v1",
                request=request,
                action=append,
            )
        assert calls == ["invoked"]
        assert _state(store) == before
        assert not store.workflow_receipt(key)
    with DrawerStore(path, HashEmbeddingProvider(32)) as reopened:
        assert _state(reopened) == before


@pytest.mark.parametrize("registry", ["procedure", "evaluation"])
def test_scoped_registry_write_rejects_hidden_payload_reference(tmp_path, registry):
    path = tmp_path / "memory.db"
    with DrawerStore(path, HashEmbeddingProvider(32)) as store:
        visible = store.add(Drawer(wing=WING, room=ROOM, content="candidate"))
        hidden = store.add(Drawer(wing=WING, room="private", content="private evidence"))
        token = issue_grant(
            store, scopes=[{"wing": WING, "rooms": [ROOM]}], capabilities=["read", "write"]
        )
        scoped = bind_grant(store, token)
        payload = {"drawer_id": visible.id, "evidence_ids": [hidden.id]}
        before = _state(store)
        with pytest.raises(AccessDenied):
            if registry == "procedure":
                scoped._register_procedure(
                    visible.id, root_id=visible.id, parent_id=None, payload=payload
                )
            else:
                scoped._register_procedure_evaluation(visible.id, payload)
        assert _state(store) == before
    with DrawerStore(path, HashEmbeddingProvider(32)) as reopened:
        assert _state(reopened) == before


@pytest.mark.parametrize("registry", ["procedure", "evaluation"])
def test_scoped_registry_write_preserves_visible_payload_reference(tmp_path, registry):
    with DrawerStore(tmp_path / "memory.db", HashEmbeddingProvider(32)) as store:
        visible = store.add(Drawer(wing=WING, room=ROOM, content="candidate"))
        token = issue_grant(
            store, scopes=[{"wing": WING, "rooms": [ROOM]}], capabilities=["read", "write"]
        )
        scoped = bind_grant(store, token)
        payload = {"drawer_id": visible.id, "evidence_ids": [visible.id]}
        if registry == "procedure":
            scoped._register_procedure(
                visible.id, root_id=visible.id, parent_id=None, payload=payload
            )
            assert scoped._procedure_record(visible.id)["evidence_ids"] == [visible.id]
        else:
            scoped._register_procedure_evaluation(visible.id, payload)
            assert scoped._procedure_evaluation(visible.id)["evidence_ids"] == [visible.id]


def test_capture_task_created_between_identity_check_and_append_is_rejected(tmp_path, monkeypatch):
    path = tmp_path / "memory.db"
    with DrawerStore(path, HashEmbeddingProvider(32)) as store:
        runtime = ManagedRuntime(store, config=_config(tmp_path))
        session = str(uuid4())
        runtime.start(session)
        original = runtime._execute
        event = _event(session)

        def shifted(operation, key, request, action):
            result = original(operation, key, request, action)
            if operation == "sequence":
                TaskBook(store).checkpoint(
                    WING,
                    ROOM,
                    "A competing request opened a task.",
                    {
                        "expected_revision": 0,
                        "idempotency_key": str(uuid4()),
                        "status": "active",
                        "completed": [],
                        "outstanding": ["A competing request opened a task."],
                        "next_action": "Check the new task.",
                        "evidence_ids": [],
                    },
                )
            return result

        monkeypatch.setattr(runtime, "_execute", shifted)
        before = _state(store)
        with pytest.raises(ManagedRuntimeError):
            runtime.capture(event)
        assert _state(store) == before
        assert not store.workflow_receipt(f"managed:event:{event['event_id']}")
        assert json.loads(TaskBook(store).resume(WING))["status"] == "none"
    with DrawerStore(path, HashEmbeddingProvider(32)) as reopened:
        assert _state(reopened) == before


def test_capture_event_identity_occupied_between_checks_rolls_back(tmp_path, monkeypatch):
    path = tmp_path / "memory.db"
    with DrawerStore(path, HashEmbeddingProvider(32)) as store:
        runtime = ManagedRuntime(store, config=_config(tmp_path))
        session = str(uuid4())
        runtime.start(session)
        event = _event(session)
        original = store._managed_event_identity_occupied
        calls = []

        def changed(**kwargs):
            calls.append(kwargs)
            if len(calls) == 2:
                second = _event(str(uuid4()))
                second["event_id"] = event["event_id"]
                bound = {"wing": WING, "room": ROOM, "request": second}
                store.execute_once(
                    idempotency_key=f"managed:event:{uuid4()}",
                    operation="managed.event.v1",
                    request=bound,
                    action=lambda: {
                        "event_id": second["event_id"],
                        "session_id": second["session_id"],
                        "sequence": second["sequence"],
                        "_managed": {
                            "operation": "managed.event.v1",
                            "request": bound,
                            "evidence_ids": [],
                        },
                    },
                )
            return original(**kwargs)

        monkeypatch.setattr(store, "_managed_event_identity_occupied", changed)
        before = _state(store)
        with pytest.raises(ManagedRuntimeError, match="changed before capture"):
            runtime.capture(event)
        assert len(calls) == 2
        assert _state(store) == before
        assert not store.workflow_receipt(f"managed:event:{event['event_id']}")
    with DrawerStore(path, HashEmbeddingProvider(32)) as reopened:
        assert _state(reopened) == before


def test_capture_selected_task_terminal_between_checks_rolls_back(tmp_path, monkeypatch):
    path = tmp_path / "memory.db"
    with DrawerStore(path, HashEmbeddingProvider(32)) as store:
        runtime = ManagedRuntime(store, config=_config(tmp_path))
        session = str(uuid4())
        runtime.start(session)
        captured = runtime.capture(_event(session))
        event = _event(
            session, task_id=captured["task_id"], revision=captured["revision"], sequence=2
        )
        original = runtime._execute

        def shifted(operation, key, request, action):
            result = original(operation, key, request, action)
            if operation == "sequence":
                current = json.loads(TaskBook(store).resume(WING, task_id=captured["task_id"]))
                TaskBook(store).checkpoint(
                    WING,
                    ROOM,
                    "The selected task was closed concurrently.",
                    {
                        "task_id": captured["task_id"],
                        "expected_revision": current["revision"],
                        "idempotency_key": str(uuid4()),
                        "status": "completed",
                        "completed": current["checkpoint"]["outstanding"],
                        "outstanding": [],
                        "next_action": "",
                        "evidence_ids": current["checkpoint"]["evidence_ids"],
                    },
                )
            return result

        monkeypatch.setattr(runtime, "_execute", shifted)
        before = _state(store)
        with pytest.raises(ManagedRuntimeError, match="selected active task"):
            runtime.capture(event)
        assert _state(store) == before
        assert json.loads(TaskBook(store).resume(WING, captured["task_id"]))["revision"] == 1
    with DrawerStore(path, HashEmbeddingProvider(32)) as reopened:
        assert _state(reopened) == before


@pytest.mark.parametrize("drift", ["revision", "terminal"])
def test_reconcile_task_drift_after_evidence_check_rolls_back(tmp_path, monkeypatch, drift):
    path = tmp_path / "memory.db"
    with DrawerStore(path, HashEmbeddingProvider(32)) as store:
        runtime = ManagedRuntime(store, config=_config(tmp_path))
        session = str(uuid4())
        runtime.start(session)
        captured = runtime.capture(_event(session))
        evidence = store.add(
            Drawer(
                wing=WING,
                room=ROOM,
                content="Restore row count checked.",
                metadata={
                    "kind": "managed.reconciliation-evidence",
                    "task_id": captured["task_id"],
                    "event_id": captured["event_id"],
                },
            )
        )
        request = {
            "schema": "cairntir.managed-reconcile.v1",
            "reconciliation_id": str(uuid4()),
            "task_id": captured["task_id"],
            "expected_revision": captured["revision"],
            "event_id": captured["event_id"],
            "event_drawer_id": captured["drawer_id"],
            "source_identity": captured["source_identity"],
            "content_sha256": captured["content_sha256"],
            "disposition": "completed",
            "reason": "Rows match backup.",
            "evidence_ids": [evidence.id],
        }
        original = runtime._execute

        def shifted(operation, key, payload, action):
            if operation == "reconcile":
                current = json.loads(TaskBook(store).resume(WING, task_id=captured["task_id"]))
                TaskBook(store).checkpoint(
                    WING,
                    ROOM,
                    "Task changed before reconciliation append.",
                    {
                        "task_id": captured["task_id"],
                        "expected_revision": current["revision"],
                        "idempotency_key": str(uuid4()),
                        "status": "active" if drift == "revision" else "completed",
                        "completed": (
                            current["checkpoint"]["completed"]
                            if drift == "revision"
                            else current["checkpoint"]["outstanding"]
                        ),
                        "outstanding": (
                            current["checkpoint"]["outstanding"] if drift == "revision" else []
                        ),
                        "next_action": "Review drift." if drift == "revision" else "",
                        "evidence_ids": current["checkpoint"]["evidence_ids"],
                    },
                )
            return original(operation, key, payload, action)

        monkeypatch.setattr(runtime, "_execute", shifted)
        before = _state(store)
        with pytest.raises(ManagedRuntimeError, match=r"stale|unavailable"):
            runtime.reconcile(request)
        assert _state(store) == before
        assert not store.workflow_receipt(f"managed:reconcile:{request['reconciliation_id']}")
    with DrawerStore(path, HashEmbeddingProvider(32)) as reopened:
        assert _state(reopened) == before


def test_duplicate_committed_event_binding_blocks_brief_after_restart(tmp_path):
    path = tmp_path / "memory.db"
    with DrawerStore(path, HashEmbeddingProvider(32)) as store:
        runtime = ManagedRuntime(store, config=_config(tmp_path))
        session = str(uuid4())
        runtime.start(session)
        captured = runtime.capture(_event(session))
        record = deepcopy(
            next(
                item
                for item in store._managed_records(wing=WING, include_events=True)
                if item["_managed"]["operation"] == "managed.event.v1"
            )
        )
        store.execute_once(
            idempotency_key=f"managed:event:{uuid4()}",
            operation="managed.event.v1",
            request=record["_managed"]["request"],
            action=lambda: record,
        )
        before = _state(store)
        with pytest.raises(ManagedRuntimeError, match="conflicting committed bindings"):
            runtime.brief()
        assert _state(store) == before
    with DrawerStore(path, HashEmbeddingProvider(32)) as reopened:
        later = ManagedRuntime(reopened, config=_config(tmp_path))
        with pytest.raises(ManagedRuntimeError, match="conflicting committed bindings"):
            later.start(str(uuid4()), task_id=captured["task_id"])
        assert _state(reopened) == before


def test_inconsistent_reconciliation_registry_blocks_brief_after_restart(tmp_path):
    path = tmp_path / "memory.db"
    with DrawerStore(path, HashEmbeddingProvider(32)) as store:
        runtime = ManagedRuntime(store, config=_config(tmp_path))
        session = str(uuid4())
        runtime.start(session)
        captured = runtime.capture(_event(session))
        payload = {
            "schema": "cairntir.managed-reconcile.v1",
            "reconciliation_id": str(uuid4()),
            "task_id": captured["task_id"],
            "expected_revision": captured["revision"],
            "event_id": captured["event_id"],
            "event_drawer_id": captured["drawer_id"],
            "source_identity": captured["source_identity"],
            "content_sha256": captured["content_sha256"],
            "disposition": "completed",
            "reason": "Owner attested the row count.",
            "evidence_ids": [],
        }
        bound = {"wing": WING, "room": ROOM, "request": payload}
        store.execute_once(
            idempotency_key=f"managed:reconcile:{payload['reconciliation_id']}",
            operation="managed.reconcile.v1",
            request=bound,
            action=lambda: {
                "task_id": captured["task_id"],
                "event_id": captured["event_id"],
                "revision": captured["revision"] + 1,
                "disposition": "completed",
                "reason": "Someone else attested the row count.",
                "evidence_ids": [],
                "_managed": {
                    "operation": "managed.reconcile.v1",
                    "request": bound,
                    "evidence_ids": [],
                },
            },
        )
        before = _state(store)
        with pytest.raises(ManagedRuntimeError, match="conflicting bindings"):
            runtime.brief()
        assert _state(store) == before
    with DrawerStore(path, HashEmbeddingProvider(32)) as reopened:
        later = ManagedRuntime(reopened, config=_config(tmp_path))
        with pytest.raises(ManagedRuntimeError, match="conflicting bindings"):
            later.start(str(uuid4()), task_id=captured["task_id"])
        assert _state(reopened) == before
