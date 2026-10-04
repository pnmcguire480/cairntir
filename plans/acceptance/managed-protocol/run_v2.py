"""Run only frozen managed protocol cases in bounded isolated processes."""

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
    candidate = Path(os.environ["MANAGED_PROTOCOL_CANDIDATE"]).resolve()
    pin = "dc2ba602e71599f142f0515d2efd7fad14972a981819167cccdf1dd5b9060a2a"
    assert sha(root / "FROZEN.json") == pin
    for name, expected in json.loads((root / "FROZEN.json").read_bytes())["files_sha256"].items():
        assert sha(root / name) == expected
    runtime = root.parent / "runtime" / label
    runtime.mkdir(parents=True)
    environment = os.environ.copy()
    environment.update({"PYTHONPATH": str(candidate / "src") + os.pathsep + str(root),
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTHONDONTWRITEBYTECODE": "1",
        "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"})
    for name in ("HOME", "USERPROFILE", "XDG_CACHE_HOME", "HF_HOME", "TEMP", "TMP"):
        directory = runtime / name.lower()
        directory.mkdir()
        environment[name] = str(directory)
    source = {name: sha(candidate / name) for name in (
        "src/cairntir/managed.py", "src/cairntir/cli.py", "src/cairntir/tasks.py",
        "src/cairntir/memory/store.py", "src/cairntir/access.py")}
    command = [sys.executable, "-m", "pytest", "-q", "-o", "addopts=", "-p", "no:cacheprovider",
               "--confcutdir", str(root)]
    if label == "wrong-control":
        command += ["-p", "wrong_control", str(root / "test_managed_protocol.py")
                    + "::test_rejected_envelope_cannot_call_runtime_or_dispatch[supplied5]"]
    else:
        command += [str(root / "test_managed_protocol.py")]
    start = time.monotonic()
    result = subprocess.run(command, cwd=runtime, env=environment, capture_output=True, timeout=25)
    output = result.stdout + result.stderr
    (root / (label + ".log")).write_bytes(output)
    receipt = {"command": command, "returncode": result.returncode,
        "seconds": round(time.monotonic() - start, 3), "files_sha256": source,
        "freeze_sha256": pin, "runner_sha256": sha(Path(__file__)),
        "expected_wrong_control_failure": label == "wrong-control" and result.returncode == 1
                                           and b"DID NOT RAISE" in output}
    (root / (label + "-execution.json")).write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    if label == "wrong-control":
        assert receipt["expected_wrong_control_failure"]
    else:
        sys.exit(result.returncode)


if __name__ == "__main__":
    main()
