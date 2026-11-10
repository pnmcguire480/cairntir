"""Behavior of human audience confirmation and specification transfer (I01)."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from cairntir.audience_lock import (
    audience_lock,
    confirm_audience,
    spec_transfer_state,
    transfer_audience_to_spec,
)
from cairntir.cli import app
from cairntir.errors import ProjectionError
from cairntir.ideation_audience import get_audience_revision, publish_audience_revision

FIELDS = ("audience", "channels", "pain", "sophistication", "desired_outcome")
BEGIN = b"<!-- cairntir:audience:begin -->"
END = b"<!-- cairntir:audience:end -->"


def _publish(env: dict[str, Any], key: str = "first", prefix: str = "chosen") -> dict[str, Any]:
    return publish_audience_revision(
        env["store"],
        env["vault"],
        env["wing"],
        {f: {"value": f"{prefix} {f}", "source_ids": ["model-guess"]} for f in FIELDS},
        {
            "model-guess": {
                "kind": "inferred",
                "content": "Inferred from project notes.",
                "supports": list(FIELDS),
            }
        },
        idempotency_key=key,
    )


@pytest.fixture
def env(tmp_path: Path) -> dict[str, Any]:
    vault = tmp_path / "vault"
    vault.mkdir()
    return {
        "store": tmp_path / "memory.db",
        "vault": vault,
        "wing": "project-alpha",
        "spec": tmp_path / "SPEC.md",
    }


def _human(answer: str | None = None) -> tuple[list[str], Any]:
    """Return shown text plus a person who types the code shown, or a fixed answer."""
    shown: list[str] = []

    def ask(prompt: str) -> str:
        shown.append(prompt)
        if answer is not None:
            return answer
        return re.search(r"Type ([0-9a-f]{6})", prompt).group(1)  # type: ignore[union-attr]

    return shown, ask


def _confirm(env: dict[str, Any], ask: Any, *, interactive: bool = True) -> dict[str, Any]:
    return confirm_audience(
        env["store"],
        env["vault"],
        env["wing"],
        interactive=interactive,
        ask=ask,
        show=lambda _text: None,
    )


def _confirmation_rows(store: Path) -> int:
    with sqlite3.connect(store) as conn:
        found = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='cairntir_audience_confirmations'"
        ).fetchone()
        if found is None:
            return 0
        return int(
            conn.execute("SELECT COUNT(*) FROM cairntir_audience_confirmations").fetchone()[0]
        )


def test_inferred_profile_stays_provisional_until_a_person_confirms(env: dict[str, Any]) -> None:
    _publish(env)
    assert audience_lock(env["store"], env["vault"], env["wing"])["lock"] == "provisional"
    _, ask = _human()
    result = _confirm(env, ask)
    assert result["lock"] == "confirmed"
    assert result["confirmation"]["method"] == "interactive-terminal"
    assert audience_lock(env["store"], env["vault"], env["wing"])["lock"] == "confirmed"


@pytest.mark.parametrize("answer", ["", "yes", "000000", "y"])
def test_wrong_or_empty_answer_never_confirms(env: dict[str, Any], answer: str) -> None:
    _publish(env)
    _, ask = _human(answer)
    with pytest.raises(ProjectionError, match="not confirmed"):
        _confirm(env, ask)
    assert _confirmation_rows(env["store"]) == 0
    assert audience_lock(env["store"], env["vault"], env["wing"])["lock"] == "provisional"


@pytest.mark.parametrize("silence", [EOFError, KeyboardInterrupt])
def test_silence_is_not_confirmation(env: dict[str, Any], silence: type[BaseException]) -> None:
    _publish(env)

    def ask(_prompt: str) -> str:
        raise silence

    with pytest.raises(ProjectionError, match="not confirmed"):
        _confirm(env, ask)
    assert _confirmation_rows(env["store"]) == 0


def test_non_interactive_caller_is_refused_before_asking(env: dict[str, Any]) -> None:
    _publish(env)
    shown, ask = _human()
    with pytest.raises(ProjectionError, match="interactive terminal"):
        _confirm(env, ask, interactive=False)
    assert shown == []
    assert _confirmation_rows(env["store"]) == 0


def test_code_changes_each_attempt_so_an_answer_cannot_be_prepared(env: dict[str, Any]) -> None:
    _publish(env)
    codes = set()
    for _ in range(4):
        shown, ask = _human("nope")
        with pytest.raises(ProjectionError):
            _confirm(env, ask)
        codes.add(re.search(r"Type ([0-9a-f]{6})", shown[0]).group(1))  # type: ignore[union-attr]
    assert len(codes) > 1


def test_person_sees_every_value_and_where_it_came_from(env: dict[str, Any]) -> None:
    _publish(env)
    seen: list[str] = []
    _, ask = _human()
    confirm_audience(
        env["store"], env["vault"], env["wing"], interactive=True, ask=ask, show=seen.append
    )
    text = "\n".join(seen)
    for field in FIELDS:
        assert f"chosen {field}" in text
    assert "model-guess" in text
    assert "inferred" in text


def test_new_revision_drops_the_earlier_confirmation(env: dict[str, Any]) -> None:
    _publish(env)
    _, ask = _human()
    _confirm(env, ask)
    _publish(env, key="second", prefix="changed")
    state = audience_lock(env["store"], env["vault"], env["wing"])
    assert state["revision"] == 2
    assert state["lock"] == "provisional"
    assert state["confirmation"] is None


def test_revision_changed_while_person_reads_is_refused(env: dict[str, Any]) -> None:
    _publish(env)

    def ask(prompt: str) -> str:
        _publish(env, key="racer", prefix="raced")
        return re.search(r"Type ([0-9a-f]{6})", prompt).group(1)  # type: ignore[union-attr]

    with pytest.raises(ProjectionError, match="changed"):
        _confirm(env, ask)
    assert _confirmation_rows(env["store"]) == 0


def test_changed_snapshot_cannot_be_confirmed(env: dict[str, Any]) -> None:
    receipt = _publish(env)
    Path(receipt["snapshot_path"]).write_bytes(b"edited\n")
    _, ask = _human()
    with pytest.raises(ProjectionError, match="snapshot"):
        _confirm(env, ask)
    assert _confirmation_rows(env["store"]) == 0


def test_confirming_twice_keeps_the_first_receipt(env: dict[str, Any]) -> None:
    _publish(env)
    _, ask = _human()
    first = _confirm(env, ask)["confirmation"]
    shown, ask_again = _human()
    assert _confirm(env, ask_again)["confirmation"] == first
    assert shown == []
    assert _confirmation_rows(env["store"]) == 1


def test_confirmation_does_not_rewrite_the_immutable_revision(env: dict[str, Any]) -> None:
    receipt = _publish(env)
    before = Path(receipt["snapshot_path"]).read_bytes()
    _, ask = _human()
    _confirm(env, ask)
    assert Path(receipt["snapshot_path"]).read_bytes() == before
    assert get_audience_revision(env["store"], env["vault"], env["wing"])["status"] == "provisional"


def test_transfer_carries_all_five_dimensions_sources_and_provisional_label(
    env: dict[str, Any],
) -> None:
    _publish(env)
    result = transfer_audience_to_spec(env["store"], env["vault"], env["wing"], env["spec"])
    text = env["spec"].read_text(encoding="utf-8")
    assert result["changed"] is True
    assert result["lock"] == "provisional"
    assert "Status: provisional" in text
    assert "not confirmed by a person" in text
    for field in FIELDS:
        # The block escapes Markdown in human values.
        shown = re.escape(field.replace("_", r"\_"))
        assert re.search(rf"- {field}: chosen {shown} .*model-guess \(inferred\)", text)


def test_transfer_after_confirmation_says_confirmed(env: dict[str, Any]) -> None:
    _publish(env)
    _, ask = _human()
    _confirm(env, ask)
    transfer_audience_to_spec(env["store"], env["vault"], env["wing"], env["spec"])
    text = env["spec"].read_text(encoding="utf-8")
    assert "Status: confirmed" in text
    assert "not confirmed by a person" not in text


def test_transfer_preserves_human_bytes_around_the_block(env: dict[str, Any]) -> None:
    _publish(env)
    head = b"# My spec\r\n\r\nCaf\xc3\xa9 notes.\r\n\r\n"
    tail = b"\r\n\r\n## Later\r\nKeep me.\r\n"
    env["spec"].write_bytes(head + BEGIN + b"\r\nold\r\n" + END + tail)
    transfer_audience_to_spec(env["store"], env["vault"], env["wing"], env["spec"])
    after = env["spec"].read_bytes()
    assert after.startswith(head + BEGIN)
    assert after.endswith(END + tail)
    assert b"old" not in after
    inside = after[len(head) : -len(tail)]
    assert b"\n" not in inside.replace(b"\r\n", b"")


def test_transfer_appends_without_touching_existing_text(env: dict[str, Any]) -> None:
    _publish(env)
    env["spec"].write_bytes(b"# My spec\nno trailing newline")
    transfer_audience_to_spec(env["store"], env["vault"], env["wing"], env["spec"])
    after = env["spec"].read_bytes()
    assert after.startswith(b"# My spec\nno trailing newline\n")
    assert after.count(BEGIN) == 1
    assert after.count(END) == 1


def test_repeat_transfer_changes_nothing(env: dict[str, Any]) -> None:
    _publish(env)
    transfer_audience_to_spec(env["store"], env["vault"], env["wing"], env["spec"])
    before = env["spec"].read_bytes()
    result = transfer_audience_to_spec(env["store"], env["vault"], env["wing"], env["spec"])
    assert result["changed"] is False
    assert env["spec"].read_bytes() == before


@pytest.mark.parametrize(
    "content",
    [
        BEGIN + b"\nonly begin\n",
        END + b"\nonly end\n",
        END + b"\n" + BEGIN + b"\n",
        BEGIN + b"\n" + END + b"\n" + BEGIN + b"\n" + END + b"\n",
    ],
)
def test_ambiguous_markers_refuse_and_preserve_the_file(
    env: dict[str, Any], content: bytes
) -> None:
    _publish(env)
    env["spec"].write_bytes(content)
    with pytest.raises(ProjectionError, match="ambiguous"):
        transfer_audience_to_spec(env["store"], env["vault"], env["wing"], env["spec"])
    assert env["spec"].read_bytes() == content


def test_invalid_utf8_spec_refuses_and_preserves_the_file(env: dict[str, Any]) -> None:
    _publish(env)
    env["spec"].write_bytes(b"\xff\xfe not utf-8")
    with pytest.raises(ProjectionError):
        transfer_audience_to_spec(env["store"], env["vault"], env["wing"], env["spec"])
    assert env["spec"].read_bytes() == b"\xff\xfe not utf-8"


def test_failed_replace_keeps_the_original_and_leaves_no_temporary_file(
    env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _publish(env)
    env["spec"].write_bytes(b"# Mine\n")

    def fail(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk trouble")

    monkeypatch.setattr("cairntir.audience_lock.os.replace", fail)
    with pytest.raises(ProjectionError, match="disk trouble"):
        transfer_audience_to_spec(env["store"], env["vault"], env["wing"], env["spec"])
    assert env["spec"].read_bytes() == b"# Mine\n"
    assert sorted(p.name for p in env["spec"].parent.iterdir() if p.name.startswith(".spec")) == []


def test_spec_goes_stale_when_the_audience_changes(env: dict[str, Any]) -> None:
    _publish(env)
    state = spec_transfer_state(env["store"], env["vault"], env["wing"], env["spec"])
    assert state == "absent"
    transfer_audience_to_spec(env["store"], env["vault"], env["wing"], env["spec"])
    assert spec_transfer_state(env["store"], env["vault"], env["wing"], env["spec"]) == "current"
    _, ask = _human()
    _confirm(env, ask)
    assert spec_transfer_state(env["store"], env["vault"], env["wing"], env["spec"]) == "stale"
    transfer_audience_to_spec(env["store"], env["vault"], env["wing"], env["spec"])
    assert spec_transfer_state(env["store"], env["vault"], env["wing"], env["spec"]) == "current"
    _publish(env, key="second", prefix="changed")
    assert spec_transfer_state(env["store"], env["vault"], env["wing"], env["spec"]) == "stale"


def test_cli_status_and_transfer_report_the_lock(env: dict[str, Any]) -> None:
    _publish(env)
    common = ["--wing", env["wing"], "--vault", str(env["vault"]), "--store", str(env["store"])]
    runner = CliRunner()
    moved = runner.invoke(app, ["audience", "transfer-spec", "--spec", str(env["spec"]), *common])
    assert moved.exit_code == 0, moved.output
    status = runner.invoke(app, ["audience", "status", "--spec", str(env["spec"]), *common])
    assert status.exit_code == 0, status.output
    assert '"lock": "provisional"' in status.output
    assert '"spec": "current"' in status.output


def test_cli_confirm_refuses_without_a_real_terminal(env: dict[str, Any]) -> None:
    _publish(env)
    common = ["--wing", env["wing"], "--vault", str(env["vault"]), "--store", str(env["store"])]
    result = CliRunner().invoke(app, ["audience", "confirm", *common], input="anything\n")
    assert result.exit_code == 1
    assert "interactive terminal" in result.output
    assert _confirmation_rows(env["store"]) == 0


def test_cli_status_reports_a_missing_store_as_a_failure(env: dict[str, Any]) -> None:
    common = ["--wing", env["wing"], "--vault", str(env["vault"]), "--store", str(env["store"])]
    result = CliRunner().invoke(app, ["audience", "status", *common])
    assert result.exit_code == 1
    assert "audience store does not exist" in result.output
    assert not env["store"].exists()
