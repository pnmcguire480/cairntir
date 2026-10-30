"""Existing malformed metadata refusals, before any tool dispatch."""

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from cairntir import paladin_bootstrap as bootstrap

if sys.flags.optimize:
    raise RuntimeError("Q07 acceptance requires Python assertions")

HERE = Path(__file__).resolve().parent

BASE = HERE

LOCK = BASE / "approved-pytest.lock"

LOCK_SHA256 = "f5f398537450c12c66aee3bb76d2e773bcad55f421568305beeb2bdb251be99d"


def _settings() -> dict:
    assert hashlib.sha256(LOCK.read_bytes()).hexdigest() == LOCK_SHA256
    repo = Path(os.environ["Q07_REPO"]).resolve()
    assert Path(bootstrap.__file__).resolve().is_relative_to(repo / "src")
    return {
        "python_executable": Path(os.environ["Q07_PYTHON"]).resolve(),
        "uv_executable": Path(os.environ["Q07_UV"]).resolve(),
        "approved_requirements": LOCK,
        "approved_sha256": LOCK_SHA256,
        "wheelhouse": Path(os.environ["Q07_WHEELHOUSE"]).resolve(),
    }


@pytest.mark.parametrize("malformation", ["nonstring-name", "nontable-pytest"])
def test_malformed_metadata_refuses_before_tool_dispatch(
    malformation: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = Path(shutil.copytree(BASE / "fixtures/clean", tmp_path / "project"))
    config = project / "pyproject.toml"
    text = config.read_text(encoding="utf-8")
    if malformation == "nonstring-name":
        text = text.replace('name = "decision-log-fixture"', "name = 7")
    else:
        text = text.replace(
            '[tool.pytest.ini_options]\npythonpath = ["src"]\ntestpaths = ["tests"]',
            '[tool]\npytest = "invalid"',
        )
    config.write_text(text, encoding="utf-8")
    assert text != (BASE / "fixtures/clean/pyproject.toml").read_text(encoding="utf-8")

    def no_dispatch(*args, **kwargs):
        raise AssertionError("Malformed project dispatched a tool")

    with monkeypatch.context() as patch:
        patch.setattr(subprocess, "Popen", no_dispatch)
        inspected = bootstrap.inspect_test_infrastructure(project)
        assert inspected["status"] == "BLOCKED"
        assert inspected["blocker"]["code"] == "UNSUPPORTED_STACK"
        prepared = bootstrap.prepare_test_bootstrap(project, tmp_path / "output", **_settings())
    assert prepared["status"] == "BLOCKED"
    assert prepared["blocker"]["code"] == "UNSUPPORTED_STACK"
    assert not (tmp_path / "output").exists()
