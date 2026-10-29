from __future__ import annotations

import ctypes
import hashlib
import importlib.util
import json
import os
from ctypes import wintypes
from pathlib import Path
from uuid import uuid4

import pytest

from cairntir.errors import CairntirError

HERE = Path(__file__).resolve().parent
OLD = HERE
PINS = {
    "support.py": (7650, "e09a8b85299de44423811663daf7368167b5c0e2aa006e370a64ed29bc780900"),
    "fixed_effect.py": (1284, "111f7c32e2aa26da15fb6a961e8a37fda95f522dbb106394249be33aec1a90d2"),
}
for filename, (size, digest) in PINS.items():
    raw = (OLD / filename).read_bytes()
    assert len(raw) == size and hashlib.sha256(raw).hexdigest() == digest
spec = importlib.util.spec_from_file_location("r06_wire_frozen_support", OLD / "support.py")
assert spec is not None and spec.loader is not None
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


def ended(pid):
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        raise AssertionError("nonmodel_peer_still_active")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        assert ctypes.get_last_error() in (87, 1168)
        return
    try:
        code = wintypes.DWORD()
        assert kernel.GetExitCodeProcess(handle, ctypes.byref(code))
        assert code.value == 0, "nonmodel_peer_did_not_exit_cleanly"
    finally:
        assert kernel.CloseHandle(handle)


def start(c):
    selected = s.seed(c["store"])
    c["task_id"] = selected["task_id"]
    config = {
        **c["host_config"],
        "model": "PUBLIC-STUB-NO-INFERENCE",
        "timeout_seconds": 8,
        "env": {**c["host_config"]["env"], "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"},
    }
    session = s.api().CodexManaged(c["runtime"], config=config)
    assert session.start(c["session_id"], task_id=c["task_id"])["status"] == "ready"
    c["event_id"] = str(uuid4())
    captured = session.capture(
        {
            "schema": "cairntir.managed-event.v1",
            "event_id": c["event_id"],
            "session_id": c["session_id"],
            "sequence": 1,
            "task_id": c["task_id"],
            "expected_revision": selected["revision"],
            "content": "PUBLIC nonmodel wire action.",
        }
    )
    assert captured["status"] == "committed"
    return session


def records(c):
    return [
        json.loads(line)
        for line in (c["root"] / "peer-wire.jsonl").read_text(encoding="utf-8").splitlines()
    ]


@pytest.mark.parametrize(
    "scenario",
    [
        "verified-prior-and-current",
        "current-metadata-is-not-ack",
        "unverified-turn",
        "wrong-thread",
        "hidden-tool",
        "null-turn-id",
        "missing-turn-id",
        "mutated-prior-history-ack",
        "prior-lifecycle",
    ],
)
def test_native_wire_correlation_boundary(scenario, tmp_path, monkeypatch):
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path / "isolated-home"))
    with s.case(tmp_path / "wire-case") as c:
        (c["root"] / "app-server").write_bytes((HERE / "peer.py").read_bytes())
        (c["root"] / "scenario.json").write_text(json.dumps(scenario), encoding="utf-8")
        session = start(c)
        first = session.turn(s.action(c))
        assert first["mode"] == "startup" and first["server_closed"] is True
        assert first["server_exit_code"] == 0 and len(s.effects(c)) == 1
        assert s.effects(c)[0]["ack_id"] == first["acknowledgement"]["ack_id"]
        initial_rows = records(c)
        first_started = [row for row in initial_rows if row["kind"] == "started"]
        assert len(first_started) == 1 and first_started[0]["peer"] == "PYTHON_NONMODEL"
        ended(first_started[0]["pid"])
        corrected = s.change(c["store"], c["task_id"])
        if scenario == "verified-prior-and-current":
            second = session.turn(s.action(c))
            assert second["mode"] == "resume" and second["server_closed"] is True
            assert second["server_exit_code"] == 0 and second["prior_history_verified"] is True
            assert second["native_thread_id"] == first["native_thread_id"]
            assert second["native_turn_id"] != first["native_turn_id"]
            assert second["prior_native_turn_id"] == first["native_turn_id"]
            assert second["history_witness"]["model_ack"] == first["model_ack"]
            assert second["model_ack"]["revision"] == corrected["revision"]
            assert second["model_ack"]["brief_sha256"] == second["brief"]["brief_sha256"]
            assert second["model_ack"] != first["model_ack"]
            assert s.CORRECTION in json.dumps(second["brief"])
            assert len(s.effects(c)) == 2
            assert s.effects(c)[1]["ack_id"] == second["acknowledgement"]["ack_id"]
            expected_effects = 2
        else:
            with pytest.raises(CairntirError):
                session.turn(s.action(c))
            expected_effects = 1
        assert len(s.effects(c)) == expected_effects
        for operation in ("managed.ack.v1", "managed.dispatch.v1", "managed.outcome.v1"):
            assert s.operations(c, operation) == expected_effects
        rows = records(c)
        starts = [row for row in rows if row["kind"] == "started"]
        closes = [row for row in rows if row["kind"] == "closed"]
        assert len(starts) == len(closes) == 2
        assert all(row["stdin_eof"] is True for row in closes)
        for row in starts:
            ended(row["pid"])
        methods = [row["method"] for row in rows if row["kind"] == "request" and row["server"] == 2]
        assert "thread/resume" in methods and "thread/turns/list" in methods
        assert ("turn/start" in methods) is (scenario != "mutated-prior-history-ack")
        second_frames = [
            row["frame"] for row in rows if row["kind"] == "sent" and row["server"] == 2
        ]
        usage_frames = [
            frame for frame in second_frames if frame.get("method") == "thread/tokenUsage/updated"
        ]
        assert bool(usage_frames) is (scenario != "mutated-prior-history-ack")
        if scenario == "prior-lifecycle":
            prior_items = [
                frame["params"]["item"]
                for frame in second_frames
                if frame.get("method") == "item/completed"
                and frame["params"].get("threadId") == first["native_thread_id"]
                and frame["params"].get("turnId") == first["native_turn_id"]
            ]
            assert len(prior_items) == 1 and prior_items[0]["type"] == "agentMessage"
            assert json.loads(prior_items[0]["text"]) == first["model_ack"]
        closed = session.close(last_sequence=1)
        assert closed["capture_complete"] is True and closed["uncertain_actions"] == []
        assert closed["pending_captures"] == []
