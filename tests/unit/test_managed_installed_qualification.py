"""Verify frozen installed proof custody and rejection of false success locally."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
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
ROOT = _EVIDENCE_ROOT / "plans/acceptance/managed-installed-qualification"
FROZEN_SHA256 = "53a59ffa4e0dbfded002cc505ad335062074321faf8f70d4a841b1f4c612e0ad"


def _helper():
    raw = (ROOT / "FROZEN.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FROZEN_SHA256
    for relative, digest in json.loads(raw)["files_sha256"].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest, relative
    specification = importlib.util.spec_from_file_location(
        "frozen_managed_installed_qualification", ROOT / "verify_installed_managed.py"
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_installed_proof_retains_exact_historical_case_identity():
    helper = _helper()
    assert callable(helper.verify_installed_managed)
    contract = json.loads((ROOT / "FROZEN.json").read_bytes())
    assert contract["production_cli_cases"] == 2 and contract["projection_api_cases"] == 2
    assert contract["originals_byte_identical"] is True


def test_installed_proof_cannot_report_pass_after_unchanged_case_failure():
    class Failed(unittest.TestCase):
        def runTest(self):  # noqa: N802 - required unittest override
            self.assertEqual("false durable receipt", "committed original evidence")

    with pytest.raises(AssertionError, match="false durable receipt"):
        _helper()._run_suite(unittest.TestSuite([Failed()]))


def test_installed_proof_cannot_substitute_skips_for_model_cases():
    class Skipped(unittest.TestCase):
        def runTest(self):  # noqa: N802 - required unittest override
            self.skipTest("production model prerequisite missing")

    with pytest.raises(AssertionError, match="production model prerequisite missing"):
        _helper()._run_suite(unittest.TestSuite([Skipped()]))
