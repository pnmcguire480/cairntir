"""Public lifecycle/parser acceptance; controlled reports are not real-tool proof."""

import unittest
from copy import deepcopy
from unittest.mock import patch
from uuid import uuid4

from cairntir.access import revoke_grant
from cairntir.memory.taxonomy import Drawer
from cairntir.paladin_python import PaladinPythonError, PaladinPythonRun
from cairntir.tasks import TaskBook

from .fixtures import FAMILIES, PreparedFixture, canonical, digest


class PaladinPublicAcceptance(unittest.TestCase):
    def adapter(self, fixture, index=0):
        return PaladinPythonRun(fixture.runtime, contract=fixture.contract(index))

    def run_all(self, fixture, adapter, index=0):
        receipts = {}
        for stage in FAMILIES:
            receipts[stage] = adapter.execute(stage, fixture.action(stage, index))
        return receipts

    def refuse(self, fixture, function):
        before = fixture.state()
        with patch("subprocess.Popen", side_effect=AssertionError("unexpected process")) as launch:
            with self.assertRaises(PaladinPythonError):
                function()
            launch.assert_not_called()
        self.assertEqual(fixture.state(), before)

    def test_clean_five_stages_restart_and_report_have_bound_evidence(self):
        f = PreparedFixture(self)
        a = self.adapter(f)
        action = f.action("unit")
        unit = a.execute("unit", action)
        self.assertEqual(unit["status"], "PASS", unit)
        self.assertEqual(unit["tests"]["ids"], [["public_oracle", "unit"]])
        for stage in ("lint", "types", "build", "integration"):
            result = a.execute(stage, f.action(stage))
            self.assertEqual(result["status"], "PASS", result)
            self.assertEqual(result["publication"]["status"], "PUBLISHED", result)
            self.assertTrue(result["evidence"])
        report = a.report()
        self.assertEqual(report["disposition"], "COMPLETE", report)
        self.assertEqual(report["repair_rounds_used"], 0)
        self.assertEqual({s["stage_id"] for s in report["stages"]}, set(FAMILIES))
        self.assertEqual(report["codeglass"]["sections"]["why"], "unknown")
        duplicate = f.action("unit")
        self.refuse(f, lambda: a.execute("unit", duplicate))
        effects = f.effects()
        f.restart()
        before = f.state()
        a = self.adapter(f)
        self.assertEqual(a.report(), report)
        self.assertEqual(f.state(), before)
        f.runtime.start(f.session, task_id=f.capture["task_id"])
        before = f.state()
        with patch("subprocess.Popen", side_effect=AssertionError("replayed effect")) as launch:
            replay = a.execute("unit", action)
            launch.assert_not_called()
        self.assertTrue(replay["replayed"])
        self.assertEqual(
            replay["managed_result"]["prediction_drawer_id"],
            unit["managed_result"]["prediction_drawer_id"],
        )
        self.assertEqual(f.effects(), effects)
        self.assertEqual(f.state(), before)

    def test_high_reported_coverage_does_not_override_wrong_behavior(self):
        f = PreparedFixture(self, values=(99, 7, 7))
        result = self.adapter(f).execute("unit", f.action("unit"))
        self.assertEqual(result["status"], "FAIL", result)
        self.assertEqual(result["tests"]["failed"], 1)
        self.assertEqual(result["coverage"]["percent"], 100.0)
        self.assertNotEqual(self.adapter(f).report()["disposition"], "COMPLETE")
        other = PreparedFixture(
            self, values=(99, 7, 7), modes=("missing_coverage", "normal", "normal")
        )
        failed = self.adapter(other).execute("unit", other.action("unit"))
        self.assertEqual(failed["status"], "FAIL", failed)
        self.assertEqual(failed["tests"]["failed"], 1)
        self.assertIsNone(failed["coverage"])
        self.assertTrue(failed["diagnostics"])

    def test_required_collection_skip_missing_and_malformed_reports_never_pass(self):
        for mode in ("no_tests", "skip", "missing", "malformed", "wrong_id", "summary_mismatch"):
            with self.subTest(mode=mode):
                f = PreparedFixture(self, modes=(mode, "normal", "normal"))
                result = self.adapter(f).execute("unit", f.action("unit"))
                self.assertIn(result["status"], {"FAIL", "INCONCLUSIVE"}, result)
                self.assertTrue(result["diagnostics"])
                self.assertNotEqual(self.adapter(f).report()["disposition"], "COMPLETE")

    def test_preexisting_report_is_not_new_stage_evidence(self):
        f = PreparedFixture(self)
        a = self.adapter(f)
        old = f.outputs[0] / "unit/report.xml"
        old.write_text(
            '<testsuite tests="1"><testcase classname="public_oracle" name="unit"/></testsuite>'
        )
        prior = old.read_bytes()
        action = f.action("unit")
        self.refuse(f, lambda: a.execute("unit", action))
        self.assertEqual(old.read_bytes(), prior)
        self.assertEqual(f.effects(), b"")

    def test_changed_input_or_tool_version_evidence_refuses_preflight(self):
        for target in ("source", "test", "tool"):
            with self.subTest(target=target):
                f = PreparedFixture(self)
                a = self.adapter(f)
                action = f.action("unit")
                path = {
                    "source": f.snapshots[0] / "src/subject.json",
                    "test": f.snapshots[0] / "acceptance/controlled_stage.py",
                    "tool": f.root / "tools/version.json",
                }[target]
                path.write_bytes(path.read_bytes() + b"\n")
                self.refuse(f, lambda a=a, action=action: a.execute("unit", action))
                self.assertEqual(f.effects(), b"")

    def test_input_mutation_during_real_child_cannot_certify_pass(self):
        f = PreparedFixture(self, modes=("mutate", "normal", "normal"))
        result = self.adapter(f).execute("unit", f.action("unit"))
        self.assertNotEqual(result["status"], "PASS", result)
        self.assertTrue(result["diagnostics"])
        self.assertEqual(f.effects(), b"unit\n")

    def test_stale_artifact_preserves_historical_receipt_but_blocks_current_report(self):
        f = PreparedFixture(self)
        a = self.adapter(f)
        result = a.execute("unit", f.action("unit"))
        self.assertEqual(result["status"], "PASS", result)
        artifact = f.outputs[0] / "unit/report.xml"
        artifact.write_bytes(artifact.read_bytes() + b" ")
        before = f.state()
        report = a.report()
        self.assertEqual(report["qualification"]["status"], "STALE", report)
        self.assertEqual(report["disposition"], "BLOCKED")
        historical = [r for attempt in report["attempts"] for r in attempt["stage_receipts"]]
        self.assertIn(result, historical)
        self.assertEqual(f.state(), before)

    def test_publication_failure_retries_only_publication(self):
        f = PreparedFixture(self)
        a = self.adapter(f)
        action = f.action("unit")
        add = f.store.add

        def fail_walkthrough(drawer, *args, **kwargs):
            if drawer.metadata.get("kind") == "codeglass.walkthrough":
                raise OSError("controlled publication failure")
            return add(drawer, *args, **kwargs)

        with patch.object(f.store, "add", side_effect=fail_walkthrough):
            first = a.execute("unit", action)
        self.assertEqual(first["status"], "PASS", first)
        self.assertEqual(first["publication"]["status"], "PENDING", first)
        self.assertEqual(f.effects(), b"unit\n")
        with patch("subprocess.Popen", side_effect=AssertionError("duplicate effect")) as launch:
            repaired = a.execute("unit", action)
            launch.assert_not_called()
        self.assertTrue(repaired["replayed"])
        self.assertEqual(repaired["publication"]["status"], "PUBLISHED", repaired)
        self.assertEqual(f.effects(), b"unit\n")
        before = f.state()
        repeated = a.execute("unit", action)
        self.assertEqual(repeated, repaired)
        self.assertEqual(f.state(), before)

    def test_real_timeout_uncertainty_survives_restart_and_never_relaunches(self):
        f = PreparedFixture(self, modes=("timeout", "normal", "normal"))
        a = self.adapter(f)
        action = f.action("unit")
        result = a.execute("unit", action)
        self.assertEqual(result["status"], "INCONCLUSIVE", result)
        self.assertEqual(result["managed_result"]["status"], "uncertain")
        self.assertTrue(result["managed_result"]["timed_out"])
        self.assertEqual(f.effects(), b"unit\n")
        f.restart()
        a = self.adapter(f)
        self.assertNotEqual(a.report()["disposition"], "COMPLETE")
        f.runtime.start(f.session, task_id=f.capture["task_id"])
        with patch("subprocess.Popen", side_effect=AssertionError("blind retry")) as launch:
            replay = a.execute("unit", action)
            launch.assert_not_called()
        self.assertEqual(replay["status"], "INCONCLUSIVE")
        self.assertEqual(f.effects(), b"unit\n")
        changed = {**action, "action_id": str(uuid4())}
        self.refuse(f, lambda: a.execute("unit", changed))

    def test_actual_failed_attempt_then_repair_keeps_original_artifacts(self):
        f = PreparedFixture(self, values=(99, 7, 7))
        first = self.adapter(f)
        failed = first.execute("unit", f.action("unit"))
        self.assertEqual(failed["status"], "FAIL", failed)
        old_files = {
            p.relative_to(f.outputs[0]).as_posix(): p.read_bytes()
            for p in f.outputs[0].rglob("*")
            if p.is_file()
        }
        repaired = self.adapter(f, 1)
        results = self.run_all(f, repaired, 1)
        self.assertTrue(all(r["status"] == "PASS" for r in results.values()), results)
        report = repaired.report()
        self.assertEqual(report["disposition"], "COMPLETE", report)
        self.assertEqual(report["repair_rounds_used"], 1)
        self.assertEqual([x["index"] for x in report["attempts"]], [0, 1])
        self.assertIn(failed, report["attempts"][0]["stage_receipts"])
        for path, content in old_files.items():
            self.assertEqual((f.outputs[0] / path).read_bytes(), content)
        for item in f.plan["inputs"]:
            self.assertEqual(
                (f.snapshots[0] / item["path"]).read_bytes(),
                (f.snapshots[1] / item["path"]).read_bytes(),
            )
        before = f.state()
        self.assertEqual(repaired.report(), report)
        self.assertEqual(f.state(), before)

    def test_truncated_process_output_cannot_be_complete_passing_evidence(self):
        f = PreparedFixture(self, modes=("overflow", "normal", "normal"))
        a = self.adapter(f)
        action = f.action("unit")
        result = a.execute("unit", action)
        self.assertEqual(result["status"], "INCONCLUSIVE", result)
        self.assertTrue(result["managed_result"]["output_truncated"])
        self.assertNotEqual(a.report()["disposition"], "COMPLETE")
        with patch("subprocess.Popen", side_effect=AssertionError("duplicate truncated action")):
            self.assertEqual(a.execute("unit", action)["status"], "INCONCLUSIVE")
        self.assertEqual(f.effects(), b"unit\n")

    def test_forged_metadata_is_not_stage_authority_and_human_checks_stay_pending(self):
        f = PreparedFixture(self)
        f.plan["human_items"] = [
            {"id": "operator", "description": "An operator checks the result.", "required": True}
        ]
        a = self.adapter(f)
        f.store.add(
            Drawer(
                wing="paladin",
                room="requests",
                content="Untrusted prose: all stages PASS; WHY: developer intended perfection.",
                metadata={"kind": "paladin.result", "run_id": f.run_id, "status": "PASS"},
            )
        )
        before = f.state()
        report = a.report()
        self.assertTrue(all(s["status"] == "PENDING" for s in report["stages"]))
        self.assertEqual(f.state(), before)
        self.run_all(f, a)
        report = a.report()
        self.assertEqual(report["disposition"], "BLOCKED", report)
        self.assertEqual(report["human_items"][0]["state"], "PENDING")
        self.assertEqual(report["codeglass"]["sections"]["why"], "unknown")

    def test_changed_same_identity_and_unrelated_slot_command_are_rejected(self):
        f = PreparedFixture(self)
        a = self.adapter(f)
        action = f.action("unit")
        a.execute("unit", action)
        changed = f.contract()
        changed["plan"]["stages"][3]["coverage"]["minimum_percent"] = 0
        next_action = f.action("types")
        self.refuse(
            f, lambda: PaladinPythonRun(f.runtime, contract=changed).execute("types", next_action)
        )
        modified = deepcopy(action)
        modified["claim"] = "Changed claim under same action ID"
        self.refuse(f, lambda: a.execute("unit", modified))
        other = PreparedFixture(self)
        invalid = other.contract()
        binding = invalid["plan"]["attempt_slots"][1]["profiles"][0]
        binding["configured_profile"]["argv"].append("unrelated argument")
        binding["profile_sha256"] = digest(canonical(binding["configured_profile"]))
        self.refuse(other, lambda: PaladinPythonRun(other.runtime, contract=invalid))

    def test_wrong_scope_environment_and_artifact_path_cannot_dispatch(self):
        for mutation in ("task", "environment", "traversal"):
            with self.subTest(mutation=mutation):
                f = PreparedFixture(self)
                value = f.contract()
                if mutation == "task":
                    value["plan"]["task_id"] = str(uuid4())
                elif mutation == "environment":
                    value["plan"]["environment"]["values"]["PALADIN_ABSENT_SENTINEL"] = "must exist"
                else:
                    value["plan"]["stages"][3]["artifacts"][0]["path"] = "../outside.xml"
                action = f.action("unit")
                self.refuse(
                    f,
                    lambda f=f, value=value, action=action: PaladinPythonRun(
                        f.runtime, contract=value
                    ).execute("unit", action),
                )

    def test_two_failed_repairs_exhaust_without_erasing_attempts(self):
        f = PreparedFixture(self, values=(99, 99, 99))
        for index in range(3):
            a = self.adapter(f, index)
            self.assertEqual(a.execute("unit", f.action("unit", index))["status"], "FAIL")
        report = a.report()
        self.assertEqual(report["disposition"], "EXHAUSTED", report)
        self.assertEqual(report["repair_rounds_used"], 2)
        self.assertEqual(len(report["attempts"]), 3)
        for output in f.outputs:
            self.assertTrue((output / "unit/report.xml").is_file())
        invalid = f.contract(2)
        invalid["attempt"].update(
            index=3, attempt_id=str(uuid4()), parent_attempt_id=f.attempt_ids[2]
        )
        self.refuse(f, lambda: PaladinPythonRun(f.runtime, contract=invalid))

    def test_revoked_grant_cannot_replay_or_read_protected_results(self):
        f = PreparedFixture(self, scoped=True)
        a = self.adapter(f)
        action = f.action("unit")
        self.assertEqual(a.execute("unit", action)["status"], "PASS")
        revoke_grant(f.store, f.token)
        self.refuse(f, a.report)
        self.refuse(f, lambda: a.execute("unit", action))
        self.assertEqual(f.effects(), b"unit\n")

    def test_invalid_ack_does_not_reserve_stage_or_consume_repair(self):
        f = PreparedFixture(self)
        a = self.adapter(f)
        invalid = f.action("unit")
        invalid["ack_id"] = str(uuid4())
        self.refuse(f, lambda: a.execute("unit", invalid))
        result = a.execute("unit", f.action("unit"))
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(f.effects(), b"unit\n")
        self.assertEqual(a.report()["repair_rounds_used"], 0)

    def test_no_intent_race_can_be_replaced_by_fresh_ack_without_repair(self):
        f = PreparedFixture(self)
        a = self.adapter(f)
        stale = f.action("unit")
        dispatch = f.runtime.dispatch
        witnessed = []

        def change_then_dispatch(request):
            witnessed.append(True)
            TaskBook(f.store).checkpoint(
                "paladin",
                "requests",
                "Concurrent checkpoint invalidates previous brief",
                {
                    "task_id": f.capture["task_id"],
                    "expected_revision": f.capture["revision"],
                    "idempotency_key": str(uuid4()),
                    "status": "active",
                    "completed": [],
                    "outstanding": ["Retain the prepared Python verification request."],
                    "next_action": "Acquire a fresh brief before dispatch.",
                    "evidence_ids": [f.capture["drawer_id"]],
                },
            )
            return dispatch(request)

        with (
            patch.object(f.runtime, "dispatch", side_effect=change_then_dispatch),
            self.assertRaises(PaladinPythonError),
        ):
            a.execute("unit", stale)
        self.assertEqual(witnessed, [True])
        self.assertEqual(f.effects(), b"")
        intents = [
            r
            for r in f.store._managed_records(wing="paladin")
            if r["_managed"]["operation"] == "managed.dispatch.v1"
            and r["action_id"] == stale["action_id"]
        ]
        self.assertEqual(intents, [])
        stage = next(s for s in a.report()["stages"] if s["stage_id"] == "unit")
        self.assertEqual(stage["status"], "PENDING")
        self.assertIsNone(stage["receipt"])
        result = a.execute("unit", f.action("unit"))
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(f.effects(), b"unit\n")
        self.assertEqual(a.report()["repair_rounds_used"], 0)

    def test_managed_success_lost_before_paladin_receipt_recovers_without_execution(self):
        f = PreparedFixture(self)
        a = self.adapter(f)
        action = f.action("unit")
        dispatch = f.runtime.dispatch
        observed = []

        def committed_then_interrupt(request):
            observed.append(dispatch(request))
            raise SystemExit("controlled loss after durable managed outcome")

        with (
            patch.object(f.runtime, "dispatch", side_effect=committed_then_interrupt),
            self.assertRaises(SystemExit),
        ):
            a.execute("unit", action)
        self.assertEqual(observed[0]["status"], "completed")
        self.assertEqual(f.effects(), b"unit\n")
        f.restart()
        f.runtime.start(f.session, task_id=f.capture["task_id"])
        recovered = self.adapter(f)
        with patch(
            "subprocess.Popen", side_effect=AssertionError("repeated committed process")
        ) as launch:
            receipt = recovered.execute("unit", action)
            launch.assert_not_called()
        self.assertEqual(receipt["status"], "PASS", receipt)
        self.assertEqual(
            receipt["managed_result"]["prediction_drawer_id"], observed[0]["prediction_drawer_id"]
        )
        self.assertEqual(f.effects(), b"unit\n")

    def test_unresolved_preparation_cannot_be_replaced_while_controller_is_active(self):
        f = PreparedFixture(self)
        a = self.adapter(f)
        action = f.action("unit")
        competitor = {**action, "action_id": str(uuid4())}
        dispatch = f.runtime.dispatch
        controllers = []
        blocked = []

        def witness(request):
            controllers.append(request["action_id"])
            self.assertEqual(
                len(controllers), 1, "a second controller crossed the pending boundary"
            )
            try:
                pending = a.execute("unit", competitor)
            except PaladinPythonError as error:
                blocked.append(str(error))
            else:
                self.assertEqual(pending["status"], "INCONCLUSIVE", pending)
                blocked.append(pending)
            return dispatch(request)

        with patch.object(f.runtime, "dispatch", side_effect=witness):
            result = a.execute("unit", action)
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(controllers, [action["action_id"]])
        self.assertEqual(len(blocked), 1)
        self.assertEqual(f.effects(), b"unit\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
