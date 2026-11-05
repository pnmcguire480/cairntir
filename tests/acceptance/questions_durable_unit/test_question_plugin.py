"""The question plugin's Node matrices and its real Python processes."""

from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().with_name("plugin")
ROOT = PLUGIN.parents[3]
SOURCE = Path(importlib.import_module("cairntir").__file__).resolve().parents[1]


def node_executable():
    node = shutil.which("node")
    if node is None and os.name == "nt":
        installed = Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "nodejs" / "node.exe"
        if installed.is_file():
            node = str(installed)
    assert node is not None, "Node is required for the plugin tests; no skip or substitution"
    return node


def test_missing_node_fails_instead_of_skipping(monkeypatch, tmp_path):
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path))
    with pytest.raises(AssertionError, match="Node is required"):
        node_executable()


@pytest.mark.parametrize(
    "harness", ["test_question_plugin.js", "test_question_plugin_submission.cjs"]
)
def test_original_question_plugin_matrix(harness, tmp_path):
    executable = node_executable()
    environment = os.environ.copy()
    for name in ("TEMP", "TMP", "XDG_CACHE_HOME", "CAIRNTIR_HOME"):
        isolated = tmp_path / name.lower()
        isolated.mkdir()
        environment[name] = str(isolated)
    # The interpreter is installed locally; both scripts and target are repository fixtures.
    result = subprocess.run(  # noqa: S603
        [
            executable,
            str(PLUGIN / harness),
            str(ROOT / "addons" / "cairntir_obsidian" / "main.js"),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_actual_question_plugin_python_processes(tmp_path):
    executable = node_executable()
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
    # Installed interpreter and repository process helper, not user input.
    result = subprocess.run(  # noqa: S603
        [
            executable,
            str(PLUGIN / "test_real_question_plugin.cjs"),
            str(ROOT / "addons" / "cairntir_obsidian" / "main.js"),
            sys.executable,
            str(SOURCE),
            str(PLUGIN / "test_question_plugin_submission.cjs"),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    receipt = json.loads(result.stdout.splitlines()[-1])
    assert receipt["status"] == "PASS" and receipt["actual_plugin_cli_launches"] == 5
