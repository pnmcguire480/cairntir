"""Black-box public contract and prepared-environment acceptance."""

import json
import os
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from cairntir.managed import ManagedRuntime
from cairntir.paladin_python import PaladinPythonError, PaladinPythonRun

from .fixtures import PreparedFixture, canonical, digest


class ContractOutcomeAcceptance(unittest.TestCase):
    def refuse(self, fixture, action):
        before, effects, environment = fixture.state(), fixture.effects(), dict(os.environ)
        with patch(
            "subprocess.Popen", side_effect=AssertionError("unexpected stage child")
        ) as child:
            with self.assertRaises(PaladinPythonError):
                action()
            child.assert_not_called()
        self.assertEqual(fixture.state(), before)
        self.assertEqual(fixture.effects(), effects)
        self.assertEqual(dict(os.environ), environment)

    def report(self, fixture, adapter, status):
        before, environment = fixture.state(), dict(os.environ)
        with patch(
            "subprocess.Popen", side_effect=AssertionError("report launched child")
        ) as child:
            report = adapter.report()
            child.assert_not_called()
        self.assertEqual(fixture.state(), before)
        self.assertEqual(dict(os.environ), environment)
        self.assertEqual(report["qualification"]["status"], status, report)
        self.assertEqual(report["disposition"], "BLOCKED", report)
        if status != "CURRENT":
            self.assertTrue(report["qualification"]["diagnostics"], report)
        return report

    def test_strict_public_schema_types_ids_and_finite_limits(self):
        for mode in ("schema", "extra", "plan_type", "uuid", "boolean_index", "nonfinite"):
            with self.subTest(mode=mode):
                f = PreparedFixture(self)
                value = f.contract()
                if mode == "schema":
                    value["schema"] = "cairntir.paladin-python-contract.v999"
                elif mode == "extra":
                    value["ignore_required_gate"] = True
                elif mode == "plan_type":
                    value["plan"] = []
                elif mode == "uuid":
                    value["run_id"] = "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"
                elif mode == "boolean_index":
                    value["attempt"]["index"] = False
                else:
                    value["plan"]["stages"][3]["coverage"]["minimum_percent"] = float("nan")
                before = repr(value)
                self.refuse(f, lambda f=f, value=value: PaladinPythonRun(f.runtime, contract=value))
                self.assertEqual(repr(value), before)

    def test_required_stage_test_and_tool_inventories(self):
        for mode in ("family", "stage_duplicate", "test_duplicate", "test_shape", "tool"):
            with self.subTest(mode=mode):
                f = PreparedFixture(self)
                value = f.contract()
                stages = value["plan"]["stages"]
                if mode == "family":
                    del stages[0]
                elif mode == "stage_duplicate":
                    stages[1]["stage_id"] = stages[0]["stage_id"]
                elif mode == "test_duplicate":
                    stages[3]["required_test_ids"] *= 2
                elif mode == "test_shape":
                    stages[3]["required_test_ids"] = [["public_oracle", "unit", "extra"]]
                else:
                    stages[3]["tool_ids"] = ["unbound-tool"]
                self.refuse(f, lambda f=f, value=value: PaladinPythonRun(f.runtime, contract=value))

    def test_finite_slots_parent_shape_and_exact_candidate_inventory(self):
        for mode in ("slot_count", "slot_index", "initial_parent", "self_parent", "inventory"):
            with self.subTest(mode=mode):
                f = PreparedFixture(self)
                value = f.contract(1 if mode == "self_parent" else 0)
                if mode == "slot_count":
                    value["plan"]["attempt_slots"].pop()
                elif mode == "slot_index":
                    value["plan"]["attempt_slots"][1]["index"] = 2
                elif mode == "initial_parent":
                    value["attempt"]["parent_attempt_id"] = str(uuid4())
                elif mode == "self_parent":
                    value["attempt"]["parent_attempt_id"] = value["attempt"]["attempt_id"]
                else:
                    value["attempt"]["inputs"][0]["path"] = "src/other.json"
                self.refuse(f, lambda f=f, value=value: PaladinPythonRun(f.runtime, contract=value))

    def test_disjoint_roots_even_with_consistent_profile_references(self):
        for mode in ("snapshot_output", "tool_payload"):
            with self.subTest(mode=mode):
                f = PreparedFixture(self)
                value = f.contract()
                slot = value["plan"]["attempt_slots"][0]
                if mode == "tool_payload":
                    value["plan"]["tools"][0]["payload_root"] = slot["snapshot_root"]
                else:
                    slot["output_root"] = slot["snapshot_root"]
                    stages = {s["stage_id"]: s for s in value["plan"]["stages"]}
                    roots = {
                        "snapshot": Path(slot["snapshot_root"]),
                        "output": Path(slot["output_root"]),
                    }
                    for binding in slot["profiles"]:
                        command = stages[binding["stage_id"]]["command"]
                        profile = binding["configured_profile"]
                        profile["argv"] = [
                            arg
                            if isinstance(arg, str)
                            else arg["prefix"] + str(roots[arg["root"]] / arg["path"])
                            for arg in command["argv"]
                        ]
                        cwd = command["cwd"]
                        profile["cwd"] = str(roots[cwd["root"]] / cwd["path"])
                        binding["profile_sha256"] = digest(canonical(profile))
                self.refuse(f, lambda f=f, value=value: PaladinPythonRun(f.runtime, contract=value))

    def test_hash_bound_tool_version_observation_must_be_semantically_valid(self):
        for mode in ("version", "exit", "executable"):
            with self.subTest(mode=mode):
                f = PreparedFixture(self)
                self.report(f, PaladinPythonRun(f.runtime, contract=f.contract()), "CURRENT")
                action = f.action("unit")
                value = f.contract()
                tool = value["plan"]["tools"][0]
                path = Path(tool["payload_root"]) / tool["version_evidence"]["path"]
                observation = json.loads(path.read_text())
                if mode == "version":
                    observation["version"] = "0.0.0"
                elif mode == "exit":
                    observation["exit_code"] = 1
                else:
                    observation["argv"][0] = str(f.root / "different-python.exe")
                path.write_bytes(canonical(observation))
                observed_sha = digest(path.read_bytes())
                tool["version_evidence"]["sha256"] = observed_sha
                for item in tool["payload_files"]:
                    if item["path"] == tool["version_evidence"]["path"]:
                        item["sha256"] = observed_sha
                adapter = PaladinPythonRun(f.runtime, contract=value)
                self.report(f, adapter, "STALE")
                self.refuse(
                    f, lambda adapter=adapter, action=action: adapter.execute("unit", action)
                )

    def test_missing_bound_files_and_roots_are_unavailable_without_writes(self):
        for mode in ("source", "test", "snapshot", "output", "tool_root", "tool_version"):
            with self.subTest(mode=mode):
                f = PreparedFixture(self)
                adapter = PaladinPythonRun(f.runtime, contract=f.contract())
                self.report(f, adapter, "CURRENT")
                action = f.action("unit")
                path = {
                    "source": f.snapshots[0] / "src/subject.json",
                    "test": f.snapshots[0] / "acceptance/contract.txt",
                    "snapshot": f.snapshots[0],
                    "output": f.outputs[0],
                    "tool_root": f.root / "tools",
                    "tool_version": f.root / "tools/version.json",
                }[mode]
                destination = f.root / ("preserved-" + mode)
                self.assertTrue(path.resolve().is_relative_to(f.root))
                self.assertTrue(destination.resolve().is_relative_to(f.root))
                path.rename(destination)
                self.assertFalse(path.exists())
                self.assertTrue(destination.exists())
                self.report(f, adapter, "UNAVAILABLE")
                self.refuse(
                    f, lambda adapter=adapter, action=action: adapter.execute("unit", action)
                )

    def test_exact_snapshot_inventory_and_future_slot_acceptance_are_frozen(self):
        for mode in ("extra_source", "repair_tests"):
            with self.subTest(mode=mode):
                f = PreparedFixture(self)
                adapter = PaladinPythonRun(f.runtime, contract=f.contract())
                self.report(f, adapter, "CURRENT")
                action = f.action("unit")
                if mode == "extra_source":
                    (f.snapshots[0] / "unlisted.py").write_text("UNLISTED = True\n")
                else:
                    path = f.snapshots[1] / "acceptance/contract.txt"
                    path.write_bytes(path.read_bytes() + b"Changed repair acceptance.\n")
                self.report(f, adapter, "STALE")
                self.refuse(
                    f, lambda adapter=adapter, action=action: adapter.execute("unit", action)
                )

    def test_environment_contradiction_and_required_absence(self):
        f = PreparedFixture(self)
        invalid = f.contract()
        invalid["plan"]["environment"]["absent"] = ["pythonutf8"]
        self.refuse(f, lambda: PaladinPythonRun(f.runtime, contract=invalid))
        name = "PALADIN_PUBLIC_MUST_BE_ABSENT"
        with patch.dict(os.environ):
            os.environ.pop(name, None)
            value = f.contract()
            value["plan"]["environment"]["absent"] = [name]
            adapter = PaladinPythonRun(f.runtime, contract=value)
            self.report(f, adapter, "CURRENT")
            action = f.action("unit")
            os.environ[name] = "unexpected"
            self.report(f, adapter, "STALE")
            self.refuse(f, lambda adapter=adapter, action=action: adapter.execute("unit", action))

    def test_actual_runtime_profile_cannot_be_substituted_by_contract_text(self):
        f = PreparedFixture(self)
        value = f.contract()
        self.report(f, PaladinPythonRun(f.runtime, contract=value), "CURRENT")
        configured = deepcopy(f.runtime_config)
        configured["profiles"]["slot0_unit"]["timeout_seconds"] = 1
        other = ManagedRuntime(f.store, config=configured)
        adapter = PaladinPythonRun(other, contract=value)
        self.report(f, adapter, "STALE")
        other.start(str(uuid4()), task_id=f.capture["task_id"])
        brief = other.brief()
        ack = other.acknowledge(
            {
                "schema": "cairntir.managed-ack.v1",
                "brief_id": brief["brief_id"],
                "brief_sha256": brief["brief_sha256"],
            }
        )
        action = {
            "schema": "cairntir.managed-action.v1",
            "action_id": str(uuid4()),
            "ack_id": ack["ack_id"],
            "profile": "slot0_unit",
            "claim": "Check frozen unit stage.",
            "predicted_outcome": "Required evidence is complete.",
            "event_ids": [f.capture["event_id"]],
        }
        self.refuse(f, lambda adapter=adapter, action=action: adapter.execute("unit", action))

    def test_repair_requires_exact_immediate_observed_nonpassing_parent(self):
        for mode in ("wrong_parent", "skipped", "premature"):
            with self.subTest(mode=mode):
                f = PreparedFixture(self, values=(7 if mode == "premature" else 99, 7, 7))
                original = PaladinPythonRun(f.runtime, contract=f.contract())
                receipt = original.execute("unit", f.action("unit"))
                self.assertEqual(receipt["status"], "PASS" if mode == "premature" else "FAIL")
                index = 2 if mode == "skipped" else 1
                value = f.contract(index)
                if mode == "wrong_parent":
                    value["attempt"]["parent_attempt_id"] = str(uuid4())
                next_action = f.action("unit", index)
                self.refuse(
                    f,
                    lambda f=f, value=value, next_action=next_action: PaladinPythonRun(
                        f.runtime, contract=value
                    ).execute("unit", next_action),
                )
                report = original.report()
                self.assertEqual(report["repair_rounds_used"], 0)
                self.assertEqual(len(report["attempts"]), 1)
                recorded = next(
                    row["receipt"] for row in report["stages"] if row["stage_id"] == "unit"
                )
                self.assertEqual(recorded, receipt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
