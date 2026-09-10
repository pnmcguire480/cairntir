"""Public MCP results must distinguish rejected work from successful work."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from cairntir.mcp.backend import CairntirBackend
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer


@pytest.fixture()
def saved_memory(tmp_cairntir_home: Path) -> int:
    with DrawerStore(
        tmp_cairntir_home / "cairntir.db", HashEmbeddingProvider(dimension=32)
    ) as store:
        return store.add(Drawer(wing="audit", room="evidence", content="Keep my exact memory.")).id


@pytest.mark.parametrize(
    ("name", "arguments", "detail"),
    [
        ("cairntir_get", {"drawer_id": 999}, "no drawer"),
        ("cairntir_recall", {"query": " "}, "non-empty query"),
        (
            "cairntir_remember",
            {"wing": "audit", "room": "evidence", "content": " "},
            "content",
        ),
        ("cairntir_crucible", {"claim": " "}, "non-empty claim"),
    ],
)
async def test_rejected_tool_is_an_error_and_session_remains_usable(
    tmp_cairntir_home: Path, saved_memory: int, name: str, arguments: dict, detail: str
) -> None:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "cairntir.mcp.server", "--host", "codex"],
        env=dict(os.environ),
        cwd=tmp_cairntir_home,
    )
    async with (
        asyncio.timeout(30),
        stdio_client(parameters) as (reader, writer),
        ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=15)) as session,
    ):
        await session.initialize()
        rejected = await session.call_tool(name, arguments)
        assert detail in rejected.content[0].text
        recovered = await session.call_tool("cairntir_get", {"drawer_id": saved_memory})
        assert not recovered.isError
        assert json.loads(recovered.content[0].text)["content"] == "Keep my exact memory."
        assert rejected.isError, f"Rejected {name} was reported as successful: {rejected}"


@pytest.mark.parametrize("name", ["cairntir_get", "cairntir_hotfix"])
async def test_update_notice_preserves_machine_readable_result(
    tmp_cairntir_home: Path, saved_memory: int, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    arguments = {"drawer_id": saved_memory}
    if name == "cairntir_hotfix":
        with DrawerStore(
            tmp_cairntir_home / "cairntir.db", HashEmbeddingProvider(dimension=32)
        ) as store:
            opened = json.loads(
                CairntirBackend(store).hotfix(
                    action="open",
                    wing="audit",
                    payload={
                        "title": "Recovery",
                        "stage": "verification",
                        "symptom": "A failed tool appears successful",
                        "acceptance": ["Failed work has an error receipt"],
                    },
                    idempotency_key="audit-case",
                )
            )
        arguments = {"action": "status", "wing": "audit", "case_id": opened["case_id"]}
    monkeypatch.setenv("CAIRNTIR_DISABLE_UPDATE_CHECK", "0")
    (tmp_cairntir_home / ".update_check").write_text(
        json.dumps({"checked_at": datetime.now(UTC).isoformat(), "latest": "999.0.0"}),
        encoding="utf-8",
    )
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "cairntir.mcp.server", "--host", "codex"],
        env=dict(os.environ),
        cwd=tmp_cairntir_home,
    )
    async with (
        asyncio.timeout(30),
        stdio_client(parameters) as (reader, writer),
        ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=15)) as session,
    ):
        await session.initialize()
        result = await session.call_tool(name, arguments)
        assert not result.isError
        try:
            decoded = json.loads(result.content[0].text)
        except json.JSONDecodeError as exc:
            raise AssertionError(f"MCP_JSON: update notice corrupted {name}: {result}") from exc
        if name == "cairntir_get":
            assert decoded["content"] == "Keep my exact memory."
        else:
            assert decoded["case_id"] == opened["case_id"]
            assert decoded["state"] == "open"
        followup = await session.call_tool("cairntir_get", {"drawer_id": saved_memory})
        assert not followup.isError
        assert json.loads(followup.content[0].text)["content"] == "Keep my exact memory."
        notices = [
            block.text for block in result.content + followup.content if "999.0.0" in block.text
        ]
        assert len(notices) == 1, "The update notice must still be delivered once."
