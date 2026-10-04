"""Additional independent source/receipt consistency witnesses."""

import json
import unittest
from uuid import uuid4

from cairntir.tasks import TaskBook

from test_managed_projection import ManagedProjectionAcceptance as Fixture


class ProjectionCorruptionAcceptance(unittest.TestCase):
    setUp = Fixture.setUp
    make_event = Fixture.make_event
    project = Fixture.project
    state = Fixture.state
    snapshot = Fixture.snapshot

    def assert_refused(self, prior):
        before = self.state()
        result = self.project()
        self.assertEqual(result["status"], "error", result)
        self.assertTrue(result["error"])
        self.assertEqual(self.target.read_bytes(), prior)
        self.assertEqual(self.state(), before)

    def test_changed_captured_content_is_not_recertified_with_new_hash(self):
        self.snapshot()
        prior = self.target.read_bytes()
        self.store._conn.execute(
            "UPDATE drawers SET content=? WHERE id=?",
            ("Changed stored source", self.capture["drawer_id"]),
        )
        self.store._conn.commit()
        self.assert_refused(prior)

    def test_missing_required_source_does_not_replace_existing_view(self):
        self.snapshot()
        prior = self.target.read_bytes()
        self.store._conn.execute("PRAGMA foreign_keys=OFF")
        self.store._conn.execute("DELETE FROM drawers WHERE id=?", (self.capture["drawer_id"],))
        self.store._conn.commit()
        self.assert_refused(prior)

    def test_checkpoint_metadata_disagreement_does_not_certify_completion(self):
        checkpoint = json.loads(
            TaskBook(self.store).checkpoint(
                "projection",
                "requests",
                "Dedicated task checkpoint",
                {
                    "task_id": self.capture["task_id"],
                    "expected_revision": self.capture["revision"],
                    "idempotency_key": str(uuid4()),
                    "status": "active",
                    "completed": ["Accepted recorded completion"],
                    "outstanding": [self.original],
                    "next_action": "Retain original",
                    "evidence_ids": [self.capture["drawer_id"]],
                },
            )
        )
        self.snapshot()
        prior = self.target.read_bytes()
        key = checkpoint["checkpoint_drawer_id"]
        raw = self.store._conn.execute(
            "SELECT metadata FROM drawers WHERE id=?", (key,)
        ).fetchone()[0]
        metadata = json.loads(raw)
        metadata["task_checkpoint"]["completed"] = ["Contradictory raw checkpoint state"]
        self.store._conn.execute(
            "UPDATE drawers SET metadata=? WHERE id=?", (json.dumps(metadata), key)
        )
        self.store._conn.commit()
        self.assert_refused(prior)

    def test_close_result_disagreement_cannot_certify_unknown_tail(self):
        self.runtime.close(last_sequence=None)
        self.snapshot()
        prior = self.target.read_bytes()
        row = self.store._conn.execute(
            "SELECT idempotency_key, result FROM workflow_runs WHERE operation='managed.close.v1' AND state='committed'"
        ).fetchone()
        result = json.loads(row["result"])
        self.assertIsNone(result["_managed"]["request"]["request"]["declared_last_sequence"])
        result["declared_last_sequence"] = 1
        result["capture_complete"] = True
        self.store._conn.execute(
            "UPDATE workflow_runs SET result=? WHERE idempotency_key=?",
            (json.dumps(result), row["idempotency_key"]),
        )
        self.store._conn.commit()
        self.assert_refused(prior)


del Fixture

if __name__ == "__main__":
    unittest.main(verbosity=2)
