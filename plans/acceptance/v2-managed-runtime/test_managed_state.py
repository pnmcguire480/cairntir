"""Independent deterministic control for brief-only concurrent startup."""

import unittest
from copy import deepcopy

import test_managed_close
from cairntir.managed import ManagedRuntime


class ManagedStateAcceptance(unittest.TestCase):
    def test_second_runtime_start_does_not_invalidate_first_complete_brief(self):
        fixture = test_managed_close.ManagedCloseAcceptance()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        first = fixture.runtime.brief()
        second = ManagedRuntime(fixture.store, config=deepcopy(fixture.config))
        other = second.start(fixture.session, task_id=fixture.receipt["task_id"])
        self.assertNotEqual(first["epoch"], other["epoch"])
        self.assertEqual(first["task"], other["task"])
        for runtime, brief in [(fixture.runtime, first), (second, other)]:
            with self.subTest(epoch=brief["epoch"]):
                ack = runtime.acknowledge(
                    {
                        "schema": "cairntir.managed-ack.v1",
                        "brief_id": brief["brief_id"],
                        "brief_sha256": brief["brief_sha256"],
                    }
                )
                self.assertEqual(ack["status"], "committed")
                self.assertEqual(ack["epoch"], brief["epoch"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
