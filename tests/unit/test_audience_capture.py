"""Behavior of command-line audience capture (I01): provisional, never confirmed."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from cairntir.audience_lock import (
    audience_lock,
    capture_audience,
    confirm_audience,
    transfer_audience_to_spec,
)
from cairntir.cli import app
from cairntir.errors import ProjectionError

VALUES = {
    "audience": "Solo makers who sell online",
    "channels": "Newsletter and short video",
    "pain": "Hours lost on repeat admin",
    "sophistication": "Knows the tools, not the method",
    "desired_outcome": "One calm hour a day",
}


@pytest.fixture
def env(tmp_path: Path) -> dict[str, Any]:
    vault = tmp_path / "vault"
    vault.mkdir()
    return {"store": tmp_path / "memory.db", "vault": vault, "wing": "project-alpha"}


def _capture(env: dict[str, Any], values: dict[str, str] | None = None) -> dict[str, Any]:
    return capture_audience(env["store"], env["vault"], env["wing"], values or VALUES)


def _revisions(store: Path) -> int:
    with sqlite3.connect(store) as conn:
        found = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='cairntir_audience_revisions'"
        ).fetchone()
        if found is None:
            return 0
        return int(conn.execute("SELECT COUNT(*) FROM cairntir_audience_revisions").fetchone()[0])


def _confirm(env: dict[str, Any]) -> dict[str, Any]:
    def ask(prompt: str) -> str:
        return re.search(r"Type ([0-9a-f]{6})", prompt).group(1)  # type: ignore[union-attr]

    return confirm_audience(
        env["store"],
        env["vault"],
        env["wing"],
        interactive=True,
        ask=ask,
        show=lambda _t: None,
    )


def test_capture_stores_all_five_fields_with_a_source_and_stays_provisional(
    env: dict[str, Any],
) -> None:
    receipt = _capture(env)
    state = audience_lock(env["store"], env["vault"], env["wing"])
    assert receipt["revision"] == 1
    assert state["lock"] == "provisional"
    assert {k: v["value"] for k, v in state["profile"].items()} == VALUES
    for item in state["profile"].values():
        (source,) = item["source_ids"]
        assert state["evidence"][source]["kind"] == "user_statement"


def test_capture_twice_with_same_values_makes_one_revision(env: dict[str, Any]) -> None:
    first = _capture(env)
    second = _capture(env)
    assert second["revision"] == first["revision"]
    assert _revisions(env["store"]) == 1


def test_changed_capture_drops_an_earlier_confirmation(env: dict[str, Any]) -> None:
    _capture(env)
    assert _confirm(env)["lock"] == "confirmed"
    _capture(env, {**VALUES, "pain": "Too many tabs"})
    state = audience_lock(env["store"], env["vault"], env["wing"])
    assert state["revision"] == 2
    assert state["lock"] == "provisional"


@pytest.mark.parametrize("bad", ["", "   ", "line\nbreak", "tab\there", "<!-- x -->"])
def test_bad_field_is_refused_and_stores_nothing(env: dict[str, Any], bad: str) -> None:
    with pytest.raises(ProjectionError):
        _capture(env, {**VALUES, "channels": bad})
    assert _revisions(env["store"]) == 0


def test_missing_field_is_refused(env: dict[str, Any]) -> None:
    partial = {k: v for k, v in VALUES.items() if k != "pain"}
    with pytest.raises(ProjectionError, match="pain"):
        _capture(env, partial)
    assert _revisions(env["store"]) == 0


def test_unknown_field_is_refused(env: dict[str, Any]) -> None:
    with pytest.raises(ProjectionError, match="budget"):
        _capture(env, {**VALUES, "budget": "big"})


def test_captured_audience_reaches_the_spec_with_sources(env: dict[str, Any]) -> None:
    _capture(env)
    spec = env["store"].parent / "SPEC.md"
    transfer_audience_to_spec(env["store"], env["vault"], env["wing"], spec)
    text = spec.read_text(encoding="utf-8")
    assert "Status: provisional" in text
    for value in VALUES.values():
        assert value in text
    assert "cli-capture (user_statement)" in text


def test_cli_capture_then_status_is_provisional(env: dict[str, Any]) -> None:
    common = ["--wing", env["wing"], "--vault", str(env["vault"]), "--store", str(env["store"])]
    args = ["audience", "capture", *common]
    for field, value in VALUES.items():
        args += [f"--{field.replace('_', '-')}", value]
    runner = CliRunner()
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    status = runner.invoke(app, ["audience", "status", *common])
    assert '"lock": "provisional"' in status.output
    assert VALUES["pain"] in status.output


def test_cli_capture_refuses_a_missing_field(env: dict[str, Any]) -> None:
    common = ["--wing", env["wing"], "--vault", str(env["vault"]), "--store", str(env["store"])]
    result = CliRunner().invoke(app, ["audience", "capture", *common, "--audience", "x"])
    assert result.exit_code != 0
    assert _revisions(env["store"]) == 0
