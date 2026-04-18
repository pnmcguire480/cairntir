"""Tests for the MCP stdio server's error-translation surface.

The transport-free backend is exercised in
``tests/integration/test_mcp_backend.py``. These tests focus on
``build_server``'s ``_call`` adapter — specifically the exception
translation that turns CairntirError and pydantic ValidationError into
clean user-facing strings instead of crashing the tool call.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from cairntir.mcp.backend import CairntirBackend
from cairntir.mcp.server import _format_validation_error, build_server
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore


@pytest.fixture()
def _backend(tmp_path: Path) -> CairntirBackend:
    store = DrawerStore(tmp_path / "mcp.db", HashEmbeddingProvider(dimension=32))
    return CairntirBackend(store)


def _invoke_call_tool(server: Any, name: str, arguments: dict[str, Any]) -> str:
    """Drive the MCP server's call_tool handler from a sync test.

    The mcp library exposes the registered handler via
    ``request_handlers[CallToolRequest]``. We reach into it because the
    public ``Server.run`` API requires a real stdio transport, which is
    overkill for asserting that one error path returns the right string.
    """
    from mcp import types

    handler = server.request_handlers[types.CallToolRequest]
    request = types.CallToolRequest(
        method="tools/call",
        params=types.CallToolRequestParams(name=name, arguments=arguments),
    )
    result = asyncio.run(handler(request))
    # ServerResult wraps a CallToolResult; pull the rendered text.
    payload = result.root.content
    assert payload, "expected at least one content block"
    return str(payload[0].text)


def test_remember_invalid_wing_returns_clean_error(_backend: CairntirBackend) -> None:
    """Pydantic ValidationError from Drawer construction must be caught.

    Previously the ``_call`` adapter only caught CairntirError; pydantic
    v2's ValidationError does not inherit from ValueError or
    CairntirError, so an invalid wing crashed the tool call as a raw
    framework error. Regression: the error must come back as a friendly
    string the LLM can read and self-correct from.
    """
    server = build_server(_backend)
    text = _invoke_call_tool(
        server,
        "cairntir_remember",
        {
            "wing": "Has Spaces And Capitals",
            "room": "valid-room",
            "content": "valid content",
        },
    )
    assert "[cairntir error]" in text
    assert "wing" in text


def test_remember_empty_content_returns_clean_error(_backend: CairntirBackend) -> None:
    server = build_server(_backend)
    text = _invoke_call_tool(
        server,
        "cairntir_remember",
        {"wing": "valid-wing", "room": "valid-room", "content": "   "},
    )
    assert "[cairntir error]" in text
    assert "content" in text


def test_recall_empty_query_returns_clean_error(_backend: CairntirBackend) -> None:
    """Backend MCPError (CairntirError subclass) must be caught and surfaced.

    Empty/whitespace query is the backend's own validation, not the
    schema's — the JSON-RPC schema accepts any string. So this exercises
    the ``except CairntirError`` branch of ``_call``.
    """
    server = build_server(_backend)
    text = _invoke_call_tool(server, "cairntir_recall", {"query": "   "})
    assert "[cairntir error]" in text
    assert "non-empty query" in text


def test_invalid_layer_caught_by_mcp_schema(_backend: CairntirBackend) -> None:
    """Invalid layer is enum-validated at the JSON-RPC layer, before dispatch.

    Documented by this test so a future refactor that loosens the tool
    schema does not silently start crashing instead of returning a clean
    framework error message.
    """
    server = build_server(_backend)
    text = _invoke_call_tool(
        server,
        "cairntir_remember",
        {
            "wing": "valid-wing",
            "room": "valid-room",
            "content": "ok",
            "layer": "made-up-layer",
        },
    )
    # MCP framework prefix, not Cairntir's — the schema validator caught it.
    assert "Input validation error" in text
    assert "made-up-layer" in text


def test_remember_succeeds_returns_confirmation(_backend: CairntirBackend) -> None:
    server = build_server(_backend)
    text = _invoke_call_tool(
        server,
        "cairntir_remember",
        {
            "wing": "cairntir",
            "room": "smoke",
            "content": "smoke test from MCP server build_server",
        },
    )
    assert "[cairntir error]" not in text
    assert "Stored drawer" in text
    assert "cairntir/smoke" in text


def test_format_validation_error_picks_first_error() -> None:
    from pydantic import BaseModel, ValidationError

    class _Sample(BaseModel):
        wing: str
        count: int

    try:
        _Sample(wing="ok", count="not-an-int")  # type: ignore[arg-type]
    except ValidationError as exc:
        rendered = _format_validation_error(exc)
    else:
        pytest.fail("expected ValidationError")
    # First error's loc and msg surface; no multi-line dump.
    assert "count" in rendered
    assert "\n" not in rendered
