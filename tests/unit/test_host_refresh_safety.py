from __future__ import annotations

import json
from pathlib import Path

import pytest

from cairntir import hosts


@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("scope", ["user", "project"])
def test_refresh_keeps_custom_codex_access_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, force: bool, scope: str
) -> None:
    target = tmp_path / ".codex" / "config.toml"
    target.parent.mkdir()
    original = (
        '# cairntir:mcp:begin\n[mcp_servers.cairntir]\ncommand = "cairntir-mcp"\n'
        'args = ["--host", "codex"]\n[mcp_servers.cairntir.env]\n'
        'CAIRNTIR_GRANT_FILE = "/private/reader-grant"\n'
        '[mcp_servers.cairntir.tools.cairntir_remember]\napproval_mode = "approve"\n'
        "# cairntir:mcp:end\n"
    )
    target.write_text(original, encoding="utf-8")

    def refuse_cli(*args: object, **kwargs: object) -> None:
        pytest.fail("refresh must not replace the protected registration through the CLI")

    monkeypatch.setattr(hosts, "_run_cli", refuse_cli)
    with pytest.raises(hosts.HostConfigurationError, match="preserving"):
        hosts.configure_host("codex", scope=scope, root=tmp_path, home=tmp_path, force=force)
    assert target.read_text(encoding="utf-8") == original


def test_forced_claude_refresh_reports_existing_registration_without_removing_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []

    def existing(*args: str) -> tuple[int, str, str]:
        calls.append(args)
        return 1, "", "MCP server cairntir already exists"

    monkeypatch.setattr(hosts, "_run_cli", existing)
    with pytest.raises(hosts.HostConfigurationError, match="preserving"):
        hosts.configure_host("claude", scope="user", root=tmp_path, home=tmp_path, force=True)
    assert len(calls) == 1
    assert calls[0][1:3] == ("mcp", "add")


@pytest.mark.parametrize("contents", ["invalid = [", "mcp_servers = 123", "[mcp_servers.cairntir]"])
def test_invalid_codex_config_is_preserved_and_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, contents: str
) -> None:
    target = tmp_path / ".codex" / "config.toml"
    target.parent.mkdir()
    target.write_text(contents, encoding="utf-8")
    monkeypatch.setattr(
        hosts, "_run_cli", lambda *args: pytest.fail("must not rewrite invalid config")
    )
    with pytest.raises(hosts.HostConfigurationError):
        hosts.configure_host("codex", scope="user", root=tmp_path, home=tmp_path)
    assert target.read_text(encoding="utf-8") == contents


def test_json_refresh_preserves_disabled_server_and_tool_restrictions(tmp_path: Path) -> None:
    target = tmp_path / ".copilot" / "mcp-config.json"
    target.parent.mkdir()
    options = {"tools": ["cairntir_get"], "disabled": True, "env": {"KEEP": "exact"}}
    target.write_text(json.dumps({"mcpServers": {"cairntir": options}}), encoding="utf-8")
    hosts.configure_host("copilot", scope="user", root=tmp_path, home=tmp_path, force=True)
    entry = json.loads(target.read_text(encoding="utf-8"))["mcpServers"]["cairntir"]
    assert {key: entry[key] for key in options} == options


def test_nonobject_json_entry_is_reported_without_rewriting(tmp_path: Path) -> None:
    target = tmp_path / ".cursor" / "mcp.json"
    target.parent.mkdir()
    original = '{"mcpServers":{"cairntir":null}}'
    target.write_text(original, encoding="utf-8")
    with pytest.raises(hosts.HostConfigurationError, match="not a JSON object"):
        hosts.configure_host("cursor", scope="user", root=tmp_path, home=tmp_path)
    assert target.read_text(encoding="utf-8") == original
