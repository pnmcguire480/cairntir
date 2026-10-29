"""Claude Code plugin bundle integrity checks."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

from cairntir import __version__

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_MANIFEST = REPO_ROOT / ".claude-plugin" / "plugin.json"
COMMANDS_DIR = REPO_ROOT / "commands"


def test_plugin_manifest_version_matches_package() -> None:
    data = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))
    assert data["version"] == __version__


def test_release_versions_agree() -> None:
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((REPO_ROOT / "uv.lock").read_text(encoding="utf-8"))
    locked = next(package for package in lock["package"] if package["name"] == "cairntir")
    plugin = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))

    assert project["project"]["version"] == __version__
    assert locked["version"] == __version__
    assert plugin["version"] == __version__


def test_plugin_manifest_lists_three_commands() -> None:
    data = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))
    assert data["commands"] == "./commands"
    assert {path.stem for path in COMMANDS_DIR.glob("*.md")} == {"remember", "recall", "reason"}


def test_plugin_command_files_exist() -> None:
    data = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))
    assert data["commands"] == "./commands"
    for name in ("remember", "recall", "reason"):
        path = COMMANDS_DIR / f"{name}.md"
        assert path.is_file(), f"missing command file {path.name}"
        assert path.read_text(encoding="utf-8").startswith("---"), (
            f"{path.name} missing frontmatter"
        )


def test_plugin_declares_mcp_server() -> None:
    data = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))
    mcp = data["mcpServers"]["cairntir"]
    # Stable shim, not ``python -m`` — see ``[project.scripts]`` in
    # pyproject.toml. Pip's launcher hard-pins the right interpreter
    # so the registered command survives venv changes.
    assert mcp["command"] == "cairntir-mcp"
    assert mcp["args"] == ["--host", "claude"]
