"""Cairntir — memory-first reasoning layer for Claude Code.

Cairntir stores verbatim drawers of memory in a wing/room taxonomy backed by
sqlite-vec, exposes a 4-layer retrieval model, and provides three skills
(crucible, quality, reason) over MCP. Its mission is to kill cross-chat AI
amnesia.

See docs/manifesto.md for the why and docs/concept.md for the what.
"""

from __future__ import annotations

__version__ = "0.1.0"
__all__ = ["__version__"]
