"""Actual tool qualification, separately run from controlled parser/lifecycle cases."""

import json
import unittest

from cairntir.paladin_python import PaladinPythonRun

from .fixtures import FAMILIES, PreparedFixture


class PaladinRealToolsAcceptance(unittest.TestCase):
    def test_clean_prepared_python_package_runs_all_five_real_stages(self):
        f = PreparedFixture(self, real=True)
        a = PaladinPythonRun(f.runtime, contract=f.contract())
        for name in FAMILIES:
            result = a.execute(name, f.action(name))
            self.assertEqual(result["status"], "PASS", result)
            self.assertEqual(result["managed_result"]["exit_code"], 0)
            self.assertTrue(result["artifacts"], name)
        report = a.report()
        self.assertEqual(report["disposition"], "COMPLETE", report)
        self.assertEqual(report["qualification"]["status"], "CURRENT")
        self.assertEqual(report["codeglass"]["sections"]["why"], "unknown")
        for name in ("unit", "integration"):
            receipt = next(x["receipt"] for x in report["stages"] if x["stage_id"] == name)
            self.assertGreater(receipt["tests"]["collected"], 0)
            self.assertEqual(receipt["tests"]["failed"], 0)
            self.assertEqual(receipt["tests"]["skipped"], 0)

    def test_known_lint_type_build_behavior_and_restart_defects_fail_their_real_stages(self):
        for variant, stage in (
            ("lint", "lint"),
            ("types", "types"),
            ("build", "build"),
            ("behavior", "unit"),
            ("restart", "integration"),
        ):
            with self.subTest(variant=variant, stage=stage):
                f = PreparedFixture(self, real=True, variants=(variant, "clean", "clean"))
                a = PaladinPythonRun(f.runtime, contract=f.contract())
                result = a.execute(stage, f.action(stage))
                self.assertEqual(result["status"], "FAIL", result)
                self.assertNotEqual(result["managed_result"]["exit_code"], 0)
                self.assertTrue(result["diagnostics"])
                self.assertNotEqual(a.report()["disposition"], "COMPLETE")
                if variant == "behavior":
                    raw = json.loads((f.outputs[0] / "unit/coverage.json").read_text())
                    self.assertGreaterEqual(raw["totals"]["percent_covered"], 95)
                    self.assertGreater(result["tests"]["failed"], 0)
                if variant == "restart":
                    self.assertGreater(result["tests"]["failed"], 0)

    def test_failed_real_pytest_attempt_repairs_in_new_slot_without_losing_evidence(self):
        f = PreparedFixture(self, real=True, variants=("behavior", "clean", "clean"))
        first = PaladinPythonRun(f.runtime, contract=f.contract())
        failed = first.execute("unit", f.action("unit"))
        self.assertEqual(failed["status"], "FAIL", failed)
        reports = {
            p.relative_to(f.outputs[0]).as_posix(): p.read_bytes()
            for p in f.outputs[0].rglob("*")
            if p.is_file()
        }
        repaired = PaladinPythonRun(f.runtime, contract=f.contract(1))
        for stage in FAMILIES:
            self.assertEqual(repaired.execute(stage, f.action(stage, 1))["status"], "PASS")
        final = repaired.report()
        self.assertEqual(final["disposition"], "COMPLETE", final)
        self.assertEqual(final["repair_rounds_used"], 1)
        self.assertIn(failed, final["attempts"][0]["stage_receipts"])
        for path, content in reports.items():
            self.assertEqual((f.outputs[0] / path).read_bytes(), content)
        for item in f.plan["inputs"]:
            self.assertEqual(
                (f.snapshots[0] / item["path"]).read_bytes(),
                (f.snapshots[1] / item["path"]).read_bytes(),
            )
