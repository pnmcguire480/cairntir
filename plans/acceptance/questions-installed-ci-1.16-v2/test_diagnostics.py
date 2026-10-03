"""Finite independent controls for the additive installed-proof diagnostics."""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
V1 = HERE / "originals/verify_installed_questions_v1.py"
V2 = HERE / "verify_installed_questions_v2.py"


def module():
    spec = importlib.util.spec_from_file_location("diagnostic_helper_v2", V2)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class Peer:
    """A finite owned-process seam; no operating-system child is created."""

    def __init__(self, executable, home, host):
        self.host = host
        self.executable = executable
        self.home = home
        self.process = SimpleNamespace(
            pid=31337, returncode=None, stdout=SimpleNamespace(at_eof=lambda: False)
        )
        self.interruptions = 0

    async def __aenter__(self):
        return self

    async def interrupt(self):
        self.interruptions += 1
        self.process.returncode = 1

    async def __aexit__(self, *_):
        await self.interrupt()


def invoke(helper, home):
    return asyncio.run(
        helper.verify_installed_questions(
            cli="cli",
            mcp="mcp",
            home=home,
            peer_factory=Peer,
            execute="execute",
            environment="environment",
            version="1.16.0",
        )
    )


def test_entire_v1_function_and_all_assertions_unchanged():
    original = V1.read_bytes()
    assert V2.read_bytes().startswith(original)
    v1 = ast.parse(original)
    v2 = ast.parse(V2.read_bytes())
    old = next(node for node in v1.body if isinstance(node, ast.AsyncFunctionDef))
    new = next(node for node in v2.body if isinstance(node, ast.AsyncFunctionDef))
    assert ast.dump(old, include_attributes=False) == ast.dump(new, include_attributes=False)
    assert [ast.dump(node) for node in ast.walk(v1) if isinstance(node, ast.Assert)] == [
        ast.dump(node) for node in ast.walk(v2) if isinstance(node, ast.Assert)
    ]
    assert "SELECT COUNT(*) FROM drawers WHERE wing=?" in ast.unparse(new.body[-3])


def test_success_preserves_return_and_shutdown_and_observes_files(tmp_path):
    helper = module()
    expected = {"status": "PASS", "cli_calls": 7, "mcp_tool_calls": 5}
    (tmp_path / "cairntir.db").write_bytes(b"owned-diagnostic-control")
    seen = []

    async def frozen(**args):
        assert args["cli"] == "cli" and args["mcp"] == "mcp"
        assert args["execute"] == "execute" and args["environment"] == "environment"
        async with args["peer_factory"]("mcp", args["home"], "codex") as peer:
            seen.append(peer)
        assert peer.interruptions == 1
        return expected

    helper._verify_installed_questions_v1 = frozen
    assert invoke(helper, tmp_path) is expected
    assert seen[0].process.returncode == 1
    data = json.loads((tmp_path / "question-proof-diagnostic.json").read_text())
    assert data["status"] == "PASS"
    assert [event["phase"] for event in data["events"]] == [
        "entered",
        "before_exit",
        "before_interrupt",
        "after_interrupt",
        "after_exit",
    ]
    assert data["events"][-1]["returncode"] == 1
    assert data["events"][-1]["pid"] == 31337
    assert data["final_files"]["cairntir.db"] == {"exists": True, "size": 24}
    assert data["final_files"]["cairntir.db-wal"] == {"exists": False}
    assert (tmp_path / "cairntir.db").read_bytes() == b"owned-diagnostic-control"


@pytest.mark.parametrize("kind", ["sqlite", "unchanged_assertion"])
def test_failure_is_same_exception_no_retry_no_false_pass_and_records_code(tmp_path, kind):
    helper = module()
    calls = []
    if kind == "sqlite":
        failure = sqlite3.OperationalError("deliberate disk I/O control")
        failure.sqlite_errorcode = 522
        failure.sqlite_errorname = "SQLITE_IOERR_SHORT_READ"
    else:
        failure = AssertionError("deliberate unchanged count assertion control")

    async def frozen(**args):
        calls.append(args)
        async with args["peer_factory"]("mcp", args["home"], "claude-code"):
            pass
        raise failure

    helper._verify_installed_questions_v1 = frozen
    with pytest.raises(type(failure)) as caught:
        invoke(helper, tmp_path)
    assert caught.value is failure
    assert len(calls) == 1
    data = json.loads((tmp_path / "question-proof-diagnostic.json").read_text())
    assert data["status"] == "FAIL"
    assert data["error"]["type"] == type(failure).__name__
    assert data["error"]["sqlite_errorcode"] == (522 if kind == "sqlite" else None)
    assert data["error"]["sqlite_errorname"] == (
        "SQLITE_IOERR_SHORT_READ" if kind == "sqlite" else None
    )
    assert len(failure.__notes__) == 1
    assert "INSTALLED_QUESTION_DIAGNOSTIC" in failure.__notes__[0]
    assert data["events"][-1]["phase"] == "after_exit"
