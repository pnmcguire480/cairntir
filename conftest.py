"""Register independently frozen E22 fixtures without editing historical fixtures."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


def pytest_configure(config):
    """Load the guarded E22 adapter through the existing frozen loader."""
    source = Path(__file__).resolve().parent
    packet = source / "plans" / "acceptance" / "embedding-artifacts-1.14"
    manifest = json.loads((packet / "ROOT-ROUTING-FREEZE.json").read_text(encoding="utf-8"))
    for name, expected in manifest["files_sha256"].items():
        target = source / "conftest.py" if name == "root_conftest.py" else packet / name
        if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            raise pytest.UsageError(f"independent E22 fixture routing custody changed: {target}")
    historical = source / "tests" / "conftest.py"
    if (
        hashlib.sha256(historical.read_bytes()).hexdigest()
        != manifest["historical_conftest_sha256"]
    ):
        raise pytest.UsageError("historical tests/conftest.py must remain byte-identical")
    path = source / "tests" / "e22_fixture_loader_v2.py"
    spec = importlib.util.spec_from_file_location("cairntir_e22_frozen_fixture_loader", path)
    if spec is None or spec.loader is None:
        raise pytest.UsageError(f"cannot load independently frozen E22 fixture loader: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.pytest_configure(config)
