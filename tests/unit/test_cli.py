"""Smoke tests for the ``cairntir`` CLI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cairntir import __version__
from cairntir.cli import app
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer, Layer
from cairntir.portable import export_drawers

runner = CliRunner()


@pytest.fixture(autouse=True)
def _use_test_embedding_space(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep CLI tests deterministic while exercising the production factory seam."""
    monkeypatch.setattr(
        "cairntir.cli.production_embedding_provider",
        lambda: HashEmbeddingProvider(dimension=384),
    )


def test_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


@pytest.mark.skipif(sys.platform != "win32", reason="Windows encoding regression")
def test_help_is_safe_when_redirected_from_a_cp1252_process() -> None:
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "cp1252"
    completed = subprocess.run(
        [sys.executable, "-m", "cairntir.cli", "--help"],
        cwd=Path(__file__).resolve().parents[2],
        env=environment,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")
    assert b"Usage:" in completed.stdout


def test_portable_import_is_idempotent_by_file_content(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path / "home"))  # type: ignore[attr-defined]
    portable = tmp_path / "drawers.jsonl"
    export_drawers(
        [Drawer(wing="cairntir", room="portable", content="import exactly once")],
        portable,
    )

    first = runner.invoke(app, ["import", str(portable)])
    replay = runner.invoke(app, ["import", str(portable)])

    assert first.exit_code == 0, first.output
    assert replay.exit_code == 0, replay.output
    assert "already imported" in replay.output
    with DrawerStore(
        tmp_path / "home" / "cairntir.db",
        HashEmbeddingProvider(dimension=384),
    ) as store:
        assert [d.content for d in store.list_by()] == ["import exactly once"]


def test_anchor_then_recall_for_change_roundtrip(tmp_path: Path, monkeypatch: object) -> None:
    """The retroactive path end to end: an old drawer becomes structurally recallable."""
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))  # type: ignore[attr-defined]
    store = DrawerStore(tmp_path / "cairntir.db", HashEmbeddingProvider(dimension=384))
    saved = store.add(
        Drawer(
            wing="cairntir",
            room="journey",
            content="cold start went from twelve minutes to 1.4s by defaulting to fastembed",
        )
    )
    store.close()
    assert saved.id is not None

    before = runner.invoke(app, ["recall-for-change", "src/cairntir/memory/embeddings.py"])
    assert before.exit_code == 0, before.output
    assert "No anchored drawers touch" in before.output

    anchored = runner.invoke(
        app,
        [
            "anchor",
            str(saved.id),
            "--path",
            "src/cairntir/memory/embeddings.py",
            "--symbol",
            "production_embedding_provider",
        ],
    )
    assert anchored.exit_code == 0, anchored.output
    assert "now carries 1 anchor(s)" in anchored.output

    after = runner.invoke(app, ["recall-for-change", "src/cairntir/memory/embeddings.py"])
    assert after.exit_code == 0, after.output
    assert f"#{saved.id}" in after.output
    assert "cold start" in after.output


def test_anchor_accepts_multiple_paths(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))  # type: ignore[attr-defined]
    store = DrawerStore(tmp_path / "cairntir.db", HashEmbeddingProvider(dimension=384))
    saved = store.add(Drawer(wing="cairntir", room="journey", content="two files"))
    store.close()
    assert saved.id is not None

    result = runner.invoke(
        app,
        [
            "anchor",
            str(saved.id),
            "--path",
            "src/cairntir/cli.py",
            "--path",
            "src/cairntir/memory/store.py",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "now carries 2 anchor(s)" in result.output


def test_anchor_unknown_drawer_fails_cleanly(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))  # type: ignore[attr-defined]
    DrawerStore(tmp_path / "cairntir.db", HashEmbeddingProvider(dimension=384)).close()

    result = runner.invoke(app, ["anchor", "9999", "--path", "src/cairntir/cli.py"])
    assert result.exit_code == 1
    combined = result.output + (result.stderr or "")
    assert "no drawer with id" in combined


def test_anchor_no_store(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))  # type: ignore[attr-defined]
    result = runner.invoke(app, ["anchor", "1", "--path", "src/cairntir/cli.py"])
    assert result.exit_code == 1
    combined = (result.output + (result.stderr or "")).lower()
    assert "no store" in combined


def test_cross_recall_no_store(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))  # type: ignore[attr-defined]
    result = runner.invoke(app, ["cross-recall", "anything"])
    assert result.exit_code == 1
    combined = (result.output + (result.stderr or "")).lower()
    assert "no store" in combined


def test_cross_recall_with_drawers(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))  # type: ignore[attr-defined]
    store = DrawerStore(tmp_path / "cairntir.db", HashEmbeddingProvider(dimension=384))
    store.add(Drawer(wing="stars-2026", room="notes", content="lockstep determinism"))
    store.add(Drawer(wing="ground-zero", room="notes", content="pure engine functions"))

    result = runner.invoke(app, ["cross-recall", "pure engine functions"])
    assert result.exit_code == 0
    assert "across" in result.stdout
    assert "[ground-zero]" in result.stdout


def test_discovery_and_human_learning_log_commands(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))  # type: ignore[attr-defined]
    with DrawerStore(
        tmp_path / "cairntir.db",
        HashEmbeddingProvider(dimension=384),
    ) as store:
        evidence = store.add(
            Drawer(
                wing="cairntir",
                room="evidence",
                content="The same repair worked three times.",
            )
        )
    assert evidence.id is not None

    recorded = runner.invoke(
        app,
        [
            "discover",
            "Repair pattern emerged",
            "The repeated sequence reduced repair time.",
            "--wing",
            "cairntir",
            "--novelty",
            "user",
            "--evidence",
            str(evidence.id),
            "--state",
            "candidate",
        ],
    )
    assert recorded.exit_code == 0, recorded.output
    assert "Recorded discovery" in recorded.output

    listing = runner.invoke(app, ["discoveries", "--wing", "cairntir"])
    assert listing.exit_code == 0
    assert "Repair pattern emerged" in listing.output

    learning_log = runner.invoke(app, ["learning-log", "--wing", "cairntir"])
    assert learning_log.exit_code == 0
    assert "Human Learning Log" in learning_log.output
    assert "Repair pattern emerged" in learning_log.output


def test_reason_non_interactive_writes_drawers(tmp_path: Path, monkeypatch: object) -> None:
    """`cairntir reason` with every flag set runs a full loop step without prompts or network."""
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))  # type: ignore[attr-defined]
    # Initialize the store so we pass the no-store-yet gate.
    DrawerStore(tmp_path / "cairntir.db", HashEmbeddingProvider(dimension=384)).close()

    result = runner.invoke(
        app,
        [
            "reason",
            "did the fix hold?",
            "--wing",
            "cairntir",
            "--claim",
            "the lazy embedder keeps startup under 2s",
            "--predicted",
            "cold-start completes in under 2s",
            "--observed",
            "cold-start completes in 1s",
            "--success",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "prediction drawer" in result.output
    assert "observation drawer" in result.output
    assert "mass_change" in result.output


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
    store = DrawerStore(tmp_path / "cairntir.db", HashEmbeddingProvider(dimension=384))
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

    get_result = runner.invoke(app, ["get", "1"])
    assert get_result.exit_code == 0
    payload = json.loads(get_result.stdout)
    assert payload["content"] == "cairn stones mark the path"
    assert payload["resource"] == "cairntir://drawer/1"


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


def test_doctor_reports_verified_embedding_space(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))
    with DrawerStore(tmp_path / "cairntir.db", HashEmbeddingProvider(dimension=384)) as store:
        store.add(Drawer(wing="cairntir", room="doctor", content="verified index"))

    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0, result.output
    assert "state:              verified" in result.output
    assert "drawers / vectors:  1 / 1" in result.output


def test_reindex_creates_backup_and_repairs_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))
    database = tmp_path / "cairntir.db"
    backup = tmp_path / "before-reindex.db"
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        store.add(Drawer(wing="cairntir", room="doctor", content="repair me"))

    result = runner.invoke(
        app,
        ["reindex", "--yes", "--backup", str(backup), "--batch-size", "1"],
    )
    assert result.exit_code == 0, result.output
    assert backup.exists()
    assert "dimension:   384" in result.output

    doctor_result = runner.invoke(app, ["doctor"])
    assert doctor_result.exit_code == 0, doctor_result.output
    assert "state:              verified" in doctor_result.output


def test_init_writes_project_mcp_json(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    target = tmp_path / ".mcp.json"
    assert target.exists()

    data = json.loads(target.read_text(encoding="utf-8"))
    # Registers the stable ``cairntir-mcp`` console script — pip's
    # launcher hard-pins the right interpreter, so we don't have to
    # bake an absolute path that breaks on venv changes.
    assert data["mcpServers"]["cairntir"]["command"] == "cairntir-mcp"
    assert data["mcpServers"]["cairntir"]["args"] == ["--host", "claude"]
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


def test_init_cursor_project_writes_mcp_and_always_rule(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    result = runner.invoke(app, ["init", "--host", "cursor"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".cursor" / "mcp.json").exists()
    rule = tmp_path / ".cursor" / "rules" / "cairntir.mdc"
    assert rule.exists()
    contents = rule.read_text(encoding="utf-8")
    assert "alwaysApply: true" in contents
    assert "cairntir_handoff" in contents


def test_init_cursor_user_prints_paste_ready_rule(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # type: ignore[attr-defined]
    monkeypatch.setenv("HOME", str(tmp_path))  # type: ignore[attr-defined]
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    result = runner.invoke(app, ["init", "--host", "cursor", "--user"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".cursor" / "mcp.json").exists()
    assert "Cursor Settings" in result.output
    assert "cairntir_handoff" in result.output
    assert not (tmp_path / ".cursor" / "rules" / "cairntir.mdc").exists()


def test_init_codex_project_preserves_existing_config(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    config = tmp_path / ".codex" / "config.toml"
    config.parent.mkdir()
    config.write_text('model = "test-model"\n', encoding="utf-8")
    result = runner.invoke(app, ["init", "--host", "codex"])
    assert result.exit_code == 0, result.output
    contents = config.read_text(encoding="utf-8")
    assert 'model = "test-model"' in contents
    assert "[mcp_servers.cairntir]" in contents
    assert (tmp_path / "AGENTS.md").exists()


def test_init_user_shells_out_to_claude_cli(monkeypatch: object, tmp_path: Path) -> None:
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

    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # type: ignore[attr-defined]
    monkeypatch.setenv("HOME", str(tmp_path))  # type: ignore[attr-defined]
    monkeypatch.setattr(shutil, "which", _fake_which)  # type: ignore[attr-defined]
    monkeypatch.setattr(subprocess, "run", _fake_run)  # type: ignore[attr-defined]

    result = runner.invoke(app, ["init", "--user"])
    assert result.exit_code == 0, result.stdout
    assert "user scope" in result.stdout
    assert calls, "claude CLI was never invoked"

    assert calls[0][1:] == [
        "mcp",
        "add",
        "-s",
        "user",
        "cairntir",
        "--",
        "cairntir-mcp",
        "--host",
        "claude",
    ]


def test_init_user_is_idempotent_on_already_exists(monkeypatch: object, tmp_path: Path) -> None:
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

    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # type: ignore[attr-defined]
    monkeypatch.setenv("HOME", str(tmp_path))  # type: ignore[attr-defined]
    monkeypatch.setattr(shutil, "which", _fake_which)  # type: ignore[attr-defined]
    monkeypatch.setattr(subprocess, "run", _fake_run)  # type: ignore[attr-defined]

    result = runner.invoke(app, ["init", "--user"])
    assert result.exit_code == 0
    assert "already registered" in result.stdout
    assert "--user --force" in result.stdout


def test_init_user_force_runs_remove_then_add(monkeypatch: object, tmp_path: Path) -> None:
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

    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # type: ignore[attr-defined]
    monkeypatch.setenv("HOME", str(tmp_path))  # type: ignore[attr-defined]
    monkeypatch.setattr(shutil, "which", _fake_which)  # type: ignore[attr-defined]
    monkeypatch.setattr(subprocess, "run", _fake_run)  # type: ignore[attr-defined]

    result = runner.invoke(app, ["init", "--user", "--force"])
    assert result.exit_code == 0
    # First call is remove, second is add.
    assert len(calls) == 2
    assert calls[0][1:5] == ["mcp", "remove", "-s", "user"]
    assert calls[1][1:5] == ["mcp", "add", "-s", "user"]


def test_upsert_greeting_creates_file_when_missing(tmp_path: Path) -> None:
    from cairntir.cli import (
        GREETING_BEGIN_MARKER,
        GREETING_END_MARKER,
        _upsert_greeting,
    )

    target = tmp_path / ".claude" / "CLAUDE.md"
    action = _upsert_greeting(target)
    assert action == "created"
    text = target.read_text(encoding="utf-8")
    assert GREETING_BEGIN_MARKER in text
    assert GREETING_END_MARKER in text
    assert "cairntir_handoff" in text


def test_upsert_greeting_appends_to_existing_file(tmp_path: Path) -> None:
    from cairntir.cli import GREETING_BEGIN_MARKER, _upsert_greeting

    target = tmp_path / "CLAUDE.md"
    target.write_text("# my existing notes\n\nkeep me safe\n", encoding="utf-8")
    action = _upsert_greeting(target)
    assert action == "appended"
    text = target.read_text(encoding="utf-8")
    assert "keep me safe" in text  # user content preserved byte-for-byte
    assert GREETING_BEGIN_MARKER in text


def test_upsert_greeting_updates_existing_markers(tmp_path: Path) -> None:
    from cairntir.cli import (
        GREETING_BEGIN_MARKER,
        GREETING_END_MARKER,
        _upsert_greeting,
    )

    target = tmp_path / "CLAUDE.md"
    old_body = "STALE OLD GREETING\n"
    target.write_text(
        f"prologue\n\n{GREETING_BEGIN_MARKER}\n{old_body}{GREETING_END_MARKER}\nepilogue\n",
        encoding="utf-8",
    )
    action = _upsert_greeting(target)
    assert action == "updated"
    text = target.read_text(encoding="utf-8")
    assert "STALE OLD GREETING" not in text
    assert "cairntir_handoff" in text
    assert "prologue" in text
    assert "epilogue" in text


def test_upsert_greeting_is_idempotent(tmp_path: Path) -> None:
    from cairntir.cli import _upsert_greeting

    target = tmp_path / "CLAUDE.md"
    _upsert_greeting(target)
    second = _upsert_greeting(target)
    assert second == "unchanged"


def test_init_user_installs_greeting_by_default(monkeypatch: object, tmp_path: Path) -> None:
    import shutil
    import subprocess
    from typing import Any

    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # type: ignore[attr-defined]
    monkeypatch.setenv("HOME", str(tmp_path))  # type: ignore[attr-defined]

    class _Ok:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def _fake_which(name: str) -> str | None:
        return "/fake/claude" if name == "claude" else None

    def _fake_run(_cmd: list[str], **_: Any) -> _Ok:
        return _Ok()

    monkeypatch.setattr(shutil, "which", _fake_which)  # type: ignore[attr-defined]
    monkeypatch.setattr(subprocess, "run", _fake_run)  # type: ignore[attr-defined]

    result = runner.invoke(app, ["init", "--user"])
    assert result.exit_code == 0
    assert "greeting preamble" in result.stdout
    claude_md = tmp_path / ".claude" / "CLAUDE.md"
    assert claude_md.exists()
    assert "cairntir_handoff" in claude_md.read_text(encoding="utf-8")


def test_init_user_no_greeting_flag_skips_install(monkeypatch: object, tmp_path: Path) -> None:
    import shutil
    import subprocess
    from typing import Any

    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # type: ignore[attr-defined]
    monkeypatch.setenv("HOME", str(tmp_path))  # type: ignore[attr-defined]

    class _Ok:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def _fake_which(name: str) -> str | None:
        return "/fake/claude" if name == "claude" else None

    def _fake_run(_cmd: list[str], **_: Any) -> _Ok:
        return _Ok()

    monkeypatch.setattr(shutil, "which", _fake_which)  # type: ignore[attr-defined]
    monkeypatch.setattr(subprocess, "run", _fake_run)  # type: ignore[attr-defined]

    result = runner.invoke(app, ["init", "--user", "--no-greeting"])
    assert result.exit_code == 0
    assert "greeting preamble" not in result.stdout
    claude_md = tmp_path / ".claude" / "CLAUDE.md"
    assert not claude_md.exists()


def test_setup_wizard_happy_path(tmp_path: Path, monkeypatch: object) -> None:
    """--yes runs every step non-interactively and reports success."""
    import shutil
    import subprocess
    from typing import Any

    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path / "home"))  # type: ignore[attr-defined]
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # type: ignore[attr-defined]
    monkeypatch.setenv("HOME", str(tmp_path))  # type: ignore[attr-defined]

    class _Ok:
        returncode = 0
        stdout = "2.1.84 (Claude Code)"
        stderr = ""

    def _fake_which(name: str) -> str | None:
        return "/fake/claude" if name == "claude" else None

    def _fake_run(_cmd: list[str], **_: Any) -> _Ok:
        return _Ok()

    monkeypatch.setattr(shutil, "which", _fake_which)  # type: ignore[attr-defined]
    monkeypatch.setattr(subprocess, "run", _fake_run)  # type: ignore[attr-defined]

    result = runner.invoke(app, ["setup", "--yes"])
    assert result.exit_code == 0, result.stdout
    # Header lines for every step. Step count is 8 since v1.1.3 added the
    # FastEmbed pre-warm step (step 7 in the new ordering).
    for i in range(1, 9):
        assert f"[{i}/8]" in result.stdout
    assert "Cairntir is ready." in result.stdout
    assert "smoke test" in result.stdout.lower()
    assert "cairntir_handoff" in result.stdout
    assert "Cursor Settings" in result.stdout
    # Greeting preamble landed.
    claude_md = tmp_path / ".claude" / "CLAUDE.md"
    assert claude_md.exists()
    assert "cairntir_handoff" in claude_md.read_text(encoding="utf-8")
    # Cursor user-scope MCP is a file; policy is printed for paste.
    assert (tmp_path / ".cursor" / "mcp.json").exists()
    # Store exists with one drawer from the smoke test.
    db = tmp_path / "home" / "cairntir.db"
    assert db.exists()


def test_setup_succeeds_when_claude_cli_missing(tmp_path: Path, monkeypatch: object) -> None:
    """A Cursor-only user can complete README's first command."""
    import shutil

    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path / "home"))  # type: ignore[attr-defined]
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # type: ignore[attr-defined]
    monkeypatch.setenv("HOME", str(tmp_path))  # type: ignore[attr-defined]

    def _no_cli(_name: str) -> str | None:
        return None

    monkeypatch.setattr(shutil, "which", _no_cli)  # type: ignore[attr-defined]
    result = runner.invoke(app, ["setup", "--yes"])
    assert result.exit_code == 0, result.stdout
    assert "claude" in result.stdout.lower()
    assert "skipped" in result.stdout.lower() or "not on PATH" in result.stdout
    assert "Cairntir is ready." in result.stdout
    assert (tmp_path / ".cursor" / "mcp.json").exists()
    assert "Cursor Settings" in result.stdout
    assert (tmp_path / "home" / "cairntir.db").exists()


def test_setup_home_override_sets_env(tmp_path: Path, monkeypatch: object) -> None:
    import shutil
    import subprocess
    from typing import Any

    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # type: ignore[attr-defined]
    monkeypatch.setenv("HOME", str(tmp_path))  # type: ignore[attr-defined]

    class _Ok:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def _fake_which(name: str) -> str | None:
        return "/fake/claude" if name == "claude" else None

    def _fake_run(_cmd: list[str], **_: Any) -> _Ok:
        return _Ok()

    monkeypatch.setattr(shutil, "which", _fake_which)  # type: ignore[attr-defined]
    monkeypatch.setattr(subprocess, "run", _fake_run)  # type: ignore[attr-defined]

    custom_home = tmp_path / "my-own-cairntir-home"
    result = runner.invoke(app, ["setup", "--yes", "--home", str(custom_home)])
    assert result.exit_code == 0
    assert str(custom_home) in result.stdout
    assert (custom_home / "cairntir.db").exists()


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


def test_replay_extends_supersedes_chain(tmp_path: Path, monkeypatch: object) -> None:
    """`cairntir replay` walks the chain, runs the recipe, and the new
    prediction drawer's supersedes_id points at the original chain leaf.
    """
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))  # type: ignore[attr-defined]
    store = DrawerStore(tmp_path / "cairntir.db", HashEmbeddingProvider(dimension=384))
    original = store.add(
        Drawer(
            wing="cairntir",
            room="journey",
            content="v1.1.3 cold-start fix prediction",
            layer=Layer.ESSENTIAL,
            claim="fastembed-default kills the MCP cold-start hang",
            predicted_outcome="cold start under 5s on every fresh install",
        )
    )
    assert original.id is not None
    store.close()

    result = runner.invoke(
        app,
        [
            "replay",
            str(original.id),
            "--evidence",
            "fastembed has held for four days; no cold-start regressions reported.",
            "--observed",
            "cold start steady at ~1.4s across multiple sessions",
            "--success",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "replay committed" in result.output
    assert "chain extended" in result.output

    # Reopen the store and confirm the new prediction drawer chains onto
    # the original via supersedes_id.
    store = DrawerStore(tmp_path / "cairntir.db", HashEmbeddingProvider(dimension=384))
    try:
        replays = store.list_by(wing="replays", limit=100)
        # The reason step writes 2 drawers (prediction + observation), the
        # crucible step writes a marker, the seed drawer is the fourth.
        assert len(replays) == 4
        # Find the drawer whose supersedes_id points at the original — that
        # is the new prediction.
        new_prediction = next((d for d in replays if d.supersedes_id == original.id), None)
        assert new_prediction is not None, (
            f"no replay drawer chains onto original #{original.id}: "
            f"supersedes pointers were {[d.supersedes_id for d in replays]}"
        )
        assert new_prediction.claim == original.claim
        assert new_prediction.predicted_outcome == original.predicted_outcome
    finally:
        store.close()


def test_replay_refuses_drawer_without_claim(tmp_path: Path, monkeypatch: object) -> None:
    """A drawer with no claim/predicted_outcome cannot be replayed."""
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))  # type: ignore[attr-defined]
    store = DrawerStore(tmp_path / "cairntir.db", HashEmbeddingProvider(dimension=384))
    plain = store.add(
        Drawer(
            wing="cairntir",
            room="notes",
            content="not a prediction-bound drawer — no claim or predicted_outcome",
        )
    )
    assert plain.id is not None
    store.close()

    result = runner.invoke(
        app,
        ["replay", str(plain.id), "--evidence", "x", "--observed", "x", "--success"],
    )
    assert result.exit_code == 1
    combined = (result.output + (result.stderr or "")).lower()
    assert "no claim/predicted_outcome" in combined or "prediction-bound" in combined


def test_replay_errors_on_missing_drawer(tmp_path: Path, monkeypatch: object) -> None:
    """A drawer id that does not exist exits with a clear message."""
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))  # type: ignore[attr-defined]
    DrawerStore(tmp_path / "cairntir.db", HashEmbeddingProvider(dimension=384)).close()

    result = runner.invoke(
        app,
        ["replay", "9999", "--evidence", "x", "--observed", "x", "--success"],
    )
    assert result.exit_code == 1
    combined = (result.output + (result.stderr or "")).lower()
    assert "no drawer" in combined or "9999" in combined


def test_reason_proposer_ollama_drafts_claim_and_predicted(
    tmp_path: Path, monkeypatch: object
) -> None:
    """`cairntir reason --proposer ollama` drafts both fields locally and
    surfaces the draft for confirmation before the loop commits."""
    import io
    import json
    import urllib.request

    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))  # type: ignore[attr-defined]
    DrawerStore(tmp_path / "cairntir.db", HashEmbeddingProvider(dimension=384)).close()

    def _fake_urlopen(req: urllib.request.Request, **_: object) -> io.BytesIO:
        body = json.loads(req.data.decode("utf-8"))  # type: ignore[union-attr]
        # Sanity: the CLI is hitting Ollama's /api/generate.
        assert req.full_url.endswith("/api/generate")
        assert body["model"] == "gemma2:2b"
        return io.BytesIO(
            json.dumps(
                {
                    "response": json.dumps(
                        {
                            "claim": "ollama wired into cairntir replay path",
                            "predicted_outcome": "the synergy stack auto-drafts hypotheses cleanly",
                        }
                    )
                }
            ).encode("utf-8")
        )

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)  # type: ignore[attr-defined]

    result = runner.invoke(
        app,
        [
            "reason",
            "did the proposer wiring land?",
            "--wing",
            "cairntir",
            "--proposer",
            "ollama",
            "--ollama-model",
            "gemma2:2b",
            "--observed",
            "yes, drafted text appeared in the CLI",
            "--success",
        ],
        # Two newline-only inputs accept the drafted claim + predicted.
        input="\n\n",
    )
    assert result.exit_code == 0, result.output
    # The draft block printed.
    assert "drafted" in result.output.lower()
    assert "ollama wired" in result.output
    # The loop committed.
    assert "prediction drawer" in result.output
    assert "observation drawer" in result.output


def test_reason_proposer_ollama_unavailable_exits_clean(
    tmp_path: Path, monkeypatch: object
) -> None:
    """If the daemon is not reachable, the CLI exits 1 with a clear message."""
    import urllib.error
    import urllib.request

    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))  # type: ignore[attr-defined]
    DrawerStore(tmp_path / "cairntir.db", HashEmbeddingProvider(dimension=384)).close()

    def _refuse(_req: urllib.request.Request, **_: object) -> object:
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", _refuse)  # type: ignore[attr-defined]

    result = runner.invoke(
        app,
        [
            "reason",
            "q",
            "--wing",
            "cairntir",
            "--proposer",
            "ollama",
            "--observed",
            "x",
            "--success",
        ],
    )
    assert result.exit_code == 1
    combined = (result.output + (result.stderr or "")).lower()
    assert "could not reach ollama" in combined or "ollama" in combined


def test_reason_unknown_proposer_exits_clean(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))  # type: ignore[attr-defined]
    DrawerStore(tmp_path / "cairntir.db", HashEmbeddingProvider(dimension=384)).close()
    result = runner.invoke(
        app,
        [
            "reason",
            "q",
            "--wing",
            "cairntir",
            "--proposer",
            "claude",  # not supported
            "--claim",
            "c",
            "--predicted",
            "p",
            "--observed",
            "o",
            "--success",
        ],
    )
    assert result.exit_code == 1
    combined = (result.output + (result.stderr or "")).lower()
    assert "unknown proposer" in combined


def test_replay_proposer_ollama_re_drafts_claim(tmp_path: Path, monkeypatch: object) -> None:
    """`cairntir replay --proposer ollama` overrides the chain-leaf
    auto-fill with a freshly-drafted claim."""
    import io
    import json
    import urllib.request

    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))  # type: ignore[attr-defined]
    store = DrawerStore(tmp_path / "cairntir.db", HashEmbeddingProvider(dimension=384))
    original = store.add(
        Drawer(
            wing="cairntir",
            room="journey",
            content="original prediction",
            layer=Layer.ESSENTIAL,
            claim="the original poorly-framed claim",
            predicted_outcome="the original predicted outcome",
        )
    )
    assert original.id is not None
    store.close()

    def _fake_urlopen(req: urllib.request.Request, **_: object) -> io.BytesIO:
        body = json.loads(req.data.decode("utf-8"))  # type: ignore[union-attr]
        # The replay's prompt should include the original claim as
        # context — the model is being asked to *reframe*, not start
        # from scratch.
        assert "original poorly-framed claim" in body["prompt"]
        return io.BytesIO(
            json.dumps(
                {
                    "response": json.dumps(
                        {
                            "claim": "the sharper reframed claim",
                            "predicted_outcome": "the sharper predicted outcome",
                        }
                    )
                }
            ).encode("utf-8")
        )

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)  # type: ignore[attr-defined]

    result = runner.invoke(
        app,
        [
            "replay",
            str(original.id),
            "--evidence",
            "the original framing missed something important",
            "--observed",
            "the prediction's framing was off",
            "--success",
            "--proposer",
            "ollama",
        ],
        input="\n\n",  # accept both drafts
    )
    assert result.exit_code == 0, result.output
    assert "sharper reframed claim" in result.output
    assert "replay committed" in result.output

    # Reopen the store and confirm the new prediction carries the
    # reframed claim, not the original.
    store = DrawerStore(tmp_path / "cairntir.db", HashEmbeddingProvider(dimension=384))
    try:
        replays = store.list_by(wing="replays", limit=100)
        new_prediction = next((d for d in replays if d.supersedes_id == original.id), None)
        assert new_prediction is not None
        assert new_prediction.claim == "the sharper reframed claim"
    finally:
        store.close()


def test_replay_no_store(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))  # type: ignore[attr-defined]
    result = runner.invoke(
        app,
        ["replay", "1", "--evidence", "x", "--observed", "x", "--success"],
    )
    assert result.exit_code == 1
    combined = (result.output + (result.stderr or "")).lower()
    assert "no store" in combined


def test_migrate_already_up_to_date(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))  # type: ignore[attr-defined]
    from cairntir.config import db_path

    DrawerStore(db_path(), HashEmbeddingProvider()).close()

    result = runner.invoke(app, ["migrate"])
    assert result.exit_code == 0
    assert "already up to date" in result.stdout


def test_anchor_repair_revives_a_legacy_drawer(tmp_path: Path, monkeypatch: object) -> None:
    """End to end on the real defect: a dead drawer becomes structurally recallable."""
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))  # type: ignore[attr-defined]
    store = DrawerStore(tmp_path / "cairntir.db", HashEmbeddingProvider(dimension=384))
    saved = store.add(
        Drawer(
            wing="detroit-clone",
            room="phase-0-bites",
            content="B07 IS DONE, the static data crate landed",
        )
    )
    # The legacy string shape cannot be written through add() anymore — the
    # P2 guard refuses it — so stage it the way the live store acquired it:
    # the row already existed before the guard did.
    legacy = json.dumps({"anchors": ["sim-core/src/tech.rs", "data/tech-tree.toml"]})
    store._conn.execute("UPDATE drawers SET metadata = ? WHERE id = ?", (legacy, saved.id))
    store._conn.commit()
    store.close()
    assert saved.id is not None

    before = runner.invoke(app, ["recall-for-change", "sim-core/src/tech.rs"])
    assert before.exit_code == 0, before.output
    assert "No anchored drawers touch" in before.output

    # The pre-existing path cannot fix it: add_anchors validates the merged list.
    blocked = runner.invoke(app, ["anchor", str(saved.id), "--path", "sim-core/src/tech.rs"])
    assert blocked.exit_code == 1, blocked.output
    assert "must be objects" in blocked.output

    repaired = runner.invoke(app, ["anchor", str(saved.id), "--repair"])
    assert repaired.exit_code == 0, repaired.output
    assert "now carries 2 anchor(s)" in repaired.output

    after = runner.invoke(app, ["recall-for-change", "sim-core/src/tech.rs"])
    assert after.exit_code == 0, after.output
    assert f"#{saved.id}" in after.output
    assert "B07 IS DONE" in after.output


def test_anchor_requires_path_or_repair(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))  # type: ignore[attr-defined]
    DrawerStore(tmp_path / "cairntir.db", HashEmbeddingProvider(dimension=384)).close()

    result = runner.invoke(app, ["anchor", "1"])

    assert result.exit_code == 1, result.output
    assert "--path at least once, or --repair" in result.output


def test_anchor_refuses_to_combine_repair_with_path(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))  # type: ignore[attr-defined]
    DrawerStore(tmp_path / "cairntir.db", HashEmbeddingProvider(dimension=384)).close()

    result = runner.invoke(app, ["anchor", "1", "--repair", "--path", "src/cairntir/cli.py"])

    assert result.exit_code == 1, result.output
    assert "takes no --path" in result.output


def test_handoff_returns_whole_drawers_under_a_budget(tmp_path: Path, monkeypatch: object) -> None:
    """End to end: the replacement for HANDOFF.md, from the command line."""
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))  # type: ignore[attr-defined]
    store = DrawerStore(tmp_path / "cairntir.db", HashEmbeddingProvider(dimension=384))
    body = "the release cadence is push daily, merge coherently, release rarely"
    store.add(Drawer(wing="cairntir", room="release", content=body, layer=Layer.ESSENTIAL))
    store.add(
        Drawer(
            wing="cairntir",
            room="project-identity",
            content="Cairntir kills cross-chat AI amnesia",
            layer=Layer.IDENTITY,
        )
    )
    store.close()

    result = runner.invoke(app, ["handoff", "cairntir"])

    assert result.exit_code == 0, result.output
    assert body in result.output, "content came back cut instead of whole"
    assert "Cairntir handoff" in result.output
    assert "SECURITY BOUNDARY" in result.output


def test_handoff_names_what_it_could_not_afford(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))  # type: ignore[attr-defined]
    store = DrawerStore(tmp_path / "cairntir.db", HashEmbeddingProvider(dimension=384))
    store.add(
        Drawer(
            wing="cairntir",
            room="journey",
            content="q" * 4_000,
            layer=Layer.ESSENTIAL,
        )
    )
    store.close()

    result = runner.invoke(app, ["handoff", "cairntir", "--budget", "500"])

    assert result.exit_code == 0, result.output
    assert "not fetched" in result.output
    assert "4,000 chars" in result.output
    assert "q" * 4_000 not in result.output


def test_handoff_reports_an_empty_wing_honestly(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))  # type: ignore[attr-defined]
    DrawerStore(tmp_path / "cairntir.db", HashEmbeddingProvider(dimension=384)).close()

    result = runner.invoke(app, ["handoff", "nothing-here"])

    assert result.exit_code == 0, result.output
    assert "Nothing is recorded" in result.output
