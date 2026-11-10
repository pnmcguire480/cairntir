import json
import unittest
from copy import deepcopy
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

from cairntir.managed import ManagedRuntime
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.paladin_python import PaladinPythonError, PaladinPythonRun
from cairntir.provenance import WriteProvenance

from .fixtures import FAMILIES, PreparedFixture


class PaladinLifecycleOutcomes(unittest.TestCase):
    def adapter(self, fixture, index=0):
        return PaladinPythonRun(fixture.runtime, contract=fixture.contract(index))

    def refuse_without_effect(self, fixture, operation):
        before = fixture.state()
        effects = [fixture.effects(index) for index in range(3)]
        with patch("subprocess.Popen", side_effect=AssertionError("unexpected child")) as launch:
            with self.assertRaises(PaladinPythonError):
                operation()
            launch.assert_not_called()
        self.assertEqual(fixture.state(), before)
        self.assertEqual([fixture.effects(index) for index in range(3)], effects)

    def passed_unit(self):
        fixture = PreparedFixture(self)
        adapter = self.adapter(fixture)
        result = adapter.execute("unit", fixture.action("unit"))
        self.assertEqual(result["status"], "PASS", result)
        report = adapter.report()
        row = next(row for row in report["stages"] if row["stage_id"] == "unit")
        self.assertEqual(row["receipt"], result)
        return fixture, adapter, result

    def source_id(self, receipt, kind):
        if kind == "registry":
            return receipt["evidence"][-1]["drawer_id"]
        return receipt["managed_result"][kind + "_drawer_id"]

    def alter_source(self, fixture, drawer_id):
        row = fixture.store._conn.execute(
            "SELECT content FROM drawers WHERE id = ?", (drawer_id,)
        ).fetchone()
        self.assertIsNotNone(row)
        changed = row["content"] + "\nUntrusted mutation café.\r\n"
        with fixture.store.transaction():
            fixture.store._conn.execute(
                "UPDATE drawers SET content = ? WHERE id = ?", (changed, drawer_id)
            )
        self.assertEqual(
            fixture.store._conn.execute(
                "SELECT content FROM drawers WHERE id = ?", (drawer_id,)
            ).fetchone()[0],
            changed,
        )

    def test_01_outer_transaction_refuses_before_any_effect(self):
        fixture = PreparedFixture(self)
        adapter = self.adapter(fixture)
        action = fixture.action("unit")
        with fixture.store.transaction():
            self.assertTrue(fixture.store.transaction_active)
            self.refuse_without_effect(fixture, lambda: adapter.execute("unit", action))
            self.assertTrue(fixture.store.transaction_active)
        self.assertFalse(fixture.store.transaction_active)
        self.assertEqual(fixture.effects(), b"")
        self.assertEqual(adapter.execute("unit", action)["status"], "PASS")
        self.assertEqual(fixture.effects(), b"unit\n")

    def test_02_changed_registry_source_cannot_authorize_report(self):
        fixture, adapter, receipt = self.passed_unit()
        self.alter_source(fixture, self.source_id(receipt, "registry"))
        self.refuse_without_effect(fixture, adapter.report)

    def test_03_changed_prediction_source_cannot_authorize_report(self):
        fixture, adapter, receipt = self.passed_unit()
        self.alter_source(fixture, self.source_id(receipt, "prediction"))
        self.refuse_without_effect(fixture, adapter.report)

    def test_04_changed_outcome_source_cannot_authorize_report(self):
        fixture, adapter, receipt = self.passed_unit()
        self.alter_source(fixture, self.source_id(receipt, "outcome"))
        self.refuse_without_effect(fixture, adapter.report)

    def test_05_expired_lifecycle_sources_cannot_authorize_report(self):
        for kind in ("registry", "prediction", "outcome"):
            with self.subTest(kind=kind):
                fixture, adapter, receipt = self.passed_unit()
                drawer_id = self.source_id(receipt, kind)
                row = fixture.store._conn.execute(
                    "SELECT provenance FROM drawers WHERE id = ?", (drawer_id,)
                ).fetchone()
                provenance = json.loads(row["provenance"])
                self.assertIsNone(provenance["valid_from"])
                provenance["valid_until"] = "2000-01-01T00:00:00+00:00"
                encoded = json.dumps(provenance)
                parsed = WriteProvenance.from_json(encoded)
                self.assertLess(parsed.valid_until, datetime.now(UTC))
                with fixture.store.transaction():
                    fixture.store._conn.execute(
                        "UPDATE drawers SET provenance = ?, valid_until = ? WHERE id = ?",
                        (encoded, provenance["valid_until"], drawer_id),
                    )
                self.refuse_without_effect(fixture, adapter.report)

    def test_06_missing_artifact_is_unavailable_without_erasing_history(self):
        fixture, adapter, receipt = self.passed_unit()
        artifact = fixture.outputs[0] / "unit/report.xml"
        retained = fixture.root / "retained-unit-report.xml"
        self.assertTrue(artifact.resolve().is_relative_to(fixture.root))
        self.assertTrue(retained.resolve().is_relative_to(fixture.root))
        exact_bytes = artifact.read_bytes()
        artifact.rename(retained)
        before = fixture.state()
        with patch(
            "subprocess.Popen", side_effect=AssertionError("report launched child")
        ) as launch:
            report = adapter.report()
            launch.assert_not_called()
        self.assertEqual(report["qualification"]["status"], "UNAVAILABLE", report)
        self.assertEqual(report["disposition"], "BLOCKED")
        self.assertIn(receipt, report["attempts"][0]["stage_receipts"])
        self.assertEqual(fixture.state(), before)
        self.assertEqual(fixture.effects(), b"unit\n")
        self.assertFalse(artifact.exists())
        self.assertEqual(retained.read_bytes(), exact_bytes)

    def test_07_repair_parent_must_match_actual_previous_attempt(self):
        fixture = PreparedFixture(self, values=(99, 7, 7))
        first = self.adapter(fixture)
        failure = first.execute("unit", fixture.action("unit"))
        self.assertEqual(failure["status"], "FAIL")
        bad = fixture.contract(1)
        bad["attempt"]["parent_attempt_id"] = str(uuid4())
        action = fixture.action("unit", 1)
        self.refuse_without_effect(
            fixture, lambda: PaladinPythonRun(fixture.runtime, contract=bad).execute("unit", action)
        )
        self.assertEqual(len(first.report()["attempts"]), 1)
        self.assertEqual(fixture.effects(1), b"")

    def test_08_repair_cannot_skip_unregistered_intermediate_slot(self):
        fixture = PreparedFixture(self, values=(99, 7, 7))
        first = self.adapter(fixture)
        self.assertEqual(first.execute("unit", fixture.action("unit"))["status"], "FAIL")
        action = fixture.action("unit", 2)
        self.refuse_without_effect(
            fixture, lambda: self.adapter(fixture, 2).execute("unit", action)
        )
        self.assertEqual(len(first.report()["attempts"]), 1)
        self.assertEqual(fixture.effects(2), b"")

    def test_09_new_repair_seals_old_attempt_against_new_execution(self):
        fixture = PreparedFixture(self, values=(99, 7, 7))
        first = self.adapter(fixture)
        old = first.execute("unit", fixture.action("unit"))
        self.assertEqual(old["status"], "FAIL")
        repaired = self.adapter(fixture, 1)
        new = repaired.execute("unit", fixture.action("unit", 1))
        self.assertEqual(new["status"], "PASS")
        action = fixture.action("integration", 0)
        self.refuse_without_effect(fixture, lambda: first.execute("integration", action))
        self.assertEqual(first.report()["qualification"]["status"], "STALE")
        report = repaired.report()
        self.assertEqual([item["index"] for item in report["attempts"]], [0, 1])
        self.assertIn(old, report["attempts"][0]["stage_receipts"])
        self.assertIn(new, report["attempts"][1]["stage_receipts"])

    def test_10_new_run_identity_cannot_bypass_managed_uncertainty(self):
        fixture = PreparedFixture(self, modes=("timeout", "normal", "normal"))
        first = self.adapter(fixture)
        result = first.execute("unit", fixture.action("unit"))
        self.assertEqual(result["status"], "INCONCLUSIVE")
        self.assertEqual(result["managed_result"]["status"], "uncertain")
        self.assertTrue(result["managed_result"]["timed_out"])
        self.assertEqual(fixture.effects(), b"unit\n")
        other = fixture.contract()
        other["run_id"] = str(uuid4())
        other["attempt"]["attempt_id"] = str(uuid4())
        alternate = PaladinPythonRun(fixture.runtime, contract=other)
        fresh = fixture.action("integration")
        self.refuse_without_effect(fixture, lambda: alternate.execute("integration", fresh))
        self.assertEqual(alternate.report()["attempts"], [])
        self.assertEqual(fixture.effects(), b"unit\n")

    def test_11_complete_report_uses_readonly_store_without_access_updates(self):
        fixture = PreparedFixture(self)
        adapter = self.adapter(fixture)
        for family in FAMILIES:
            self.assertEqual(adapter.execute(family, fixture.action(family))["status"], "PASS")
        expected = adapter.report()
        self.assertEqual(expected["disposition"], "COMPLETE")
        before = fixture.state()
        counters = [
            tuple(row)
            for row in fixture.store._conn.execute(
                "SELECT id, access_count, last_accessed_at FROM drawers ORDER BY id"
            )
        ]
        with DrawerStore(
            fixture.root / "memory.db", HashEmbeddingProvider(32), read_only=True
        ) as readonly:
            runtime = ManagedRuntime(readonly, config=deepcopy(fixture.runtime_config))
            reader = PaladinPythonRun(runtime, contract=fixture.contract())
            changes = readonly._conn.total_changes
            with patch(
                "subprocess.Popen", side_effect=AssertionError("read launched child")
            ) as launch:
                self.assertEqual(reader.report(), expected)
                self.assertEqual(reader.report(), expected)
                launch.assert_not_called()
            self.assertEqual(readonly._conn.total_changes, changes)
            self.assertEqual(
                [
                    tuple(row)
                    for row in readonly._conn.execute(
                        "SELECT id, access_count, last_accessed_at FROM drawers ORDER BY id"
                    )
                ],
                counters,
            )
        self.assertEqual(fixture.state(), before)
