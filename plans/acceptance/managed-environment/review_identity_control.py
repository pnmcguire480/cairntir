"""Post-freeze review probe: remove canonical binding in memory, never on disk."""
import hashlib
import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
REPO = Path(os.environ["MANAGED_REVIEW_SOURCE"])
SOURCE = REPO / "src/cairntir/managed.py"
sha = lambda data: hashlib.sha256(data).hexdigest()
source_before = sha(SOURCE.read_bytes())
assert source_before == "7d1c1bfb8ebee9ee3eff89b5bdd5b87c9108830a98091c02d54cdd4dff652a93"
manifest_raw = (ROOT / "FROZEN.json").read_bytes()
assert sha(manifest_raw) == "eae874e88a3d09cba95acd23d56313a1a8ebf04486246f98c52eeb7cc2cec714"
for name, digest in json.loads(manifest_raw)["files_sha256"].items():
    assert sha((ROOT / name).read_bytes()) == digest
baseline = json.loads((ROOT / "BASELINE.json").read_text(encoding="utf-8-sig"))
assert sha((ROOT / "baseline.log").read_bytes()) == baseline["log_sha256"]
assert baseline["exit_code"] == 1
candidate_dir = ROOT.parents[1] / "cairntir-managed-hardening-20261004"
candidate_receipt = candidate_dir / "environment-unittest-round1.json"
candidate_log = candidate_dir / "environment-unittest-round1.log"
assert json.loads(candidate_receipt.read_text())["returncode"] == 0
assert "OK (skipped=1)" in candidate_log.read_text()

import cairntir.managed as managed
import test_managed_environment as tests

original = managed._configuration
def without_identity(value):
    result = original(value)
    for profile in result["profiles"].values():
        profile.pop("executable_path")
    return result

names = [
    "test_exact_invocation_and_input_preserved_but_canonical_target_is_bound",
    "test_same_byte_target_retarget_after_ack_refuses_dispatch_without_writes",
]
stream = io.StringIO()
with patch.object(managed, "_configuration", without_identity), patch.object(tests, "_configuration", without_identity):
    suite = unittest.TestSuite(tests.ManagedEnvironmentAcceptance(name) for name in names)
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
log = stream.getvalue()
(ROOT / "identity-bypass.log").write_text(log, encoding="utf-8")
assert len(result.failures) == 2 and not result.errors and not result.skipped, log
assert "same-byte target retargeting lost its identity binding" in log
assert "forbidden dispatch" in log
assert sha(SOURCE.read_bytes()) == source_before
for name, digest in json.loads(manifest_raw)["files_sha256"].items():
    assert sha((ROOT / name).read_bytes()) == digest
receipt = {
    "negative_control": "PASS: canonical identity bypass rejected by both unchanged frozen controls",
    "mutant_result": "2 failures, 0 errors, 0 skips",
    "observed_failures": ["same-byte target identity binding collapsed", "retargeted action reached forbidden Popen"],
    "source_sha256": source_before,
    "source_and_frozen_tests_unchanged": True,
    "baseline_log_sha256": baseline["log_sha256"],
    "candidate_clean_receipt_sha256": sha(candidate_receipt.read_bytes()),
    "candidate_clean_log_sha256": sha(candidate_log.read_bytes()),
    "negative_log_sha256": sha((ROOT / "identity-bypass.log").read_bytes()),
    "qualification": "Windows inert controls pass; actual POSIX venv/module witness and hosted full gates remain required",
}
(ROOT / "IDENTITY-BYPASS.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
print(log)
print(json.dumps(receipt, indent=2))
