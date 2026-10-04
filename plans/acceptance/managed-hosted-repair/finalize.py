"""Append final independent source binding and bounded repair receipts."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root = Path(__file__).resolve().parent
    candidate = Path(r"C:\Users\pnmcg\AppData\Local\Temp\cairntir-managed-hosted-repair-20261003")
    prior = Path(r"C:\Users\pnmcg\AppData\Local\Temp\cairntir-managed-work-20261003")
    pin = "a76a2d7be6d30b29cf01f8a2e5d5847786328da60605a950f43fedd741b5f946"
    assert sha(root / "FROZEN.json") == pin
    frozen = json.loads((root / "FROZEN.json").read_bytes())
    public = candidate / "plans/acceptance/managed-hosted-repair"
    assert sha(public / "FROZEN.json") == pin
    for name, digest in frozen["files_sha256"].items():
        assert sha(root / name) == digest and sha(public / name) == digest
    runtime = [
        "src/cairntir/managed.py", "src/cairntir/managed_projection.py", "src/cairntir/access.py",
        "src/cairntir/memory/store.py", "src/cairntir/cli.py", "src/cairntir/tasks.py",
        "src/cairntir/obsidian.py",
    ]
    assert all(sha(candidate / name) == sha(prior / name) for name in runtime)
    consumers = [
        "scripts/restore_managed_evidence.py", "scripts/verify_package.py",
        "scripts/check_verification_preservation.py", "tests/unit/test_managed_runtime.py",
        "tests/unit/test_last_session_projection.py", "tests/unit/test_managed_port_acceptance.py",
        "tests/unit/test_managed_installed_qualification.py", "tests/unit/test_managed_hosted_repair.py",
        "plans/acceptance/managed-evidence-archive/resources.zip", ".github/workflows/ci.yml",
        ".github/workflows/codeql.yml", "pyproject.toml",
    ]
    binding = {
        "files_sha256": {name: sha(candidate / name) for name in runtime + consumers},
        "runtime_byte_identical_to_pre_repair_candidate": True,
        "frozen_artifacts_exact_in_candidate": len(frozen["files_sha256"]),
        "freeze_sha256": pin,
    }
    (root / "SOURCE-BINDINGS.json").write_text(json.dumps(binding, indent=2) + "\n")
    for suffix in ("json", "log"):
        shutil.copyfile(root.parent / ("independent-amendment." + suffix), root / ("normal-adapter." + suffix))
    normal = json.loads((root / "normal-adapter.json").read_bytes())
    negative = json.loads((root / "negative-control.json").read_bytes())
    assert normal["returncode"] == 0
    assert b"50 passed, 1 skipped, 9 subtests passed" in (root / "normal-adapter.log").read_bytes()
    assert negative["expected_failed_rejection_assertion"] and negative["candidate_helper_unchanged"]
    result = {
        "result": "PASS bounded amendment acceptance; hosted qualification pending",
        "normal_execution_owner": "root, immutable receipt independently inspected",
        "normal": {"passed": 50, "skipped": 1, "subtests_passed": 9, "pytest_seconds": 4.78,
                   "wall_seconds": normal["seconds"]},
        "skip": "Inherited Windows symlink privilege prerequisite in original projection controls",
        "negative": {"expected_failed_cases": 1, "pytest_seconds": 0.17,
                     "wall_seconds": negative["seconds"], "unchanged_rejection_oracle": True},
        "contract": {"resources": 8, "packets": 4, "frozen_artifacts": 38,
                     "original_manifest_entries_verified": 250,
                     "packaging_cases": 15, "durable_visibility_cases": 25, "projection_cases": 11},
        "review": "No additional defect found in validate-before-write helper, trusted member paths, snapshot lifetime or installed copy/pin routing",
        "assertions": "All 33 durable assertion ASTs and 14 normalized visibility assertion ASTs retained; projection AST identical after diagnostic normalization; old consumer bodies/assertions retained",
        "limits": ["No local full suite, coverage, model load or installed package execution",
                   "Fresh hosted CI and CodeQL remain required; no hosted pass claimed"],
        "source_bindings_sha256": sha(root / "SOURCE-BINDINGS.json"),
    }
    (root / "FINAL-RESULT.json").write_text(json.dumps(result, indent=2) + "\n")
    files = {
        file.relative_to(root).as_posix(): sha(file)
        for file in sorted(root.rglob("*"))
        if file.is_file() and file.name != "SEAL.json"
    }
    seal = {"files_sha256": files, "frozen_contract_sha256": pin,
            "result_sha256": sha(root / "FINAL-RESULT.json"), "artifact_count": len(files)}
    (root / "SEAL.json").write_text(json.dumps(seal, indent=2) + "\n")
    print(json.dumps({"seal_sha256": sha(root / "SEAL.json"), "artifacts": len(files),
                      "source_bindings_sha256": sha(root / "SOURCE-BINDINGS.json")}, indent=2))


if __name__ == "__main__":
    main()
