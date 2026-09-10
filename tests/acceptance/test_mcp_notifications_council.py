"""Independent stdio acceptance; only the committed-write probe substitutes embeddings."""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer


def seed(home: Path) -> None:
    home.mkdir()
    with DrawerStore(home / "cairntir.db", HashEmbeddingProvider(dimension=32)) as store:
        store.add(Drawer(wing="audit", room="evidence", content="Exact seed."))


def cache(home: Path, latest: str) -> None:
    (home / ".update_check").write_text(
        json.dumps({"checked_at": datetime.now(UTC).isoformat(), "latest": latest}),
        encoding="utf-8",
    )


async def run_stdio(
    home: Path, operations: list[tuple[str, dict]], *, hash_embedder: bool = False
) -> list:
    env = {
        **os.environ,
        "CAIRNTIR_HOME": str(home),
        "CAIRNTIR_DISABLE_UPDATE_CHECK": "0",
        "CAIRNTIR_DISABLE_AUTOREGISTER": "1",
        "CAIRNTIR_ENABLE_EMBEDDER_WARMUP": "0",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "OMP_NUM_THREADS": "2",
        "MKL_NUM_THREADS": "2",
        "OPENBLAS_NUM_THREADS": "2",
    }
    args = ["-m", "cairntir.mcp.server", "--host", "codex"]
    if hash_embedder:
        args = [
            "-c",
            "import asyncio; from cairntir.memory.embeddings import HashEmbeddingProvider; "
            "from cairntir.mcp import server; "
            "server.production_embedding_provider = lambda: HashEmbeddingProvider(dimension=32); "
            "asyncio.run(server._amain(host='codex'))",
        ]
    parameters = StdioServerParameters(command=sys.executable, args=args, env=env, cwd=str(home))
    with (home / "stderr.txt").open("w", encoding="utf-8") as errlog:
        async with (
            asyncio.timeout(40),
            stdio_client(parameters, errlog=errlog) as (reader, writer),
            ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=15)) as session,
        ):
            await session.initialize()
            await session.list_tools()
            return [await session.call_tool(name, arguments) for name, arguments in operations]


@pytest.mark.asyncio
async def test_invalid_utf8_cache_does_not_block_actual_server_startup(tmp_path: Path) -> None:
    home = tmp_path / "home"
    seed(home)
    (home / ".update_check").write_bytes(b"\xff")
    results = await run_stdio(home, [("cairntir_get", {"drawer_id": 1})])
    assert not results[0].isError, results[0]
    assert json.loads(results[0].content[0].text)["content"] == "Exact seed."


@pytest.mark.asyncio
async def test_malformed_version_does_not_change_actual_read_receipt(tmp_path: Path) -> None:
    home = tmp_path / "home"
    seed(home)
    cache(home, "\u00b2")
    results = await run_stdio(
        home, [("cairntir_get", {"drawer_id": 1}), ("cairntir_get", {"drawer_id": 1})]
    )
    for result in results:
        assert not result.isError, result
        assert json.loads(result.content[0].text)["content"] == "Exact seed."


@pytest.mark.asyncio
async def test_committed_write_keeps_success_receipt_with_corrupt_notifier(tmp_path: Path) -> None:
    home = tmp_path / "home"
    seed(home)
    cache(home, "\u00b2")
    results = await run_stdio(
        home,
        [
            (
                "cairntir_remember",
                {"wing": "audit", "room": "evidence", "content": "Exact committed request."},
            ),
            ("cairntir_get", {"drawer_id": 2}),
        ],
        hash_embedder=True,
    )
    with sqlite3.connect(home / "cairntir.db") as connection:
        rows = connection.execute("SELECT id, content FROM drawers ORDER BY id").fetchall()
    assert rows == [(1, "Exact seed."), (2, "Exact committed request.")]
    assert not results[0].isError, results[0]
    assert "Stored drawer #2" in results[0].content[0].text
    assert not results[1].isError, results[1]
    assert json.loads(results[1].content[0].text)["content"] == "Exact committed request."


@pytest.mark.asyncio
async def test_healthy_notice_preserves_json_and_follows_rejection(tmp_path: Path) -> None:
    home = tmp_path / "home"
    seed(home)
    cache(home, "999.0.0")
    results = await run_stdio(
        home,
        [
            ("cairntir_get", {"drawer_id": 999}),
            ("cairntir_get", {"drawer_id": 1}),
            ("cairntir_get", {"drawer_id": 1}),
        ],
    )
    assert results[0].isError, results[0]
    for result in results[1:]:
        assert not result.isError, result
        assert json.loads(result.content[0].text)["content"] == "Exact seed."
    notices = [block for result in results for block in result.content if "999.0.0" in block.text]
    assert len(notices) == 1, notices
