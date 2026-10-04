"""Seal installed-proof caller boundary evidence and unchanged original custody."""

import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_seal(folder, expected_count, expected_digest):
    path = folder / "SEAL.json"
    assert sha(path) == expected_digest
    files = json.loads(path.read_bytes())["files_sha256"]
    assert len(files) == expected_count
    assert all(sha(folder / relative) == expected for relative, expected in files.items())
    return expected_digest


def main():
    root = Path(__file__).resolve().parent
    candidate = Path(r"C:\Users\pnmcg\AppData\Local\Temp\ct-i1004")
    prior = Path(r"C:\Users\pnmcg\AppData\Local\Temp\ct-r1004")
    freezes = {"FROZEN.json": "e51d583bb4f6b562b136f04227d95d0c74e3988b8b2713767c57f8bb566b1eb1",
               "FROZEN-v3.json": "f663c514a6d83f180a831737bf1030ff30ad78f568a8ad5ab4fc92fccf50b620"}
    for name, pin in freezes.items():
        assert sha(root / name) == pin
        files = json.loads((root / name).read_bytes())["files_sha256"]
        assert all(sha(root / relative) == expected for relative, expected in files.items())
    old_pin = "5c7d52db32d06b13305ca7986ce45de7aa19c5a850cf544031e24490e49a1091"
    verify_seal(root / "originals/portability", 23, old_pin)
    verify_seal(candidate / "plans/acceptance/managed-portability", 23, old_pin)
    source = {path.relative_to(candidate).as_posix(): sha(path)
              for path in sorted((candidate / "src").rglob("*"))
              if path.is_file() and "__pycache__" not in path.parts and path.suffix not in {".pyc", ".pyo"}}
    assert all(sha(prior / relative) == expected for relative, expected in source.items())
    helper = "scripts/restore_managed_evidence.py"
    assert sha(candidate / helper) == sha(prior / helper)
    baseline = json.loads((root / "baseline-execution.json").read_bytes())
    fixture = json.loads((root / "candidate-execution.json").read_bytes())
    final = json.loads((root / "candidate-v3-execution.json").read_bytes())
    assert baseline["returncode"] == 1 and fixture["returncode"] == 1 and final["returncode"] == 0
    assert b"4 failed, 6 passed in 2.07s" in (root / "baseline.log").read_bytes()
    assert b"1 failed, 9 passed in 2.63s" in (root / "candidate.log").read_bytes()
    assert b"10 passed in 2.61s" in (root / "candidate-v3.log").read_bytes()
    assert all(sha(candidate / name) == expected for name, expected in final["files_sha256"].items())
    result = {"result": "PASS finite installed-proof caller boundary repair; full hosted qualification pending",
              "baseline": {"passed": 6, "target_failed": 4, "pytest_seconds": 2.07,
                           "wall_seconds": baseline["seconds"]},
              "retained_fixture_failure": {"passed": 9, "fixture_failed": 1, "pytest_seconds": 2.63,
                                          "wall_seconds": fixture["seconds"]},
              "final": {"passed": 10, "skipped": 0, "pytest_seconds": 2.61,
                        "wall_seconds": final["seconds"]},
              "review": "Only verifier TemporaryDirectory parent and canonical directory assignment change; all44 installed assertion ASTs identical; strict restore helper and runtime unchanged",
              "proof": "Historical actual install_and_verify rejects output-inside-checkout and modeled temp alias before first tool; amended actual function restores all8 original resources outside ROOT and reaches only an inert first-tool sentinel",
              "no_real_tools_installation_or_models": True,
              "fixture_amendment": "v3 corrects one leftover inherited expected AST string; original v2/old7security and byte oracles and failures retained",
              "source_files_sha256": source, "boundary_bindings_sha256": final["files_sha256"],
              "prior23capsule_and_copy_exact": True, "prior23seal_sha256": old_pin,
              "freezes_sha256": freezes, "normal_module": "test_installed_boundary_v3.py",
              "normal_fixture": "synthetic_checkout",
              "limits": ["Modeled platform alias; actual macOS routing remains hosted proof",
                         "Only first tool boundary executed with inert shim; full installed/model stages remain hosted checks",
                         "No local full suite or coverage run; no full qualification claim"]}
    (root / "FINAL-RESULT.json").write_text(json.dumps(result, indent=2) + "\n")
    files = {path.relative_to(root).as_posix(): sha(path) for path in sorted(root.rglob("*"))
             if path.is_file() and path != root / "SEAL.json"}
    (root / "SEAL.json").write_text(json.dumps({"files_sha256": files, "artifact_count": len(files),
        "result_sha256": sha(root / "FINAL-RESULT.json")}, indent=2) + "\n")
    print(json.dumps({"seal_sha256": sha(root / "SEAL.json"), "artifacts": len(files),
                      "result_sha256": sha(root / "FINAL-RESULT.json")}, indent=2))


if __name__ == "__main__":
    main()
