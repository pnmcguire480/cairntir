"""Bounded inert installed-verifier boundary execution with frozen integrity."""

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root = Path(__file__).resolve().parent
    label = sys.argv[1]
    candidate = Path(os.environ["MANAGED_PORTABILITY_CANDIDATE"]).resolve()
    pin = "e51d583bb4f6b562b136f04227d95d0c74e3988b8b2713767c57f8bb566b1eb1"
    assert sha(root / "FROZEN.json") == pin
    for relative, expected in json.loads((root / "FROZEN.json").read_bytes())["files_sha256"].items():
        assert sha(root / relative) == expected
    runtime = root.parent / "runtime" / label
    runtime.mkdir(parents=True)
    environment = os.environ.copy()
    environment.update({"PYTHONPATH": str(candidate / "src"), "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                        "PYTHONDONTWRITEBYTECODE": "1", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"})
    for name in ("HOME", "USERPROFILE", "XDG_CACHE_HOME", "HF_HOME", "TEMP", "TMP"):
        directory = runtime / name.lower()
        directory.mkdir()
        environment[name] = str(directory)
    files = {name: sha(candidate / name) for name in (
        "scripts/verify_package.py", "scripts/restore_managed_evidence.py", "src/cairntir/managed.py",
        "tests/unit/test_managed_runtime.py", "tests/unit/test_last_session_projection.py",
        "tests/unit/test_managed_port_acceptance.py", "tests/unit/test_managed_installed_qualification.py")}
    command = [sys.executable, "-m", "pytest", "-q", "-o", "addopts=", "-p", "no:cacheprovider",
               "--confcutdir", str(root), str(root / "test_installed_boundary.py")]
    start = time.monotonic()
    result = subprocess.run(command, cwd=runtime, env=environment, capture_output=True, timeout=25)
    (root / (label + ".log")).write_bytes(result.stdout + result.stderr)
    receipt = {"command": command, "returncode": result.returncode,
               "seconds": round(time.monotonic() - start, 3), "files_sha256": files,
               "runner_sha256": sha(Path(__file__)), "frozen_sha256": pin}
    (root / (label + "-execution.json")).write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
