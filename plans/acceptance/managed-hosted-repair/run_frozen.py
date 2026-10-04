"""Run only the frozen additive normal adapter in an isolated local environment."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CANDIDATE = Path(r"C:\Users\pnmcg\AppData\Local\Temp\cairntir-managed-hosted-repair-20261003")


def main():
    label, router = sys.argv[1:]
    route = Path(router).resolve()
    assert route.is_relative_to(CANDIDATE / "tests")
    frozen = ROOT / "FROZEN.json"
    assert hashlib.sha256(frozen.read_bytes()).hexdigest() == "a76a2d7be6d30b29cf01f8a2e5d5847786328da60605a950f43fedd741b5f946"
    for relative, digest in json.loads(frozen.read_bytes())["files_sha256"].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest, relative
    runtime = ROOT.parent / "runtime" / label
    runtime.mkdir(parents=True)
    env = dict(os.environ)
    env.update(PYTHONPATH=str(CANDIDATE / "src"), PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1",
               PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", MANAGED_REPAIR_CANDIDATE=str(CANDIDATE),
               CAIRNTIR_HOME=str(runtime / "home"), XDG_CACHE_HOME=str(runtime / "cache"),
               HF_HOME=str(runtime / "hf"), HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
               CAIRNTIR_DISABLE_AUTOREGISTER="1", CAIRNTIR_DISABLE_UPDATE_CHECK="1",
               TEMP=str(runtime), TMP=str(runtime))
    source_names = ["scripts/restore_managed_evidence.py", "scripts/verify_package.py",
                    "src/cairntir/managed.py", "src/cairntir/managed_projection.py",
                    "tests/unit/test_managed_port_acceptance.py", "tests/unit/test_managed_runtime.py",
                    "tests/unit/test_last_session_projection.py", "tests/unit/test_managed_installed_qualification.py"]
    source_names.append(route.relative_to(CANDIDATE).as_posix())
    binding = {name: hashlib.sha256((CANDIDATE / name).read_bytes()).hexdigest() for name in source_names}
    (ROOT / (label + "-source.json")).write_text(json.dumps(binding, indent=2) + "\n", encoding="utf-8")
    command = [sys.executable, "-m", "pytest", "-c", str(CANDIDATE / "pyproject.toml"),
               "--rootdir", str(CANDIDATE), "--confcutdir", str(ROOT),
               "--override-ini", "addopts=", "-p", "no:cacheprovider", str(route),
               "--junitxml", str(ROOT / (label + ".xml"))]
    started = time.monotonic()
    result = subprocess.run(command, cwd=CANDIDATE, env=env, capture_output=True, timeout=60)
    (ROOT / (label + ".log")).write_bytes(result.stdout + result.stderr)
    receipt = {"command": command, "exit_code": result.returncode,
               "seconds": time.monotonic() - started, "freeze_sha256": hashlib.sha256(frozen.read_bytes()).hexdigest(),
               "model_install_fullsuite_execution": False}
    (ROOT / (label + ".json")).write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(result.stdout.decode("utf-8", errors="replace"))
    print(result.stderr.decode("utf-8", errors="replace"))
    print(json.dumps(receipt))
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
