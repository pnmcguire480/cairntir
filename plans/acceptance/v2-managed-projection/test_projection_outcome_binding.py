"""An unrelated committed outcome cannot resolve another action's uncertainty."""

import json
import unittest
from unittest.mock import patch
from uuid import uuid4

from test_projection_corruption import ProjectionCorruptionAcceptance as Fixture


class ProjectionOutcomeAcceptance(unittest.TestCase):
    setUp = Fixture.setUp
    make_event = Fixture.make_event
    project = Fixture.project
    state = Fixture.state
    snapshot = Fixture.snapshot
    assert_refused = Fixture.assert_refused

    def action(self):
        brief = self.runtime.brief()
        ack = self.runtime.acknowledge(
            {
                "schema": "cairntir.managed-ack.v1",
                "brief_id": brief["brief_id"],
                "brief_sha256": brief["brief_sha256"],
            }
        )
        return {
            "schema": "cairntir.managed-action.v1",
            "action_id": str(uuid4()),
            "ack_id": ack["ack_id"],
            "profile": "check",
            "claim": "Check source",
            "predicted_outcome": "Source exists",
            "event_ids": [self.capture["event_id"]],
        }

    def test_outcome_public_action_id_cannot_hide_different_uncertain_intent(self):
        completed = self.runtime.dispatch(self.action())
        self.assertEqual(completed["status"], "completed")
        uncertain = self.action()
        with (
            patch("subprocess.Popen", side_effect=SystemExit("post-intent interruption")),
            self.assertRaises(SystemExit),
        ):
            self.runtime.dispatch(uncertain)
        self.assertEqual(self.runtime.status(uncertain["action_id"])["status"], "uncertain")
        self.snapshot()
        prior = self.target.read_bytes()
        row = self.store._conn.execute(
            "SELECT idempotency_key, result FROM workflow_runs WHERE operation='managed.outcome.v1' AND state='committed'"
        ).fetchone()
        result = json.loads(row["result"])
        result["action_id"] = uncertain["action_id"]
        self.store._conn.execute(
            "UPDATE workflow_runs SET result=? WHERE idempotency_key=?",
            (json.dumps(result), row["idempotency_key"]),
        )
        self.store._conn.commit()
        self.assert_refused(prior)


del Fixture

if __name__ == "__main__":
    unittest.main(verbosity=2)
