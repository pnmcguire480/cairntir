"""Freeze independent controls and exact historical/platform inputs before porting."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
OLD = Path(r"C:\Users\pnmcg\AppData\Local\Temp\cairntir-final-0930")
BASE = Path(r"C:\Users\pnmcg\AppData\Local\Temp\cairntir-managed-work-20261003")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


originals = HERE / "originals"
originals.mkdir(exist_ok=True)
for name, source in {
    "managed.py": OLD / "plans/acceptance/home-host-capture-20261001/evidence/source-baseline/managed.py",
    "managed_projection.py": OLD / "src/cairntir/managed_projection.py",
}.items():
    target = originals / name
    if target.exists():
        raise RuntimeError("original already copied")
    target.write_bytes(source.read_bytes())
runtime = OLD / "plans/acceptance/v2-managed-runtime"
projection = OLD / "plans/acceptance/v2-managed-projection"
historical = {
    str(root / name): sha(root / name)
    for root, names in (
        (runtime, ("PACKAGE-FROZEN.json", "CORE-FROZEN.json", "PROCESS-FROZEN.json",
                   "CLOSE-FROZEN.json", "CONFIG-FROZEN.json", "STATE-FROZEN.json",
                   "STATE-FOLLOWUP.json")),
        (runtime / "supplement", ("PACKAGE.json", "FROZEN.json")),
        (projection, ("PACKAGE-FROZEN.json", "FROZEN.json", "CORRUPTION-FROZEN.json",
                      "OUTCOME-FROZEN.json")),
    )
    for name in names
}
platform = {
    name: sha(BASE / name)
    for name in ("src/cairntir/memory/store.py", "src/cairntir/access.py",
                 "src/cairntir/tasks.py", "src/cairntir/durability.py",
                 "src/cairntir/obsidian.py", "src/cairntir/cli.py", "src/cairntir/questions.py")
}
expectations = {
    "base_head": "c71abb6808dffe75d9c303734f80f667d5c81cba",
    "historical_manifests_sha256": historical,
    "platform_source_sha256": platform,
    "runtime_input_sha256": sha(originals / "managed.py"),
    "projection_input_sha256": sha(originals / "managed_projection.py"),
    "historical_controls": {"runtime": 28, "runtime_outcomes": 11,
                            "projection": 16, "projection_supplement": 4},
    "historical_paths_are_inert_reference_only": True,
    "fresh_candidate_binding_required_before_each_execution": True,
    "structural_absence": {
        "managed_module_absent": not (BASE / "src/cairntir/managed.py").exists(),
        "projection_module_absent": not (BASE / "src/cairntir/managed_projection.py").exists(),
        "not_a_runtime_regression_claim": True,
    },
}
(HERE / "INPUT-EXPECTATIONS.json").write_text(json.dumps(expectations, indent=2), encoding="utf-8")
names = ("CONTRACT.md", "test_managed_durable_boundaries.py", "bypass_guard_control.py",
         "INPUT-EXPECTATIONS.json", "originals/managed.py", "originals/managed_projection.py")
freeze = {
    "frozen_at_utc": datetime.now(UTC).isoformat(),
    "version": 1,
    "cases": 24,
    "files_sha256": {name: sha(HERE / name) for name in names},
    "runtime_tests_executed": False,
    "scope": "existing explicit managed foreground runtime plus explicit Last Session projection",
    "repair_rounds": 2,
    "verification_reserve_fraction": 0.25,
}
target = HERE / "FREEZE.json"
if target.exists():
    raise RuntimeError("append-only freeze already exists")
target.write_text(json.dumps(freeze, indent=2), encoding="utf-8")
print(json.dumps({"freeze_sha256": sha(target), "tests_sha256": sha(HERE / names[1]),
                  "runtime_input_sha256": expectations["runtime_input_sha256"],
                  "projection_input_sha256": expectations["projection_input_sha256"]}, indent=2))
