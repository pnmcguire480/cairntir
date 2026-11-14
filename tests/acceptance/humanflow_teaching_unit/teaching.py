"""Shared setup for the R12 host-narrated teaching artifact.

The run reuses the HumanFlow acceptance fixture files (read only): a
two-attempt managed Python run of ``flow.py`` with a bug and then a repair.
"""

from __future__ import annotations

import hashlib
import shutil
import unittest
from pathlib import Path
from typing import Any

from paladin_python_unit import fixtures

from cairntir.paladin_python import PaladinPythonRun

HERE = Path(__file__).resolve().parent
ARTIFACT = HERE / "artifact"
FLOW = HERE.parent / "humanflow_unit" / "fixture"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def prepare_fixture(case: unittest.TestCase) -> Any:
    """Build the same three-slot flow fixture the HumanFlow acceptance uses."""
    fixture = fixtures.PreparedFixture(case, modes=("flow", "flow", "flow"))
    for index, snapshot in enumerate(fixture.snapshots):
        shutil.copyfile(FLOW / "run_stage.py", snapshot / "acceptance/controlled_stage.py")
        shutil.copyfile(
            FLOW / ("flow-bug.py" if index == 0 else "flow-repair.py"),
            snapshot / "src/flow.py",
        )
    child = next(
        row for row in fixture.plan["inputs"] if row["path"] == "acceptance/controlled_stage.py"
    )
    child["sha256"] = _sha((FLOW / "run_stage.py").read_bytes())
    fixture.implementation_paths.append("src/flow.py")
    fixture.plan["implementation_paths"] = list(fixture.implementation_paths)
    stage = next(row for row in fixture.plan["stages"] if row["stage_id"] == "integration")
    stage["required_test_ids"] = [
        ["r12_flow.FlowChecks", name]
        for name in ("test_positive", "test_negative", "test_label", "test_missing")
    ]
    stage["artifacts"].append(
        {"path": "integration/trace.json", "format": "file", "required_members": []}
    )
    return fixture


def run_two(fixture: Any) -> PaladinPythonRun:
    """Execute the buggy attempt and then the repaired attempt for real."""
    first = PaladinPythonRun(fixture.runtime, contract=fixture.contract(0))
    first.execute("integration", fixture.action("integration", 0))
    second = PaladinPythonRun(fixture.runtime, contract=fixture.contract(1))
    second.execute("integration", fixture.action("integration", 1))
    return second


def selectors(fixture: Any) -> dict[str, Any]:
    """Select both versions of flow.py and both recorded traces."""
    return {
        "source_spans": tuple(
            {
                "attempt_id": fixture.attempt_ids[index],
                "path": "src/flow.py",
                "start_line": 1,
                "end_line": 9,
            }
            for index in (0, 1)
        ),
        "artifact_paths": tuple(
            {
                "attempt_id": fixture.attempt_ids[index],
                "stage_id": "integration",
                "path": "integration/trace.json",
            }
            for index in (0, 1)
        ),
    }


def _detail(row: dict[str, Any]) -> str:
    kind = row["kind"]
    if kind == "source_span":
        return f"{row['path']}:{row['start_line']}-{row['end_line']}"
    if kind == "artifact":
        return f"{row['stage_id']}:{row['path']}"
    if kind == "stage_result":
        return f"{row['stage_id']}:{row['status']}"
    if kind == "case":
        return f"{row['stage_id']}:{row['name']}:{row['outcome']}"
    raise AssertionError(f"unexpected anchor kind {kind}")


def stable_keys(bundle: dict[str, Any]) -> dict[str, str]:
    """Map each opaque anchor id to a key that survives fresh UUIDs and drawer ids.

    The key includes the observed outcome, so a fresh run whose results differ
    cannot silently inherit the preserved narration.
    """
    index = {row["attempt_id"]: row["index"] for row in bundle["checks"]["attempts"]}
    keys: dict[str, str] = {}
    for row in bundle["anchors"]:
        key = f"{row['kind']}|{index[row['attempt_id']]}|{_detail(row)}"
        if key in keys.values():
            raise AssertionError(f"ambiguous stable anchor key {key}")
        keys[row["id"]] = key
    return keys


def rebind(response: dict[str, Any], old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Point the preserved claims at the same evidence in a fresh run, text unchanged."""
    by_key = {key: anchor for anchor, key in stable_keys(new).items()}
    old_keys = stable_keys(old)

    def move(ref: str) -> str:
        return by_key[old_keys[ref]]

    claims = [
        {
            **claim,
            "subject_ref": move(claim["subject_ref"]),
            "support_refs": [move(ref) for ref in claim["support_refs"]],
        }
        for claim in response["claims"]
    ]
    return {**response, "claims": claims}
