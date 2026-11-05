"""Independent public managed JSONL routing, failure and close behavior."""

from __future__ import annotations

import json

import pytest

from cairntir import managed


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
    "operation,envelope_request",
    [
        ("capture", {"verbatim": "  caf\u00e9\r\nline two  ", "nested": {"original": True}}),
        ("acknowledge", {"brief_id": "producer-owned identity"}),
        ("dispatch", {"profile": "fixed startup profile", "event_ids": ["producer identity"]}),
        ("brief", {}),
        ("status", {"action_id": "exact status identity"}),
        ("close", {"last_sequence": 7}),
    ],
)
def test_allowed_envelope_routes_exactly_one_public_operation(operation, envelope_request):
    runtime = RecordingRuntime()
    supplied = command(operation, envelope_request)
    before = json.dumps(supplied, ensure_ascii=False)
    result = managed.stream_command(runtime, supplied)
    assert runtime.calls == [(operation, envelope_request)]
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
