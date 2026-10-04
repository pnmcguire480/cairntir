"""Preserve a case-insensitive receipt collision and restore exact frozen bytes."""

import hashlib
import json
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent
    original = root / "BASELINE.json"
    collision = original.read_bytes()
    receipt = json.loads(collision)
    assert receipt["returncode"] == 1 and "files_sha256" in receipt
    preserved = root / "baseline-execution.json"
    assert not preserved.exists()
    original.rename(preserved)
    routers = ["tests/unit/" + name for name in (
        "test_managed_runtime.py", "test_last_session_projection.py",
        "test_managed_port_acceptance.py", "test_managed_installed_qualification.py",
    )]
    unchanged = ["scripts/restore_managed_evidence.py", "scripts/verify_package.py"]
    data = {"routers": routers,
            "unchanged": {relative: receipt["files_sha256"][relative] for relative in unchanged},
            "input_head": "ca96e787"}
    original.write_text(json.dumps(data, indent=2) + "\n")
    expected = json.loads((root / "FROZEN.json").read_bytes())["files_sha256"]["BASELINE.json"]
    actual = hashlib.sha256(original.read_bytes()).hexdigest()
    assert actual == expected
    old_runner = (root / "run.py").read_bytes()
    revised = old_runner.replace(b'(label + ".json")', b'(label + "-execution.json")')
    assert revised != old_runner
    (root / "run_v2.py").write_bytes(revised)
    amendment = {"fixture_issue": "Windows case-insensitive baseline.json collided with BASELINE.json after valid baseline test execution",
                 "preserved_receipt_sha256": hashlib.sha256(collision).hexdigest(),
                 "restored_baseline_sha256": actual, "original_freeze_unchanged": True,
                 "old_runner_sha256": hashlib.sha256(old_runner).hexdigest(),
                 "new_runner_sha256": hashlib.sha256(revised).hexdigest(),
                 "amendment": "Only receipt filename adds -execution; test bytes and assertions unchanged"}
    (root / "FIXTURE-AMENDMENT.json").write_text(json.dumps(amendment, indent=2) + "\n")
    print(json.dumps(amendment, indent=2))


if __name__ == "__main__":
    main()
