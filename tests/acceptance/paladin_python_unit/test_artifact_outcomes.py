"""Public process-level artifact acceptance, not fabricated real-tool proof."""

import json
import unittest
import zipfile
from pathlib import Path

from cairntir.paladin_python import PaladinPythonRun

from .fixtures import PreparedFixture, bound


class ArtifactOutcomeAcceptance(unittest.TestCase):
    def execute(self, mode, stage="unit"):
        f = PreparedFixture(self, modes=(mode, "normal", "normal"))
        child = Path(__file__).with_name("artifact_child.py").read_bytes()
        for snapshot in f.snapshots:
            controller = snapshot / "acceptance/controlled_stage.py"
            (snapshot / "acceptance/base_stage.py").write_bytes(controller.read_bytes())
            controller.write_bytes(child)
        first = f.snapshots[0]
        f.plan["inputs"] = [
            bound(
                path,
                path.relative_to(first).as_posix(),
                "test" if path.suffix == ".py" else "config",
            )
            for path in sorted((first / "acceptance").iterdir())
            if path.is_file()
        ]
        f.plan["finalization"]["acceptance_paths"] = [item["path"] for item in f.plan["inputs"]]
        adapter = PaladinPythonRun(f.runtime, contract=f.contract())
        result = adapter.execute(stage, f.action(stage))
        self.assertEqual(result["managed_result"]["exit_code"], 0, result)
        self.assertEqual(result["managed_result"]["status"], "completed", result)
        self.assertEqual(f.effects(), (stage + "\n").encode())
        return f, adapter, result

    def incomplete(self, adapter, result):
        self.assertNotEqual(result["status"], "PASS", result)
        self.assertTrue(result["diagnostics"], result)
        self.assertNotEqual(adapter.report()["disposition"], "COMPLETE")

    def test_valid_coverage_below_frozen_floor_is_failure(self):
        _, adapter, result = self.execute("coverage_below")
        self.assertEqual(result["tests"]["passed"], 1)
        self.assertEqual(result["coverage"]["percent"], 50.0)
        self.assertEqual(result["status"], "FAIL", result)
        self.incomplete(adapter, result)

    def test_coverage_of_unrelated_source_cannot_replace_required_source(self):
        f, adapter, result = self.execute("coverage_missing_source")
        raw = json.loads((f.outputs[0] / "unit/coverage.json").read_text())
        self.assertEqual(list(raw["files"]), ["src/unrelated.json"])
        self.incomplete(adapter, result)

    def test_zero_nonfinite_and_inconsistent_coverage_are_not_success(self):
        for mode in ("coverage_zero", "coverage_nonfinite", "coverage_inconsistent"):
            with self.subTest(mode=mode):
                _, adapter, result = self.execute(mode)
                self.incomplete(adapter, result)

    def test_valid_absolute_source_and_branch_report_preserves_statement_gate(self):
        _, _, result = self.execute("coverage_absolute_branch")
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(result["coverage"]["percent"], 100.0)
        self.assertEqual(result["coverage"]["source_paths"], ["src/subject.json"])

    def test_duplicate_test_identity_cannot_count_as_two_executed_cases(self):
        _, adapter, result = self.execute("junit_duplicate")
        self.incomplete(adapter, result)

    def test_contradictory_suite_and_case_outcomes_cannot_pass(self):
        _, adapter, result = self.execute("junit_contradictory")
        self.incomplete(adapter, result)

    def test_wheel_member_must_equal_bound_source_even_with_coherent_record(self):
        f, adapter, result = self.execute("wheel_wrong_source", "build")
        with zipfile.ZipFile(f.outputs[0] / "build/fixture.whl") as archive:
            self.assertNotEqual(
                archive.read("paladin_fixture/subject.json"),
                (f.snapshots[0] / "src/subject.json").read_bytes(),
            )
        self.incomplete(adapter, result)

    def test_wheel_record_must_match_actual_member_bytes(self):
        _, adapter, result = self.execute("wheel_bad_record", "build")
        self.incomplete(adapter, result)

    def test_duplicate_or_traversal_wheel_member_refuses_success(self):
        for mode in ("wheel_duplicate", "wheel_traversal"):
            with self.subTest(mode=mode):
                f, adapter, result = self.execute(mode, "build")
                self.incomplete(adapter, result)
                self.assertFalse((f.outputs[0] / "outside.txt").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
