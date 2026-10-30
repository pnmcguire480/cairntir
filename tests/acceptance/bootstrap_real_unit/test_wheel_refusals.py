"""Original wheel refusals with a genuine independently approved wheel baseline."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from cairntir.paladin_bootstrap import (
    prepare_test_bootstrap,
)

from . import inputs

if sys.flags.optimize:
    raise RuntimeError("Q07 acceptance requires Python assertions")

HERE = Path(__file__).parent

FIXTURES = HERE / "fixtures"

LOCK = HERE / "approved-pytest.lock"

LOCK_SHA256 = "f5f398537450c12c66aee3bb76d2e773bcad55f421568305beeb2bdb251be99d"


def _copy_project(name: str, destination: Path) -> Path:
    return Path(shutil.copytree(FIXTURES / name, destination))


def _tree_hashes(root: Path) -> dict[str, tuple[bool, str]]:
    return {
        path.relative_to(root).as_posix(): (
            path.is_symlink(),
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in root.rglob("*")
        if path.is_file()
    }


def _wheelhouse() -> Path:
    return inputs.settings()["wheelhouse"]


def _uv_executable() -> Path:
    return inputs.settings()["uv_executable"]


def _assert_no_prepared_manifest(bootstrap_root: Path) -> None:
    if not bootstrap_root.exists():
        return
    assert not list(bootstrap_root.rglob("pyvenv.cfg"))
    for path in bootstrap_root.rglob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError):
            continue
        assert not (isinstance(payload, dict) and payload.get("status") == "PREPARED")


def _prepare_blocked(
    project: Path,
    bootstrap_root: Path,
    expected_code: str,
    monkeypatch: pytest.MonkeyPatch,
    *,
    wheelhouse: Path,
    approved_sha256: str = LOCK_SHA256,
) -> None:
    assert hashlib.sha256(LOCK.read_bytes()).hexdigest() == LOCK_SHA256
    project_before = _tree_hashes(project)
    wheelhouse_before = _tree_hashes(wheelhouse)
    lock_before = LOCK.read_bytes()
    real_popen = subprocess.Popen

    def no_install_dispatch(argv, *args, **kwargs):
        tokens = (
            str(argv).lower().split()
            if isinstance(argv, (str, os.PathLike))
            else [str(part).lower() for part in argv]
        )
        assert not {"venv", "pip", "install", "sync", "build"}.intersection(tokens), argv
        assert not (tokens and Path(tokens[0]).stem == "pip"), argv
        assert not any(token.startswith(("http://", "https://")) for token in tokens), argv
        return real_popen(argv, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(subprocess, "Popen", no_install_dispatch)
        result = prepare_test_bootstrap(
            project,
            bootstrap_root,
            python_executable=Path(sys.executable).resolve(),
            uv_executable=_uv_executable(),
            approved_requirements=LOCK,
            approved_sha256=approved_sha256,
            wheelhouse=wheelhouse,
        )

    assert result["status"] == "BLOCKED"
    assert result["blocker"]["code"] == expected_code
    assert _tree_hashes(project) == project_before
    assert _tree_hashes(wheelhouse) == wheelhouse_before
    assert LOCK.read_bytes() == lock_before
    _assert_no_prepared_manifest(bootstrap_root)


@pytest.mark.parametrize(
    ("damage", "code"),
    [
        ("missing", "WHEELHOUSE_INCOMPLETE"),
        ("extra", "WHEELHOUSE_INCOMPLETE"),
        ("corrupt", "WHEEL_HASH_MISMATCH"),
    ],
)
def test_wheelhouse_anomalies_refuse_before_dispatch(
    damage: str, code: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _copy_project("clean", tmp_path / "project")
    wheelhouse = Path(shutil.copytree(_wheelhouse(), tmp_path / "wheels"))
    wheels = sorted(wheelhouse.glob("*.whl"))
    assert len(wheels) == 6
    if damage == "missing":
        wheels[0].unlink()
    elif damage == "extra":
        (wheelhouse / "unexpected-0.0.0-py3-none-any.whl").write_bytes(b"extra wheel")
    else:
        wheels[0].write_bytes(wheels[0].read_bytes() + b"corrupt")

    _prepare_blocked(project, tmp_path / "bootstrap", code, monkeypatch, wheelhouse=wheelhouse)
