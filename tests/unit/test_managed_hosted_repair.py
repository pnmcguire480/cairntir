"""Run independently frozen archive controls and maintained behavioral amendments."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_PACKET = Path(__file__).resolve().parents[2] / "plans/acceptance/managed-hosted-repair"
_PINNED = "a76a2d7be6d30b29cf01f8a2e5d5847786328da60605a950f43fedd741b5f946"
_RAW = (_PACKET / "FROZEN.json").read_bytes()
if hashlib.sha256(_RAW).hexdigest() != _PINNED:
    raise pytest.UsageError("independent hosted repair freeze changed")
for _name, _digest in json.loads(_RAW)["files_sha256"].items():
    if hashlib.sha256((_PACKET / _name).read_bytes()).hexdigest() != _digest:
        raise pytest.UsageError(f"independent hosted repair artifact changed: {_name}")


def _load(name: str, relative: str):
    specification = importlib.util.spec_from_file_location(name, _PACKET / relative)
    if specification is None or specification.loader is None:
        raise pytest.UsageError(f"independent hosted repair controls unavailable: {relative}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


_ARCHIVE = _load("frozen_managed_archive_acceptance", "test_managed_archive_acceptance.py")
_DURABLE = _load("frozen_managed_durable_v4", "active/test_managed_durable_boundaries_v4.py")
_VISIBILITY = _load("frozen_managed_visibility_v3", "active/test_hidden_event_v3.py")
_PROJECTION = _load("frozen_managed_projection_v2", "active/test_managed_projection_v2.py")

for _name, _value in vars(_ARCHIVE).items():
    if _name.startswith("test_") or _name == "fixture":
        globals()[_name] = _value

durable = _DURABLE.durable
test_caller_transaction_cannot_issue_managed_durable_receipts = (
    _DURABLE.test_caller_transaction_cannot_issue_managed_durable_receipts
)
test_projection_cannot_publish_caller_uncommitted_checkpoint = (
    _DURABLE.test_projection_cannot_publish_caller_uncommitted_checkpoint
)
test_hidden_required_event_cannot_become_complete_capture_or_projection = (
    _VISIBILITY.test_hidden_required_event_cannot_become_complete_capture_or_projection
)


class TestMaintainedManagedProjection(_PROJECTION.ManagedProjectionAcceptance):
    pass
