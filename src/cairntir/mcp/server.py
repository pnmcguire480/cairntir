"""MCP stdio server exposing the six Cairntir tools.

Run directly with ``python -m cairntir.mcp.server`` — see ``.mcp.json``. The
server holds a single :class:`~cairntir.mcp.backend.CairntirBackend`
instance backed by the store at :func:`cairntir.config.db_path`.
"""

from __future__ import annotations

import asyncio
import os
import threading
from typing import Any, Final

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server
from pydantic import ValidationError

from cairntir.config import db_path
from cairntir.errors import CairntirError, EmbeddingError
from cairntir.mcp.backend import CairntirBackend
from cairntir.memory.embeddings import SentenceTransformerProvider
from cairntir.memory.store import DrawerStore
from cairntir.update import maybe_check_in_background, pending_update_banner

_SERVER_NAME = "cairntir"

_WARMUP_DISABLE_ENV_VAR: Final[str] = "CAIRNTIR_DISABLE_EMBEDDER_WARMUP"
"""Set to a truthy value to skip the post-handshake embedder warmup.

The warmup is cheap-to-skip and only matters for production
``SentenceTransformerProvider`` users. Setting this off in CI or in
tests that use the deterministic ``HashEmbeddingProvider`` is harmless
and quiet.
"""

_WARMUP_PROBE: Final[str] = "cairntir embedder warmup"
"""The text the warmup thread embeds. Content is irrelevant — only the
side effect (loading the model) matters."""


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
            name="cairntir_cross_recall",
            description=(
                "Semantic search across EVERY wing. Use when a question might find "
                "its answer in a different project than the active one."
            ),
            inputSchema={
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
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
        case "cairntir_cross_recall":
            return backend.cross_recall(**args)
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
        except ValidationError as exc:
            # Pydantic ValidationError is raised by Drawer construction when
            # the caller's arguments fail wing/room/content validation. It
            # does NOT inherit from ValueError or CairntirError in pydantic
            # v2, so the previous CairntirError-only catch let it crash the
            # tool call as a raw framework error. Surface it as a clean
            # message — the caller (an LLM) can read the field path and
            # retry with a corrected argument.
            text = f"[cairntir error] invalid argument: {_format_validation_error(exc)}"

        if not update_banner_shown:
            banner = pending_update_banner()
            if banner is not None:
                text = f"{banner}\n\n{text}"
            update_banner_shown = True

        return [types.TextContent(type="text", text=text)]

    return server


def _format_validation_error(exc: ValidationError) -> str:
    """Render a pydantic ValidationError as one short user-facing line.

    Pydantic's default repr is multi-line and includes a URL, which is
    noisy in a tool-response context. We pick the first error and
    summarize it: ``field: message`` is enough for the LLM caller to
    self-correct.
    """
    errors = exc.errors()
    if not errors:
        return str(exc)
    first = errors[0]
    location = ".".join(str(part) for part in first.get("loc", ())) or "<root>"
    message = first.get("msg", "validation failed")
    return f"{location}: {message}"


def _warmup_disabled() -> bool:
    raw = os.environ.get(_WARMUP_DISABLE_ENV_VAR, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def warm_embedder_in_background(store: DrawerStore) -> threading.Thread | None:
    """Spawn a daemon thread that loads the embedder model.

    The cold-start fix in ``DrawerStore.__init__`` made the handshake
    fast by skipping ``embedder.dimension`` on existing databases. But
    the embedder still cold-loads on the *first* ``embed()`` call —
    which means the first ``cairntir_remember`` or ``cairntir_recall``
    after a server start blocks the user for ~25 seconds while
    sentence-transformers + torch import.

    This helper kicks off a single throwaway ``embed()`` call in a
    daemon thread. The asyncio event loop runs the MCP handshake in
    parallel; by the time the user's first tool call arrives the
    model is partially or fully loaded, so first-write latency drops
    from ~25s to ~0s in the happy case.

    Returns the thread (so tests can ``join`` it) or ``None`` if the
    warmup is disabled by env var. Failures are intentionally
    swallowed: a warmup miss simply means the next real ``embed()``
    call surfaces the actual error to the user; crashing a background
    thread for a best-effort optimization would defeat the point.
    """
    if _warmup_disabled():
        return None

    def _warm() -> None:
        try:
            store._embedder.embed([_WARMUP_PROBE])
        except (EmbeddingError, OSError):
            # Best-effort. The next real embed() call will surface the
            # real error path to the user; don't crash the daemon for a
            # warmup miss.
            return

    thread = threading.Thread(
        target=_warm,
        name="cairntir-embedder-warmup",
        daemon=True,
    )
    thread.start()
    return thread


async def _amain() -> None:
    # Kick off the background PyPI check so the *next* tool call (or
    # the one after) sees the latest-version cache. The check runs in
    # a daemon thread, fail-silent on network or permission errors.
    maybe_check_in_background()

    store = DrawerStore(db_path(), SentenceTransformerProvider())
    backend = CairntirBackend(store)

    # Warm the embedder while the asyncio handshake completes. The
    # MCP initialize JSON-RPC is mostly I/O-bound and releases the GIL
    # often, so torch + sentence-transformers can load in parallel.
    # By the time the user's first tool call arrives, the model is
    # warm and first-write latency is no longer ~25 seconds.
    warm_embedder_in_background(store)

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
