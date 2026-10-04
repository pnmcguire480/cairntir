"""Run frozen portability, invocation and foreground protocol acceptance."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_SOURCE = Path(__file__).resolve().parents[2]


def _load(packet: str, freeze: str, pin: str, filename: str):
    root = _SOURCE / "plans/acceptance" / packet
    raw = (root / freeze).read_bytes()
    if hashlib.sha256(raw).hexdigest() != pin:
        raise pytest.UsageError(f"independent hardening freeze changed: {packet}")
    for name, digest in json.loads(raw)["files_sha256"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
            raise pytest.UsageError(f"independent hardening artifact changed: {packet}/{name}")
    name = "frozen_" + packet.replace("-", "_")
    spec = importlib.util.spec_from_file_location(name, root / filename)
    if spec is None or spec.loader is None:
        raise pytest.UsageError(f"independent hardening module unavailable: {packet}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


with patch.dict(os.environ, {"MANAGED_PORTABILITY_CANDIDATE": str(_SOURCE)}):
    _PORTABILITY = _load(
        "managed-installed-boundary",
        "FROZEN-v3.json",
        "f663c514a6d83f180a831737bf1030ff30ad78f568a8ad5ab4fc92fccf50b620",
        "test_installed_boundary_v3.py",
    )

synthetic_checkout = _PORTABILITY.synthetic_checkout
for _name, _value in vars(_PORTABILITY).items():
    if _name.startswith("test_"):
        globals()[_name] = _value

_ENVIRONMENT = _load(
    "managed-environment",
    "FROZEN.json",
    "eae874e88a3d09cba95acd23d56313a1a8ebf04486246f98c52eeb7cc2cec714",
    "test_managed_environment.py",
)


class TestManagedEnvironment(_ENVIRONMENT.ManagedEnvironmentAcceptance):
    pass


_PROTOCOL = _load(
    "managed-protocol",
    "FROZEN-v2.json",
    "0a50afb4b4b820c95335655dde6537f0af4829bec068b84861f635adf27bae25",
    "test_managed_protocol_v2.py",
)
cli_loop = _PROTOCOL.cli_loop
for _name, _value in vars(_PROTOCOL).items():
    if _name.startswith("test_"):
        globals()[_name] = _value
