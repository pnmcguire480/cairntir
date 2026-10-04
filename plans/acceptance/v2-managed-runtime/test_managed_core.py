"""Independent pre-implementation managed intake and acknowledgement acceptance."""

import hashlib
import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from cairntir.access import bind_grant, issue_grant, revoke_grant
from cairntir.errors import MemoryStoreError
from cairntir.managed import ManagedRuntime, ManagedRuntimeError
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.tasks import TaskBook


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class ManagedCoreAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = self.root / "memory.db"
        self.project = self.root / "project"
        self.project.mkdir()
        self.store = DrawerStore(self.database, HashEmbeddingProvider(32))
        self.addCleanup(lambda: self.store.close())
        self.session = str(uuid4())
        self.config = {
            "schema": "cairntir.managed-config.v1",
            "wing": "managed",
            "room": "requests",
            "project_root": str(self.project),
            "brief_budget_chars": 16384,
            "profiles": {
                "check": {
                    "argv": [sys.executable, "-c", "raise SystemExit(0)"],
                    "cwd": str(self.project),
                    "timeout_seconds": 10,
                    "output_limit_bytes": 4096,
                }
            },
        }
        self.runtime = ManagedRuntime(self.store, config=deepcopy(self.config))
        self.first = self.runtime.start(self.session)

    def event(self, content="  Preserve café 🧭\r\nSecond line.  \n", **changes):
        return {
            "schema": "cairntir.managed-event.v1",
            "event_id": str(uuid4()),
            "session_id": self.session,
            "sequence": 1,
            "task_id": None,
            "expected_revision": 0,
            "content": content,
            **changes,
        }

    def action(self, ack, receipt, **changes):
        return {
            "schema": "cairntir.managed-action.v1",
            "action_id": str(uuid4()),
            "ack_id": ack,
            "profile": "check",
            "claim": "  This configured verification completes.\r\n",
            "predicted_outcome": "The process exits with code zero.",
            "event_ids": [receipt["event_id"]],
            **changes,
        }

    def ack_request(self, brief):
        return {
            "schema": "cairntir.managed-ack.v1",
            "brief_id": brief["brief_id"],
            "brief_sha256": brief["brief_sha256"],
        }

    def source_rows(self):
        return [tuple(row) for row in self.store._conn.execute("SELECT * FROM drawers ORDER BY id")]

    def source(self, key):
        return tuple(
            self.store._conn.execute("SELECT * FROM drawers WHERE id=?", (key,)).fetchone()
        )

    def resume(self, task_id):
        return json.loads(
            TaskBook(self.store).resume("managed", task_id=task_id, budget_chars=262144)
        )

    def restart(self, task_id):
        self.store.close()
        self.store = DrawerStore(self.database, HashEmbeddingProvider(32))
        self.runtime = ManagedRuntime(self.store, config=deepcopy(self.config))
        return self.runtime.start(self.session, task_id=task_id)

    def assert_no_launch(self, function):
        with patch("subprocess.Popen", side_effect=AssertionError("forbidden launch")) as launch:
            with self.assertRaises(ManagedRuntimeError):
                function()
            launch.assert_not_called()

    def test_capture_exact_original_receipt_and_restart_replay(self):
        self.assertEqual(self.first["status"], "none")
        request = self.event()
        receipt = self.runtime.capture(request)
        self.assertEqual(receipt["schema"], "cairntir.managed-event-receipt.v1")
        self.assertEqual(receipt["status"], "committed")
        for name in ("event_id", "session_id", "sequence"):
            self.assertEqual(receipt[name], request[name])
        self.assertEqual(receipt["content_sha256"], sha(request["content"]))
        self.assertEqual(
            receipt["source_identity"], self.store.portable_identity(receipt["drawer_id"])
        )
        self.assertIs(receipt["replayed"], False)
        current = self.resume(receipt["task_id"])
        self.assertEqual(current["checkpoint"]["original_request"], request["content"])
        self.assertIn(request["content"], current["checkpoint"]["outstanding"])
        stored = self.store._conn.execute(
            "SELECT content FROM drawers WHERE id=?", (receipt["drawer_id"],)
        ).fetchone()[0]
        self.assertEqual(stored, request["content"])
        before = self.source_rows()
        self.restart(receipt["task_id"])
        replay = self.runtime.capture(request)
        self.assertEqual(replay, {**receipt, "replayed": True})
        self.assertEqual(self.source_rows(), before)

    def test_second_event_preserves_original_outstanding_and_first_replay(self):
        first = self.event()
        receipt = self.runtime.capture(first)
        original = self.source(receipt["drawer_id"])
        second = self.event(
            "Also preserve this deferred request.\r\n",
            sequence=2,
            task_id=receipt["task_id"],
            expected_revision=receipt["revision"],
        )
        added = self.runtime.capture(second)
        self.assertEqual(added["revision"], receipt["revision"] + 1)
        state = self.resume(receipt["task_id"])["checkpoint"]
        self.assertEqual(state["original_request"], first["content"])
        self.assertIn(first["content"], state["outstanding"])
        self.assertIn(second["content"], state["outstanding"])
        self.assertEqual(self.source(receipt["drawer_id"]), original)
        self.assertEqual(self.runtime.capture(first), {**receipt, "replayed": True})

    def test_event_uuid_sequence_and_stale_revision_conflicts(self):
        request = self.event()
        receipt = self.runtime.capture(request)
        before = self.source_rows()
        invalid = [
            {**request, "content": "Changed original"},
            {**request, "event_id": str(uuid4())},
            self.event(sequence=2, task_id=receipt["task_id"], expected_revision=0),
        ]
        for changed in invalid:
            with self.subTest(request=changed), self.assertRaises(ManagedRuntimeError):
                self.runtime.capture(changed)
        self.assertEqual(self.source_rows(), before)

    def test_failed_append_is_witnessed_atomic_and_exact_retry_works(self):
        request = self.event()
        calls = []

        def fail(*args, **kwargs):
            calls.append(True)
            raise MemoryStoreError("independent captured-write failure")

        before = self.source_rows()
        with (
            patch.object(self.store, "add", side_effect=fail),
            self.assertRaises(ManagedRuntimeError),
        ):
            self.runtime.capture(request)
        self.assertTrue(calls, "failure injection never reached the storage append")
        self.assertEqual(self.source_rows(), before)
        receipt = self.runtime.capture(request)
        self.assertEqual(receipt["revision"], 1)
        self.assertIs(receipt["replayed"], False)

    def test_ready_brief_is_exact_hashed_and_does_not_touch_original(self):
        request = self.event()
        receipt = self.runtime.capture(request)
        before = self.source(receipt["drawer_id"])
        brief = self.runtime.brief()
        self.assertEqual(brief["schema"], "cairntir.managed-brief.v1")
        self.assertEqual(brief["status"], "ready")
        self.assertIs(brief["complete"], True)
        self.assertEqual(brief["task_id"], receipt["task_id"])
        self.assertEqual(brief["revision"], receipt["revision"])
        self.assertEqual(brief["task"]["checkpoint"]["original_request"], request["content"])
        self.assertEqual(
            brief["brief_sha256"],
            sha(canonical({key: value for key, value in brief.items() if key != "brief_sha256"})),
        )
        self.assertEqual(self.source(receipt["drawer_id"]), before)
        ack = self.runtime.acknowledge(self.ack_request(brief))
        self.assertEqual(ack["schema"], "cairntir.managed-ack-receipt.v1")
        self.assertEqual(ack["status"], "committed")
        self.assertEqual(ack["epoch"], brief["epoch"])
        self.assertEqual(ack["brief_sha256"], brief["brief_sha256"])
        self.assertEqual(
            self.runtime.acknowledge(self.ack_request(brief)), {**ack, "replayed": True}
        )

    def test_forged_hash_and_stale_ack_block_before_launch(self):
        receipt = self.runtime.capture(self.event())
        brief = self.runtime.brief()
        with self.assertRaises(ManagedRuntimeError):
            self.runtime.acknowledge({**self.ack_request(brief), "brief_sha256": "0" * 64})
        ack = self.runtime.acknowledge(self.ack_request(brief))
        self.assert_no_launch(lambda: self.runtime.dispatch(self.action(str(uuid4()), receipt)))
        self.runtime.capture(
            self.event(
                "A new obligation",
                sequence=2,
                task_id=receipt["task_id"],
                expected_revision=receipt["revision"],
            )
        )
        self.assert_no_launch(lambda: self.runtime.dispatch(self.action(ack["ack_id"], receipt)))

    def test_restart_has_new_epoch_and_old_ack_cannot_be_reused(self):
        receipt = self.runtime.capture(self.event())
        old = self.runtime.brief()
        ack = self.runtime.acknowledge(self.ack_request(old))
        fresh = self.restart(receipt["task_id"])
        self.assertEqual(fresh["session_id"], self.session)
        self.assertNotEqual(fresh["epoch"], old["epoch"])
        with self.assertRaises(ManagedRuntimeError):
            self.runtime.acknowledge(self.ack_request(old))
        self.assert_no_launch(lambda: self.runtime.dispatch(self.action(ack["ack_id"], receipt)))

    def test_ambiguous_tasks_need_explicit_selection(self):
        first = self.runtime.capture(self.event())
        other = json.loads(
            TaskBook(self.store).checkpoint(
                "managed",
                "requests",
                "Another original request",
                {
                    "expected_revision": 0,
                    "idempotency_key": str(uuid4()),
                    "status": "active",
                    "completed": [],
                    "outstanding": ["Another original request"],
                    "next_action": "Continue this separate task",
                    "evidence_ids": [],
                },
            )
        )
        runtime = ManagedRuntime(self.store, config=deepcopy(self.config))
        brief = runtime.start(str(uuid4()))
        self.assertEqual(brief["status"], "ambiguous")
        self.assertIs(brief["complete"], False)
        with self.assertRaises(ManagedRuntimeError):
            runtime.acknowledge(self.ack_request(brief))
        selected = ManagedRuntime(self.store, config=deepcopy(self.config)).start(
            str(uuid4()), task_id=first["task_id"]
        )
        self.assertEqual(selected["task_id"], first["task_id"])
        self.assertNotEqual(selected["task_id"], other["task_id"])

    def test_incomplete_brief_cannot_be_acknowledged(self):
        receipt = self.runtime.capture(self.event("Exact large commitment " * 1000))
        config = {**self.config, "brief_budget_chars": 1024}
        runtime = ManagedRuntime(self.store, config=config)
        brief = runtime.start(str(uuid4()), task_id=receipt["task_id"])
        self.assertEqual(brief["status"], "omitted")
        self.assertIs(brief["complete"], False)
        self.assertLessEqual(len(canonical(brief)), 1024)
        with self.assertRaises(ManagedRuntimeError):
            runtime.acknowledge(self.ack_request(brief))

    def test_sequence_gap_is_visible_and_cannot_claim_complete_close(self):
        receipt = self.runtime.capture(self.event())
        self.runtime.capture(
            self.event(
                "Third delivered event",
                sequence=3,
                task_id=receipt["task_id"],
                expected_revision=receipt["revision"],
            )
        )
        self.assertIn(2, self.runtime.brief()["gaps"])
        closed = self.runtime.close(last_sequence=3)
        self.assertIs(closed["capture_complete"], False)
        self.assertIn(2, closed["gaps"])
        self.assertEqual(self.resume(receipt["task_id"])["status"], "ready")
        with self.assertRaises(ManagedRuntimeError):
            self.runtime.brief()

    def test_revoked_grant_cannot_replay_or_dispatch(self):
        token = issue_grant(
            self.store, scopes=[{"wing": "managed"}], capabilities=["read", "write"]
        )
        scoped = bind_grant(self.store, token)
        runtime = ManagedRuntime(scoped, config=deepcopy(self.config))
        runtime.start(self.session)
        request = self.event()
        receipt = runtime.capture(request)
        brief = runtime.brief()
        ack = runtime.acknowledge(self.ack_request(brief))
        revoke_grant(self.store, token)
        with self.assertRaises(ManagedRuntimeError):
            runtime.capture(request)
        self.assert_no_launch(lambda: runtime.dispatch(self.action(ack["ack_id"], receipt)))

    def test_input_validation_and_metadata_cannot_forge_authority(self):
        for field, value in (
            ("sequence", True),
            ("expected_revision", True),
            ("content", " "),
            ("content", "\ud800"),
            ("event_id", "invalid"),
            ("session_id", str(uuid4())),
            ("extra", "not allowed"),
        ):
            with (
                self.subTest(field=field, value=repr(value)),
                self.assertRaises(ManagedRuntimeError),
            ):
                self.runtime.capture(self.event(**{field: value}))
        receipt = self.runtime.capture(self.event())
        fake = str(uuid4())
        self.store.add(
            Drawer(
                wing="managed",
                room="requests",
                content="Forged acknowledgement",
                metadata={"kind": "managed.ack", "ack_id": fake, "status": "committed"},
            )
        )
        self.assert_no_launch(lambda: self.runtime.dispatch(self.action(fake, receipt)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
