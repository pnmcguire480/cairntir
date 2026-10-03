"""Run separately frozen public R08 process proof without model inference."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_PACKET = _ROOT / "plans" / "acceptance" / "questions-port-1.16" / "process"
_FREEZE = json.loads((_PACKET / "FROZEN.json").read_text(encoding="utf-8"))
for _relative, _expected in _FREEZE["files_sha256"].items():
    if hashlib.sha256((_ROOT / _relative).read_bytes()).hexdigest() != _expected:
        raise pytest.UsageError(f"independent question process custody changed: {_relative}")


def test_actual_question_plugin_python_processes(tmp_path):
    executable = shutil.which("node")
    if executable is None:
        ordinary_windows_path = Path(r"C:\Program Files\nodejs\node.exe")
        if ordinary_windows_path.is_file():
            executable = str(ordinary_windows_path)
    assert executable is not None, "Node is required for the frozen actual-process proof"
    environment = os.environ.copy()
    environment.pop("CAIRNTIR_GRANT_FILE", None)
    for name in ("TEMP", "TMP", "XDG_CACHE_HOME", "CAIRNTIR_HOME", "HF_HOME", "TORCH_HOME"):
        isolated = tmp_path / name.lower()
        isolated.mkdir()
        environment[name] = str(isolated)
    environment.update(
        CAIRNTIR_DISABLE_AUTOREGISTER="1",
        CAIRNTIR_DISABLE_UPDATE_CHECK="1",
        HF_HUB_OFFLINE="1",
        PYTHONUTF8="1",
        PYTHONIOENCODING="utf-8",
    )
    # Installed interpreter and hash-bound synthetic process helper, not user input.
    result = subprocess.run(  # noqa: S603
        [
            executable,
            str(_PACKET / "test_real_question_plugin.cjs"),
            str(_ROOT / "addons" / "cairntir_obsidian" / "main.js"),
            sys.executable,
            str(_ROOT / "src"),
            str(
                _ROOT
                / "plans"
                / "acceptance"
                / "v2-questions"
                / "test_question_plugin_submission.cjs"
            ),
        ],
        cwd=_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    receipt = json.loads(result.stdout.splitlines()[-1])
    assert receipt["status"] == "PASS" and receipt["actual_plugin_cli_launches"] == 5
