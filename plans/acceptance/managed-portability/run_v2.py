"""Record one bounded, isolated seven-case portability execution."""

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
    pin = "5e4c59ffce6d9187ff3e814ba0f7a89aed3b47baf7536a7c1c4d3222280665ae"
    assert sha(root / "FROZEN.json") == pin
    for relative, expected in json.loads((root / "FROZEN.json").read_bytes())["files_sha256"].items():
        assert sha(root / relative) == expected
    baseline = json.loads((root / "BASELINE.json").read_bytes())
    bindings = {relative: sha(candidate / relative)
                for relative in baseline["routers"] + list(baseline["unchanged"])}
    runtime = root.parent / "runtime" / label
    runtime.mkdir(parents=True)
    environment = os.environ.copy()
    environment.update({"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTHONDONTWRITEBYTECODE": "1",
                        "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"})
    for name in ("HOME", "USERPROFILE", "XDG_CACHE_HOME", "HF_HOME", "TEMP", "TMP"):
        directory = runtime / name.lower()
        directory.mkdir()
        environment[name] = str(directory)
    command = [sys.executable, "-m", "pytest", "-q", "-o", "addopts=", "-p", "no:cacheprovider",
               "--confcutdir", str(root), str(root / "test_portability.py")]
    start = time.monotonic()
    result = subprocess.run(command, env=environment, cwd=runtime, capture_output=True, timeout=45)
    (root / (label + ".log")).write_bytes(result.stdout + result.stderr)
    receipt = {"command": command, "returncode": result.returncode,
               "seconds": round(time.monotonic() - start, 3), "files_sha256": bindings,
               "runner_sha256": sha(Path(__file__)), "frozen_sha256": pin}
    (root / (label + "-execution.json")).write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
