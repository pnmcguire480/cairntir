"""Execute independently frozen managed receipt and projection boundary controls."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_PACKET = _ROOT / "plans/acceptance/managed-session-port"
_BYTES = (_PACKET / "FREEZE.json").read_bytes()
if hashlib.sha256(_BYTES).hexdigest() != (
    "448611a9929ea1af7d39af4ef044563a61cab792a28d58cb3031c56d21b01d8e"
):
    raise pytest.UsageError("managed port independent freeze changed")
for _RELATIVE, _EXPECTED in json.loads(_BYTES)["files_sha256"].items():
    if hashlib.sha256((_PACKET / _RELATIVE).read_bytes()).hexdigest() != _EXPECTED:
        raise pytest.UsageError(f"managed port independent custody changed: {_RELATIVE}")
_SPEC = importlib.util.spec_from_file_location(
    "frozen_managed_durable_boundaries", _PACKET / "test_managed_durable_boundaries.py"
)
if _SPEC is None or _SPEC.loader is None:
    raise pytest.UsageError("managed port independent controls unavailable")
_CONTROLS = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _CONTROLS
_SPEC.loader.exec_module(_CONTROLS)

durable = _CONTROLS.durable
test_caller_transaction_cannot_issue_managed_durable_receipts = (
    _CONTROLS.test_caller_transaction_cannot_issue_managed_durable_receipts
)
test_projection_cannot_publish_caller_uncommitted_checkpoint = (
    _CONTROLS.test_projection_cannot_publish_caller_uncommitted_checkpoint
)
