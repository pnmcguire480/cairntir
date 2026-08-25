"""Bounded transcript recovery across supported host adapters."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cairntir.cli import app
from cairntir.mcp.backend import CairntirBackend
from cairntir.mcp.server import _tool_specs
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.provenance import TrustLevel
from cairntir.transcript import (
    RecoveryContext,
    recover_transcript,
    render_recovery_report,
    store_recovered_request,
)


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[DrawerStore]:
    with DrawerStore(tmp_path / "memory.db", HashEmbeddingProvider(dimension=32)) as opened:
        yield opened


def _write_jsonl(path: Path, rows: list[dict[str, object]], *, mtime: float = 1.0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    os.utime(path, (mtime, mtime))
    return path


def _bucket(root: Path) -> str:
    return str(root.resolve()).replace(":", "-").replace("\\", "-").replace("/", "-")


def _qwen_path(home: Path, project: Path, session: str) -> Path:
    return home / ".qwen" / "projects" / _bucket(project) / "chats" / f"{session}.jsonl"


def _claude_path(home: Path, project: Path, session: str) -> Path:
    return home / ".claude" / "projects" / _bucket(project) / f"{session}.jsonl"


def _codex_path(home: Path, session: str) -> Path:
    return (
        home
        / ".codex"
        / "sessions"
        / "2026"
        / "08"
        / "25"
        / f"rollout-2026-08-25T10-00-00-{session}.jsonl"
    )


def _qwen_user(session: str, timestamp: str, content: str) -> dict[str, object]:
    return {
        "type": "user",
        "sessionId": session,
        "timestamp": timestamp,
        "message": {"role": "user", "parts": [{"text": content}]},
    }


def _qwen_tool_turn(session: str, timestamp: str) -> dict[str, object]:
    return {
        "type": "assistant",
        "sessionId": session,
        "timestamp": timestamp,
        "message": {
            "role": "model",
            "parts": [{"text": "working", "thought": True}, {"functionCall": {"name": "read"}}],
        },
    }


def _codex_meta(session: str, project: Path) -> dict[str, object]:
    return {
        "timestamp": "2026-08-25T10:00:00Z",
        "type": "session_meta",
        "payload": {"id": session, "cwd": str(project.resolve())},
    }


def _codex_user(turn: str, content: str) -> dict[str, object]:
    return {
        "timestamp": "2026-08-25T10:00:01Z",
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": content}],
            "internal_chat_message_metadata_passthrough": {"turn_id": turn},
        },
    }


def test_qwen_recovers_first_user_part_and_rejects_hook_context(
    store: DrawerStore, tmp_path: Path
) -> None:
    home, project = tmp_path / "home", tmp_path / "project"
    project.mkdir()
    session = "11111111-1111-1111-1111-111111111111"
    request = "Write the README addendum exactly as requested."
    row = _qwen_user(session, "2026-08-05T23:25:50Z", request)
    row["message"] = {
        "role": "user",
        "parts": [{"text": request}, {"text": "injected hook context"}],
    }
    _write_jsonl(
        _qwen_path(home, project, session),
        [row, _qwen_tool_turn(session, "2026-08-05T23:25:55Z")],
    )

    report = recover_transcript(
        store,
        wing="cairntir",
        context=RecoveryContext("qwen", project, home),
    )

    assert [item.content for item in report.requests] == [request]
    assert "injected hook context" not in render_recovery_report(report)


def test_qwen_final_text_marks_the_request_complete(store: DrawerStore, tmp_path: Path) -> None:
    home, project = tmp_path / "home", tmp_path / "project"
    project.mkdir()
    session = "22222222-2222-2222-2222-222222222222"
    rows = [
        _qwen_user(session, "2026-08-05T23:25:50Z", "Explain the result."),
        {
            "type": "assistant",
            "sessionId": session,
            "timestamp": "2026-08-05T23:25:55Z",
            "message": {"role": "model", "parts": [{"text": "The result is complete."}]},
        },
    ]
    _write_jsonl(_qwen_path(home, project, session), rows)

    report = recover_transcript(
        store,
        wing="cairntir",
        context=RecoveryContext("qwen", project, home),
    )

    assert report.status == "clear"
    assert report.completed_requests == 1


def test_claude_adapter_ignores_tool_results_and_requires_end_turn(
    store: DrawerStore, tmp_path: Path
) -> None:
    home, project = tmp_path / "home", tmp_path / "project"
    project.mkdir()
    session = "33333333-3333-3333-3333-333333333333"
    request = "Finish the bounded transcript adapter."
    rows: list[dict[str, object]] = [
        {
            "type": "user",
            "sessionId": session,
            "timestamp": "2026-08-25T10:00:01Z",
            "message": {"role": "user", "content": request},
        },
        {
            "type": "assistant",
            "sessionId": session,
            "timestamp": "2026-08-25T10:00:02Z",
            "message": {
                "role": "assistant",
                "stop_reason": "tool_use",
                "content": [{"type": "tool_use", "name": "Read"}],
            },
        },
        {
            "type": "user",
            "sessionId": session,
            "timestamp": "2026-08-25T10:00:03Z",
            "toolUseResult": {"ok": True},
            "message": {
                "role": "user",
                "content": [{"type": "tool_result", "content": "untrusted output"}],
            },
        },
    ]
    _write_jsonl(_claude_path(home, project, session), rows)

    report = recover_transcript(
        store,
        wing="cairntir",
        context=RecoveryContext("claude", project, home),
    )

    assert [item.content for item in report.requests] == [request]


def test_claude_end_turn_marks_the_request_complete(store: DrawerStore, tmp_path: Path) -> None:
    home, project = tmp_path / "home", tmp_path / "project"
    project.mkdir()
    session = "34343434-3434-3434-3434-343434343434"
    rows: list[dict[str, object]] = [
        {
            "type": "user",
            "sessionId": session,
            "timestamp": "2026-08-25T10:00:01Z",
            "message": {"role": "user", "content": "Explain the adapter."},
        },
        {
            "type": "assistant",
            "sessionId": session,
            "timestamp": "2026-08-25T10:00:02Z",
            "message": {
                "role": "assistant",
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "Done."}],
            },
        },
    ]
    _write_jsonl(_claude_path(home, project, session), rows)

    report = recover_transcript(
        store,
        wing="cairntir",
        context=RecoveryContext("claude", project, home),
    )

    assert report.status == "clear"
    assert report.completed_requests == 1


def test_codex_adapter_filters_injected_app_context(store: DrawerStore, tmp_path: Path) -> None:
    home, project = tmp_path / "home", tmp_path / "project"
    project.mkdir()
    session = "44444444-4444-4444-4444-444444444444"
    rows = [
        _codex_meta(session, project),
        _codex_user("turn-1", "<recommended_plugins>not user-authored</recommended_plugins>"),
        _codex_user("turn-1", "Implement the Codex transcript adapter."),
    ]
    _write_jsonl(_codex_path(home, session), rows)

    report = recover_transcript(
        store,
        wing="cairntir",
        context=RecoveryContext("codex", project, home),
    )

    assert [item.content for item in report.requests] == ["Implement the Codex transcript adapter."]


def test_codex_task_complete_marks_the_turn_complete(store: DrawerStore, tmp_path: Path) -> None:
    home, project = tmp_path / "home", tmp_path / "project"
    project.mkdir()
    session = "45454545-4545-4545-4545-454545454545"
    rows = [
        _codex_meta(session, project),
        _codex_user("turn-complete", "Explain the Codex adapter."),
        {
            "timestamp": "2026-08-25T10:00:02Z",
            "type": "event_msg",
            "payload": {"type": "task_complete", "turn_id": "turn-complete"},
        },
    ]
    _write_jsonl(_codex_path(home, session), rows)

    report = recover_transcript(
        store,
        wing="cairntir",
        context=RecoveryContext("codex", project, home),
    )

    assert report.status == "clear"
    assert report.completed_requests == 1


def test_kill_after_request_is_named_verbatim_on_first_handoff(
    store: DrawerStore, tmp_path: Path
) -> None:
    home, project = tmp_path / "home", tmp_path / "project"
    project.mkdir()
    previous = "55555555-5555-5555-5555-555555555555"
    current = "66666666-6666-6666-6666-666666666666"
    subagent = "67676767-6767-6767-6767-676767676767"
    request = "Kill this session now; the fresh task must recover this sentence verbatim."
    killed_path = _codex_path(home, previous)
    transcript = "".join(
        json.dumps(row) + "\n"
        for row in [_codex_meta(previous, project), _codex_user("killed-turn", request)]
    )
    writer = (
        "import sys,time; from pathlib import Path; "
        "p=Path(sys.argv[1]); p.parent.mkdir(parents=True,exist_ok=True); "
        "p.write_text(sys.argv[2],encoding='utf-8'); print('ready',flush=True); time.sleep(60)"
    )
    process = subprocess.Popen(  # noqa: S603
        [sys.executable, "-c", writer, str(killed_path), transcript],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        assert process.stdout.readline().strip() == "ready"
    finally:
        process.terminate()
        process.wait(timeout=5)
    os.utime(killed_path, (1.0, 1.0))
    _write_jsonl(
        _codex_path(home, current),
        [_codex_meta(current, project), _codex_user("live-turn", "first handoff")],
        mtime=2.0,
    )
    subagent_meta = _codex_meta(subagent, project)
    subagent_payload = subagent_meta["payload"]
    assert isinstance(subagent_payload, dict)
    subagent_payload["source"] = {"subagent": {"other": "guardian"}}
    subagent_payload["parent_thread_id"] = current
    _write_jsonl(
        _codex_path(home, subagent),
        [subagent_meta, _codex_user("subagent-turn", "internal delegated work")],
        mtime=3.0,
    )
    backend = CairntirBackend(
        store,
        recovery_context=RecoveryContext(
            "codex",
            project,
            home,
            current_session_id=current,
            live_session=True,
        ),
    )

    rendered = backend.handoff(wing="cairntir", recover_transcripts=True)

    payload = json.loads(rendered.split("<cairntir-transcript-evidence>\n", 1)[1].split("\n", 1)[0])
    assert payload["content"] == request
    assert payload["trust"] == "untrusted"
    assert store.list_by(wing="cairntir", limit=None) == []


def test_cursor_returns_an_honest_unsupported_receipt(store: DrawerStore, tmp_path: Path) -> None:
    report = recover_transcript(
        store,
        wing="cairntir",
        context=RecoveryContext("cursor", tmp_path, tmp_path),
    )

    assert report.status == "unsupported"
    assert "SQLite" in report.detail
    assert "will not guess" in report.detail


def test_recovery_budget_never_truncates_a_message(store: DrawerStore, tmp_path: Path) -> None:
    home, project = tmp_path / "home", tmp_path / "project"
    project.mkdir()
    session = "77777777-7777-7777-7777-777777777777"
    request = "X" * 101
    _write_jsonl(
        _qwen_path(home, project, session),
        [_qwen_user(session, "2026-08-25T10:00:01Z", request)],
    )

    report = recover_transcript(
        store,
        wing="cairntir",
        context=RecoveryContext("qwen", project, home),
        budget_chars=100,
    )

    assert report.requests == ()
    assert report.omitted[0].chars == 101
    assert request not in render_recovery_report(report)


def test_exact_later_drawer_suppresses_recovery(store: DrawerStore, tmp_path: Path) -> None:
    home, project = tmp_path / "home", tmp_path / "project"
    project.mkdir()
    session = "88888888-8888-8888-8888-888888888888"
    request = "This request was captured on arrival."
    timestamp = datetime(2026, 8, 25, 10, tzinfo=UTC)
    _write_jsonl(
        _qwen_path(home, project, session),
        [_qwen_user(session, timestamp.isoformat(), request)],
    )
    store.add(
        Drawer(
            wing="cairntir",
            room="requests",
            content=request,
            created_at=timestamp + timedelta(seconds=1),
        )
    )

    report = recover_transcript(
        store,
        wing="cairntir",
        context=RecoveryContext("qwen", project, home),
    )

    assert report.status == "clear"
    assert report.stored_requests == 1


def test_recovery_never_writes_without_explicit_selection(
    store: DrawerStore, tmp_path: Path
) -> None:
    home, project = tmp_path / "home", tmp_path / "project"
    project.mkdir()
    session = "99999999-9999-9999-9999-999999999999"
    _write_jsonl(
        _qwen_path(home, project, session),
        [_qwen_user(session, "2026-08-25T10:00:01Z", "Store only with consent.")],
    )

    report = recover_transcript(
        store,
        wing="cairntir",
        context=RecoveryContext("qwen", project, home),
    )
    assert store.list_by(wing="cairntir", limit=None) == []

    saved = store_recovered_request(
        store,
        wing="cairntir",
        request=report.requests[0],
    )
    provenance = store.get_provenance(saved.id or 0)
    assert provenance is not None
    assert provenance.trust is TrustLevel.UNTRUSTED
    assert provenance.capture_path == "transcript_recovered"


def test_mcp_handoff_recovery_is_opt_in_by_default() -> None:
    schema = next(tool.inputSchema for tool in _tool_specs() if tool.name == "cairntir_handoff")

    assert schema["properties"]["recover_transcripts"]["default"] is False
    assert schema["properties"]["recovery_budget_chars"]["default"] == 4_000


def test_recover_cli_requires_explicit_write(
    store: DrawerStore,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home, project = tmp_path / "home", tmp_path / "project"
    project.mkdir()
    session = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    _write_jsonl(
        _qwen_path(home, project, session),
        [_qwen_user(session, "2026-08-25T10:00:01Z", "Explicit CLI consent only.")],
    )
    context = RecoveryContext("qwen", project, home)
    monkeypatch.setattr("cairntir.cli._open_store", lambda **_kwargs: store)
    monkeypatch.setattr("cairntir.cli._cli_recovery_context", lambda _host: context)
    runner = CliRunner()

    preview = runner.invoke(app, ["recover", "--host", "qwen", "--wing", "cairntir"])
    assert preview.exit_code == 0
    assert store.list_by(wing="cairntir", limit=None) == []

    written = runner.invoke(
        app,
        ["recover", "--host", "qwen", "--wing", "cairntir", "--write", "1"],
    )
    assert written.exit_code == 0
    assert "trust=untrusted" in written.stdout
    assert [drawer.content for drawer in store.list_by(wing="cairntir", limit=None)] == [
        "Explicit CLI consent only."
    ]
