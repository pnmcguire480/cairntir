"""Transport-free backend for Cairntir's MCP tools.

The backend wraps a :class:`~cairntir.memory.store.DrawerStore` and a
:class:`~cairntir.memory.retrieval.Retriever` with pure-Python methods, one
per MCP tool. The MCP :mod:`cairntir.mcp.server` module is a thin adapter
that turns JSON-RPC calls into method invocations and text replies.

Keeping the backend transport-free lets the unit tests invoke tools directly
without needing to stand up a stdio server.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from cairntir.errors import MCPError
from cairntir.memory.retrieval import RetrievalResult, Retriever
from cairntir.memory.taxonomy import Drawer, Layer

if TYPE_CHECKING:
    from cairntir.memory.store import DrawerStore


class CairntirBackend:
    """Transport-free implementation of the six Cairntir MCP tools."""

    def __init__(self, store: DrawerStore) -> None:
        """Create a backend over an existing :class:`DrawerStore`."""
        self._store = store
        self._retriever = Retriever(store)

    # ------------------------------------------------------------------ tools

    def remember(
        self,
        *,
        wing: str,
        room: str,
        content: str,
        layer: str = "on_demand",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Store a verbatim drawer. Returns a human-readable confirmation."""
        try:
            layer_enum = Layer(layer)
        except ValueError as exc:
            raise MCPError(
                f"invalid layer {layer!r}; expected one of {[x.value for x in Layer]}"
            ) from exc
        drawer = Drawer(
            wing=wing,
            room=room,
            content=content,
            layer=layer_enum,
            metadata=metadata or {},
        )
        saved = self._store.add(drawer)
        return (
            f"Stored drawer #{saved.id} in {saved.wing}/{saved.room} (layer={saved.layer.value})."
        )

    def recall(
        self,
        *,
        query: str,
        wing: str | None = None,
        room: str | None = None,
        limit: int = 10,
    ) -> str:
        """Semantic search. Returns a formatted list of hits."""
        if not query.strip():
            raise MCPError("recall requires a non-empty query")
        hits = self._store.search(query, wing=wing, room=room, limit=limit)
        if not hits:
            return f"No drawers matched {query!r}."
        lines = [f"{len(hits)} hit(s) for {query!r}:"]
        for drawer, distance in hits:
            snippet = _snippet(drawer.content)
            lines.append(
                f"  #{drawer.id}  {drawer.wing}/{drawer.room}  "
                f"[{drawer.layer.value}]  d={distance:.4f}  — {snippet}"
            )
        return "\n".join(lines)

    def session_start(self, *, wing: str, query: str | None = None) -> str:
        """Load the 4-layer context for ``wing`` and render it as text."""
        result = self._retriever.load(wing=wing, query=query, include_deep=False)
        return _format_retrieval(wing, result)

    def timeline(self, *, wing: str, entity: str, limit: int = 50) -> str:
        """Chronological view of drawers in ``wing`` mentioning ``entity``."""
        if not entity.strip():
            raise MCPError("timeline requires a non-empty entity")
        drawers = self._store.list_by(wing=wing, limit=limit)
        needle = entity.lower()
        matched = [
            d
            for d in drawers
            if needle in d.content.lower()
            or needle in json.dumps(d.metadata, sort_keys=True).lower()
        ]
        matched.sort(key=lambda d: d.created_at)
        if not matched:
            return f"No timeline entries for {entity!r} in wing {wing!r}."
        lines = [f"Timeline for {entity!r} in {wing!r} ({len(matched)} entries):"]
        for d in matched:
            lines.append(f"  {_fmt_ts(d.created_at)}  #{d.id}  {d.room}  — {_snippet(d.content)}")
        return "\n".join(lines)

    def audit(self, *, wing: str) -> str:
        """Phase-2 stub for the Quality skill. Real invocation lands in Phase 3."""
        essentials = self._store.list_by(wing=wing, layer=Layer.ESSENTIAL, limit=100)
        return (
            f"[cairntir.audit] Phase-2 stub — Quality skill runs in Phase 3.\n"
            f"Wing={wing!r}, essential drawers={len(essentials)}. "
            f"Invoke the `quality` skill against these drawers to produce a full audit."
        )

    def crucible(self, *, claim: str) -> str:
        """Phase-2 stub for the Crucible skill. Real invocation lands in Phase 3."""
        if not claim.strip():
            raise MCPError("crucible requires a non-empty claim")
        return (
            f"[cairntir.crucible] Phase-2 stub — Crucible skill runs in Phase 3.\n"
            f"Claim: {claim}\n"
            f"Next: invoke the `crucible` skill to stress-test this claim "
            f"against stored memory."
        )


# ------------------------------------------------------------------ helpers


def _snippet(content: str, limit: int = 100) -> str:
    single = " ".join(content.split())
    return single if len(single) <= limit else single[: limit - 1] + "…"


def _fmt_ts(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%d %H:%M")


def _format_retrieval(wing: str, result: RetrievalResult) -> str:
    lines = [f"# Cairntir session_start — wing={wing!r}", ""]
    for title, drawers in (
        ("Identity", result.identity),
        ("Essential", result.essential),
        ("On-demand", result.on_demand),
        ("Deep", result.deep),
    ):
        lines.append(f"## {title} ({len(drawers)})")
        if not drawers:
            lines.append("  (none)")
        for d in drawers:
            lines.append(f"  #{d.id}  {d.room}  — {_snippet(d.content)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
