from __future__ import annotations

import importlib
import json
import os
import sys
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from cairntir.errors import CairntirError
from cairntir.managed import ManagedRuntime
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.tasks import TaskBook

WING = "r06-codex-test"
ROOM = "requests"
ORIGINAL = "PUBLIC R06: verify the selected task before controlled work."
CORRECTION = "PUBLIC R06 CORRECTION: use the revised task direction."


def api():
    return importlib.import_module("cairntir.codex_managed")


def task(store, task_id):
    return json.loads(TaskBook(store).resume(WING, task_id, 262144))


def seed(store, content=ORIGINAL):
    return json.loads(
        TaskBook(store).checkpoint(
            WING,
            ROOM,
            content,
            {
                "expected_revision": 0,
                "idempotency_key": str(uuid4()),
                "status": "active",
                "completed": [],
                "outstanding": [content],
                "next_action": "Verify the selected task.",
                "evidence_ids": [],
            },
        )
    )


def change(store, task_id, content=CORRECTION, *, terminal=False):
    resumed = task(store, task_id)
    current = resumed["checkpoint"]
    return json.loads(
        TaskBook(store).checkpoint(
            WING,
            ROOM,
            content,
            {
                "task_id": task_id,
                "expected_revision": resumed["revision"],
                "idempotency_key": str(uuid4()),
                "status": "completed" if terminal else "active",
                "completed": ["PUBLIC done"] if terminal else current["completed"],
                "outstanding": [] if terminal else [*current["outstanding"], content],
                "next_action": "" if terminal else "Verify the revised task.",
                "evidence_ids": current["evidence_ids"],
            },
        )
    )


class FakeTransport:
    def __init__(self, mutate=None, error=None):
        self.calls = []
        self.mutate = mutate
        self.error = error

    def __call__(self, *, config, mode, thread_id, brief, prior_turn_id, prior_ack):
        call = deepcopy(
            {
                "mode": mode,
                "thread_id": thread_id,
                "brief": brief,
                "prior_turn_id": prior_turn_id,
                "prior_ack": prior_ack,
            }
        )
        self.calls.append(call)
        if self.error is not None:
            raise self.error
        reply = {
            "thread_id": thread_id or "PUBLIC-native-thread",
            "turn_id": f"PUBLIC-native-turn-{len(self.calls)}",
            "persistent": True,
            "server_closed": True,
            "server_exit_code": 0,
            "history_verified": mode == "resume",
            "prior_turn_id": prior_turn_id,
            "prior_ack": deepcopy(prior_ack),
            "native_tool_activity": False,
            "model_ack": {
                "schema": "cairntir.codex-managed-ack.v1",
                "brief_id": brief["brief_id"],
                "brief_sha256": brief["brief_sha256"],
                "task_id": brief["task_id"],
                "revision": brief["revision"],
            },
        }
        if self.mutate is not None:
            self.mutate(reply, call)
        return reply


@contextmanager
def case(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    database = root / "memory.db"
    if database.exists():
        raise ValueError("fixture database already exists")
    effect = root / "fixed_effect.py"
    effect.write_bytes(Path(__file__).with_name("fixed_effect.py").read_bytes())
    marker = root / "effects.jsonl"
    home = root / "host-home"
    home.mkdir()
    env = {"CODEX_HOME": str(home)}
    for key, folder in (
        ("HOME", "home"),
        ("USERPROFILE", "home"),
        ("APPDATA", "appdata"),
        ("LOCALAPPDATA", "localappdata"),
        ("TEMP", "temp"),
        ("TMP", "temp"),
    ):
        path = root / folder
        path.mkdir(exist_ok=True)
        env[key] = str(path)
    for key in ("SYSTEMROOT", "WINDIR", "PATH", "COMSPEC", "PATHEXT"):
        if key in os.environ:
            env[key] = os.environ[key]
    config = {
        "schema": "cairntir.managed-config.v1",
        "wing": WING,
        "room": ROOM,
        "project_root": str(root),
        "brief_budget_chars": 32768,
        "profiles": {
            "verify": {
                "argv": [sys.executable, "-I", "-B", str(effect), str(database), str(marker)],
                "cwd": str(root),
                "timeout_seconds": 30,
                "output_limit_bytes": 65536,
            }
        },
    }
    host_config = {
        "schema": "cairntir.codex-managed-config.v1",
        "executable": sys.executable,
        "codex_home": str(home),
        "cwd": str(root),
        "model": "gpt-6.1-sol",
        "timeout_seconds": 120,
        "output_limit_bytes": 1048576,
        "env": env,
    }
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        runtime = ManagedRuntime(store, config=config)
        yield {
            "root": root,
            "database": database,
            "marker": marker,
            "store": store,
            "runtime": runtime,
            "runtime_config": config,
            "host_config": host_config,
            "session_id": str(uuid4()),
        }


def start_selected(c, host=None, *, session_class=None):
    selected = seed(c["store"])
    c["task_id"] = selected["task_id"]
    c["host"] = host if host is not None else FakeTransport()
    cls = session_class or api().CodexManaged
    session = cls(c["runtime"], config=c["host_config"], transport=c["host"])
    brief = session.start(c["session_id"], task_id=c["task_id"])
    assert brief["status"] == "ready"
    event_id = str(uuid4())
    event = {
        "schema": "cairntir.managed-event.v1",
        "event_id": event_id,
        "session_id": c["session_id"],
        "sequence": 1,
        "task_id": c["task_id"],
        "expected_revision": selected["revision"],
        "content": "PUBLIC R06: perform the fixed verification action.",
    }
    captured = session.capture(event)
    assert captured["status"] == "committed"
    c["event_id"] = event_id
    c["event"] = event
    c["session"] = session
    return session


def action(c):
    return {
        "schema": "cairntir.codex-managed-action.v1",
        "action_id": str(uuid4()),
        "profile": "verify",
        "claim": "PUBLIC fixed verification observes committed ACK and intent.",
        "predicted_outcome": "PUBLIC one fixed effect follows this acknowledged action.",
        "event_ids": [c["event_id"]],
    }


def effects(c):
    if not c["marker"].exists():
        return []
    return [json.loads(line) for line in c["marker"].read_text(encoding="utf-8").splitlines()]


def operations(c, operation):
    return (
        c["store"]
        ._conn.execute(
            "SELECT COUNT(*) FROM workflow_runs WHERE operation=? AND state='committed'",
            (operation,),
        )
        .fetchone()[0]
    )


def assert_missing_ack_refused(session, c):
    try:
        session.turn(action(c))
    except CairntirError:
        pass
    else:
        raise AssertionError("invalid_host_ack_accepted")
    assert effects(c) == []
    assert operations(c, "managed.ack.v1") == 0
    assert operations(c, "managed.dispatch.v1") == 0
