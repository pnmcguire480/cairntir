"""Normal pytest routing for independently frozen Python and Node acceptance."""

from pathlib import Path
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import unittest

import pytest


HERE = Path(__file__).resolve().parent
PACKET = (
    HERE
    if (HERE / "ORIGINALS-FREEZE.json").exists()
    else (HERE.parent / "plans" / "acceptance" / "obsidian-correction-1.15")
)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise pytest.UsageError(f"cannot load frozen acceptance: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


originals = json.loads((PACKET / "ORIGINALS-FREEZE.json").read_text(encoding="utf-8"))
freeze = json.loads((PACKET / "INTEGRATION-FREEZE.json").read_text(encoding="utf-8"))
for relative, expected in originals["files_sha256"].items():
    path = PACKET / relative
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise pytest.UsageError(f"frozen original acceptance custody changed: {path}")
for relative, expected in freeze["files_sha256"].items():
    path = (
        Path(__file__)
        if relative == "test_obsidian_frozen_acceptance.py"
        else PACKET / relative
    )
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise pytest.UsageError(
            f"frozen integration acceptance custody changed: {path}"
        )

for filename in originals["selected_python"]:
    module = _load(
        "frozen_obsidian_" + Path(filename).stem,
        PACKET / "originals" / "v2-obsidian" / filename,
    )
    for name, value in vars(module).items():
        if isinstance(value, type) and issubclass(value, unittest.TestCase):
            globals()[name] = value

integration = _load("frozen_obsidian_integration", PACKET / "test_integration.py")
for name, value in vars(integration).items():
    if name.startswith("test_") or name == "flow":
        globals()[name] = value


def node_executable():
    node = shutil.which("node")
    if node is None and os.name == "nt":
        installed = (
            Path(os.environ.get("ProgramFiles", "C:/Program Files"))
            / "nodejs"
            / "node.exe"
        )
        if installed.is_file():
            node = str(installed)
    assert node is not None, (
        "Installed Node is required for frozen plugin acceptance; no skip/substitution"
    )
    return node


def test_required_node_v3_plugin_acceptance():
    result = subprocess.run(
        [
            node_executable(),
            str(
                PACKET
                / "originals"
                / "v2-obsidian-plugin"
                / "test-obsidian-plugin-v3.cjs"
            ),
            str(integration.REPO / "addons" / "cairntir_obsidian" / "main.js"),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert '"cases":46' in result.stdout and '"assertions":401' in result.stdout


def test_actual_plugin_python_subprocess():
    result = subprocess.run(
        [
            node_executable(),
            str(PACKET / "test_real_plugin.cjs"),
            str(integration.REPO / "addons" / "cairntir_obsidian" / "main.js"),
            integration.sys.executable,
            str(integration.REPO / "src"),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert '"actual_python_processes":3' in result.stdout
