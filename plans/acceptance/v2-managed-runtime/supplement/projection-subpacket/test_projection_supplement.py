"""Public projection outcomes frozen after the original full-source run."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from cairntir.managed import ManagedRuntime
from cairntir.managed_projection import project_last_session
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.tasks import TaskBook


class ProjectionSupplementAcceptance(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.store = DrawerStore(self.root / "memory.db", HashEmbeddingProvider(32))
        self.addCleanup(self.store.close)
        self.target = self.root / "Last Session.md"
        self.session = str(uuid4())
        self.runtime = ManagedRuntime(
            self.store,
            config={
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
            },
        )
        self.epoch = self.runtime.start(self.session)["epoch"]
        self.original = "Preserve the violet receipt exactly.\r\n"
        self.capture = self.runtime.capture(
            {
                "schema": "cairntir.managed-event.v1",
                "event_id": str(uuid4()),
                "session_id": self.session,
                "sequence": 1,
                "task_id": None,
                "expected_revision": 0,
                "content": self.original,
            }
        )

    def project(self):
        return project_last_session(
            self.store,
            root=self.root,
            path=self.target,
            wing="projection",
            session_id=self.session,
            epoch=self.epoch,
        )

    def state(self):
        return "\n".join(self.store._conn.iterdump())

    def clean_view(self):
        result = self.project()
        self.assertEqual(result["status"], "complete", result)
        return self.target.read_bytes()

    def refused(self, prior):
        before = self.state()
        result = self.project()
        self.assertEqual(result["status"], "error", result)
        self.assertTrue(result["error"])
        self.assertNotIn("snapshot", result)
        self.assertEqual(self.target.read_bytes(), prior)
        self.assertEqual(self.state(), before)

    def action(self):
        brief = self.runtime.brief()
        ack = self.runtime.acknowledge(
            {
                "schema": "cairntir.managed-ack.v1",
                "brief_id": brief["brief_id"],
                "brief_sha256": brief["brief_sha256"],
            }
        )
        result = self.runtime.dispatch(
            {
                "schema": "cairntir.managed-action.v1",
                "action_id": str(uuid4()),
                "ack_id": ack["ack_id"],
                "profile": "check",
                "claim": "The fixed verification command exits successfully.",
                "predicted_outcome": "Exit zero with no output.",
                "event_ids": [self.capture["event_id"]],
            }
        )
        self.assertEqual(result["status"], "completed", result)
        return result

    def test_required_source_current_visibility(self):
        prior = self.clean_view()
        key = self.capture["drawer_id"]
        original = self.store._conn.execute(
            "SELECT provenance FROM drawers WHERE id=?", (key,)
        ).fetchone()[0]
        cases = {
            "secret": {"sensitivity": "secret"},
            "expired": {"valid_until": "2000-01-01T00:00:00+00:00"},
            "future": {"valid_from": "9999-01-01T00:00:00+00:00"},
        }
        for name, changes in cases.items():
            with self.subTest(name=name):
                altered = {**json.loads(original), **changes}
                self.store._conn.execute(
                    "UPDATE drawers SET provenance=? WHERE id=?", (json.dumps(altered), key)
                )
                self.store._conn.commit()
                try:
                    self.refused(prior)
                finally:
                    self.store._conn.execute(
                        "UPDATE drawers SET provenance=? WHERE id=?", (original, key)
                    )
                    self.store._conn.commit()
        self.assertEqual(self.clean_view(), prior)

    def test_raw_action_evidence_cannot_be_recertified(self):
        outcome = self.action()
        prior = self.clean_view()
        cases = [
            (outcome["prediction_drawer_id"], "claim", "A different claim"),
            (outcome["prediction_drawer_id"], "predicted_outcome", "An unrecorded prediction"),
            (outcome["outcome_drawer_id"], "observed_outcome", "A forged observation"),
            (outcome["outcome_drawer_id"], "supersedes_id", self.capture["drawer_id"]),
        ]
        for key, column, value in cases:
            with self.subTest(column=column):
                original = self.store._conn.execute(
                    f"SELECT {column} FROM drawers WHERE id=?", (key,)
                ).fetchone()[0]
                self.store._conn.execute(f"UPDATE drawers SET {column}=? WHERE id=?", (value, key))
                self.store._conn.commit()
                try:
                    self.refused(prior)
                finally:
                    self.store._conn.execute(
                        f"UPDATE drawers SET {column}=? WHERE id=?", (original, key)
                    )
                    self.store._conn.commit()
        self.assertEqual(self.clean_view(), prior)

    def test_public_session_and_ack_cannot_transplant_bound_action(self):
        self.action()
        prior = self.clean_view()
        row = self.store._conn.execute(
            "SELECT idempotency_key, result FROM workflow_runs "
            "WHERE operation='managed.dispatch.v1' AND state='committed'"
        ).fetchone()
        for field in ("epoch", "ack_id"):
            with self.subTest(field=field):
                altered = json.loads(row["result"])
                altered[field] = str(uuid4())
                self.store._conn.execute(
                    "UPDATE workflow_runs SET result=? WHERE idempotency_key=?",
                    (json.dumps(altered), row["idempotency_key"]),
                )
                self.store._conn.commit()
                try:
                    self.refused(prior)
                finally:
                    self.store._conn.execute(
                        "UPDATE workflow_runs SET result=? WHERE idempotency_key=?",
                        (row["result"], row["idempotency_key"]),
                    )
                    self.store._conn.commit()
        self.assertEqual(self.clean_view(), prior)

    def test_checkpoint_advance_during_read_requires_clean_retry(self):
        prior = self.clean_view()
        read = self.store._task_drawers
        after_append = []
        completed = ["Independently recorded violet verification\r\n"]
        outstanding = [self.original, "Still obtain the blue receipt."]

        def advance_once(keys):
            drawers = read(keys)
            if not after_append:
                after_append.append(None)
                TaskBook(self.store).checkpoint(
                    "projection",
                    "requests",
                    "Concurrent explicit checkpoint",
                    {
                        "task_id": self.capture["task_id"],
                        "expected_revision": self.capture["revision"],
                        "idempotency_key": str(uuid4()),
                        "status": "active",
                        "completed": completed,
                        "outstanding": outstanding,
                        "next_action": "Read the blue receipt.",
                        "evidence_ids": [self.capture["drawer_id"]],
                    },
                )
                after_append[0] = self.state()
            return drawers

        with patch.object(self.store, "_task_drawers", side_effect=advance_once):
            rejected = self.project()
        self.assertEqual(rejected["status"], "error", rejected)
        self.assertTrue(rejected["error"])
        self.assertNotIn("snapshot", rejected)
        self.assertEqual(self.target.read_bytes(), prior)
        self.assertEqual(self.state(), after_append[0])
        result = self.project()
        self.assertEqual(result["status"], "complete", result)
        snapshot = result["snapshot"]
        self.assertEqual(snapshot["revision"], self.capture["revision"] + 1)
        self.assertEqual(snapshot["completed"], completed)
        self.assertEqual(snapshot["outstanding"], outstanding)
        self.assertEqual(snapshot["next_action"], "Read the blue receipt.")
        self.assertEqual(snapshot["original_request"], self.original)
        self.assertEqual(self.state(), after_append[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
