"""Independent regression for persisted Codex launchers with Unicode paths."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import pytest

from cairntir.hosts import configure_host


@pytest.mark.parametrize("directory", ["plain-project", "café-project", "🧭-project"])
def test_codex_project_configuration_preserves_unicode_interpreter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, directory: str
) -> None:
    interpreter = tmp_path / directory / ".venv" / "bin" / "python"
    monkeypatch.setattr(sys, "executable", str(interpreter))
    project = tmp_path / "configured-project"
    result = configure_host(
        "codex",
        scope="project",
        root=project,
        home=tmp_path / "user",
        install_policy=False,
    )
    assert result.registration == "created"
    target = project / ".codex" / "config.toml"
    assert result.registration_path == target
    persisted = target.read_text(encoding="utf-8")
    try:
        parsed = tomllib.loads(persisted)
    except tomllib.TOMLDecodeError as exc:
        raise AssertionError(
            f"COUNCIL_TOML: configure_host reported created; invalid persisted TOML: {persisted!r}"
        ) from exc
    assert parsed["mcp_servers"]["cairntir"] == {
        "command": str(interpreter),
        "args": ["-m", "cairntir.mcp.server", "--host", "codex"],
    }
    repeated = configure_host(
        "codex",
        scope="project",
        root=project,
        home=tmp_path / "user",
        install_policy=False,
    )
    assert repeated.registration == "unchanged"
    assert target.read_text(encoding="utf-8") == persisted
