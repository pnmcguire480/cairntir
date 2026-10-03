"""Pytest integration for independently frozen E22 synthetic review controls."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parent


def _source_root():
    configured = os.environ.get("CAIRNTIR_REVIEW_SOURCE_ROOT")
    if configured:
        return Path(configured).resolve()
    for parent in HERE.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "src/cairntir").is_dir():
            return parent
    raise AssertionError("Place the review packet beneath its source checkout or set CAIRNTIR_REVIEW_SOURCE_ROOT")


@pytest.mark.parametrize("runner,expected_cases", [
    ("run_review_portable.py", 8),
    ("hub_layout_control_v2.py", 3),
    ("cache_permission_control.py", 1),
])
def test_frozen_e22_review(runner, expected_cases, tmp_path, monkeypatch):
    freeze = json.loads((HERE / "PYTEST-FREEZE.json").read_text(encoding="utf-8-sig"))
    for name, expected in freeze["files_sha256"].items():
        assert hashlib.sha256((HERE / name).read_bytes()).hexdigest() == expected, name
    report = tmp_path / (Path(runner).stem + ".json")
    spec = importlib.util.spec_from_file_location("e22_review_" + Path(runner).stem, HERE / runner)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(sys, "argv", [runner, "--source-root", str(_source_root()), "--report", str(report)])
    code = module.main()
    result = json.loads(report.read_text(encoding="utf-8"))
    assert code == 0, result
    assert result["cases"] == expected_cases, result
    assert result["failures"] == [] and result["errors"] == [], result
    if runner == "run_review_portable.py":
        assert result["wrong_control"]["disable_preload_verification_detected"] is True
