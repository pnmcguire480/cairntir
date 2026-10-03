"""Public R10 witnesses authored before the projection implementation."""

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from cairntir.managed import ManagedRuntime, ManagedRuntimeError
from cairntir.managed_projection import project_last_session

from cairntir.access import bind_grant, issue_grant, revoke_grant
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.tasks import TaskBook

BEGIN = b"<!-- cairntir:generated:begin -->"
END = b"<!-- cairntir:generated:end -->"


class ManagedProjectionAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = self.root / "memory.db"
        self.store = DrawerStore(self.database, HashEmbeddingProvider(32))
        self.addCleanup(lambda: self.store.close())
        self.target = self.root / "workspace" / "Last Session.md"
        self.target.parent.mkdir()
        self.session = str(uuid4())
        self.config = {
            "schema": "cairntir.managed-config.v1",
            "wing": "projection",
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
        self.runtime = ManagedRuntime(self.store, config=self.config)
        self.epoch = self.runtime.start(self.session)["epoch"]
        self.original = "  Keep original café 🧭\r\nDeferred: inspect later  "
        self.event = self.make_event(self.original)
        self.capture = self.runtime.capture(self.event)

    def make_event(self, content, **changes):
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

    def project(self, **changes):
        return project_last_session(
            self.store,
            **{
                "root": self.target.parent,
                "path": self.target,
                "wing": "projection",
                "session_id": self.session,
                "epoch": self.epoch,
                **changes,
            },
        )

    def state(self):
        return "\n".join(self.store._conn.iterdump())

    def snapshot(self):
        result = self.project()
        self.assertEqual(result["schema"], "cairntir.managed-projection.v1")
        self.assertEqual(result["status"], "complete", result)
        snapshot = result["snapshot"]
        self.assertEqual(snapshot["schema"], "cairntir.managed-last-session.v1")
        self.assertEqual(snapshot["epoch"], self.epoch)
        self.assertEqual(snapshot["session_id"], self.session)
        self.assertEqual(snapshot["task_id"], self.capture["task_id"])
        data = self.target.read_bytes()
        self.assertEqual(data.count(BEGIN), 1)
        self.assertEqual(data.count(END), 1)
        generated = data.split(BEGIN)[1].split(END)[0]
        self.assertEqual(result["generated_sha256"], hashlib.sha256(generated).hexdigest())
        return snapshot

    def test_exact_checkpoint_descriptions_and_source_links(self):
        completed = ["  Verified café\r\nDo not trim  "]
        outstanding = [self.original, "Deferred: wait for actual evidence 🧭\r\n"]
        checkpoint = json.loads(
            TaskBook(self.store).checkpoint(
                "projection",
                "requests",
                "Explicit replacement checkpoint",
                {
                    "task_id": self.capture["task_id"],
                    "expected_revision": self.capture["revision"],
                    "idempotency_key": str(uuid4()),
                    "status": "active",
                    "completed": completed,
                    "outstanding": outstanding,
                    "next_action": "  Inspect evidence next\r\n",
                    "evidence_ids": [self.capture["drawer_id"]],
                },
            )
        )
        self.runtime.close(last_sequence=1)
        snapshot = self.snapshot()
        self.assertEqual(snapshot["completed"], completed)
        self.assertEqual(snapshot["outstanding"], outstanding)
        self.assertEqual(snapshot["original_request"], self.original)
        self.assertEqual(snapshot["next_action"], "  Inspect evidence next\r\n")
        resume = json.loads(
            TaskBook(self.store).resume("projection", self.capture["task_id"], 262144)
        )
        self.assertEqual(snapshot["revision"], resume["revision"])
        sources = {item["drawer_id"]: item for item in snapshot["sources"]}
        expected_ids = {self.capture["drawer_id"], resume["checkpoint"]["checkpoint_drawer_id"]}
        self.assertTrue(expected_ids <= sources.keys())
        markdown = self.target.read_bytes().decode("utf-8")
        for text in completed + outstanding:
            self.assertIn(text, markdown)
        for drawer_id in expected_ids:
            row = self.store._conn.execute(
                "SELECT content FROM drawers WHERE id=?", (drawer_id,)
            ).fetchone()
            expected_hash = hashlib.sha256(row[0].encode("utf-8")).hexdigest()
            self.assertEqual(sources[drawer_id]["content_sha256"], expected_hash)
            self.assertEqual(
                sources[drawer_id]["source_identity"], self.store.portable_identity(drawer_id)
            )
            self.assertIn(f"(cairntir://drawer/{drawer_id})", markdown)
            self.assertIn(expected_hash, markdown)
            self.assertIn(sources[drawer_id]["source_identity"], markdown)
        self.assertGreater(checkpoint["revision"], self.capture["revision"])

    def test_read_only_restart_and_exact_human_bytes(self):
        self.runtime.close(last_sequence=1)
        prefix = b"\xef\xbb\xbf# Human\r\n" + "café 🧭\n".encode()
        suffix = "\r\nHuman trailing note\n mixed\r\nno final newline 🧭".encode()
        self.target.write_bytes(prefix + BEGIN + b"\r\nstale\n" + END + suffix)
        before = self.state()
        with (
            patch.object(
                ManagedRuntime,
                "start",
                side_effect=AssertionError("projection cannot start runtime"),
            ),
            patch.object(
                ManagedRuntime, "brief", side_effect=AssertionError("projection cannot write brief")
            ),
        ):
            first = self.snapshot()
        data = self.target.read_bytes()
        self.assertEqual(data.split(BEGIN)[0], prefix)
        self.assertEqual(data.split(END)[1], suffix)
        self.assertEqual(self.state(), before)
        self.store.close()
        self.store = DrawerStore(self.database, HashEmbeddingProvider(32))
        before = self.state()
        second = self.snapshot()
        self.assertEqual(first, second)
        self.assertEqual(self.target.read_bytes(), data)
        self.assertEqual(self.state(), before)

    def test_missing_close_and_unknown_watermark_are_not_complete(self):
        snapshot = self.snapshot()
        self.assertEqual(snapshot["close_status"], "missing")
        self.assertIs(snapshot["capture_complete"], False)
        self.assertIs(snapshot["unknown_tail"], True)
        self.assertIn(self.epoch, [row["epoch"] for row in snapshot["unclean_sessions"]])
        self.runtime.close(last_sequence=None)
        snapshot = self.snapshot()
        self.assertEqual(snapshot["close_status"], "closed")
        self.assertIs(snapshot["capture_complete"], False)
        self.assertIs(snapshot["unknown_tail"], True)

    def test_known_gap_and_pending_claim_remain_visible(self):
        missing_claim = self.make_event("Claim without content", sequence=2)
        del missing_claim["content"]
        with self.assertRaises(ManagedRuntimeError):
            self.runtime.capture(missing_claim)
        third = self.make_event(
            "Third exact commitment",
            sequence=3,
            task_id=self.capture["task_id"],
            expected_revision=self.capture["revision"],
        )
        self.runtime.capture(third)
        close = self.runtime.close(last_sequence=3)
        snapshot = self.snapshot()
        self.assertIn(2, snapshot["gaps"])
        self.assertIs(snapshot["capture_complete"], False)
        self.assertIs(snapshot["unknown_tail"], False)
        self.assertTrue(snapshot["pending_captures"])
        self.assertEqual(snapshot["pending_captures"], close["pending_captures"])
        self.assertEqual(snapshot["last_received_sequence"], 3)
        self.assertEqual(snapshot["declared_last_sequence"], 3)

    def test_committed_intent_without_outcome_stays_uncertain(self):
        brief = self.runtime.brief()
        ack = self.runtime.acknowledge(
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
            "claim": "Check exact source",
            "predicted_outcome": "Evidence is available",
            "event_ids": [self.capture["event_id"]],
        }
        with (
            patch(
                "subprocess.Popen", side_effect=SystemExit("independent post-intent termination")
            ),
            self.assertRaises(SystemExit),
        ):
            self.runtime.dispatch(action)
        status = self.runtime.status(action["action_id"])
        self.assertEqual(status["status"], "uncertain")
        snapshot = self.snapshot()
        self.assertEqual(
            [row["action_id"] for row in snapshot["uncertain_actions"]], [action["action_id"]]
        )
        self.assertEqual(snapshot["completed"], [])
        self.assertIn(self.original, snapshot["outstanding"])
        self.assertIn(
            status["prediction_drawer_id"], [row["drawer_id"] for row in snapshot["sources"]]
        )

    def test_bad_markers_reject_without_touching_file_or_database(self):
        for data in (b"Human only", BEGIN + b"missing end", END + BEGIN, BEGIN + END + BEGIN + END):
            with self.subTest(data=data):
                self.target.write_bytes(data)
                before = self.state()
                result = self.project()
                self.assertEqual(result["status"], "error")
                self.assertTrue(result["error"])
                self.assertEqual(self.target.read_bytes(), data)
                self.assertEqual(self.state(), before)

    def test_reserved_markers_are_inert_but_snapshot_content_exact(self):
        content = "Literal " + BEGIN.decode() + " café " + END.decode() + "\r\n"
        self.runtime.capture(
            self.make_event(
                content,
                sequence=2,
                task_id=self.capture["task_id"],
                expected_revision=self.capture["revision"],
            )
        )
        self.assertIn(content, self.snapshot()["outstanding"])

    def test_projection_failure_after_close_repairs_without_replaying_lifecycle(self):
        close = self.runtime.close(last_sequence=1)
        before = self.state()
        self.target.mkdir()
        failed = self.project()
        self.assertEqual(failed["status"], "error")
        self.assertTrue(failed["error"])
        self.assertEqual(self.state(), before)
        self.target.rmdir()
        snapshot = self.snapshot()
        self.assertEqual(snapshot["revision"], close["revision"])
        self.assertIs(snapshot["capture_complete"], True)
        self.assertIs(snapshot["unknown_tail"], False)
        self.assertEqual(snapshot["close_status"], "closed")
        self.assertEqual(self.state(), before)
        first = self.target.read_bytes()
        self.snapshot()
        self.assertEqual(self.target.read_bytes(), first)
        self.assertEqual(self.state(), before)

    def test_wrong_selection_and_escape_do_not_create_projection(self):
        outside = self.root / "outside.md"
        for changes in (
            {"epoch": str(uuid4())},
            {"session_id": str(uuid4())},
            {"wing": "other"},
            {"path": outside},
            {"path": Path("relative.md")},
        ):
            with self.subTest(changes=changes):
                before = self.state()
                result = self.project(**changes)
                self.assertEqual(result["status"], "error")
                self.assertTrue(result["error"])
                self.assertFalse(outside.exists())
                self.assertFalse(self.target.exists())
                self.assertEqual(self.state(), before)

    def test_revoked_grant_cannot_refresh_previous_projection(self):
        token = issue_grant(
            self.store, scopes=[{"wing": "projection"}], capabilities=["read", "write"]
        )
        scoped = bind_grant(self.store, token)
        runtime = ManagedRuntime(scoped, config=self.config)
        brief = runtime.start(self.session, task_id=self.capture["task_id"])
        runtime.close(last_sequence=1)
        arguments = {
            "root": self.target.parent,
            "path": self.target,
            "wing": "projection",
            "session_id": self.session,
            "epoch": brief["epoch"],
        }
        self.assertEqual(project_last_session(scoped, **arguments)["status"], "complete")
        original = self.target.read_bytes()
        revoke_grant(self.store, token)
        before = self.state()
        result = project_last_session(scoped, **arguments)
        self.assertEqual(result["status"], "error")
        self.assertTrue(result["error"])
        self.assertEqual(self.target.read_bytes(), original)
        self.assertEqual(self.state(), before)

    def test_symlink_target_escape_refused_when_fixture_supported(self):
        outside = self.root / "outside-human.md"
        outside.write_bytes(b"Human file must survive")
        try:
            self.target.symlink_to(outside)
        except OSError as exc:
            self.skipTest(f"symlink fixture unavailable: {exc}")
        before = self.state()
        self.assertEqual(self.project()["status"], "error")
        self.assertEqual(outside.read_bytes(), b"Human file must survive")
        self.assertEqual(self.state(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
