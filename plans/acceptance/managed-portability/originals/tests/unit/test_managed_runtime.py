"""Run independently frozen managed-runtime acceptance with immutable byte checks."""

import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

import cairntir.managed

_SOURCE = Path(__file__).resolve().parents[2]
_RESTORE_SPEC = importlib.util.spec_from_file_location(
    "managed_evidence_restore", _SOURCE / "scripts/restore_managed_evidence.py"
)
if _RESTORE_SPEC is None or _RESTORE_SPEC.loader is None:
    raise RuntimeError("managed evidence reconstruction helper is unavailable")
_RESTORE = importlib.util.module_from_spec(_RESTORE_SPEC)
_RESTORE_SPEC.loader.exec_module(_RESTORE)
_EVIDENCE_TEMP = tempfile.TemporaryDirectory(prefix="cairntir-managed-evidence-")
_EVIDENCE_ROOT = _RESTORE.restore(_SOURCE, Path(_EVIDENCE_TEMP.name) / "snapshot")
PACKET = _EVIDENCE_ROOT / "plans/acceptance/v2-managed-runtime"
PACKAGE_SHA256 = "5ddb331d10e66649c18c3f18d4e67d0d6d33769f0cb8452ee8b625e21422936e"
FOLLOWUP_SHA256 = "53e32d6df660e315868de4ee5b41eea924607f315091d0c7429266c35f34afdd"


def _verify():
    raw = (PACKET / "PACKAGE-FROZEN.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == PACKAGE_SHA256
    for name, digest in json.loads(raw)["files"].items():
        assert hashlib.sha256((PACKET / name).read_bytes()).hexdigest() == digest, name
    raw = (PACKET / "STATE-FOLLOWUP.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FOLLOWUP_SHA256
    for name, digest in json.loads(raw)["files"].items():
        assert hashlib.sha256((PACKET / name).read_bytes()).hexdigest() == digest, name
    for name in (
        "CORE-FROZEN.json",
        "PROCESS-FROZEN.json",
        "CLOSE-FROZEN.json",
        "CONFIG-FROZEN.json",
        "STATE-FROZEN.json",
    ):
        frozen = json.loads((PACKET / name).read_bytes())
        for filename, digest in {**frozen["files"], **frozen.get("fixture_dependency", {})}.items():
            assert hashlib.sha256((PACKET / filename).read_bytes()).hexdigest() == digest, filename


def _load(name):
    spec = importlib.util.spec_from_file_location("frozen_managed_" + name, PACKET / name)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_verify()
_core = _load("test_managed_core.py")
_process = _load("test_managed_process.py")
_close = _load("test_managed_close.py")
with patch.dict(sys.modules, {"test_managed_process": _process}):
    _config = _load("test_managed_config.py")
with patch.dict(sys.modules, {"test_managed_close": _close}):
    _state = _load("test_managed_state.py")
SUITES = {
    "core": _core.ManagedCoreAcceptance,
    "process": _process.ManagedProcessAcceptance,
    "close": _close.ManagedCloseAcceptance,
    "config": _config.ManagedConfigurationAcceptance,
    "state": _state.ManagedStateAcceptance,
}
CASES = [
    (suite, name)
    for suite, case_type in SUITES.items()
    for name in unittest.defaultTestLoader.getTestCaseNames(case_type)
]
MODEL_CASES = {
    "test_real_cli_jsonl_start_capture_brief_ack_dispatch_close",
    "test_cli_changed_config_cannot_launch_using_previous_ack",
}


@pytest.mark.parametrize(("suite", "name"), CASES, ids=[name for _, name in CASES])
def test_frozen_managed_runtime(tmp_path, monkeypatch, suite, name):
    if name in MODEL_CASES and not os.environ.get("MANAGED_ACCEPTANCE_MODEL_CACHE"):
        pytest.skip(
            "Set MANAGED_ACCEPTANCE_MODEL_CACHE to run the explicit "
            "offline production-model CLI gate"
        )
    monkeypatch.setenv("PYTHONPATH", str(Path(cairntir.managed.__file__).resolve().parents[1]))
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
