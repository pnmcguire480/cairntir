"""Doctor must recognize hosts wired through the `cairntir-mcp` launcher."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cairntir.hosts import inspect_host


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.mark.parametrize(
    "command",
    [
        "cairntir-mcp",
        "cairntir-mcp.exe",
        "CAIRNTIR-MCP.EXE",
        r"C:\Tools\Scripts\cairntir-mcp.exe",
        "/home/me/.venv/bin/cairntir-mcp",
    ],
)
def test_launcher_entry_counts_as_configured(tmp_path: Path, command: str) -> None:
    _write_json(
        tmp_path / ".cursor" / "mcp.json",
        {"mcpServers": {"cairntir": {"command": command, "args": ["--host", "cursor"]}}},
    )
    status = inspect_host("cursor", scope="project", root=tmp_path, home=tmp_path)
    assert status.mcp_configured is True


def test_opencode_folded_launcher_counts_as_configured(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "opencode.json",
        {"mcp": {"cairntir": {"command": ["cairntir-mcp", "--host", "opencode"]}}},
    )
    status = inspect_host("opencode", scope="project", root=tmp_path, home=tmp_path / "home")
    assert status.mcp_configured is True


def test_codex_launcher_counts_as_configured(tmp_path: Path) -> None:
    config = tmp_path / ".codex" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text(
        '[mcp_servers.cairntir]\ncommand = "cairntir-mcp"\nargs = ["--host", "codex"]\n',
        encoding="utf-8",
    )
    status = inspect_host("codex", scope="project", root=tmp_path, home=tmp_path / "home")
    assert status.mcp_configured is True


@pytest.mark.parametrize(
    "entry",
    [
        {"command": "cairntir-mcp", "args": ["--host", "qwen"]},
        {"command": "cairntir-mcp"},
        {"command": "cairntir-mcp", "args": "--host cursor"},
        {"command": "not-cairntir-mcp", "args": ["--host", "cursor"]},
        {"command": "cairntir", "args": ["--host", "cursor"]},
        {"command": ["cairntir-mcp", 7], "args": []},
        {"args": ["--host", "cursor"]},
    ],
)
def test_other_entries_are_still_reported_missing(tmp_path: Path, entry: dict[str, object]) -> None:
    _write_json(tmp_path / ".cursor" / "mcp.json", {"mcpServers": {"cairntir": entry}})
    status = inspect_host("cursor", scope="project", root=tmp_path, home=tmp_path)
    assert status.mcp_configured is False
