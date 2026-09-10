"""Independent host registration outcomes using real generated launchers and MCP."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import shutil
import sys
import tomllib
from datetime import timedelta
from pathlib import Path

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from cairntir import register
from cairntir.hosts import configure_host
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer

MEMORY = "Memory survives a desktop host restart."
REQUEST = "Recover the unfinished council request exactly."


@pytest.fixture()
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, int]:
    profile, project, store_home = (
        tmp_path / "profile",
        tmp_path / "project",
        tmp_path / "store",
    )
    for path in (profile, project, store_home):
        path.mkdir()
    for name, value in {
        "HOME": str(profile),
        "USERPROFILE": str(profile),
        "CAIRNTIR_HOME": str(store_home),
        "CAIRNTIR_SESSION_ID": "live-council-session",
        "CAIRNTIR_DISABLE_UPDATE_CHECK": "1",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "PYTHONUTF8": "1",
    }.items():
        monkeypatch.setenv(name, value)
    for name in ("CAIRNTIR_GRANT_FILE", "CAIRNTIR_ENABLE_EMBEDDER_WARMUP"):
        monkeypatch.delenv(name, raising=False)
    with DrawerStore(store_home / "cairntir.db", HashEmbeddingProvider(dimension=32)) as store:
        saved = store.add(Drawer(wing="council", room="evidence", content=MEMORY))
    bucket = re.sub(r"[^a-zA-Z0-9]", "-", str(project.resolve()))
    transcript = profile / ".claude" / "projects" / bucket / "older-session.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text(
        json.dumps(
            {
                "type": "user",
                "sessionId": "older-session",
                "timestamp": "2026-09-01T10:00:00Z",
                "message": {"role": "user", "content": REQUEST},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert saved.id is not None
    return profile, project, saved.id


async def invoke(argv: list[str], project: Path, name: str, arguments: dict):
    parameters = StdioServerParameters(
        command=argv[0], args=argv[1:], env=dict(os.environ), cwd=project
    )
    async with (
        asyncio.timeout(25),
        stdio_client(parameters) as (reader, writer),
        ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=10)) as session,
    ):
        await session.initialize()
        return await session.call_tool(name, arguments)


async def test_absolute_launcher_control_reads_memory_with_empty_path(
    isolated: tuple[Path, Path, int], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, project, drawer_id = isolated
    monkeypatch.setenv("PATH", str(tmp_path / "empty-path"))
    result = await invoke(
        [sys.executable, "-m", "cairntir.mcp.server", "--host", "codex"],
        project,
        "cairntir_get",
        {"drawer_id": drawer_id},
    )
    assert not result.isError, result
    assert json.loads(result.content[0].text)["content"] == MEMORY


@pytest.mark.parametrize(
    "host,scope", [("cursor", "user"), ("codex", "project"), ("opencode", "user")]
)
async def test_generated_registration_launches_without_install_shell_path(
    isolated: tuple[Path, Path, int],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    host: str,
    scope: str,
) -> None:
    profile, project, drawer_id = isolated
    setup = configure_host(host, scope=scope, root=project, home=profile)
    assert setup.registration_path is not None
    text = setup.registration_path.read_text(encoding="utf-8")
    if setup.registration_path.suffix == ".toml":
        spec = tomllib.loads(text)["mcp_servers"]["cairntir"]
    else:
        config = json.loads(text)
        spec = config["mcp" if host == "opencode" else "mcpServers"]["cairntir"]
    argv = spec["command"]
    if isinstance(argv, str):
        argv = [argv, *spec.get("args", [])]
    monkeypatch.setenv("PATH", str(tmp_path / "empty-path"))
    resolved = shutil.which(argv[0])
    assert resolved is not None, (
        f"COUNCIL_LAUNCHER: generated {host} command cannot resolve without installer PATH: {argv}"
    )
    result = await invoke([resolved, *argv[1:]], project, "cairntir_get", {"drawer_id": drawer_id})
    assert not result.isError, f"COUNCIL_LAUNCHER: generated {host} command failed: {result}"
    assert json.loads(result.content[0].text)["content"] == MEMORY


async def test_explicit_claude_control_recovers_unfinished_request(
    isolated: tuple[Path, Path, int],
) -> None:
    _, project, _ = isolated
    result = await invoke(
        [sys.executable, "-m", "cairntir.mcp.server", "--host", "claude"],
        project,
        "cairntir_handoff",
        {"wing": "council", "recover_transcripts": True},
    )
    assert not result.isError, result
    assert "status=recovered" in result.content[0].text
    assert REQUEST in result.content[0].text


async def test_automatic_registration_recovers_as_its_actual_host(
    isolated: tuple[Path, Path, int], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, project, _ = isolated
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    recorder = fake_bin / "record.py"
    capture = fake_bin / "registered.json"
    recorder.write_text(
        "import json,sys\nfrom pathlib import Path\n"
        "if sys.argv[1:3] == ['mcp', 'add']:\n"
        " Path(__file__).with_name('registered.json').write_text(json.dumps(sys.argv[1:]))\n"
        " print('registered')\n",
        encoding="utf-8",
    )
    if os.name == "nt":
        stub = fake_bin / "claude.cmd"
        stub.write_text(f'@echo off\n"{sys.executable}" "{recorder}" %*\n', encoding="utf-8")
    else:
        stub = fake_bin / "claude"
        stub.write_text(
            f'#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(recorder))} "$@"\n',
            encoding="utf-8",
        )
        stub.chmod(0o700)
    monkeypatch.setenv(
        "PATH",
        os.pathsep.join((str(fake_bin), str(Path(sys.executable).parent), os.environ["PATH"])),
    )
    monkeypatch.setenv("CAIRNTIR_DISABLE_AUTOREGISTER", "0")
    assert register.ensure_registered(force=True) == "registered"
    recorded = json.loads(capture.read_text(encoding="utf-8"))
    argv = recorded[recorded.index("--") + 1 :]
    result = await invoke(
        argv,
        project,
        "cairntir_handoff",
        {"wing": "council", "recover_transcripts": True},
    )
    assert not result.isError, (
        f"COUNCIL_HOST_CONTEXT: auto-registered launcher cannot recover host evidence: {result}"
    )
    assert "status=recovered" in result.content[0].text
    assert REQUEST in result.content[0].text
