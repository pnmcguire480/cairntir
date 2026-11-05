"""The Obsidian plugin's Node harness and its real Python processes."""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
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


def test_required_node_v3_plugin_acceptance():
    result = subprocess.run(  # noqa: S603
        [
            node_executable(),
            str(
                HERE / "plugin" / "originals" / "v2-obsidian-plugin" / "test-obsidian-plugin-v3.cjs"
            ),
            str(ROOT / "addons" / "cairntir_obsidian" / "main.js"),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=False,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert '"cases":46' in result.stdout and '"assertions":401' in result.stdout


def test_actual_plugin_python_subprocess():
    result = subprocess.run(  # noqa: S603
        [
            node_executable(),
            str(HERE / "plugin" / "test_real_plugin.cjs"),
            str(ROOT / "addons" / "cairntir_obsidian" / "main.js"),
            sys.executable,
            str(SOURCE),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=False,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert '"actual_python_processes":3' in result.stdout
