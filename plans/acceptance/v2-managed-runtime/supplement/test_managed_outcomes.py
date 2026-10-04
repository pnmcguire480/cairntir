"""Public managed failure outcomes frozen before their first candidate execution."""

import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from cairntir.access import bind_grant, issue_grant, revoke_grant
from cairntir.managed import ManagedRuntime, ManagedRuntimeError, stream_command
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.tasks import TaskBook


class ManagedOutcomeAcceptance(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.database = self.root / "memory.db"
        self.store = DrawerStore(self.database, HashEmbeddingProvider(32))
        self.addCleanup(self.store.close)
        self.session = str(uuid4())
        self.marker = self.root / "effect.txt"
        self.original = "  Keep this café request\r\nOutstanding until explicit completion.  "
        self.config = {
            "schema": "cairntir.managed-config.v1",
            "wing": "outcomes",
            "room": "requests",
            "project_root": str(self.root),
            "brief_budget_chars": 16384,
            "profiles": {
                "check": {
                    "argv": [sys.executable, "-c", "raise SystemExit(0)"],
                    "cwd": str(self.root),
                    "timeout_seconds": 10,
                    "output_limit_bytes": 4096,
                }
            },
        }

    def ready(self, body="", *, timeout=10, limit=4096, store=None):
        code = (
            "from pathlib import Path; import os,time; "
            f"p=Path({str(self.marker)!r}); "
            "f=p.open('ab'); f.write(b'launched\\n'); f.flush(); os.fsync(f.fileno()); f.close(); "
            + body
        )
        profile = self.config["profiles"]["check"]
        profile.update(
            argv=[sys.executable, "-c", code],
            timeout_seconds=timeout,
            output_limit_bytes=limit,
        )
        runtime = ManagedRuntime(store or self.store, config=deepcopy(self.config))
        first = runtime.start(self.session)
        event = {
            "schema": "cairntir.managed-event.v1",
            "event_id": str(uuid4()),
            "session_id": self.session,
            "sequence": 1,
            "task_id": None,
            "expected_revision": 0,
            "content": self.original,
        }
        receipt = runtime.capture(event)
        brief = runtime.brief()
        ack = runtime.acknowledge(
            {
                "schema": "cairntir.managed-ack.v1",
                "brief_id": brief["brief_id"],
                "brief_sha256": brief["brief_sha256"],
            }
        )
        action = {
            "schema": "cairntir.managed-action.v1",
            "action_id": str(uuid4()),
            "ack_id": ack["ack_id"],
            "profile": "check",
            "claim": "  Execute one configured check\r\n",
            "predicted_outcome": "The process exits zero and its output is observable.",
            "event_ids": [receipt["event_id"]],
        }
        return runtime, receipt, action, first

    def state(self):
        return "\n".join(self.store._conn.iterdump())

    def reject_without_launch_or_write(self, operation):
        before = self.state()
        with patch("subprocess.Popen", side_effect=AssertionError("forbidden launch")) as launch:
            with self.assertRaises(ManagedRuntimeError):
                operation()
            launch.assert_not_called()
        self.assertEqual(self.state(), before)

    def assert_request_still_owed(self, receipt):
        resumed = json.loads(TaskBook(self.store).resume("outcomes", receipt["task_id"], 262144))
        self.assertEqual(resumed["checkpoint"]["original_request"], self.original)
        self.assertEqual(resumed["checkpoint"]["completed"], [])
        self.assertIn(self.original, resumed["checkpoint"]["outstanding"])
        original = self.store._conn.execute(
            "SELECT content FROM drawers WHERE id=?", (receipt["drawer_id"],)
        ).fetchone()[0]
        self.assertEqual(original, self.original)

    def assert_replay_no_effect(self, runtime, action, expected):
        before = self.state()
        with patch("subprocess.Popen", side_effect=AssertionError("duplicate launch")) as launch:
            replay = runtime.dispatch(action)
            launch.assert_not_called()
        self.assertEqual(replay, {**expected, "replayed": True})
        self.assertEqual(self.marker.read_bytes(), b"launched\n")
        self.assertEqual(self.state(), before)

    def test_invalid_configuration_never_writes_or_launches(self):
        variants = []
        for field, value in (
            ("schema", "unsupported"),
            ("project_root", "relative-root"),
            ("project_root", str(self.root / "absent")),
            ("profiles", {}),
            ("profiles", []),
            ("brief_budget_chars", True),
            ("brief_budget_chars", 1023),
        ):
            variants.append({**deepcopy(self.config), field: value})
        for field, value in (
            ("argv", [sys.executable, "bad\x00argument"]),
            ("argv", [sys.executable, 7]),
            ("timeout_seconds", True),
            ("timeout_seconds", 0),
            ("output_limit_bytes", 0),
            ("cwd", str(self.root.parent)),
        ):
            changed = deepcopy(self.config)
            changed["profiles"]["check"][field] = value
            variants.append(changed)
        for config in variants:
            with self.subTest(config=config):
                self.reject_without_launch_or_write(
                    lambda: ManagedRuntime(self.store, config=config)
                )
        self.assertEqual(
            ManagedRuntime(self.store, config=self.config).start(self.session)["status"], "none"
        )

    def test_invalid_actions_and_missing_ack_have_no_durable_effect(self):
        runtime, _, action, _ = self.ready()
        for field, value in (
            ("schema", "unsupported"),
            ("action_id", str(uuid4()).upper()),
            ("profile", "unconfigured"),
            ("event_ids", []),
            ("event_ids", "not-a-list"),
            ("event_ids", [action["event_ids"][0]] * 2),
            ("event_ids", [str(uuid4())]),
            ("ack_id", str(uuid4())),
        ):
            with self.subTest(field=field, value=value):
                changed = {**action, field: value}
                self.reject_without_launch_or_write(lambda: runtime.dispatch(changed))
        result = runtime.dispatch(action)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(self.marker.read_bytes(), b"launched\n")

    def test_protocol_errors_and_unknown_status_do_not_change_state(self):
        runtime, _, action, _ = self.ready()
        self.reject_without_launch_or_write(lambda: runtime.start(self.session))
        self.reject_without_launch_or_write(lambda: runtime.status(str(uuid4())))
        for command in (
            {"schema": "cairntir.managed-command.v1", "operation": "brief", "request": []},
            {"schema": "cairntir.managed-command.v1", "operation": "unknown", "request": {}},
            {"schema": "cairntir.managed-command.v1", "operation": "status", "request": {}},
        ):
            with self.subTest(command=command):
                self.reject_without_launch_or_write(lambda: stream_command(runtime, command))
        completed = runtime.dispatch(action)
        report = stream_command(
            runtime,
            {
                "schema": "cairntir.managed-command.v1",
                "operation": "status",
                "request": {"action_id": action["action_id"]},
            },
        )
        self.assertEqual(report, {**completed, "replayed": True})

    def test_nonzero_child_is_failed_without_completing_the_request(self):
        runtime, receipt, action, _ = self.ready(
            "os.write(1,b'exact stdout\\r\\n'); os.write(2,b'exact stderr\\n'); raise SystemExit(7)"
        )
        result = runtime.dispatch(action)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["exit_code"], 7)
        self.assertEqual(result["stdout"], "exact stdout\r\n")
        self.assertEqual(result["stderr"], "exact stderr\n")
        self.assertIs(result["timed_out"], False)
        self.assertIs(result["output_truncated"], False)
        self.assert_request_still_owed(receipt)
        self.assert_replay_no_effect(runtime, action, result)

    def test_timeout_retains_uncertainty_and_blocks_another_action(self):
        runtime, receipt, action, _ = self.ready("time.sleep(3)", timeout=1)
        result = runtime.dispatch(action)
        self.assertEqual(result["status"], "uncertain")
        self.assertIsNone(result["outcome_drawer_id"])
        self.assertIsNone(result["exit_code"])
        self.assertIs(result["timed_out"], True)
        self.assertIs(result["output_truncated"], False)
        self.assert_request_still_owed(receipt)
        self.assert_replay_no_effect(runtime, action, result)
        changed = {**action, "action_id": str(uuid4())}
        self.reject_without_launch_or_write(lambda: runtime.dispatch(changed))

    def test_output_cap_is_bounded_uncertain_and_never_relaunched(self):
        runtime, receipt, action, _ = self.ready("os.write(1,b'x'*8192)", limit=128)
        result = runtime.dispatch(action)
        self.assertEqual(result["status"], "uncertain")
        self.assertIs(result["output_truncated"], True)
        self.assertIsNone(result["outcome_drawer_id"])
        self.assertIsNone(result["exit_code"])
        self.assertEqual(result["stdout"], "x" * 128)
        self.assertEqual(result["stderr"], "")
        self.assert_request_still_owed(receipt)
        self.assert_replay_no_effect(runtime, action, result)

    def test_observation_read_error_is_witnessed_and_remains_uncertain(self):
        runtime, receipt, action, _ = self.ready()
        popen = subprocess.Popen
        failures = []

        class BrokenRead:
            def __init__(self, pipe):
                self.pipe = pipe

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.pipe.close()

            def read1(self, size):
                failures.append(size)
                raise OSError("independent output observation failure")

        def inject(*args, **kwargs):
            child = popen(*args, **kwargs)
            child.stdout = BrokenRead(child.stdout)
            return child

        with patch("subprocess.Popen", side_effect=inject):
            result = runtime.dispatch(action)
        self.assertEqual(len(failures), 1)
        self.assertEqual(result["status"], "uncertain")
        self.assertIsNone(result["outcome_drawer_id"])
        self.assertIsNone(result["exit_code"])
        self.assertIs(result["timed_out"], False)
        self.assertIs(result["output_truncated"], False)
        self.assert_request_still_owed(receipt)
        self.assert_replay_no_effect(runtime, action, result)

    def test_changed_raw_event_cannot_authorize_dispatch(self):
        runtime, receipt, action, _ = self.ready()
        self.store._conn.execute(
            "UPDATE drawers SET content=? WHERE id=?", ("Corrupted source", receipt["drawer_id"])
        )
        self.store._conn.commit()
        self.reject_without_launch_or_write(lambda: runtime.dispatch(action))
        self.assertFalse(self.marker.exists())

    def test_ack_requires_its_brief_in_the_committed_registry(self):
        runtime, _, _, _ = self.ready()
        brief = runtime.brief()
        matches = []
        for key, raw in self.store._conn.execute(
            "SELECT idempotency_key,result FROM workflow_runs WHERE operation='managed.brief.v1'"
        ):
            if json.loads(raw)["brief_id"] == brief["brief_id"]:
                matches.append(key)
        self.assertEqual(len(matches), 1)
        self.store._conn.execute("DELETE FROM workflow_runs WHERE idempotency_key=?", (matches[0],))
        self.store._conn.commit()
        self.reject_without_launch_or_write(
            lambda: runtime.acknowledge(
                {
                    "schema": "cairntir.managed-ack.v1",
                    "brief_id": brief["brief_id"],
                    "brief_sha256": brief["brief_sha256"],
                }
            )
        )

    def test_completed_action_rejects_profile_rebinding_after_restart(self):
        runtime, receipt, action, _ = self.ready()
        self.assertEqual(runtime.dispatch(action)["status"], "completed")
        changed = deepcopy(self.config)
        changed["profiles"]["check"]["output_limit_bytes"] = 2048
        restarted = ManagedRuntime(self.store, config=changed)
        restarted.start(self.session, task_id=receipt["task_id"])
        self.reject_without_launch_or_write(lambda: restarted.dispatch(action))
        self.assertEqual(self.marker.read_bytes(), b"launched\n")

    def test_revoked_grant_cannot_read_completed_result_or_replay(self):
        token = issue_grant(
            self.store, scopes=[{"wing": "outcomes"}], capabilities=["read", "write"]
        )
        scoped = bind_grant(self.store, token)
        runtime, _, action, _ = self.ready(store=scoped)
        result = runtime.dispatch(action)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(runtime.status(action["action_id"])["action_id"], action["action_id"])
        revoke_grant(self.store, token)
        self.reject_without_launch_or_write(lambda: runtime.status(action["action_id"]))
        self.reject_without_launch_or_write(lambda: runtime.dispatch(action))
        self.assertEqual(self.marker.read_bytes(), b"launched\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
