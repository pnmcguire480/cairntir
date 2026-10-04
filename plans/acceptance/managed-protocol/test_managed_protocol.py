"""Independent public managed JSONL routing, failure and close behavior."""

from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from cairntir import cli, managed
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.tasks import TaskBook


def command(operation, request):
    return {"schema": "cairntir.managed-command.v1", "operation": operation, "request": request}


def line(operation, request):
    return json.dumps(command(operation, request)) + "\n"


class RecordingRuntime:
    def __init__(self):
        self.calls = []
        self.fail_operation = None
        self.after_start = None

    def receipt(self, operation, request):
        self.calls.append((operation, request))
        if operation == self.fail_operation:
            raise managed.ManagedRuntimeError("independent synthetic operation failure")
        return {"schema": "cairntir.managed-" + operation + ".v1", "operation": operation}

    def start(self, session_id, *, task_id=None):
        result = self.receipt("start", {"session_id": session_id, "task_id": task_id})
        if self.after_start:
            self.after_start()
        return result

    def capture(self, request):
        return self.receipt("capture", request)

    def acknowledge(self, request):
        return self.receipt("acknowledge", request)

    def dispatch(self, request):
        return self.receipt("dispatch", request)

    def brief(self):
        return self.receipt("brief", {})

    def status(self, action_id):
        return self.receipt("status", {"action_id": action_id})

    def close(self, *, last_sequence=None):
        return self.receipt("close", {"last_sequence": last_sequence})


@pytest.mark.parametrize(
    "operation,request",
    [
        ("capture", {"verbatim": "  caf\u00e9\r\nline two  ", "nested": {"original": True}}),
        ("acknowledge", {"brief_id": "producer-owned identity"}),
        ("dispatch", {"profile": "fixed startup profile", "event_ids": ["producer identity"]}),
        ("brief", {}),
        ("status", {"action_id": "exact status identity"}),
        ("close", {"last_sequence": 7}),
    ],
)
def test_allowed_envelope_routes_exactly_one_public_operation(operation, request):
    runtime = RecordingRuntime()
    supplied = command(operation, request)
    before = json.dumps(supplied, ensure_ascii=False)
    result = managed.stream_command(runtime, supplied)
    assert runtime.calls == [(operation, request)]
    assert result["operation"] == operation
    assert json.dumps(supplied, ensure_ascii=False) == before


@pytest.mark.parametrize(
    "supplied",
    [
        [],
        {"schema": "cairntir.managed-command.v1", "operation": "brief"},
        {**command("brief", {}), "executable": "arbitrary caller executable"},
        {**command("brief", {}), "schema": "foreign.schema"},
        command("capture", []),
        command("start", {}),
        command("__getattribute__", {"name": "_store"}),
        command("status", {}),
        command("status", {"action_id": "identity", "argv": ["untrusted"]}),
        command("brief", {"replace_configuration": True}),
        command("close", {}),
        command("close", {"last_sequence": 1, "approve": True}),
    ],
)
def test_rejected_envelope_cannot_call_runtime_or_dispatch(supplied):
    runtime = RecordingRuntime()
    with pytest.raises(managed.ManagedRuntimeError):
        managed.stream_command(runtime, supplied)
    assert runtime.calls == [], "Rejected envelope reached runtime state or process dispatch"


@pytest.fixture
def cli_loop(tmp_path, monkeypatch):
    config = tmp_path / "managed.json"
    config.write_text(json.dumps({"inert_configuration": True}), encoding="utf-8")
    runtime = RecordingRuntime()
    lifecycle = []
    session_id = str(uuid4())

    @contextmanager
    def open_store(*, capture_path):
        assert capture_path == "cli.managed"
        lifecycle.append("entered")
        try:
            yield object()
        finally:
            lifecycle.append("closed")

    monkeypatch.setattr(cli, "_open_store", open_store)
    monkeypatch.setattr(managed, "ManagedRuntime", lambda store, *, config: runtime)
    monkeypatch.setattr("cairntir.access.startup_token", lambda: None)

    def invoke(text):
        result = CliRunner().invoke(
            cli.app, ["managed", "--config", str(config), "--session-id", session_id], input=text
        )
        output = [json.loads(value) for value in result.stdout.splitlines()]
        return result, output

    return invoke, runtime, lifecycle, config, session_id


def test_cli_explicit_close_stops_without_processing_following_commands(cli_loop):
    invoke, runtime, lifecycle, _config, session_id = cli_loop
    result, output = invoke(
        line("brief", {})
        + line("status", {"action_id": "exact-id"})
        + line("close", {"last_sequence": 4})
        + line("dispatch", {"bad": True})
    )
    assert result.exit_code == 0, result.exception
    assert [item["operation"] for item in output] == ["start", "brief", "status", "close"]
    assert runtime.calls == [
        ("start", {"session_id": session_id, "task_id": None}),
        ("brief", {}),
        ("status", {"action_id": "exact-id"}),
        ("close", {"last_sequence": 4}),
    ]
    assert lifecycle == ["entered", "closed"]


def test_cli_eof_closes_without_inventing_producer_watermark(cli_loop):
    invoke, runtime, lifecycle, _config, _session_id = cli_loop
    result, output = invoke("")
    assert result.exit_code == 0, result.exception
    assert [item["operation"] for item in output] == ["start", "close"]
    assert runtime.calls[-1] == ("close", {"last_sequence": None})
    assert lifecycle == ["entered", "closed"]


@pytest.mark.parametrize(
    "invalid,error_operation",
    [
        ("{broken JSON}\n", "decode"),
        (
            '{"schema":"cairntir.managed-command.v1","operation":"brief","operation":"dispatch","request":{}}\n',
            "decode",
        ),
        (
            '{"schema":"cairntir.managed-command.v1","operation":"capture","request":{"content":"first","content":"second"}}\n',
            "decode",
        ),
        ("[]\n", "decode"),
        (line("start", {}), "start"),
        (line("brief", {"argv": ["arbitrary"]}), "brief"),
    ],
)
def test_cli_rejects_bad_input_keeps_serving_and_exits_nonzero(cli_loop, invalid, error_operation):
    invoke, runtime, lifecycle, _config, _session_id = cli_loop
    result, output = invoke(invalid + line("brief", {}) + line("close", {"last_sequence": 0}))
    assert result.exit_code == 1
    assert [item["schema"] for item in output] == [
        "cairntir.managed-start.v1",
        "cairntir.managed-error.v1",
        "cairntir.managed-brief.v1",
        "cairntir.managed-close.v1",
    ]
    assert output[1]["status"] == "error" and output[1]["operation"] == error_operation
    assert output[1]["error"].strip()
    assert [name for name, _request in runtime.calls] == ["start", "brief", "close"]
    assert lifecycle == ["entered", "closed"]


def test_cli_oversized_line_is_drained_and_next_command_remains_intact(cli_loop):
    invoke, runtime, lifecycle, _config, _session_id = cli_loop
    oversized = "x" * (2 * 1024 * 1024 + 23) + "\n"
    result, output = invoke(oversized + line("brief", {}) + line("close", {"last_sequence": 0}))
    assert result.exit_code == 1
    assert [item["operation"] for item in output] == ["start", "decode", "brief", "close"]
    assert output[1]["schema"] == "cairntir.managed-error.v1"
    assert "input limit" in output[1]["error"]
    assert [name for name, _request in runtime.calls] == ["start", "brief", "close"]
    assert lifecycle == ["entered", "closed"]


def test_cli_operation_failure_never_emits_success_for_failed_capture(cli_loop):
    invoke, runtime, lifecycle, _config, _session_id = cli_loop
    runtime.fail_operation = "capture"
    result, output = invoke(
        line("capture", {"content": "exact supplied text"})
        + line("brief", {})
        + line("close", {"last_sequence": 0})
    )
    assert result.exit_code == 1
    assert [item["operation"] for item in output] == ["start", "capture", "brief", "close"]
    assert output[1]["schema"] == "cairntir.managed-error.v1"
    assert not any(item["schema"] == "cairntir.managed-capture.v1" for item in output)
    assert runtime.calls[1] == ("capture", {"content": "exact supplied text"})
    assert lifecycle == ["entered", "closed"]


def test_cli_eof_close_failure_is_error_and_never_success(cli_loop):
    invoke, runtime, lifecycle, _config, _session_id = cli_loop
    runtime.fail_operation = "close"
    result, output = invoke("")
    assert result.exit_code == 1
    assert [item["schema"] for item in output] == [
        "cairntir.managed-start.v1",
        "cairntir.managed-error.v1",
    ]
    assert output[1]["operation"] == "close" and output[1]["status"] == "error"
    assert lifecycle == ["entered", "closed"]


def test_cli_start_failure_does_not_accept_input_or_claim_close(cli_loop):
    invoke, runtime, lifecycle, _config, _session_id = cli_loop
    runtime.fail_operation = "start"
    result, output = invoke(line("dispatch", {}) + line("close", {"last_sequence": 0}))
    assert result.exit_code == 1
    assert len(output) == 1 and output[0]["schema"] == "cairntir.managed-error.v1"
    assert output[0]["operation"] == "start"
    assert [name for name, _request in runtime.calls] == ["start"]
    assert lifecycle == ["entered", "closed"]


def test_cli_changed_config_refuses_all_following_commands(cli_loop):
    invoke, runtime, lifecycle, config, _session_id = cli_loop
    runtime.after_start = lambda: config.write_text('{"changed":true}', encoding="utf-8")
    result, output = invoke(line("dispatch", {"profile": "untrusted change"}))
    assert result.exit_code == 1
    assert [item["operation"] for item in output] == ["start", "dispatch", "close"]
    assert output[1]["schema"] == "cairntir.managed-error.v1"
    assert "configuration changed" in output[1]["error"]
    assert [name for name, _request in runtime.calls] == ["start", "close"]
    assert lifecycle == ["entered", "closed"]


@pytest.mark.parametrize("explicit_watermark", [False, True])
def test_real_hash_store_close_distinguishes_eof_from_complete_capture(
    tmp_path, monkeypatch, explicit_watermark
):
    project = tmp_path / "project"
    project.mkdir()
    config = tmp_path / "managed.json"
    config.write_text(
        json.dumps(
            {
                "schema": "cairntir.managed-config.v1",
                "wing": "protocol",
                "room": "requests",
                "project_root": str(project.resolve()),
                "brief_budget_chars": 16384,
                "profiles": {
                    "inert": {
                        "argv": [str(Path(sys.executable).resolve()), "-c", "pass"],
                        "cwd": str(project.resolve()),
                        "timeout_seconds": 2,
                        "output_limit_bytes": 100,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    session_id, event_id = str(uuid4()), str(uuid4())
    exact = "  original request caf\u00e9\r\nsecond line  \n"
    event = {
        "schema": "cairntir.managed-event.v1",
        "event_id": event_id,
        "session_id": session_id,
        "sequence": 1,
        "task_id": None,
        "expected_revision": 0,
        "content": exact,
    }
    with DrawerStore(tmp_path / "synthetic.db", HashEmbeddingProvider(16)) as store:

        @contextmanager
        def open_store(*, capture_path):
            assert capture_path == "cli.managed"
            yield store

        monkeypatch.setattr(cli, "_open_store", open_store)
        monkeypatch.setattr("cairntir.access.startup_token", lambda: None)
        text = line("capture", event)
        if explicit_watermark:
            text += line("close", {"last_sequence": 1})
        result = CliRunner().invoke(
            cli.app, ["managed", "--config", str(config), "--session-id", session_id], input=text
        )
        assert result.exit_code == 0, result.exception
        output = [json.loads(value) for value in result.stdout.splitlines()]
        assert len(output) == 3
        captured, closed = output[1:]
        assert captured["schema"] == "cairntir.managed-event-receipt.v1"
        assert captured["event_id"] == event_id
        assert closed["schema"] == "cairntir.managed-close.v1"
        assert closed["capture_complete"] is explicit_watermark
        assert closed["declared_last_sequence"] == (1 if explicit_watermark else None)
        resumed = json.loads(
            TaskBook(store).resume("protocol", task_id=captured["task_id"], budget_chars=262144)
        )
        assert resumed["status"] == "ready", "Closing worker falsely completed its task"
        assert resumed["checkpoint"]["original_request"] == exact
