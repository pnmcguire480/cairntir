"""Route independently frozen question-port controls through ordinary pytest."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_PACKET = _ROOT / "plans" / "acceptance" / "questions-port-1.16"
_FREEZE = json.loads((_PACKET / "FREEZE.json").read_text(encoding="utf-8"))
for _relative, _expected in _FREEZE["files_sha256"].items():
    if hashlib.sha256((_ROOT / _relative).read_bytes()).hexdigest() != _expected:
        raise pytest.UsageError(f"independent question-port custody changed: {_relative}")
_SPEC = importlib.util.spec_from_file_location(
    "frozen_question_durable_ack", _PACKET / "test_questions_durable_ack.py"
)
if _SPEC is None or _SPEC.loader is None:
    raise pytest.UsageError("cannot load frozen question durable-ack controls")
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
for _name, _value in vars(_MODULE).items():
    if _name.startswith("test_") or _name == "durable":
        globals()[_name] = _value


@pytest.mark.parametrize(
    "harness", ["test_question_plugin.js", "test_question_plugin_submission.cjs"]
)
def test_original_question_plugin_matrix(harness, tmp_path):
    executable = shutil.which("node")
    if executable is None:
        ordinary_windows_path = Path(r"C:\Program Files\nodejs\node.exe")
        if ordinary_windows_path.is_file():
            executable = str(ordinary_windows_path)
    assert executable is not None, "Node is required to run the frozen public plugin matrices"
    environment = os.environ.copy()
    for name in ("TEMP", "TMP", "XDG_CACHE_HOME", "CAIRNTIR_HOME"):
        isolated = tmp_path / name.lower()
        isolated.mkdir()
        environment[name] = str(isolated)
    # The interpreter is installed locally; both scripts and target are hash-bound fixtures.
    result = subprocess.run(  # noqa: S603
        [
            executable,
            str(_ROOT / "plans" / "acceptance" / "v2-questions" / harness),
            str(_ROOT / "addons" / "cairntir_obsidian" / "main.js"),
        ],
        cwd=_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
