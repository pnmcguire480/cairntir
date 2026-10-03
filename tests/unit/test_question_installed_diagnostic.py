"""Run finite independently frozen installed-question diagnostic controls."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_PACKET = _ROOT / "plans" / "acceptance" / "questions-installed-ci-1.16-v2"
_FREEZE_BYTES = (_PACKET / "FROZEN.json").read_bytes()
if hashlib.sha256(_FREEZE_BYTES).hexdigest() != (
    "e2bdc7b33901223f38f1460b339ebdf484a73ca743ec7c1ad59dfab44ba0c534"
):
    raise pytest.UsageError("installed question diagnostic freeze changed")
_FREEZE = json.loads(_FREEZE_BYTES.decode("utf-8-sig"))
for _RELATIVE, _EXPECTED in _FREEZE["files_sha256"].items():
    if hashlib.sha256((_PACKET / _RELATIVE).read_bytes()).hexdigest() != _EXPECTED:
        raise pytest.UsageError(f"installed question diagnostic custody changed: {_RELATIVE}")

_SPEC = importlib.util.spec_from_file_location(
    "frozen_installed_question_diagnostics", _PACKET / "test_diagnostics.py"
)
if _SPEC is None or _SPEC.loader is None:
    raise pytest.UsageError("installed question diagnostic tests unavailable")
_CONTROLS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_CONTROLS)

test_entire_v1_function_and_all_assertions_unchanged = (
    _CONTROLS.test_entire_v1_function_and_all_assertions_unchanged
)
test_success_preserves_return_and_shutdown_and_observes_files = (
    _CONTROLS.test_success_preserves_return_and_shutdown_and_observes_files
)
test_failure_is_same_exception_no_retry_no_false_pass_and_records_code = (
    _CONTROLS.test_failure_is_same_exception_no_retry_no_false_pass_and_records_code
)
