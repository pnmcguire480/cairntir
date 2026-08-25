from __future__ import annotations

import json
from pathlib import Path

import pytest

from cairntir.hosts import (
    MEMORY_POLICY,
    POLICY_BEGIN_MARKER,
    POLICY_END_MARKER,
    HostConfigurationError,
    configure_host,
    inspect_host,
    load_json_object,
    mcp_spec,
    merge_mcp_spec,
    upsert_marked_policy,
)


def test_merge_mcp_spec_preserves_other_servers() -> None:
    original = {"mcpServers": {"other": {"command": "other-server"}}}
    merged, changed = merge_mcp_spec(original)
    assert changed is True
    assert merged["mcpServers"]["other"]["command"] == "other-server"
    assert merged["mcpServers"]["cairntir"] == {
        "command": "cairntir-mcp",
        "args": [],
    }
    _, changed_again = merge_mcp_spec(merged)
    assert changed_again is False


def test_host_specs_share_server_but_identify_the_capture_host() -> None:
    assert mcp_spec("claude") == {
        "command": "cairntir-mcp",
        "args": ["--host", "claude"],
    }
    assert mcp_spec("codex")["args"] == ["--host", "codex"]
    assert mcp_spec("cursor")["args"] == ["--host", "cursor"]
    assert mcp_spec("qwen")["args"] == ["--host", "qwen"]


def test_load_json_object_rejects_invalid_and_non_object_json(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{", encoding="utf-8")
    with pytest.raises(HostConfigurationError, match="not valid readable JSON"):
        load_json_object(malformed)

    array = tmp_path / "array.json"
    array.write_text("[]", encoding="utf-8")
    with pytest.raises(HostConfigurationError, match="not a JSON object"):
        load_json_object(array)


def test_upsert_policy_preserves_user_content_and_updates_its_own_block(
    tmp_path: Path,
) -> None:
    target = tmp_path / "AGENTS.md"
    target.write_text("# User policy\n\nKeep this.\n", encoding="utf-8")
    assert upsert_marked_policy(target, body="STALE_POLICY_TEXT\n") == "appended"
    assert upsert_marked_policy(target, body=MEMORY_POLICY) == "updated"
    assert upsert_marked_policy(target, body=MEMORY_POLICY) == "unchanged"
    contents = target.read_text(encoding="utf-8")
    assert "cairntir_handoff" in contents


def test_upsert_policy_refuses_incomplete_markers(tmp_path: Path) -> None:
    target = tmp_path / "CLAUDE.md"
    target.write_text(f"{POLICY_BEGIN_MARKER}\nbroken", encoding="utf-8")
    with pytest.raises(HostConfigurationError, match="only one"):
        upsert_marked_policy(target)


def test_configure_cursor_project_creates_mcp_and_always_rule(tmp_path: Path) -> None:
    result = configure_host(
        "cursor",
        scope="project",
        root=tmp_path,
        home=tmp_path / "home",
    )
    assert result.registration == "created"
    assert result.policy == "created"
    assert result.registration_path == tmp_path / ".cursor" / "mcp.json"
    config = json.loads(result.registration_path.read_text(encoding="utf-8"))
    assert config["mcpServers"]["cairntir"]["command"] == "cairntir-mcp"
    assert config["mcpServers"]["cairntir"]["args"] == ["--host", "cursor"]
    assert result.policy_path is not None
    policy = result.policy_path.read_text(encoding="utf-8")
    assert "alwaysApply: true" in policy
    assert "Claude Code, Codex, Cursor, and Qwen Code" in policy

    status = inspect_host("cursor", scope="project", root=tmp_path, home=tmp_path)
    assert status.mcp_configured is True
    assert status.policy_configured is True


def test_configure_cursor_user_is_honest_about_manual_global_rule(tmp_path: Path) -> None:
    result = configure_host(
        "cursor",
        scope="user",
        root=tmp_path / "project",
        home=tmp_path / "home",
    )
    assert result.registration_path == tmp_path / "home" / ".cursor" / "mcp.json"
    assert result.policy_path is None
    assert result.policy.startswith("manual:")

    status = inspect_host(
        "cursor",
        scope="user",
        root=tmp_path / "project",
        home=tmp_path / "home",
    )
    assert status.mcp_configured is True
    assert status.policy_configured is None
    assert "Cursor Settings" in status.policy_detail


def test_configure_codex_project_appends_owned_toml_block(tmp_path: Path) -> None:
    config = tmp_path / ".codex" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text('model = "gpt-test"\n', encoding="utf-8")

    result = configure_host(
        "codex",
        scope="project",
        root=tmp_path,
        home=tmp_path / "home",
    )
    assert result.registration == "appended"
    contents = config.read_text(encoding="utf-8")
    assert 'model = "gpt-test"' in contents
    assert "[mcp_servers.cairntir]" in contents
    assert 'args = ["--host", "codex"]' in contents
    assert (tmp_path / "AGENTS.md").exists()

    status = inspect_host("codex", scope="project", root=tmp_path, home=tmp_path)
    assert status.mcp_configured is True
    assert status.policy_configured is True


def test_codex_project_refuses_unowned_conflicting_stanza(tmp_path: Path) -> None:
    config = tmp_path / ".codex" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text(
        '[mcp_servers.cairntir]\ncommand = "wrong-command"\nargs = []\n',
        encoding="utf-8",
    )
    with pytest.raises(HostConfigurationError, match="user-owned TOML"):
        configure_host(
            "codex",
            scope="project",
            root=tmp_path,
            home=tmp_path / "home",
        )


def test_configure_claude_project_preserves_existing_mcp_and_policy(
    tmp_path: Path,
) -> None:
    mcp = tmp_path / ".mcp.json"
    mcp.write_text(
        json.dumps({"mcpServers": {"existing": {"command": "keep-me"}}}),
        encoding="utf-8",
    )
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("# Existing\n", encoding="utf-8")

    result = configure_host(
        "claude",
        scope="project",
        root=tmp_path,
        home=tmp_path / "home",
    )
    assert result.registration == "updated"
    config = json.loads(mcp.read_text(encoding="utf-8"))
    assert config["mcpServers"]["existing"]["command"] == "keep-me"
    assert config["mcpServers"]["cairntir"]["command"] == "cairntir-mcp"
    assert config["mcpServers"]["cairntir"]["args"] == ["--host", "claude"]
    assert "# Existing" in claude_md.read_text(encoding="utf-8")


def test_inspect_host_reports_missing_project_files(tmp_path: Path) -> None:
    status = inspect_host("cursor", scope="project", root=tmp_path, home=tmp_path)
    assert status.mcp_configured is False
    assert status.policy_configured is False
    assert "missing" in status.mcp_detail
    assert "missing" in status.policy_detail


def test_configure_qwen_project_creates_settings_and_qwen_md(tmp_path: Path) -> None:
    qwen_dir = tmp_path / ".qwen"
    qwen_dir.mkdir()
    (qwen_dir / "settings.json").write_text(
        json.dumps({"model": {"name": "kept"}, "mcpServers": {"other": {"command": "x"}}}),
        encoding="utf-8",
    )

    result = configure_host(
        "qwen",
        scope="project",
        root=tmp_path,
        home=tmp_path / "home",
    )
    assert result.registration == "updated"
    assert result.registration_path == qwen_dir / "settings.json"
    config = json.loads(result.registration_path.read_text(encoding="utf-8"))
    assert config["model"] == {"name": "kept"}
    assert config["mcpServers"]["other"] == {"command": "x"}
    assert config["mcpServers"]["cairntir"] == {
        "command": "cairntir-mcp",
        "args": ["--host", "qwen"],
    }
    assert result.policy == "created"
    assert result.policy_path == tmp_path / "QWEN.md"
    assert "cairntir_handoff" in result.policy_path.read_text(encoding="utf-8")

    status = inspect_host("qwen", scope="project", root=tmp_path, home=tmp_path)
    assert status.mcp_configured is True
    assert status.policy_configured is True


def test_configure_qwen_user_targets_home_qwen_dir(tmp_path: Path) -> None:
    home = tmp_path / "home"
    result = configure_host(
        "qwen",
        scope="user",
        root=tmp_path / "project",
        home=home,
    )
    assert result.registration == "created"
    assert result.registration_path == home / ".qwen" / "settings.json"
    assert result.policy_path == home / ".qwen" / "QWEN.md"
    assert result.policy_path is not None and result.policy_path.exists()

    status = inspect_host("qwen", scope="user", root=tmp_path / "project", home=home)
    assert status.mcp_configured is True
    assert status.policy_configured is True


def test_repo_policy_blocks_match_memory_policy() -> None:
    """Installed copies must not drift from MEMORY_POLICY. They already had."""
    repo = Path(__file__).resolve().parents[2]
    targets = (
        repo / "CLAUDE.md",
        repo / "AGENTS.md",
        repo / "QWEN.md",
        repo / ".cursor" / "rules" / "cairntir.mdc",
    )
    expected = MEMORY_POLICY.strip()
    for path in targets:
        text = path.read_text(encoding="utf-8")
        begin = text.index(POLICY_BEGIN_MARKER) + len(POLICY_BEGIN_MARKER)
        end = text.index(POLICY_END_MARKER)
        body = text[begin:end].strip()
        assert body == expected, f"{path} policy block drifted from hosts.MEMORY_POLICY"
