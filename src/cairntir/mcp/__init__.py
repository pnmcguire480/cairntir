"""Host-neutral MCP server exposing Cairntir's memory and reasoning tools.

The transport-free backend lives in :mod:`cairntir.mcp.backend`; the stdio
adapter lives in :mod:`cairntir.mcp.server`.
"""

from __future__ import annotations

from cairntir.mcp.backend import CairntirBackend

__all__ = ["CairntirBackend"]
