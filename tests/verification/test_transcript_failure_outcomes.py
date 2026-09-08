from __future__ import annotations

import json
import re

import pytest
from test_recovery_outcomes import TEXT, contents

from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.transcript import RecoveryContext, recover_transcript, render_recovery_report

REQUEST = "Resume the Unicode request: café 日本語 🌲."


@pytest.mark.parametrize(
    "shape", ["claude-string", "claude-parts", "qwen", "codex-event", "codex-parts"]
)
def test_recovered_request_retains_exact_whitespace_and_unicode(seeded, transcript_case, shape):
    database, _, _ = seeded
    expected = TEXT + "\n\n" if shape.endswith("parts") else TEXT
    if shape.startswith("claude"):
        content = (
            TEXT
            if shape.endswith("string")
            else [{"type": "text", "text": TEXT}, {"type": "text", "text": "\n"}]
        )
        host, row = "claude", {"type": "user", "message": {"role": "user", "content": content}}
    elif shape == "qwen":
        host, row = (
            "qwen",
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "parts": [{"text": TEXT}, {"text": "injected hook context"}],
                },
            },
        )
    elif shape == "codex-event":
        host, row = (
            "codex",
            {"type": "event_msg", "payload": {"type": "user_message", "message": TEXT}},
        )
    else:
        host, row = (
            "codex",
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": TEXT},
                        {"type": "input_text", "text": "\n"},
                    ],
                },
            },
        )
    context, _ = transcript_case(host, [row])
    before = contents(database)
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        report = recover_transcript(store, wing="recovery", context=context)
        assert len(report.requests) == 1
        assert report.requests[0].content == expected, (
            "RECOVERY: transcript altered original whitespace"
        )
        assert report.used_chars == len(expected)
    assert contents(database) == before


@pytest.fixture()
def transcript_case(tmp_path):
    home, project = tmp_path / "host-home", tmp_path / "project"
    project.mkdir(exist_ok=True)

    def prepare(host, rows):
        context = RecoveryContext(host=host, home=home, project_root=project)
        if host == "codex":
            path = home / ".codex" / "sessions" / "rollout-verification.jsonl"
            rows = [{"type": "session_meta", "payload": {"cwd": str(project)}}, *rows]
        else:
            bucket = re.sub(r"[^a-zA-Z0-9]", "-", str(project.resolve()))
            path = home / f".{host}" / "projects" / bucket
            if host == "qwen":
                path /= "chats"
            path /= "verification.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
        )
        return context, path

    return prepare


@pytest.mark.parametrize("host", ["claude", "qwen", "codex"])
def test_malformed_tail_reports_degradation_without_inventing_or_saving_a_request(
    seeded, transcript_case, host
):
    database, _, _ = seeded
    context, path = transcript_case(host, [])
    with path.open("ab") as handle:
        handle.write(b"{broken\n[]\n\xff\n")
    before = contents(database)
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        result = recover_transcript(store, wing="recovery", context=context)
    assert result.status == "degraded" and result.malformed_events == 3
    assert result.requests == () and result.stored_requests == 0
    assert "3 malformed" in render_recovery_report(result)
    assert contents(database) == before


@pytest.mark.parametrize("host", ["claude", "qwen"])
@pytest.mark.parametrize("shape", ["not-message", "wrong-role", "empty", "nontext-parts"])
def test_tool_or_non_user_transcript_content_is_never_mistaken_for_a_request(
    seeded, transcript_case, host, shape
):
    message = {"role": "user", "content": REQUEST, "parts": [{"text": REQUEST}]}
    if shape == "not-message":
        message = []
    elif shape == "wrong-role":
        message["role"] = "tool"
    elif shape == "empty":
        message.update(content="", parts=[])
    else:
        message.update(
            content=[{"type": "image", "text": REQUEST}],
            parts=[None, {"functionCall": {"name": "tool"}}],
        )
    database, _, _ = seeded
    context, _ = transcript_case(host, [{"type": "user", "message": message}])
    before = contents(database)
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        result = recover_transcript(store, wing="recovery", context=context)
    assert result.requests == () and result.status == "clear"
    assert contents(database) == before


@pytest.mark.parametrize("timestamp", [None, "not-a-date", "2026-09-07T12:00:00"])
def test_unfinished_request_uses_an_explicit_fallback_time_and_remains_unsaved(
    seeded, transcript_case, timestamp
):
    database, _, _ = seeded
    context, path = transcript_case(
        "claude",
        [
            {
                "type": "user",
                "timestamp": timestamp,
                "message": {"role": "user", "content": [{"type": "text", "text": REQUEST}]},
            }
        ],
    )
    before = contents(database)
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        result = recover_transcript(store, wing="recovery", context=context)
    assert result.status == "recovered" and len(result.requests) == 1
    recovered = result.requests[0]
    assert recovered.content == REQUEST and recovered.session_id == "verification"
    assert recovered.timestamp.tzinfo is not None
    if timestamp != "2026-09-07T12:00:00":
        assert recovered.timestamp.timestamp() == pytest.approx(path.stat().st_mtime)
    assert result.stored_requests == 0 and contents(database) == before


@pytest.mark.parametrize("field", ["budget_chars", "max_requests", "max_events"])
def test_invalid_recovery_limits_fail_before_reading_or_writing(seeded, tmp_path, field):
    database, _, _ = seeded
    before = contents(database)
    context = RecoveryContext(host="claude", home=tmp_path / "absent", project_root=tmp_path)
    with (
        DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store,
        pytest.raises(ValueError, match="positive"),
    ):
        recover_transcript(store, wing="recovery", context=context, **{field: 0})
    assert contents(database) == before and not context.home.exists()


@pytest.mark.parametrize(
    "reason", ["wrong-project", "child-task", "wrong-metadata", "oversized-header"]
)
def test_codex_history_outside_the_requested_context_cannot_leak_into_recovery(
    seeded, transcript_case, reason
):
    database, _, _ = seeded
    context, path = transcript_case(
        "codex",
        [
            {
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "private unrelated request"},
            }
        ],
    )
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    if reason == "wrong-project":
        rows[0]["payload"]["cwd"] = str(context.project_root / "other")
    elif reason == "child-task":
        rows[0]["payload"]["parent_thread_id"] = "parent"
    elif reason == "wrong-metadata":
        rows[0] = {"type": "session_meta", "payload": []}
    else:
        rows[0]["padding"] = "x" * 262145
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    before = contents(database)
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        result = recover_transcript(store, wing="recovery", context=context)
    assert result.status == "unavailable" and result.requests == ()
    assert "private unrelated request" not in render_recovery_report(result)
    assert contents(database) == before


def test_codex_valid_request_survives_invalid_utf8_later_in_the_file(seeded, transcript_case):
    database, _, _ = seeded
    context, path = transcript_case(
        "codex", [{"type": "event_msg", "payload": {"type": "user_message", "message": REQUEST}}]
    )
    with path.open("ab") as handle:
        handle.write(b"\xff\n")
    before = contents(database)
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        result = recover_transcript(store, wing="recovery", context=context)
    assert [request.content for request in result.requests] == [REQUEST], (
        "RECOVERY: valid transcript request was lost"
    )
    assert result.malformed_events == 1
    assert contents(database) == before


@pytest.mark.parametrize("header", [None, [], "not metadata", 1])
def test_nonobject_codex_header_is_unavailable_instead_of_crashing(seeded, transcript_case, header):
    database, _, _ = seeded
    context, path = transcript_case("codex", [])
    path.write_text(json.dumps(header) + "\n", encoding="utf-8")
    before = contents(database)
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        result = recover_transcript(store, wing="recovery", context=context)
    assert result.status == "unavailable" and result.requests == ()
    assert contents(database) == before
