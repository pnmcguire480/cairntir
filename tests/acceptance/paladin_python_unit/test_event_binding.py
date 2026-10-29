"""Additive captured-event refusal acceptance, independent of implementation."""

import unittest
from copy import deepcopy
from unittest.mock import patch

from cairntir.managed import ManagedRuntime, ManagedRuntimeError
from cairntir.paladin_python import PaladinPythonError, PaladinPythonRun

from .fixtures import PreparedFixture

OBSERVATIONS = []


class EventBindingAcceptance(unittest.TestCase):
    def exercise(self, operation):
        f = PreparedFixture(self)
        adapter = PaladinPythonRun(f.runtime, contract=f.contract())
        action = f.action("unit")
        receipt = adapter.execute("unit", action)
        self.assertEqual(receipt["status"], "PASS", receipt)
        clean = adapter.report()
        self.assertEqual(clean["qualification"]["status"], "CURRENT")
        fresh = PaladinPythonRun(
            ManagedRuntime(f.store, config=deepcopy(f.runtime_config)), contract=f.contract()
        )
        before = f.state()
        self.assertEqual(fresh.report(), clean)
        self.assertEqual(f.state(), before)
        effects = f.effects()
        self.assertEqual(effects, b"unit\n")
        source_id = f.capture["drawer_id"]
        original = f.store._conn.execute(
            "SELECT content FROM drawers WHERE id = ?", (source_id,)
        ).fetchone()[0]
        changed = original + "\r\nChanged after committed execution."
        cursor = f.store._conn.execute(
            "UPDATE drawers SET content = ? WHERE id = ?", (changed, source_id)
        )
        self.assertEqual(cursor.rowcount, 1)
        f.store._conn.commit()
        self.assertEqual(
            f.store._conn.execute(
                "SELECT content FROM drawers WHERE id = ?", (source_id,)
            ).fetchone()[0],
            changed,
        )
        before = f.state()
        with self.assertRaises(ManagedRuntimeError):
            f.runtime.status(action["action_id"])
        self.assertEqual(f.state(), before)
        error = None
        result = None
        with patch("subprocess.Popen", side_effect=AssertionError("unexpected child")) as launch:
            try:
                result = (
                    fresh.report() if operation == "report" else adapter.execute("unit", action)
                )
            except PaladinPythonError as exc:
                error = str(exc)
            launch.assert_not_called()
        self.assertEqual(f.state(), before)
        self.assertEqual(f.effects(), effects)
        OBSERVATIONS.append(
            {
                "operation": operation,
                "managed_refused": True,
                "paladin_error": error,
                "returned_qualification": result.get("qualification") if result else None,
                "returned_status": result.get("status") if result else None,
                "recorded_stage_status": next(
                    row["status"] for row in result["stages"] if row["stage_id"] == "unit"
                )
                if result and "stages" in result
                else None,
                "child_marker": effects.decode(),
                "database_unchanged_after_fixture": True,
            }
        )
        self.assertIsNotNone(error, "changed captured event was accepted by PALADIN")

    def test_reconstructed_report_refuses_changed_captured_source(self):
        self.exercise("report")

    def test_exact_replay_refuses_changed_captured_source(self):
        self.exercise("replay")
