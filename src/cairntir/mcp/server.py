"""MCP stdio server exposing Cairntir's host-neutral tools.

Run directly with ``python -m cairntir.mcp.server`` — see ``.mcp.json``. The
server holds a single :class:`~cairntir.mcp.backend.CairntirBackend`
instance backed by the store at :func:`cairntir.config.db_path`.
"""

from __future__ import annotations

import argparse
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
from cairntir.memory.embeddings import production_embedding_provider
from cairntir.memory.store import DrawerStore
from cairntir.provenance import TrustLevel, WriteProvenance
from cairntir.update import maybe_check_in_background, pending_update_banner

_SERVER_NAME = "cairntir"


def _trace(message: str) -> None:
    """Append a timestamped diagnostic line to ``cairntir_home() / mcp.log``.

    Stderr is captured by Claude Code and not easily inspectable;
    a log file in the user's Cairntir home is. Best-effort: an OSError
    here means the home dir isn't writable, in which case we silently
    skip — diagnostics should never crash the server.
    """
    try:
        from datetime import UTC, datetime

        from cairntir.config import cairntir_home

        log_path = cairntir_home() / "mcp.log"
        stamp = datetime.now(UTC).isoformat(timespec="milliseconds")
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"{stamp} pid={os.getpid()} {message}\n")
    except (OSError, ImportError):
        return


_WARMUP_ENABLE_ENV_VAR: Final[str] = "CAIRNTIR_ENABLE_EMBEDDER_WARMUP"
"""Set to a truthy value to opt INTO the post-handshake embedder warmup.

The warmup is disabled by default because the legacy model provider once
raced a background load against a synchronous semantic request and wedged
the MCP transport. FastEmbed is now the production provider, but background
model initialization stays opt-in until concurrency is proven across every
supported platform. ``cairntir setup`` performs a safe foreground pre-warm.
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
            name="cairntir_get",
            description=(
                "Fetch one complete, verbatim drawer by id as structured JSON. "
                "Use this for cairntir://drawer/<id> references returned by recall."
            ),
            inputSchema={
                "type": "object",
                "required": ["drawer_id"],
                "properties": {
                    "drawer_id": {"type": "integer", "minimum": 1},
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
            description=(
                "Load 4-layer context plus active discoveries for a wing. "
                "Pure SQL — never triggers the embedder. Use cairntir_recall "
                "for semantic search after the session is loaded."
            ),
            inputSchema={
                "type": "object",
                "required": ["wing"],
                "properties": {
                    "wing": {"type": "string"},
                },
            },
        ),
        types.Tool(
            name="cairntir_discover",
            description=(
                "Record an evidence-backed emergent pattern or positive capability gain. "
                "Tell the user after recording it. Use novelty=user when it is new to "
                "the user, cairntir when Cairntir's behavior differs from its baseline, "
                "and general only when external research supports broader novelty."
            ),
            inputSchema={
                "type": "object",
                "required": ["wing", "title", "summary", "novelty", "evidence_ids"],
                "properties": {
                    "wing": {"type": "string"},
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "novelty": {
                        "type": "string",
                        "enum": ["user", "cairntir", "general"],
                    },
                    "evidence_ids": {
                        "type": "array",
                        "items": {"type": "integer", "minimum": 1},
                        "minItems": 1,
                    },
                    "state": {
                        "type": "string",
                        "enum": [
                            "signal",
                            "candidate",
                            "corroborated",
                            "promoted",
                            "rejected",
                            "expired",
                        ],
                        "default": "signal",
                    },
                },
            },
        ),
        types.Tool(
            name="cairntir_discovery_transition",
            description=(
                "Append a reviewed lifecycle transition for a discovery. "
                "Never rewrites or deletes the earlier learning record."
            ),
            inputSchema={
                "type": "object",
                "required": ["drawer_id", "state", "note"],
                "properties": {
                    "drawer_id": {"type": "integer", "minimum": 1},
                    "state": {
                        "type": "string",
                        "enum": [
                            "signal",
                            "candidate",
                            "corroborated",
                            "promoted",
                            "rejected",
                            "expired",
                        ],
                    },
                    "note": {"type": "string"},
                },
            },
        ),
        types.Tool(
            name="cairntir_discoveries",
            description="List the current leaves of the append-only Discovery Ledger.",
            inputSchema={
                "type": "object",
                "properties": {
                    "wing": {"type": "string"},
                    "state": {
                        "type": "string",
                        "enum": [
                            "signal",
                            "candidate",
                            "corroborated",
                            "promoted",
                            "rejected",
                            "expired",
                        ],
                    },
                    "limit": {"type": "integer", "default": 100, "minimum": 1},
                },
            },
        ),
        types.Tool(
            name="cairntir_learning_log",
            description=(
                "Read the easy-to-access Human Learning Log of candidate, "
                "corroborated, and promoted discoveries."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "wing": {"type": "string"},
                    "include_candidates": {"type": "boolean", "default": True},
                    "limit": {"type": "integer", "default": 100, "minimum": 1},
                },
            },
        ),
        types.Tool(
            name="cairntir_discover_scan",
            description=(
                "Propose conservative discovery candidates from repeated "
                "prediction/observation episodes. Never auto-promotes."
            ),
            inputSchema={
                "type": "object",
                "required": ["wing"],
                "properties": {
                    "wing": {"type": "string"},
                    "min_observations": {
                        "type": "integer",
                        "default": 3,
                        "minimum": 2,
                    },
                    "confidence_threshold": {
                        "type": "number",
                        "default": 0.8,
                        "exclusiveMinimum": 0.5,
                        "maximum": 1.0,
                    },
                },
            },
        ),
        types.Tool(
            name="cairntir_calibration",
            description=(
                "Show empirical prediction success, uncertainty, unresolved "
                "predictions, belief mass, and contradictions for a wing."
            ),
            inputSchema={
                "type": "object",
                "required": ["wing"],
                "properties": {"wing": {"type": "string"}},
            },
        ),
        types.Tool(
            name="cairntir_codeglass_record",
            description=(
                "Store an evidence-cited WHAT/HOW/WHERE/WHEN/WHY walkthrough. "
                "Each non-unknown section must contain a [source:...] citation."
            ),
            inputSchema={
                "type": "object",
                "required": [
                    "wing",
                    "target",
                    "reader_level",
                    "what",
                    "how",
                    "where",
                    "when",
                    "why",
                    "evidence_ids",
                    "glossary",
                    "danger_zones",
                ],
                "properties": {
                    "wing": {"type": "string"},
                    "target": {"type": "string"},
                    "reader_level": {
                        "type": "string",
                        "enum": ["novice", "intermediate", "expert"],
                    },
                    "what": {"type": "string"},
                    "how": {"type": "string"},
                    "where": {"type": "string"},
                    "when": {"type": "string"},
                    "why": {"type": "string"},
                    "evidence_ids": {
                        "type": "array",
                        "items": {"type": "integer", "minimum": 1},
                        "minItems": 1,
                    },
                    "glossary": {"type": "string"},
                    "danger_zones": {"type": "string"},
                    "idempotency_key": {"type": "string"},
                },
            },
        ),
        types.Tool(
            name="cairntir_codeglass_teachback",
            description=(
                "Record two or three reviewed teach-back answers. Use phase=immediate "
                "after the walkthrough and phase=delayed later to measure retention."
            ),
            inputSchema={
                "type": "object",
                "required": ["walkthrough_id", "phase", "responses"],
                "properties": {
                    "walkthrough_id": {"type": "integer", "minimum": 1},
                    "phase": {
                        "type": "string",
                        "enum": ["immediate", "delayed"],
                    },
                    "responses": {
                        "type": "array",
                        "minItems": 2,
                        "maxItems": 3,
                        "items": {
                            "type": "object",
                            "required": ["question", "answer", "score"],
                            "properties": {
                                "question": {"type": "string"},
                                "answer": {"type": "string"},
                                "score": {
                                    "type": "number",
                                    "minimum": 0.0,
                                    "maximum": 1.0,
                                },
                            },
                        },
                    },
                    "mastered_concepts": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "misunderstood_concepts": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "idempotency_key": {"type": "string"},
                },
            },
        ),
        types.Tool(
            name="cairntir_codeglass_retention",
            description=(
                "Compare immediate and delayed CodeGlass teach-back scores and "
                "show mastered concepts and concepts to revisit."
            ),
            inputSchema={
                "type": "object",
                "required": ["walkthrough_id"],
                "properties": {
                    "walkthrough_id": {"type": "integer", "minimum": 1},
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
        case "cairntir_get":
            return backend.get(**args)
        case "cairntir_cross_recall":
            return backend.cross_recall(**args)
        case "cairntir_session_start":
            return backend.session_start(**args)
        case "cairntir_discover":
            return backend.discover(**args)
        case "cairntir_discovery_transition":
            return backend.transition_discovery(**args)
        case "cairntir_discoveries":
            return backend.discoveries(**args)
        case "cairntir_learning_log":
            return backend.learning_log(**args)
        case "cairntir_discover_scan":
            return backend.discover_scan(**args)
        case "cairntir_calibration":
            return backend.calibration(**args)
        case "cairntir_codeglass_record":
            return backend.codeglass_record(**args)
        case "cairntir_codeglass_teachback":
            return backend.codeglass_teachback(**args)
        case "cairntir_codeglass_retention":
            return backend.codeglass_retention(**args)
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
        _trace(f"_call enter name={name!r} args_keys={sorted(arguments.keys())}")
        try:
            text = _dispatch(backend, name, arguments)
            _trace(f"_call dispatch ok name={name!r} text_len={len(text)}")
        except CairntirError as exc:
            _trace(f"_call CairntirError name={name!r} msg={exc}")
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

        _trace(f"_call returning name={name!r} final_len={len(text)}")
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


def _warmup_enabled() -> bool:
    raw = os.environ.get(_WARMUP_ENABLE_ENV_VAR, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def warm_embedder_in_background(store: DrawerStore) -> threading.Thread | None:
    """Spawn a daemon thread that loads the embedder model (opt-in).

    Returns ``None`` unless ``CAIRNTIR_ENABLE_EMBEDDER_WARMUP=1`` is set
    in the environment. It remains default-off because model providers may
    not make concurrent first-load guarantees.

    When enabled, the helper kicks off a single throwaway ``embed()``
    call in a daemon thread so the model loads in parallel with the
    MCP handshake. First-write latency drops from ~25s to ~0s in the
    happy case. Normal installations should use ``cairntir setup`` to
    pre-warm in the foreground instead.

    Failures are intentionally swallowed: a warmup miss simply means
    the next real ``embed()`` call surfaces the actual error to the
    user; crashing a background thread for a best-effort optimization
    would defeat the point.
    """
    if not _warmup_enabled():
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


async def _amain(*, host: str = "unknown", model: str = "unknown") -> None:
    # Force HuggingFace Hub fully offline so local model providers never
    # try to revalidate cached assets against the network during load.
    # The model files are cached locally after first download; phoning
    # home on every server start adds latency and, on flaky/blocked
    # networks, can wedge the load indefinitely. Users who genuinely
    # need to download a new model should run a one-time download
    # outside the MCP server.
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    _trace("amain start")
    # Kick off the background PyPI check so the *next* tool call (or
    # the one after) sees the latest-version cache. The check runs in
    # a daemon thread, fail-silent on network or permission errors.
    maybe_check_in_background()
    _trace("update check spawned")

    store = DrawerStore(
        db_path(),
        production_embedding_provider(),
        provenance=WriteProvenance.create(
            host=host,
            capture_path="mcp",
            trust=TrustLevel.AGENT_GENERATED,
            model=model,
        ),
    )
    _trace("DrawerStore opened")
    backend = CairntirBackend(store)

    # Warm the embedder while the asyncio handshake completes. The MCP
    # initialize JSON-RPC is mostly I/O-bound and releases the GIL often,
    # so the ONNX session can load in parallel. With fastembed as the
    # default provider, cold start is already ~5s instead of the 1-12 min
    # torch took, so this warmup is now an optional polish rather than a
    # survival mechanism — kept opt-in via CAIRNTIR_ENABLE_EMBEDDER_WARMUP
    # for the same race-safety reasons documented on
    # warm_embedder_in_background().
    warm_embedder_in_background(store)
    _trace("warmup considered")

    server = build_server(backend)
    _trace("server built; entering stdio_server")
    async with stdio_server() as (read, write):
        _trace("stdio_server entered; starting server.run")
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    """Entry point for the ``cairntir-mcp`` console script.

    Also reachable as ``python -m cairntir.mcp.server``. The console
    script is the registered command — see ``cairntir.cli._mcp_spec``
    and the ``[project.scripts]`` entry in ``pyproject.toml``.
    """
    parser = argparse.ArgumentParser(description="Run the Cairntir MCP stdio server")
    parser.add_argument("--host", default="unknown")
    parser.add_argument("--model", default=os.environ.get("CAIRNTIR_MODEL", "unknown"))
    args = parser.parse_args()
    asyncio.run(_amain(host=args.host, model=args.model))


if __name__ == "__main__":
    main()
