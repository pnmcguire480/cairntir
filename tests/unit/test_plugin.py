"""Claude Code plugin bundle integrity checks."""

from __future__ import annotations

import json
from pathlib import Path

from cairntir import __version__

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_MANIFEST = REPO_ROOT / ".claude-plugin" / "plugin.json"
COMMANDS_DIR = REPO_ROOT / "commands"


def test_plugin_manifest_version_matches_package() -> None:
    data = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))
    assert data["version"] == __version__


def test_plugin_manifest_lists_three_commands() -> None:
    data = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))
    names = {c["name"] for c in data["commands"]}
    assert names == {"remember", "recall", "reason"}


def test_plugin_command_files_exist() -> None:
    data = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))
    for entry in data["commands"]:
        path = REPO_ROOT / entry["file"]
        assert path.is_file(), f"missing command file {entry['file']}"
        body = path.read_text(encoding="utf-8")
        assert body.startswith("---"), f"{entry['file']} missing frontmatter"


def test_plugin_declares_mcp_server() -> None:
    data = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))
    mcp = data["mcpServers"]["cairntir"]
    assert mcp["command"] == "python"
    assert mcp["args"] == ["-m", "cairntir.mcp.server"]
