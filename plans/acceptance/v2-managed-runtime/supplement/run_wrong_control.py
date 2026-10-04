"""Disable only output-overflow detection in an owned disposable candidate copy."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

packet = Path(__file__).resolve().parent
source = Path(sys.argv[1]).resolve()
destination = packet / "wrong-output-control" / "src"
destination.mkdir(parents=True, exist_ok=False)
shutil.copytree(source / "cairntir", destination / "cairntir", ignore=shutil.ignore_patterns("__pycache__"))
module = destination / "cairntir" / "managed.py"
before = module.read_bytes()
needle = b"if len(chunk) > remaining:"
assert before.count(needle) == 1
module.write_bytes(before.replace(needle, b"if False:  # independently disabled overflow detection"))
env = {**os.environ, "PYTHONPATH": str(destination), "PYTHONDONTWRITEBYTECODE": "1"}
result = subprocess.run(
    [sys.executable, str(packet / "test_managed_outcomes.py"),
     "ManagedOutcomeAcceptance.test_output_cap_is_bounded_uncertain_and_never_relaunched"],
    env=env, cwd=packet, capture_output=True, timeout=30,
)
output = result.stdout + result.stderr
(packet / "wrong-output-control.log").write_bytes(output)
detected = result.returncode == 1 and b"FAIL:" in output and b"'completed' != 'uncertain'" in output
receipt = {
    "schema": "cairntir.public-wrong-control.v1",
    "status": "detected" if detected else "unexpected",
    "exit_code": result.returncode,
    "original_managed_sha256": hashlib.sha256(before).hexdigest(),
    "mutant_managed_sha256": hashlib.sha256(module.read_bytes()).hexdigest(),
    "unchanged_test_sha256": hashlib.sha256((packet / "test_managed_outcomes.py").read_bytes()).hexdigest(),
    "log_sha256": hashlib.sha256(output).hexdigest(),
    "mutation": "Only owned copy overflow detector disabled; real child emits 8192 bytes under 128-byte cap.",
}
(packet / "wrong-output-result.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
print(json.dumps(receipt))
raise SystemExit(0 if detected else 1)
