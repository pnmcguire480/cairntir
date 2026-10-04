"""Seal bounded caller portability evidence and unchanged prior custody."""

import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root = Path(__file__).resolve().parent
    candidate = Path(r"C:\Users\pnmcg\AppData\Local\Temp\ct-p1004")
    prior = Path(r"C:\Users\pnmcg\AppData\Local\Temp\cairntir-managed-hosted-repair-20261003")
    pin = "5e4c59ffce6d9187ff3e814ba0f7a89aed3b47baf7536a7c1c4d3222280665ae"
    assert sha(root / "FROZEN.json") == pin
    frozen = json.loads((root / "FROZEN.json").read_bytes())
    for relative, expected in frozen["files_sha256"].items():
        assert sha(root / relative) == expected
    old_folder = candidate / "plans/acceptance/managed-hosted-repair"
    old_seal = old_folder / "SEAL.json"
    assert sha(old_seal) == "d51e4ae28afda97d9df1745097a13fa9071a58bb5dab11eca32c70940aca5e86"
    old = json.loads(old_seal.read_bytes())
    for relative, expected in old["files_sha256"].items():
        assert sha(old_folder / relative) == expected
    assert len(old["files_sha256"]) == 49
    previous_packet = root.parents[1] / "cairntir-managed-qualification-20261003"
    previous_seal = previous_packet / "TERMINAL-SEAL.json"
    previous = json.loads(previous_seal.read_bytes())
    for relative, expected in previous["files_sha256"].items():
        assert sha(previous_packet / relative) == expected
    assert len(previous["files_sha256"]) == 83
    source = {path.relative_to(candidate).as_posix(): sha(path)
              for path in sorted((candidate / "src").rglob("*")) if path.is_file()}
    assert all(sha(prior / relative) == expected for relative, expected in source.items())
    baseline = json.loads((root / "baseline-replay-execution.json").read_bytes())
    final = json.loads((root / "candidate-execution.json").read_bytes())
    assert baseline["returncode"] == 1 and final["returncode"] == 0
    assert b"1 failed, 6 passed in 1.13s" in (root / "baseline-replay.log").read_bytes()
    assert b"7 passed in 1.18s" in (root / "candidate.log").read_bytes()
    preservation = {"frozen_artifact_count": len(frozen["files_sha256"]),
                    "old49artifacts_exact": True, "old_seal_sha256": sha(old_seal),
                    "prior83sealedfiles_exact": True,
                    "prior_terminal_seal_sha256": sha(previous_seal),
                    "all_source_files_unchanged": len(source), "source_files_sha256": source,
                    "final_routing_files_sha256": final["files_sha256"]}
    (root / "PRESERVATION.json").write_text(json.dumps(preservation, indent=2) + "\n")
    result = {"result": "PASS finite caller-only portability amendment; actual macOS hosted collection pending",
              "authoritative_baseline": {"passed": 6, "expected_failed": 1, "pytest_seconds": 1.13,
                                          "wall_seconds": baseline["seconds"]},
              "candidate": {"passed": 7, "skipped": 0, "pytest_seconds": 1.18,
                            "wall_seconds": final["seconds"]},
              "initial_receipt": "Invalidated as preservation-harness history after case-insensitive receipt filename collision; original frozen baseline restored exactly; authoritative replay uses distinct receipt name",
              "review": "Only four module-level caller Path(...).resolve() additions; every other router byte, helper/verifier byte and all source files unchanged. Unsafe source/archive link rejection remains demonstrated",
              "installed_paths": "CLI output.resolve() canonicalizes TemporaryDirectory(dir=output); no installed routing change needed",
              "limits": ["Mocked filesystem alias with no privileged symlink creation",
                         "No local full suite, models, installs or API use",
                         "Fresh hosted macOS collection, CI and CodeQL required; no hosted pass claimed"],
              "preservation_sha256": sha(root / "PRESERVATION.json")}
    (root / "FINAL-RESULT.json").write_text(json.dumps(result, indent=2) + "\n")
    files = {path.relative_to(root).as_posix(): sha(path) for path in sorted(root.rglob("*"))
             if path.is_file() and path.name != "SEAL.json"}
    (root / "SEAL.json").write_text(json.dumps({"files_sha256": files,
        "frozen_sha256": pin, "artifact_count": len(files)}, indent=2) + "\n")
    print(json.dumps({"seal_sha256": sha(root / "SEAL.json"), "artifacts": len(files),
                      "preservation_sha256": sha(root / "PRESERVATION.json")}, indent=2))


if __name__ == "__main__":
    main()
