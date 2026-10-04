"""Run only three frozen inert qualification controls and maintained-file style checks."""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CANDIDATE = Path(r"C:\Users\pnmcg\AppData\Local\Temp\cairntir-managed-work-20261003")
ROUTER = CANDIDATE / "tests/unit/test_managed_installed_qualification.py"


def main():
    runtime = ROOT / "runtime-local"
    runtime.mkdir()
    env = dict(os.environ)
    env.update(PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTHONDONTWRITEBYTECODE="1",
               PYTHONPATH=str(CANDIDATE / "src"), PYTHONUTF8="1",
               CAIRNTIR_HOME=str(runtime / "home"), HF_HOME=str(runtime / "hf"),
               HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
               CAIRNTIR_DISABLE_AUTOREGISTER="1", CAIRNTIR_DISABLE_UPDATE_CHECK="1")
    commands = {
        "local-controls": [sys.executable, "-m", "pytest", "-c", str(CANDIDATE / "pyproject.toml"),
                           "--rootdir", str(CANDIDATE), "--confcutdir", str(ROOT),
                           "--override-ini", "addopts=", "-p", "no:cacheprovider", str(ROUTER),
                           "--junitxml", str(ROOT / "local-controls.xml")],
        "router-lint": [sys.executable, "-m", "ruff", "check", "--config", str(CANDIDATE / "pyproject.toml"), str(ROUTER)],
        "router-format": [sys.executable, "-m", "ruff", "format", "--check", "--config", str(CANDIDATE / "pyproject.toml"), str(ROUTER)],
    }
    for name, command in commands.items():
        result = subprocess.run(command, cwd=CANDIDATE, env=env, capture_output=True, timeout=30)
        (ROOT / (name + ".log")).write_bytes(result.stdout + result.stderr)
        (ROOT / (name + ".json")).write_text(json.dumps({"command": command, "exit_code": result.returncode,
                                                       "no_installed_or_model_execution": True}, indent=2) + "\n", encoding="utf-8")
        print(result.stdout.decode("utf-8", errors="replace"))
        print(result.stderr.decode("utf-8", errors="replace"))
        assert result.returncode == 0, name


if __name__ == "__main__":
    main()
