"""Smoke tests for the ``cairntir`` CLI."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from cairntir import __version__
from cairntir.cli import app
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer, Layer

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_root_banner() -> None:
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "cairntir" in result.stdout


def test_status_empty(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))  # type: ignore[attr-defined]
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "not yet initialized" in result.stdout or "empty" in result.stdout


def test_recall_no_store(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))  # type: ignore[attr-defined]
    result = runner.invoke(app, ["recall", "anything"])
    assert result.exit_code == 1
    assert "no store" in result.stderr.lower() or "no store" in result.output.lower()


def test_status_and_recall_with_drawers(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))  # type: ignore[attr-defined]
    store = DrawerStore(tmp_path / "cairntir.db", HashEmbeddingProvider())
    store.add(
        Drawer(
            wing="demo",
            room="notes",
            content="cairn stones mark the path",
            layer=Layer.ESSENTIAL,
        )
    )
    store.add(
        Drawer(
            wing="demo",
            room="notes",
            content="palantir sees across distance",
            layer=Layer.ON_DEMAND,
        )
    )

    status = runner.invoke(app, ["status"])
    assert status.exit_code == 0
    assert "2 drawers" in status.stdout
    # Regression: each wing must be printed exactly once.
    assert status.stdout.count("  demo  (") == 1

    recall = runner.invoke(app, ["recall", "cairn stones mark the path", "--limit", "5"])
    assert recall.exit_code == 0
    assert "hit" in recall.stdout


def test_migrate_check_reports_version(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))  # type: ignore[attr-defined]
    # Force the store into existence at the current schema version.
    from cairntir.config import db_path
    from cairntir.memory.store import SCHEMA_VERSION

    DrawerStore(db_path(), HashEmbeddingProvider()).close()

    result = runner.invoke(app, ["migrate", "--check"])
    assert result.exit_code == 0
    assert f"library version:  {SCHEMA_VERSION}" in result.stdout
    assert f"current version:  {SCHEMA_VERSION}" in result.stdout


def test_migrate_missing_db_exits_nonzero(tmp_path: Path) -> None:
    result = runner.invoke(app, ["migrate", str(tmp_path / "nope.db")])
    assert result.exit_code == 1


def test_init_writes_project_mcp_json(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    target = tmp_path / ".mcp.json"
    assert target.exists()
    import sys

    data = json.loads(target.read_text(encoding="utf-8"))
    # Pinned to the current interpreter so Claude Code spawns the
    # Python that actually has Cairntir installed, not bare `python`.
    assert data["mcpServers"]["cairntir"]["command"] == sys.executable
    assert data["mcpServers"]["cairntir"]["args"] == ["-m", "cairntir.mcp.server"]
    assert "registered cairntir" in result.stdout


def test_init_is_idempotent(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    runner.invoke(app, ["init"])
    second = runner.invoke(app, ["init"])
    assert second.exit_code == 0
    assert "already registered" in second.stdout


def test_init_preserves_other_mcp_servers(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    target = tmp_path / ".mcp.json"
    target.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "other": {"command": "node", "args": ["server.js"]},
                }
            }
        ),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    data = json.loads(target.read_text(encoding="utf-8"))
    assert "other" in data["mcpServers"]
    assert data["mcpServers"]["other"]["command"] == "node"
    assert "cairntir" in data["mcpServers"]


def test_init_user_shells_out_to_claude_cli(monkeypatch: object) -> None:
    import shutil
    import subprocess
    from typing import Any

    calls: list[list[str]] = []

    class _Result:
        returncode = 0
        stdout = "Added stdio MCP server cairntir to user config"
        stderr = ""

    def _fake_which(name: str) -> str | None:
        return "/fake/claude" if name == "claude" else None

    def _fake_run(cmd: list[str], **_: Any) -> _Result:
        calls.append(cmd)
        return _Result()

    monkeypatch.setattr(shutil, "which", _fake_which)  # type: ignore[attr-defined]
    monkeypatch.setattr(subprocess, "run", _fake_run)  # type: ignore[attr-defined]

    result = runner.invoke(app, ["init", "--user"])
    assert result.exit_code == 0, result.stdout
    assert "user scope" in result.stdout
    assert calls, "claude CLI was never invoked"
    import sys

    assert calls[0][1:] == [
        "mcp",
        "add",
        "-s",
        "user",
        "cairntir",
        "--",
        sys.executable,
        "-m",
        "cairntir.mcp.server",
    ]


def test_init_user_is_idempotent_on_already_exists(monkeypatch: object) -> None:
    import shutil
    import subprocess
    from typing import Any

    class _AlreadyExists:
        returncode = 1
        stdout = ""
        stderr = "MCP server cairntir already exists in user config"

    def _fake_which(name: str) -> str | None:
        return "/fake/claude" if name == "claude" else None

    def _fake_run(_cmd: list[str], **_: Any) -> _AlreadyExists:
        return _AlreadyExists()

    monkeypatch.setattr(shutil, "which", _fake_which)  # type: ignore[attr-defined]
    monkeypatch.setattr(subprocess, "run", _fake_run)  # type: ignore[attr-defined]

    result = runner.invoke(app, ["init", "--user"])
    assert result.exit_code == 0
    assert "already registered" in result.stdout
    assert "--user --force" in result.stdout


def test_init_user_force_runs_remove_then_add(monkeypatch: object) -> None:
    import shutil
    import subprocess
    from typing import Any

    calls: list[list[str]] = []

    class _Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def _fake_which(name: str) -> str | None:
        return "/fake/claude" if name == "claude" else None

    def _fake_run(cmd: list[str], **_: Any) -> _Result:
        calls.append(cmd)
        return _Result()

    monkeypatch.setattr(shutil, "which", _fake_which)  # type: ignore[attr-defined]
    monkeypatch.setattr(subprocess, "run", _fake_run)  # type: ignore[attr-defined]

    result = runner.invoke(app, ["init", "--user", "--force"])
    assert result.exit_code == 0
    # First call is remove, second is add.
    assert len(calls) == 2
    assert calls[0][1:5] == ["mcp", "remove", "-s", "user"]
    assert calls[1][1:5] == ["mcp", "add", "-s", "user"]


def test_init_user_errors_when_claude_cli_missing(monkeypatch: object) -> None:
    import shutil

    def _no_claude(_name: str) -> str | None:
        return None

    monkeypatch.setattr(shutil, "which", _no_claude)  # type: ignore[attr-defined]
    result = runner.invoke(app, ["init", "--user"])
    assert result.exit_code != 0


def test_init_rejects_malformed_config(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    target = tmp_path / ".mcp.json"
    target.write_text("not json at all", encoding="utf-8")
    result = runner.invoke(app, ["init"])
    assert result.exit_code != 0


def test_migrate_already_up_to_date(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))  # type: ignore[attr-defined]
    from cairntir.config import db_path

    DrawerStore(db_path(), HashEmbeddingProvider()).close()

    result = runner.invoke(app, ["migrate"])
    assert result.exit_code == 0
    assert "already up to date" in result.stdout
