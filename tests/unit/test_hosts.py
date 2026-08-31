from __future__ import annotations

import json
from pathlib import Path

import pytest

from cairntir.hosts import (
    MEMORY_POLICY,
    POLICY_BEGIN_MARKER,
    POLICY_END_MARKER,
    SUPPORTED_HOSTS,
    TRANSCRIPT_HOSTS,
    HostConfigurationError,
    configure_host,
    inspect_host,
    load_json_object,
    mcp_container_key,
    mcp_entry,
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


def test_transcript_hosts_are_a_strict_subset_of_supported_hosts() -> None:
    """Wiring a host is cheap; reading its transcripts is a per-host adapter.

    Collapsing the two tuples is what would let a merely-wired host reach
    RecoveryContext.current and KeyError on a missing session variable.
    """
    assert set(TRANSCRIPT_HOSTS) < set(SUPPORTED_HOSTS)
    assert set(TRANSCRIPT_HOSTS) == {"claude", "codex", "cursor", "qwen"}


def test_configure_gemini_user_writes_settings_and_gemini_md(tmp_path: Path) -> None:
    home = tmp_path / "home"
    gemini_dir = home / ".gemini"
    gemini_dir.mkdir(parents=True)
    (gemini_dir / "settings.json").write_text(
        json.dumps({"model": {"name": "kept"}, "mcpServers": {"other": {"command": "x"}}}),
        encoding="utf-8",
    )

    result = configure_host("gemini", scope="user", root=tmp_path / "project", home=home)

    assert result.registration == "updated"
    assert result.registration_path == gemini_dir / "settings.json"
    config = json.loads((gemini_dir / "settings.json").read_text(encoding="utf-8"))
    assert config["model"] == {"name": "kept"}, "unrelated user settings must survive"
    assert config["mcpServers"]["other"] == {"command": "x"}
    assert config["mcpServers"]["cairntir"] == {
        "command": "cairntir-mcp",
        "args": ["--host", "gemini"],
    }
    assert result.policy_path == gemini_dir / "GEMINI.md"
    assert result.policy == "created"

    status = inspect_host("gemini", scope="user", root=tmp_path / "project", home=home)
    assert status.mcp_configured is True
    assert status.policy_configured is True


def test_configure_opencode_project_uses_mcp_key_and_command_array(tmp_path: Path) -> None:
    """OpenCode stores servers under `mcp`, not `mcpServers`, with argv folded
    into one array. Writing the portable spec here would load nothing."""
    result = configure_host(
        "opencode",
        scope="project",
        root=tmp_path,
        home=tmp_path / "home",
    )

    assert result.registration_path == tmp_path / "opencode.json"
    config = json.loads((tmp_path / "opencode.json").read_text(encoding="utf-8"))
    assert "mcpServers" not in config
    assert config["mcp"]["cairntir"] == {
        "type": "local",
        "command": ["cairntir-mcp", "--host", "opencode"],
        "enabled": True,
    }
    assert result.policy_path == tmp_path / "AGENTS.md"

    status = inspect_host("opencode", scope="project", root=tmp_path, home=tmp_path / "home")
    assert status.mcp_configured is True


def test_configure_copilot_user_matches_the_shape_its_own_cli_writes(tmp_path: Path) -> None:
    """`copilot mcp add` writes type/tools alongside command/args. Matching that
    shape is what keeps init idempotent against a config the user also edits."""
    home = tmp_path / "home"
    result = configure_host("copilot", scope="user", root=tmp_path / "project", home=home)

    assert result.registration_path == home / ".copilot" / "mcp-config.json"
    config = json.loads(result.registration_path.read_text(encoding="utf-8"))
    assert config["mcpServers"]["cairntir"] == {
        "command": "cairntir-mcp",
        "args": ["--host", "copilot"],
        "type": "local",
        "tools": ["*"],
    }
    assert result.policy_path is None
    assert "no verified user-scope instructions file" in result.policy

    _, changed_again = merge_mcp_spec(config, host="copilot")
    assert changed_again is False, "second init must be a no-op"


def test_copilot_project_scope_avoids_the_shared_mcp_json(tmp_path: Path) -> None:
    """Copilot also reads a bare .mcp.json, but Claude owns that file at project
    scope and the two entry shapes differ -- each init would clobber the other."""
    result = configure_host(
        "copilot",
        scope="project",
        root=tmp_path,
        home=tmp_path / "home",
    )
    assert result.registration_path == tmp_path / ".github" / "mcp.json"
    assert not (tmp_path / ".mcp.json").exists()
    assert result.policy_path == tmp_path / "AGENTS.md"


def test_cline_refuses_project_scope_but_inspect_stays_readable(tmp_path: Path) -> None:
    with pytest.raises(HostConfigurationError, match="no verified project-scoped"):
        configure_host("cline", scope="project", root=tmp_path, home=tmp_path / "home")

    # inspect_host is read-only and must report, never raise.
    status = inspect_host("cline", scope="project", root=tmp_path, home=tmp_path / "home")
    assert status.mcp_configured is None
    assert "no verified project-scoped" in status.mcp_detail


def test_configure_cline_user_targets_its_settings_file(tmp_path: Path) -> None:
    home = tmp_path / "home"
    result = configure_host("cline", scope="user", root=tmp_path / "project", home=home)

    expected = home / ".cline" / "data" / "settings" / "cline_mcp_settings.json"
    assert result.registration_path == expected
    config = json.loads(expected.read_text(encoding="utf-8"))
    assert config["mcpServers"]["cairntir"] == {
        "command": "cairntir-mcp",
        "args": ["--host", "cline"],
    }
    assert result.policy_path is None


def test_container_key_and_entry_stay_paired_for_every_supported_host() -> None:
    for host in SUPPORTED_HOSTS:
        key = mcp_container_key(host)
        entry = mcp_entry(host)
        assert key in {"mcp", "mcpServers"}
        assert entry, f"{host} produced an empty MCP entry"
        if key == "mcpServers" and host != "copilot":
            assert entry == mcp_spec(host)


def test_status_tolerates_host_added_fields_around_our_entry(tmp_path: Path) -> None:
    """Codex per-tool approval_mode nests extra keys under mcp_servers.cairntir.

    Exact-equality status reported that correctly wired config as unconfigured.
    """
    config = tmp_path / ".codex" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text(
        "[mcp_servers.cairntir]\n"
        'command = "cairntir-mcp"\n'
        'args = ["--host", "codex"]\n\n'
        "[mcp_servers.cairntir.tools.cairntir_remember]\n"
        'approval_mode = "approve"\n',
        encoding="utf-8",
    )
    status = inspect_host("codex", scope="project", root=tmp_path, home=tmp_path / "home")
    assert status.mcp_configured is True

    settings = tmp_path / ".gemini" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "cairntir": {
                        "command": "cairntir-mcp",
                        "args": ["--host", "gemini"],
                        "trust": True,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    gemini_status = inspect_host("gemini", scope="project", root=tmp_path, home=tmp_path / "home")
    assert gemini_status.mcp_configured is True


def test_status_still_rejects_an_entry_pointing_at_another_command(tmp_path: Path) -> None:
    settings = tmp_path / ".gemini" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        json.dumps({"mcpServers": {"cairntir": {"command": "someone-elses-mcp", "args": []}}}),
        encoding="utf-8",
    )
    status = inspect_host("gemini", scope="project", root=tmp_path, home=tmp_path / "home")
    assert status.mcp_configured is False


def test_codex_user_scope_never_shells_out_when_already_correct(tmp_path: Path) -> None:
    """`codex mcp add` rewrites the whole stanza and drops anything nested under
    it. Re-running init must not cost the user their approval_mode gates."""
    home = tmp_path / "home"
    config = home / ".codex" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text(
        "[mcp_servers.cairntir]\n"
        'command = "cairntir-mcp"\n'
        'args = ["--host", "codex"]\n\n'
        "[mcp_servers.cairntir.tools.cairntir_remember]\n"
        'approval_mode = "approve"\n',
        encoding="utf-8",
    )
    before = config.read_text(encoding="utf-8")

    result = configure_host(
        "codex",
        scope="user",
        root=tmp_path / "project",
        home=home,
        install_policy=False,
    )

    assert result.registration == "unchanged"
    assert config.read_text(encoding="utf-8") == before, "config.toml must be untouched"
    assert "approval_mode" in config.read_text(encoding="utf-8")
