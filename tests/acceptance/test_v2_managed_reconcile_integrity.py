import json
import sys
from copy import deepcopy
from uuid import uuid4

import pytest

from cairntir.access import bind_grant, issue_grant, revoke_grant
from cairntir.managed import ManagedRuntime, ManagedRuntimeError
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.tasks import TaskBook

WING = "managed_reconcile_integrity"
ROOM = "requests"
COMMITMENT = "Finish the database migration after checking the restored rows."


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
    drawers = store._conn.execute(
        "SELECT id, wing, room, content, metadata FROM drawers ORDER BY id"
    ).fetchall()
    workflows = store._conn.execute("SELECT * FROM workflow_runs ORDER BY idempotency_key")
    return tuple(map(tuple, drawers)), tuple(map(tuple, workflows))


def _capture(store, root):
    runtime = ManagedRuntime(store, config=_config(root))
    session_id = str(uuid4())
    runtime.start(session_id)
    captured = runtime.capture(
        {
            "schema": "cairntir.managed-event.v1",
            "event_id": str(uuid4()),
            "session_id": session_id,
            "sequence": 1,
            "task_id": None,
            "expected_revision": 0,
            "content": COMMITMENT,
        }
    )
    evidence = store.add(
        Drawer(
            wing=WING,
            room=ROOM,
            content="Operator checked the restored row count against the backup.",
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
        "reason": "Restore verified against the backup.",
        "evidence_ids": [evidence.id],
    }
    return runtime, captured, request


def _resume(store, task_id):
    return json.loads(TaskBook(store).resume(WING, task_id=task_id))


def test_completion_replays_exact_receipt_without_duplication_and_survives_restart(tmp_path):
    path = tmp_path / "memory.db"
    with DrawerStore(path, HashEmbeddingProvider(32)) as store:
        runtime, captured, request = _capture(store, tmp_path)
        first = runtime.reconcile(request)
        assert first["status"] == "committed" and first["replayed"] is False
        resumed = _resume(store, captured["task_id"])
        assert resumed["revision"] == first["revision"]
        assert COMMITMENT in resumed["checkpoint"]["completed"]
        assert COMMITMENT not in resumed["checkpoint"]["outstanding"]
        before = _state(store)
        replay = runtime.reconcile(request)
        assert replay == {**first, "replayed": True}
        assert _state(store) == before
    with DrawerStore(path, HashEmbeddingProvider(32)) as reopened:
        resumed = _resume(reopened, captured["task_id"])
        assert resumed["revision"] == first["revision"]
        next_runtime = ManagedRuntime(reopened, config=_config(tmp_path))
        brief = next_runtime.start(str(uuid4()), task_id=captured["task_id"])
        assert brief["unfinished_events"] == []
        assert brief["complete"] is True


@pytest.mark.parametrize(
    "change",
    [
        "bad_digest",
        "wrong_task",
        "stale_revision",
        "wrong_event_drawer",
        "wrong_source",
        "missing_evidence",
    ],
)
def test_reconciliation_rejects_unbound_or_stale_proof_without_new_receipt(tmp_path, change):
    with DrawerStore(tmp_path / "memory.db", HashEmbeddingProvider(32)) as store:
        runtime, captured, original = _capture(store, tmp_path)
        request = deepcopy(original)
        if change == "bad_digest":
            request["content_sha256"] = request["content_sha256"].upper()
        elif change == "wrong_task":
            request["task_id"] = str(uuid4())
        elif change == "stale_revision":
            request["expected_revision"] -= 1
        elif change == "wrong_event_drawer":
            request["event_drawer_id"] = request["evidence_ids"][0]
        elif change == "wrong_source":
            request["source_identity"] = str(uuid4())
        else:
            request["evidence_ids"] = []
        before = _state(store)
        revision = _resume(store, captured["task_id"])["revision"]
        with pytest.raises(ManagedRuntimeError):
            runtime.reconcile(request)
        assert _state(store) == before
        assert _resume(store, captured["task_id"])["revision"] == revision
        assert store.workflow_receipt(f"managed:reconcile:{request['reconciliation_id']}") is None


def test_reconciliation_refuses_commitment_removed_from_checkpoint(tmp_path):
    with DrawerStore(tmp_path / "memory.db", HashEmbeddingProvider(32)) as store:
        runtime, captured, request = _capture(store, tmp_path)
        current = _resume(store, captured["task_id"])
        old = current["checkpoint"]
        corrected = json.loads(
            TaskBook(store).checkpoint(
                WING,
                ROOM,
                "Operator removed the promise from this task.",
                {
                    "task_id": captured["task_id"],
                    "expected_revision": current["revision"],
                    "idempotency_key": str(uuid4()),
                    "status": "active",
                    "completed": old["completed"],
                    "outstanding": [],
                    "next_action": old["next_action"],
                    "evidence_ids": old["evidence_ids"],
                },
            )
        )
        request["expected_revision"] = corrected["revision"]
        before = _state(store)
        with pytest.raises(ManagedRuntimeError, match="absent from the task"):
            runtime.reconcile(request)
        assert _state(store) == before
        assert _resume(store, captured["task_id"])["revision"] == corrected["revision"]


def test_revoked_room_grant_cannot_reconcile_after_capture(tmp_path):
    with DrawerStore(tmp_path / "memory.db", HashEmbeddingProvider(32)) as store:
        _, captured, request = _capture(store, tmp_path)
        token = issue_grant(
            store,
            scopes=[{"wing": WING, "rooms": [ROOM]}],
            capabilities=["read", "write"],
        )
        scoped = ManagedRuntime(bind_grant(store, token), config=_config(tmp_path))
        scoped.start(str(uuid4()), task_id=captured["task_id"])
        revoke_grant(store, token)
        before = _state(store)
        with pytest.raises(ManagedRuntimeError):
            scoped.reconcile(request)
        assert _state(store) == before
        assert store.workflow_receipt(f"managed:reconcile:{request['reconciliation_id']}") is None
