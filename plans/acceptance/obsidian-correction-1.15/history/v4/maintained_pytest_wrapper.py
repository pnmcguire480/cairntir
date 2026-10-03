"""Collect the independently frozen correction acceptance during normal pytest."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

import pytest

_packet = (
    Path(__file__).resolve().parents[1]
    / "plans"
    / "acceptance"
    / "obsidian-correction-1.15"
)
_manifest = json.loads(
    (_packet / "INTEGRATION-FREEZE.json").read_text(encoding="utf-8")
)
_expected = _manifest["files_sha256"]["maintained_pytest_wrapper.py"]
if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != _expected:
    raise pytest.UsageError("independently frozen Obsidian pytest routing changed")
_path = _packet / "test_obsidian_frozen_acceptance.py"
_spec = importlib.util.spec_from_file_location("frozen_obsidian_acceptance", _path)
if _spec is None or _spec.loader is None:
    raise pytest.UsageError(
        f"cannot load independently frozen Obsidian acceptance: {_path}"
    )
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
for _name, _value in vars(_module).items():
    if (
        _name.startswith("test_")
        or _name == "flow"
        or (isinstance(_value, type) and issubclass(_value, unittest.TestCase))
    ):
        globals()[_name] = _value
