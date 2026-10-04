"""Run frozen managed durability, corrected file fixtures, and visibility control."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import pytest

_SOURCE = Path(__file__).resolve().parents[2]
_RESTORE_SPEC = importlib.util.spec_from_file_location(
    "managed_evidence_restore", _SOURCE / "scripts/restore_managed_evidence.py"
)
if _RESTORE_SPEC is None or _RESTORE_SPEC.loader is None:
    raise RuntimeError("managed evidence reconstruction helper is unavailable")
_RESTORE = importlib.util.module_from_spec(_RESTORE_SPEC)
_RESTORE_SPEC.loader.exec_module(_RESTORE)
_EVIDENCE_TEMP = tempfile.TemporaryDirectory(prefix="cairntir-managed-evidence-")
_EVIDENCE_ROOT = _RESTORE.restore(_SOURCE, Path(_EVIDENCE_TEMP.name).resolve() / "snapshot")
_PACKET = _EVIDENCE_ROOT / "plans/acceptance/managed-session-port"


def _verify(directory: Path, expected: str) -> None:
    raw = (directory / "FREEZE.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise pytest.UsageError("independent managed port freeze changed")
    frozen = json.loads(raw.decode("utf-8-sig"))
    for relative, digest in frozen["files_sha256"].items():
        if hashlib.sha256((directory / relative).read_bytes()).hexdigest() != digest:
            raise pytest.UsageError(f"independent managed port custody changed: {relative}")
    for relative, digest in frozen.get("fixture_dependency_sha256", {}).items():
        if hashlib.sha256((_PACKET / relative).read_bytes()).hexdigest() != digest:
            raise pytest.UsageError(f"independent managed fixture changed: {relative}")


def _load(name: str, path: Path):
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise pytest.UsageError("independent managed port controls unavailable")
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


_verify(_PACKET, "448611a9929ea1af7d39af4ef044563a61cab792a28d58cb3031c56d21b01d8e")
_verify(
    _PACKET / "marker-amendment-v2",
    "ac1899dfe2232e3c3ad7afb84c3dedd9fa127a15b72a0cd15a303ef276958328",
)
_verify(
    _PACKET / "raw-projection-amendment-v3",
    "71b3a6897fe3de130f664af9c960efb50847a65af56a8cc6ec46bfd538c0b575",
)
_verify(
    _PACKET / "visibility-v1",
    "b4ed819a5d0ebc88f8f8514841a0cedca1dc7b480c9c675fea5eb8711c007310",
)
_verify(
    _PACKET / "visibility-v2",
    "5334505390aa967d2e2f02e0825fe2bc51effd9cd5c2cc0bd37582847b37e330",
)
_CONTROLS = _load(
    "frozen_managed_durable_boundaries",
    _PACKET / "raw-projection-amendment-v3/test_managed_durable_boundaries_v3.py",
)
_VISIBILITY = _load("frozen_managed_visibility", _PACKET / "visibility-v2/test_hidden_event_v2.py")

durable = _CONTROLS.durable
test_caller_transaction_cannot_issue_managed_durable_receipts = (
    _CONTROLS.test_caller_transaction_cannot_issue_managed_durable_receipts
)
test_projection_cannot_publish_caller_uncommitted_checkpoint = (
    _CONTROLS.test_projection_cannot_publish_caller_uncommitted_checkpoint
)
test_hidden_required_event_cannot_become_complete_capture_or_projection = (
    _VISIBILITY.test_hidden_required_event_cannot_become_complete_capture_or_projection
)
