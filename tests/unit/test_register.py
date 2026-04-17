"""Tests for the silent self-heal registration helper."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from cairntir import register


@pytest.fixture()
def _tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("CAIRNTIR_HOME", str(home))
    # Re-enable the helper for these focused tests — conftest disables
    # it globally so unrelated tests stay quiet.
    monkeypatch.delenv("CAIRNTIR_DISABLE_AUTOREGISTER", raising=False)
    return home


def test_disable_env_var_short_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAIRNTIR_DISABLE_AUTOREGISTER", "1")
    assert register.ensure_registered() == "disabled"


def test_no_claude_returns_status(_tmp_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    assert register.ensure_registered() == "no-claude"


def test_present_when_listing_already_contains_cairntir(
    _tmp_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: "/fake/claude")

    class _Listing:
        returncode = 0
        stdout = "some-other: ok\ncairntir: connected\n"
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *_a, **_kw: _Listing())

    assert register.ensure_registered() == "present"
    # Checkpoint written so the next call short-circuits.
    assert (register._checkpoint_path()).exists()


def test_registered_when_add_succeeds(
    _tmp_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: "/fake/claude")

    calls: list[list[str]] = []

    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def _fake_run(cmd: list[str], **_: Any) -> _Result:
        calls.append(cmd)
        if cmd[1:3] == ["mcp", "list"]:
            r = _Result()
            r.stdout = "no cairntir here\n"
            return r
        return _Result()

    monkeypatch.setattr(subprocess, "run", _fake_run)

    assert register.ensure_registered() == "registered"
    add_call = calls[1]
    # Must register the stable shim, not python -m
    assert add_call[1:] == [
        "mcp",
        "add",
        "-s",
        "user",
        "cairntir",
        "--",
        "cairntir-mcp",
    ]


def test_already_exists_treated_as_success(
    _tmp_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: "/fake/claude")

    class _Listing:
        returncode = 0
        stdout = "no cairntir\n"
        stderr = ""

    class _Exists:
        returncode = 1
        stdout = ""
        stderr = "MCP server cairntir already exists in user config"

    def _fake_run(cmd: list[str], **_: Any) -> Any:
        if cmd[1:3] == ["mcp", "list"]:
            return _Listing()
        return _Exists()

    monkeypatch.setattr(subprocess, "run", _fake_run)
    assert register.ensure_registered() == "registered"


def test_checkpoint_short_circuits_on_fast_path(
    _tmp_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    register._checkpoint_path().write_text("ok\n", encoding="utf-8")

    def _should_not_be_called(_name: str) -> str | None:
        raise AssertionError("checkpoint must short-circuit before claude lookup")

    monkeypatch.setattr(shutil, "which", _should_not_be_called)
    assert register.ensure_registered() == "checkpoint"


def test_force_bypasses_checkpoint(
    _tmp_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    register._checkpoint_path().write_text("ok\n", encoding="utf-8")
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    assert register.ensure_registered(force=True) == "no-claude"


def test_clear_checkpoint_removes_file(_tmp_home: Path) -> None:
    p = register._checkpoint_path()
    p.write_text("ok\n", encoding="utf-8")
    register.clear_checkpoint()
    assert not p.exists()
    # Idempotent: second call on a missing file does not raise.
    register.clear_checkpoint()


def test_subprocess_failure_returns_failed(
    _tmp_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: "/fake/claude")

    class _Listing:
        returncode = 0
        stdout = "no cairntir\n"
        stderr = ""

    class _Fail:
        returncode = 2
        stdout = ""
        stderr = "kaboom"

    def _fake_run(cmd: list[str], **_: Any) -> Any:
        if cmd[1:3] == ["mcp", "list"]:
            return _Listing()
        return _Fail()

    monkeypatch.setattr(subprocess, "run", _fake_run)
    assert register.ensure_registered() == "failed"


def test_oserror_during_list_skips_to_register(
    _tmp_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If `claude mcp list` raises, we should still attempt the add."""
    monkeypatch.setattr(shutil, "which", lambda _name: "/fake/claude")

    calls: list[list[str]] = []

    class _Ok:
        returncode = 0
        stdout = ""
        stderr = ""

    def _fake_run(cmd: list[str], **_: Any) -> Any:
        calls.append(cmd)
        if cmd[1:3] == ["mcp", "list"]:
            raise OSError("transient")
        return _Ok()

    monkeypatch.setattr(subprocess, "run", _fake_run)
    assert register.ensure_registered() == "registered"
    assert any(c[1:3] == ["mcp", "add"] for c in calls)
