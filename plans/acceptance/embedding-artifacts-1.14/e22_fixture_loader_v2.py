"""Normal-CI loader for the independently frozen exact synthetic fixture adapter."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


def pytest_configure(config):
    source = Path(__file__).resolve().parent.parent
    packet = source / "plans" / "acceptance" / "embedding-artifacts-1.14"
    manifest = json.loads((packet / "INTEGRATION-CI-FREEZE.json").read_text(encoding="utf-8"))
    for name, expected in manifest["files_sha256"].items():
        if name == "e22_fixture_loader_v2.py":
            target = source / "tests" / name
        elif name == "test_embedding_artifact_acceptance.py":
            target = source / "tests" / "unit" / name
        else:
            target = packet / name
        if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            raise pytest.UsageError(f"independent E22 fixture adapter custody changed: {target}")
    path = packet / "e22_exact_fixture_adapter_v2.py"
    spec = importlib.util.spec_from_file_location("cairntir_e22_independent_registry_adapter", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    config.pluginmanager.register(module, "cairntir-e22-independent-registry-adapter")
