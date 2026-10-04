"""Seal finite independent foreground managed protocol controls and history."""

import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root = Path(__file__).resolve().parent
    candidate = Path(r"C:\Users\pnmcg\AppData\Local\Temp\ct-r1004")
    pins = {"FROZEN.json": "dc2ba602e71599f142f0515d2efd7fad14972a981819167cccdf1dd5b9060a2a",
            "FROZEN-v2.json": "0a50afb4b4b820c95335655dde6537f0af4829bec068b84861f635adf27bae25"}
    for name, expected in pins.items():
        assert sha(root / name) == expected
        for relative, digest in json.loads((root / name).read_bytes())["files_sha256"].items():
            assert sha(root / relative) == digest
    collection = json.loads((root / "normal-execution.json").read_bytes())
    normal = json.loads((root / "normal-v2-execution.json").read_bytes())
    wrong = json.loads((root / "wrong-control-execution.json").read_bytes())
    assert collection["returncode"] == 2
    assert normal["returncode"] == 0
    assert wrong["expected_wrong_control_failure"]
    assert b"33 passed in 1.41s" in (root / "normal-v2.log").read_bytes()
    assert b"1 failed in 0.38s" in (root / "wrong-control.log").read_bytes()
    for receipt in (collection, normal, wrong):
        assert receipt["files_sha256"] == normal["files_sha256"]
    assert all(sha(candidate / relative) == expected
               for relative, expected in normal["files_sha256"].items())
    result = {"result": "PASS bounded public managed JSONL protocol controls",
              "normal": {"passed": 33, "skipped": 0, "pytest_seconds": 1.41,
                         "wall_seconds": normal["seconds"]},
              "wrong_control": {"expected_failed": 1, "pytest_seconds": 0.38,
                               "wall_seconds": wrong["seconds"],
                               "oracle": "Unchanged refusal assertion rejects unsupported start routed to dispatch"},
              "fixture_history": "v1 pytest collection error from reserved request parameter retained; v2 changes first test parameter/local identifier to payload and sorts imports; all56 normalized assertion ASTs retained",
              "runtime_changes_by_tester": False,
              "source_files_sha256": normal["files_sha256"],
              "freezes_sha256": pins,
              "normal_public_module": "test_managed_protocol_v2.py",
              "normal_public_fixture": "cli_loop",
              "runner_history": "run.py timeout60 original retained; run_v2 timeout25 before execution; run_v3 uses additive fixture v2",
              "limits": ["Synthetic/inert stores and actual Typer loop; no configured process dispatched",
                         "No production model loading, installation, API use, full local suite or coverage execution",
                         "Coverage floor and complete qualification remain hosted checks; no coverage improvement claimed here"]}
    (root / "FINAL-RESULT.json").write_text(json.dumps(result, indent=2) + "\n")
    files = {path.relative_to(root).as_posix(): sha(path)
             for path in sorted(root.rglob("*")) if path.is_file() and path.name != "SEAL.json"}
    (root / "SEAL.json").write_text(json.dumps({"files_sha256": files,
        "artifact_count": len(files), "result_sha256": sha(root / "FINAL-RESULT.json")}, indent=2) + "\n")
    print(json.dumps({"seal_sha256": sha(root / "SEAL.json"), "artifact_count": len(files),
                      "result_sha256": sha(root / "FINAL-RESULT.json")}, indent=2))


if __name__ == "__main__":
    main()
