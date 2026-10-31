"""A repair cannot seal a prior attempt whose controller is still pending."""

import unittest
from copy import deepcopy
from unittest.mock import patch
from uuid import uuid4

from cairntir.managed import ManagedRuntime
from cairntir.paladin_python import PaladinPythonError, PaladinPythonRun

from .fixtures import PreparedFixture


class PendingRepairAcceptance(unittest.TestCase):
    def test_repair_waits_for_existing_prepared_controller_to_settle(self):
        f = PreparedFixture(self, values=(99, 7, 7))
        old = PaladinPythonRun(f.runtime, contract=f.contract())
        self.assertEqual(old.execute("unit", f.action("unit"))["status"], "FAIL")
        other = ManagedRuntime(f.store, config=deepcopy(f.runtime_config))
        other.start(f.session, task_id=f.capture["task_id"])
        brief = other.brief()
        ack = other.acknowledge(
            {
                "schema": "cairntir.managed-ack.v1",
                "brief_id": brief["brief_id"],
                "brief_sha256": brief["brief_sha256"],
            }
        )
        repair_action = {
            "schema": "cairntir.managed-action.v1",
            "action_id": str(uuid4()),
            "ack_id": ack["ack_id"],
            "profile": "slot1_lint",
            "claim": "Attempt repair lint",
            "predicted_outcome": "Passing fixed lint",
            "event_ids": [f.capture["event_id"]],
        }
        repair = PaladinPythonRun(other, contract=f.contract(1))
        old_action = f.action("types")
        original_dispatch = f.runtime.dispatch
        admitted = []
        refused = []

        def attempt_repair_then_original(request):
            try:
                with patch.object(
                    other, "dispatch", side_effect=SystemExit("repair controller admitted")
                ):
                    repair.execute("lint", repair_action)
            except PaladinPythonError as error:
                refused.append(str(error))
            except SystemExit:
                admitted.append(True)
            return original_dispatch(request)

        with patch.object(f.runtime, "dispatch", side_effect=attempt_repair_then_original):
            result = old.execute("types", old_action)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(admitted, [], "new attempt sealed an unresolved prepared controller")
        self.assertEqual(len(refused), 1)
        self.assertEqual(f.effects(), b"unit\ntypes\n")
        self.assertEqual(f.effects(1), b"")
        self.assertEqual(len(old.report()["attempts"]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
