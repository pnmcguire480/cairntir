"""Existing Q07 refusal controls; deliberately no valid installation baseline."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from cairntir.paladin_bootstrap import (
    inspect_test_infrastructure,
    prepare_test_bootstrap,
)

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
    value = os.environ.get("Q07_WHEELHOUSE")
    assert value, "Q07_WHEELHOUSE must name the controlled empty predispatch directory"
    path = Path(value).resolve(strict=True)
    assert path.is_dir()
    return path


def _uv_executable() -> Path:
    value = os.environ.get("Q07_UV")
    assert value, "Set Q07_UV to the approved uv executable"
    return Path(value).resolve(strict=True)


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
    ("name", "code"),
    [("unsupported-js", "UNSUPPORTED_STACK"), ("mixed", "MIXED_STACK")],
)
def test_unsupported_stack_is_named_and_never_prepared(
    name: str, code: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _copy_project(name, tmp_path / "project")
    inspection = inspect_test_infrastructure(project)
    assert inspection["status"] == "BLOCKED"
    assert inspection["blocker"]["code"] == code
    _prepare_blocked(project, tmp_path / "bootstrap", code, monkeypatch, wheelhouse=_wheelhouse())


def test_wrong_lock_sha_refuses_before_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _copy_project("clean", tmp_path / "project")
    _prepare_blocked(
        project,
        tmp_path / "bootstrap",
        "UNAPPROVED_LOCK",
        monkeypatch,
        wheelhouse=_wheelhouse(),
        approved_sha256="0" * 64,
    )


def test_source_symlink_or_pytest_path_escape_is_unsafe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _copy_project("clean", tmp_path / "project")
    outside = tmp_path / "outside.py"
    outside.write_text("SECRET = 'outside'\n", encoding="utf-8")
    link = project / "src" / "outside.py"
    try:
        link.symlink_to(outside)
    except OSError:
        outside_tests = tmp_path / "outside-tests"
        outside_tests.mkdir()
        (outside_tests / "test_escape.py").write_text("def test_escape(): pass\n", encoding="utf-8")
        config = project / "pyproject.toml"
        config.write_text(
            config.read_text(encoding="utf-8").replace(
                'testpaths = ["tests"]', 'testpaths = ["../outside-tests"]'
            ),
            encoding="utf-8",
        )
    outside_before = outside.read_bytes()

    inspection = inspect_test_infrastructure(project)
    assert inspection["status"] == "BLOCKED"
    assert inspection["blocker"]["code"] == "UNSAFE_INPUT"
    _prepare_blocked(
        project,
        tmp_path / "bootstrap",
        "UNSAFE_INPUT",
        monkeypatch,
        wheelhouse=_wheelhouse(),
    )
    assert outside.read_bytes() == outside_before


def test_absent_tests_are_not_a_prepared_bootstrap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _copy_project("clean", tmp_path / "project")
    (project / "tests" / "test_decision_log.py").unlink()
    inspection = inspect_test_infrastructure(project)
    assert inspection["status"] == "BLOCKED"
    assert inspection["blocker"]["code"] == "NO_TESTS"
    _prepare_blocked(
        project, tmp_path / "bootstrap", "NO_TESTS", monkeypatch, wheelhouse=_wheelhouse()
    )
