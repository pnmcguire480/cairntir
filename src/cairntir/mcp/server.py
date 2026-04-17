"""MCP stdio server exposing the six Cairntir tools.

Run directly with ``python -m cairntir.mcp.server`` — see ``.mcp.json``. The
server holds a single :class:`~cairntir.mcp.backend.CairntirBackend`
instance backed by the store at :func:`cairntir.config.db_path`.
"""

from __future__ import annotations

import asyncio
from typing import Any

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from cairntir.config import db_path
from cairntir.errors import CairntirError
from cairntir.mcp.backend import CairntirBackend
from cairntir.memory.embeddings import SentenceTransformerProvider
from cairntir.memory.store import DrawerStore
from cairntir.update import maybe_check_in_background, pending_update_banner

_SERVER_NAME = "cairntir"


def _tool_specs() -> list[types.Tool]:
    return [
        types.Tool(
            name="cairntir_remember",
            description="Store a verbatim memory drawer in a wing/room.",
            inputSchema={
                "type": "object",
                "required": ["wing", "room", "content"],
                "properties": {
                    "wing": {"type": "string"},
                    "room": {"type": "string"},
                    "content": {"type": "string"},
                    "layer": {
                        "type": "string",
                        "enum": ["identity", "essential", "on_demand", "deep"],
                        "default": "on_demand",
                    },
                    "metadata": {"type": "object"},
                },
            },
        ),
        types.Tool(
            name="cairntir_recall",
            description="Semantic search across stored drawers.",
            inputSchema={
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "wing": {"type": "string"},
                    "room": {"type": "string"},
                    "limit": {"type": "integer", "default": 10, "minimum": 1},
                },
            },
        ),
        types.Tool(
            name="cairntir_session_start",
            description="Load the 4-layer context for a wing (the amnesia killer).",
            inputSchema={
                "type": "object",
                "required": ["wing"],
                "properties": {
                    "wing": {"type": "string"},
                    "query": {"type": "string"},
                },
            },
        ),
        types.Tool(
            name="cairntir_timeline",
            description="Chronological view of drawers in a wing mentioning an entity.",
            inputSchema={
                "type": "object",
                "required": ["wing", "entity"],
                "properties": {
                    "wing": {"type": "string"},
                    "entity": {"type": "string"},
                    "limit": {"type": "integer", "default": 50, "minimum": 1},
                },
            },
        ),
        types.Tool(
            name="cairntir_audit",
            description="Run the Quality skill over a wing.",
            inputSchema={
                "type": "object",
                "required": ["wing"],
                "properties": {"wing": {"type": "string"}},
            },
        ),
        types.Tool(
            name="cairntir_crucible",
            description="Stress-test a claim with the Crucible skill.",
            inputSchema={
                "type": "object",
                "required": ["claim"],
                "properties": {"claim": {"type": "string"}},
            },
        ),
    ]


def _dispatch(backend: CairntirBackend, name: str, args: dict[str, Any]) -> str:
    match name:
        case "cairntir_remember":
            return backend.remember(**args)
        case "cairntir_recall":
            return backend.recall(**args)
        case "cairntir_session_start":
            return backend.session_start(**args)
        case "cairntir_timeline":
            return backend.timeline(**args)
        case "cairntir_audit":
            return backend.audit(**args)
        case "cairntir_crucible":
            return backend.crucible(**args)
        case _:
            raise CairntirError(f"unknown tool {name!r}")


def build_server(backend: CairntirBackend) -> Server[Any, Any]:
    """Build a :class:`Server` wired to ``backend``.

    The first tool call per process appends a one-line update banner if
    a newer Cairntir is on PyPI. The banner is opt-out via the
    ``CAIRNTIR_DISABLE_UPDATE_CHECK`` environment variable. Subsequent
    calls in the same session do not repeat the banner — repetition is
    noise, not signal.
    """
    server: Server[Any, Any] = Server(_SERVER_NAME)
    update_banner_shown = False

    @server.list_tools()
    async def _list() -> list[types.Tool]:
        return _tool_specs()

    @server.call_tool()
    async def _call(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
        nonlocal update_banner_shown
        try:
            text = _dispatch(backend, name, arguments)
        except CairntirError as exc:
            text = f"[cairntir error] {exc}"

        if not update_banner_shown:
            banner = pending_update_banner()
            if banner is not None:
                text = f"{banner}\n\n{text}"
            update_banner_shown = True

        return [types.TextContent(type="text", text=text)]

    return server


async def _amain() -> None:
    # Kick off the background PyPI check so the *next* tool call (or
    # the one after) sees the latest-version cache. The check runs in
    # a daemon thread, fail-silent on network or permission errors.
    maybe_check_in_background()

    store = DrawerStore(db_path(), SentenceTransformerProvider())
    backend = CairntirBackend(store)
    server = build_server(backend)
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    """Entry point for the ``cairntir-mcp`` console script.

    Also reachable as ``python -m cairntir.mcp.server``. The console
    script is the registered command — see ``cairntir.cli._mcp_spec``
    and the ``[project.scripts]`` entry in ``pyproject.toml``.
    """
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
