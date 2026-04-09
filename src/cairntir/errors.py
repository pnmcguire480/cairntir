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


class MemoryStoreError(CairntirError):
    """Raised when the memory layer fails to read or write a drawer."""


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


class PortableFormatError(CairntirError):
    """Raised when a portable drawer envelope is malformed, stale, or unverifiable."""


class ExternalUrlError(PortableFormatError):
    """Raised when a drawer references a non-cairntir URL.

    The v0.5 portable format enforces a structural prohibition: memories
    point to other memories, never to rot-prone external systems. Export
    fails closed if a drawer's content or metadata smuggles in an
    ``http://``, ``https://``, ``ftp://``, ``file://``, or ``ssh://`` URL.
    Only ``cairntir://<content_hash>`` references are permitted.
    """
