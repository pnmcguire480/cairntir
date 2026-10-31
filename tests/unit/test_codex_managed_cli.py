from __future__ import annotations

import json
from contextlib import contextmanager

import pytest
from typer.testing import CliRunner

from cairntir import cli, codex_managed, managed


def command(operation, request):
    return (
        json.dumps(
            {
                "schema": "cairntir.codex-managed-command.v1",
                "operation": operation,
                "request": request,
            }
        )
        + "\n"
    )


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    config = tmp_path / "codex.json"
    runtime_config = {"runtime_identity": "selected-runtime"}
    host_config = {"host_identity": "selected-host"}
    config.write_text(
        json.dumps(
            {
                "schema": "cairntir.codex-managed-cli.v1",
                "runtime": runtime_config,
                "host": host_config,
            }
        ),
        encoding="utf-8",
    )
    calls, lifecycle = [], []
    behavior = {"fail": None, "change_config": False}
    store, runtime = object(), object()

    @contextmanager
    def open_store(*, capture_path):
        assert capture_path == "cli.codex-managed"
        lifecycle.append("open")
        try:
            yield store
        finally:
            lifecycle.append("close")

    def make_runtime(selected_store, *, config):
        assert selected_store is store
        assert config == runtime_config
        return runtime

    class RecordingSession:
        def __init__(self, selected_runtime, *, config):
            assert selected_runtime is runtime
            assert config == host_config

        def start(self, session_id, *, task_id):
            calls.append(("start", session_id, task_id))
            if behavior["fail"] == "start":
                raise codex_managed.CodexManagedError("startup refused")
            if behavior["change_config"]:
                config.write_text("{}", encoding="utf-8")
            return {"schema": "cairntir.codex-managed-start.v1"}

        def capture(self, request):
            calls.append(("capture", request))
            return {"schema": "cairntir.managed-event-receipt.v1"}

        def turn(self, request):
            calls.append(("turn", request))
            return {"schema": "cairntir.codex-managed-result.v1"}

        def status(self, action_id):
            calls.append(("status", action_id))
            return {"schema": "cairntir.managed-action-status.v1"}

        def close(self, last_sequence=None):
            calls.append(("close", last_sequence))
            if behavior["fail"] == "close":
                raise codex_managed.CodexManagedError("close refused")
            return {"schema": "cairntir.managed-close.v1"}

    monkeypatch.setattr(cli, "_startup_grant", None)
    monkeypatch.setattr("cairntir.access.startup_token", lambda: None)
    monkeypatch.setattr(cli, "_open_store", open_store)
    monkeypatch.setattr(managed, "ManagedRuntime", make_runtime)
    monkeypatch.setattr(codex_managed, "CodexManaged", RecordingSession)

    def invoke(text="", task_id=None):
        args = ["codex-managed", "--config", str(config), "--session-id", "session-exact"]
        if task_id is not None:
            args.extend(["--task-id", task_id])
        result = CliRunner().invoke(cli.app, args, input=text)
        return result, [json.loads(line) for line in result.stdout.splitlines()]

    return invoke, config, calls, lifecycle, behavior


@pytest.mark.parametrize("invalid", ["{broken", '{"schema":"wrong","runtime":{},"host":{}}'])
def test_invalid_configuration_refuses_before_opening_store(bridge, invalid):
    invoke, config, calls, lifecycle, _ = bridge
    config.write_text(invalid, encoding="utf-8")
    result, output = invoke(command("turn", {"action_id": "must-not-run"}))
    assert result.exit_code == 1
    assert calls == lifecycle == []
    assert len(output) == 1
    assert output[0]["schema"] == "cairntir.codex-managed-error.v1"
    assert output[0]["operation"] == "start"
    assert output[0]["status"] == "error" and output[0]["error"]


def test_exact_task_and_requests_reach_selected_session(bridge):
    invoke, _, calls, lifecycle, _ = bridge
    request = {"content": "  café\r\nkeep exact  ", "event_id": "event-exact"}
    turn = {"action_id": "action-exact", "profile": "selected"}
    result, output = invoke(
        command("capture", request)
        + command("turn", turn)
        + command("status", {"action_id": "action-exact"})
        + command("close", {"last_sequence": 7}),
        task_id="task-exact",
    )
    assert result.exit_code == 0, result.exception
    assert calls == [
        ("start", "session-exact", "task-exact"),
        ("capture", request),
        ("turn", turn),
        ("status", "action-exact"),
        ("close", 7),
    ]
    assert len(output) == 5 and lifecycle == ["open", "close"]


def test_explicit_close_does_not_dispatch_following_turn(bridge):
    invoke, _, calls, lifecycle, _ = bridge
    result, output = invoke(
        command("close", {"last_sequence": 0}) + command("turn", {"action_id": "forbidden"})
    )
    assert result.exit_code == 0, result.exception
    assert calls == [("start", "session-exact", None), ("close", 0)]
    assert output[-1]["schema"] == "cairntir.managed-close.v1"
    assert lifecycle == ["open", "close"]


def test_eof_closes_without_inventing_capture_watermark(bridge):
    invoke, _, calls, lifecycle, _ = bridge
    result, output = invoke()
    assert result.exit_code == 0, result.exception
    assert calls == [("start", "session-exact", None), ("close", None)]
    assert len(output) == 2 and output[-1]["schema"] == "cairntir.managed-close.v1"
    assert lifecycle == ["open", "close"]


@pytest.mark.parametrize(
    "invalid",
    [
        '{"schema":"cairntir.codex-managed-command.v1","operation":"status",'
        '"operation":"turn","request":{}}\n',
        "x" * (2 * 1024 * 1024 + 23) + "\n",
    ],
    ids=["duplicate-key", "oversized-line"],
)
def test_bad_line_is_rejected_and_next_command_still_runs(bridge, invalid):
    invoke, _, calls, lifecycle, _ = bridge
    result, output = invoke(invalid + command("status", {"action_id": "next-exact"}))
    assert result.exit_code == 1
    assert calls == [
        ("start", "session-exact", None),
        ("status", "next-exact"),
        ("close", None),
    ]
    assert len(output) == 4
    assert output[1]["schema"] == "cairntir.codex-managed-error.v1"
    assert output[1]["operation"] == "decode"
    assert output[1]["error"]
    assert lifecycle == ["open", "close"]


def test_configuration_change_prevents_dispatch(bridge):
    invoke, _, calls, lifecycle, behavior = bridge
    behavior["change_config"] = True
    result, output = invoke(command("turn", {"action_id": "forbidden"}))
    assert result.exit_code == 1
    assert calls == [("start", "session-exact", None), ("close", None)]
    assert output[1]["schema"] == "cairntir.codex-managed-error.v1"
    assert output[1]["operation"] == "turn"
    assert "configuration changed" in output[1]["error"]
    assert lifecycle == ["open", "close"]


@pytest.mark.parametrize("operation", ["start", "close"])
def test_lifecycle_error_is_typed_and_store_is_closed(bridge, operation):
    invoke, _, calls, lifecycle, behavior = bridge
    behavior["fail"] = operation
    result, output = invoke()
    assert result.exit_code == 1
    assert calls == [("start", "session-exact", None)] + (
        [("close", None)] if operation == "close" else []
    )
    assert output[-1] == {
        "schema": "cairntir.codex-managed-error.v1",
        "status": "error",
        "operation": operation,
        "error": "startup refused" if operation == "start" else "close refused",
    }
    assert not any(row["schema"] == "cairntir.managed-close.v1" for row in output)
    assert lifecycle == ["open", "close"]
