"""MCP server exposing 6 tools: remember, recall, session_start, timeline, audit, crucible.

The transport-free backend lives in :mod:`cairntir.mcp.backend`; the stdio
adapter lives in :mod:`cairntir.mcp.server`.
"""

from __future__ import annotations

from cairntir.mcp.backend import CairntirBackend

__all__ = ["CairntirBackend"]
