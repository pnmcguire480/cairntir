"""A refreshed host launcher must retain its real MCP startup grant."""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
from contextlib import closing
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from cairntir.access import issue_grant
from cairntir.hosts import configure_host
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer

ROOT = Path(__file__).resolve().parents[2]
READABLE = "  Original café evidence.\nPreserve this exact request.\t\n"
PRIVATE = "PRIVATE STARTUP CANARY: unrelated wing evidence."


def _saved_state(database: Path) -> tuple[list[tuple], list[tuple]]:
    with closing(sqlite3.connect(database)) as conn:
        return (
            conn.execute("SELECT * FROM drawers ORDER BY id").fetchall(),
            conn.execute("SELECT * FROM access_grants ORDER BY token_hash").fetchall(),
        )


async def test_host_refresh_preserves_real_mcp_startup_scope(tmp_cairntir_home: Path) -> None:
    database = tmp_cairntir_home / "cairntir.db"
    grant_file = tmp_cairntir_home / "read grant.txt"
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        readable = store.add(Drawer(wing="shared-wing", room="evidence", content=READABLE))
        private = store.add(Drawer(wing="private-wing", room="evidence", content=PRIVATE))
        provenance = store.get_provenance(readable.id)
        assert provenance is not None
        grant = issue_grant(
            store,
            scopes=[{"wing": "shared-wing", "rooms": ["evidence"]}],
            capabilities=["read"],
        )
        grant_file.write_text(grant, encoding="utf-8")
    original_state = _saved_state(database)
    project = tmp_cairntir_home / "project"
    config_path = project / ".cursor" / "mcp.json"
    config_path.parent.mkdir(parents=True)
    configured_environment = {
        "CAIRNTIR_HOME": str(tmp_cairntir_home),
        "CAIRNTIR_GRANT_FILE": str(grant_file),
        "PRESERVE_HOST_OPTION": "original value",
    }
    config_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "cairntir": {
                        "command": sys.executable,
                        "args": ["-m", "cairntir.mcp.server", "--host", "cursor"],
                        "env": configured_environment,
                        "disabled": False,
                        "timeout": 30000,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    async def check_fresh_server() -> None:
        configured = json.loads(config_path.read_text(encoding="utf-8"))["mcpServers"]["cairntir"]
        environment = dict(os.environ)
        environment.pop("CAIRNTIR_GRANT_FILE", None)
        environment.pop("CAIRNTIR_ENABLE_EMBEDDER_WARMUP", None)
        environment.update(
            CAIRNTIR_HOME=str(tmp_cairntir_home),
            PYTHONPATH=str(ROOT / "src"),
            PYTHONIOENCODING="utf-8",
            CAIRNTIR_DISABLE_AUTOREGISTER="1",
            CAIRNTIR_DISABLE_UPDATE_CHECK="1",
            HF_HUB_OFFLINE="1",
            TRANSFORMERS_OFFLINE="1",
            FASTEMBED_CACHE_PATH=str(tmp_cairntir_home / "unused-model-cache"),
        )
        environment.update(configured.get("env", {}))
        parameters = StdioServerParameters(
            command=configured["command"],
            args=configured["args"],
            env=environment,
            cwd=project,
        )
        async with (
            asyncio.timeout(40),
            stdio_client(parameters) as (reader, writer),
            ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=20)) as session,
        ):
            await session.initialize()
            allowed = await session.call_tool("cairntir_get", {"drawer_id": readable.id})
            assert not allowed.isError
            payload = json.loads(allowed.content[0].text)
            assert payload["content"] == READABLE
            assert payload["provenance"] == provenance.to_dict()
            denied = await session.call_tool("cairntir_get", {"drawer_id": private.id})
            assert denied.isError, "Startup grant was lost: private evidence became readable"
            assert "access denied" in denied.content[0].text.lower()
            assert PRIVATE not in denied.model_dump_json()
            recovered = await session.call_tool("cairntir_get", {"drawer_id": readable.id})
            assert not recovered.isError
            assert json.loads(recovered.content[0].text)["content"] == READABLE
        assert _saved_state(database) == original_state

    await check_fresh_server()
    configure_host(
        "cursor", scope="project", root=project, home=tmp_cairntir_home / "user", force=False
    )
    refreshed = json.loads(config_path.read_text(encoding="utf-8"))["mcpServers"]["cairntir"]
    assert refreshed["env"] == configured_environment
    assert refreshed["disabled"] is False
    assert refreshed["timeout"] == 30000
    assert grant_file.read_text(encoding="utf-8") == grant
    await check_fresh_server()
    assert not (tmp_cairntir_home / "unused-model-cache").exists()
