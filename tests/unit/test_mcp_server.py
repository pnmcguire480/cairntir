"""Tests for the MCP stdio server's error-translation surface.

The transport-free backend is exercised in
``tests/integration/test_mcp_backend.py``. These tests focus on
``build_server``'s ``_call`` adapter — specifically the exception
translation that turns CairntirError and pydantic ValidationError into
clean user-facing strings instead of crashing the tool call.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from cairntir import __version__
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


def test_session_start_tool_spec_does_not_advertise_query() -> None:
    """`cairntir_session_start` MUST NOT advertise a ``query`` parameter.

    Regression: 1.1.0 advertised it; Claude Code routinely passed a query;
    the resulting embed() cold load took ~2.5 minutes on real machines and
    Claude Code's MCP timeout fired well before the response arrived. The
    fix in 1.1.2 strips ``query`` from the tool spec so session_start is
    pure SQL — sub-second on cold MCP servers, every time. The backend
    method still accepts ``query`` for direct library callers.
    """
    from cairntir.mcp.server import _tool_specs

    specs = {tool.name: tool for tool in _tool_specs()}
    session_start = specs["cairntir_session_start"]
    properties = session_start.inputSchema["properties"]
    assert "wing" in properties
    assert "query" not in properties, (
        "cairntir_session_start MUST NOT advertise a query parameter — "
        "it triggers the embedder cold load and wedges Claude Code's "
        "MCP timeout. Use cairntir_recall for semantic search."
    )


def test_get_tool_spec_exposes_exact_drawer_fetch() -> None:
    from cairntir.mcp.server import _tool_specs

    specs = {tool.name: tool for tool in _tool_specs()}
    get_tool = specs["cairntir_get"]
    assert get_tool.inputSchema["required"] == ["drawer_id"]
    assert get_tool.inputSchema["properties"]["drawer_id"]["minimum"] == 1


def test_discovery_tools_are_exposed_with_evidence_requirement() -> None:
    from cairntir.mcp.server import _tool_specs

    specs = {tool.name: tool for tool in _tool_specs()}
    assert {
        "cairntir_discover",
        "cairntir_discovery_transition",
        "cairntir_discoveries",
        "cairntir_learning_log",
        "cairntir_discover_scan",
        "cairntir_calibration",
        "cairntir_codeglass_record",
        "cairntir_codeglass_teachback",
        "cairntir_codeglass_retention",
    } <= specs.keys()
    discover = specs["cairntir_discover"]
    assert "evidence_ids" in discover.inputSchema["required"]
    assert discover.inputSchema["properties"]["evidence_ids"]["minItems"] == 1


def test_hotfix_tool_spec_exposes_discriminated_action_payloads() -> None:
    from cairntir.mcp.server import _tool_specs

    specs = {tool.name: tool for tool in _tool_specs()}
    hotfix = specs["cairntir_hotfix"]
    variants = hotfix.inputSchema["oneOf"]
    actions = {variant["properties"]["action"]["const"] for variant in variants}
    assert actions == {
        "open",
        "recommend",
        "authorize",
        "preflight",
        "record_attempt",
        "rollback",
        "verify",
        "settle",
        "status",
    }
    open_variant = next(
        variant for variant in variants if variant["properties"]["action"]["const"] == "open"
    )
    open_payload = open_variant["properties"]["payload"]
    assert set(open_payload["required"]) == {"title", "stage", "symptom", "acceptance"}
    assert open_payload["additionalProperties"] is False


def test_hotfix_tool_dispatch_returns_structured_receipt(_backend: CairntirBackend) -> None:
    server = build_server(_backend)
    text = _invoke_call_tool(
        server,
        "cairntir_hotfix",
        {
            "action": "open",
            "wing": "cairntir",
            "payload": {
                "title": "MCP hotfix",
                "stage": "a4",
                "symptom": "assertion failed",
                "acceptance": ["MCP receipt returns"],
            },
            "idempotency_key": "mcp-hotfix-open",
        },
    )
    payload = json.loads(text)
    assert payload["schema"] == "cairntir.hotfix.v1"
    assert payload["state"] == "open"
    assert payload["legal_actions"] == ["recommend", "settle"]


def test_get_tool_returns_complete_drawer(_backend: CairntirBackend) -> None:
    server = build_server(_backend)
    _invoke_call_tool(
        server,
        "cairntir_remember",
        {
            "wing": "cairntir",
            "room": "exact",
            "content": "complete content through MCP",
        },
    )
    text = _invoke_call_tool(server, "cairntir_get", {"drawer_id": 1})
    assert '"content": "complete content through MCP"' in text
    assert '"resource": "cairntir://drawer/1"' in text


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


def test_server_handshake_reports_cairntir_version(_backend: CairntirBackend) -> None:
    """The handshake must advertise Cairntir's version, not the SDK's.

    ``Server(name)`` built without ``version=`` makes the mcp library fall
    back to reporting its own package version in ``serverInfo``, so every
    host shows the SDK's number and an operator cannot tell which Cairntir
    they are actually talking to.
    """
    options = build_server(_backend).create_initialization_options()
    assert options.server_version == __version__
