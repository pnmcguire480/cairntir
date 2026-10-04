"""One inert archive-member hash bypass; retain the frozen rejection oracle."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CANDIDATE = Path(os.environ["MANAGED_REPAIR_CANDIDATE"]).resolve()
RUNTIME = ROOT.parent / "runtime" / "member-hash-bypass"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    helper = CANDIDATE / "scripts/restore_managed_evidence.py"
    original = helper.read_bytes()
    old = b"if hashlib.sha256(data).hexdigest() != expected:"
    assert original.count(old) == 1
    altered = original.replace(old, b"if False:  # deliberate inert negative control")
    RUNTIME.mkdir(parents=True)
    mutation = RUNTIME / "candidate/scripts/restore_managed_evidence.py"
    mutation.parent.mkdir(parents=True)
    mutation.write_bytes(altered)
    proof = {
        "runner_sha256": sha(Path(__file__).read_bytes()),
        "candidate_helper_sha256": sha(original),
        "mutated_helper_sha256": sha(altered),
        "acceptance_sha256": sha((ROOT / "test_managed_archive_acceptance.py").read_bytes()),
        "freeze_sha256": sha((ROOT / "FROZEN.json").read_bytes()),
        "mutation": "Disable only individual member content hash rejection; transport and membership checks retained",
        "oracle": "Unchanged frozen content-defect case must fail DID NOT RAISE",
        "no_candidate_write": True,
    }
    (ROOT / "NEGATIVE-FROZEN.json").write_text(json.dumps(proof, indent=2) + "\n")
    environment = os.environ.copy()
    environment.update({
        "MANAGED_REPAIR_CANDIDATE": str(RUNTIME / "candidate"),
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
    })
    for key in ("HOME", "USERPROFILE", "XDG_CACHE_HOME", "HF_HOME", "TEMP", "TMP"):
        path = RUNTIME / key.lower()
        path.mkdir()
        environment[key] = str(path)
    command = [
        sys.executable, "-m", "pytest", "-q", "-o", "addopts=", "-p", "no:cacheprovider",
        "--confcutdir", str(ROOT),
        str(ROOT / "test_managed_archive_acceptance.py")
        + "::test_archive_structural_defects_reject_after_independent_transport_binding[content]",
    ]
    started = time.monotonic()
    result = subprocess.run(command, env=environment, cwd=RUNTIME, capture_output=True, timeout=30)
    output = result.stdout + result.stderr
    (ROOT / "negative-control.log").write_bytes(output)
    receipt = {
        "command": command,
        "returncode": result.returncode,
        "seconds": round(time.monotonic() - started, 3),
        "expected_failed_rejection_assertion": result.returncode == 1 and b"DID NOT RAISE" in output,
        "candidate_helper_unchanged": sha(helper.read_bytes()) == proof["candidate_helper_sha256"],
        "negative_freeze_sha256": sha((ROOT / "NEGATIVE-FROZEN.json").read_bytes()),
    }
    (ROOT / "negative-control.json").write_text(json.dumps(receipt, indent=2) + "\n")
    assert receipt["expected_failed_rejection_assertion"] and receipt["candidate_helper_unchanged"]
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
