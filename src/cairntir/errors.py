"""Typed exceptions for Cairntir.

Every error in Cairntir must be a subclass of :class:`CairntirError`. Bare
``except:`` and ``except: pass`` are banned by pre-commit and CI. If you catch
an exception, you either handle it meaningfully or you re-raise with context.
"""

from __future__ import annotations


class CairntirError(Exception):
    """Base exception for all Cairntir errors."""


class ConfigError(CairntirError):
    """Raised when configuration is missing or invalid."""


class MemoryError_(CairntirError):
    """Raised when the memory layer fails to read or write a drawer.

    Named with a trailing underscore to avoid shadowing the Python builtin.
    """


class TaxonomyError(CairntirError):
    """Raised when a wing, room, or drawer identifier is invalid."""


class RetrievalError(CairntirError):
    """Raised when retrieval fails (embedding, search, or layer loading)."""


class EmbeddingError(CairntirError):
    """Raised when the embedding provider fails."""


class SkillError(CairntirError):
    """Raised when a skill (crucible, quality, reason) fails to execute."""


class MCPError(CairntirError):
    """Raised when an MCP tool receives invalid arguments or fails to dispatch."""
