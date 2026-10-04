"""Run frozen managed outcome acceptance after validating every packet byte."""

import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

import pytest

PACKET = Path(__file__).resolve().parents[2] / "plans/acceptance/v2-managed-runtime/supplement"
PACKAGE_SHA256 = "a74ed500834440c6ba70b452c13f5ac2bca4027e8d4d82efb14ff2101c4c537d"


def _verify():
    raw = (PACKET / "PACKAGE.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == PACKAGE_SHA256
    for name, digest in json.loads(raw)["files"].items():
        assert hashlib.sha256((PACKET / name).read_bytes()).hexdigest() == digest, name


def _load(name):
    spec = importlib.util.spec_from_file_location("frozen_outcomes_" + name, PACKET / name)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_verify()
_runtime = _load("test_managed_outcomes.py")
_projection = _load("projection-subpacket/test_projection_supplement.py")
SUITES = {
    "runtime": _runtime.ManagedOutcomeAcceptance,
    "projection": _projection.ProjectionSupplementAcceptance,
}
CASES = [
    (suite, name)
    for suite, case_type in SUITES.items()
    for name in unittest.defaultTestLoader.getTestCaseNames(case_type)
]


@pytest.mark.parametrize(("suite", "name"), CASES, ids=[name for _, name in CASES])
def test_frozen_managed_outcome(tmp_path, monkeypatch, suite, name):
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CAIRNTIR_DISABLE_AUTOREGISTER", "1")
    monkeypatch.setenv("CAIRNTIR_DISABLE_UPDATE_CHECK", "1")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("PYTHONUTF8", "1")
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    result = unittest.TestResult()
    SUITES[suite](name).run(result)
    assert not result.errors, "\n".join(detail for _, detail in result.errors)
    assert not result.failures, "\n".join(detail for _, detail in result.failures)
    assert not result.skipped
    assert result.testsRun == 1
