"""Independent close completeness and prior-epoch visibility witnesses."""

import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from cairntir.errors import MemoryStoreError
from cairntir.managed import ManagedRuntime, ManagedRuntimeError
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore


class ManagedCloseAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = self.root / "memory.db"
        self.store = DrawerStore(self.database, HashEmbeddingProvider(32))
        self.addCleanup(lambda: self.store.close())
        self.session = str(uuid4())
        self.config = {
            "schema": "cairntir.managed-config.v1",
            "wing": "managed",
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
        self.runtime = ManagedRuntime(self.store, config=deepcopy(self.config))
        self.runtime.start(self.session)
        self.receipt = self.runtime.capture(self.event())

    def event(self, **changes):
        return {
            "schema": "cairntir.managed-event.v1",
            "event_id": str(uuid4()),
            "session_id": self.session,
            "sequence": 1,
            "task_id": None,
            "expected_revision": 0,
            "content": "  Exact producer claim café\r\n",
            **changes,
        }

    def next_event(self):
        return self.event(
            sequence=2,
            task_id=self.receipt["task_id"],
            expected_revision=self.receipt["revision"],
        )

    def failed_append(self, event):
        calls = []

        def fail(*args, **kwargs):
            calls.append(True)
            raise MemoryStoreError("independent witnessed capture append fault")

        with patch.object(self.store, "add", side_effect=fail):
            with self.assertRaises(ManagedRuntimeError):
                self.runtime.capture(event)
        self.assertTrue(calls, "fault must hit the actual append operation")

    def test_malformed_claim_cannot_be_hidden_by_matching_committed_watermark(self):
        claimed = self.next_event()
        del claimed["content"]
        with self.assertRaises(ManagedRuntimeError):
            self.runtime.capture(claimed)
        self.assertIs(self.runtime.close(last_sequence=1)["capture_complete"], False)

    def test_different_successful_claim_does_not_erase_failed_claim(self):
        failed = self.next_event()
        self.failed_append(failed)
        different = {**failed, "event_id": str(uuid4()), "content": "Different producer claim"}
        self.assertEqual(self.runtime.capture(different)["status"], "committed")
        self.assertIs(self.runtime.close(last_sequence=2)["capture_complete"], False)

    def test_exact_failed_claim_retry_can_restore_complete_close(self):
        failed = self.next_event()
        self.failed_append(failed)
        self.assertEqual(self.runtime.capture(failed)["status"], "committed")
        self.assertIs(self.runtime.close(last_sequence=2)["capture_complete"], True)

    def test_restart_reports_prior_unclean_epoch_and_excludes_closed_epoch(self):
        prior = self.runtime.brief()
        self.store.close()
        self.store = DrawerStore(self.database, HashEmbeddingProvider(32))
        second = ManagedRuntime(self.store, config=deepcopy(self.config))
        restarted = second.start(self.session, task_id=self.receipt["task_id"])
        records = restarted["unclean_sessions"]
        expected = {
            "session_id": self.session,
            "epoch": prior["epoch"],
            "task_id": self.receipt["task_id"],
        }
        self.assertEqual(
            [
                {key: entry[key] for key in expected}
                for entry in records
                if entry["epoch"] == prior["epoch"]
            ],
            [expected],
        )
        self.assertNotIn(restarted["epoch"], [entry["epoch"] for entry in records])
        second.close(last_sequence=1)
        self.store.close()
        self.store = DrawerStore(self.database, HashEmbeddingProvider(32))
        third = ManagedRuntime(self.store, config=deepcopy(self.config))
        latest = third.start(self.session, task_id=self.receipt["task_id"])
        epochs = [entry["epoch"] for entry in latest["unclean_sessions"]]
        self.assertIn(prior["epoch"], epochs)
        self.assertNotIn(restarted["epoch"], epochs)
        self.assertNotIn(latest["epoch"], epochs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
