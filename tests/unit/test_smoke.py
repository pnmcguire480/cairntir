"""Smoke tests for the Cairntir package bootstrap.

These are intentionally minimal. They verify that the package imports, the
version is exposed, and the error hierarchy is wired correctly. Real tests
arrive with Phase 1.
"""

from __future__ import annotations

import cairntir
from cairntir import errors


def test_version_is_exposed() -> None:
    """The package exposes a dunder version string."""
    assert isinstance(cairntir.__version__, str)
    assert cairntir.__version__


def test_error_hierarchy() -> None:
    """All Cairntir errors inherit from the base exception."""
    for exc_cls in (
        errors.ConfigError,
        errors.MemoryStoreError,
        errors.TaxonomyError,
        errors.RetrievalError,
        errors.EmbeddingError,
        errors.SkillError,
        errors.MCPError,
    ):
        assert issubclass(exc_cls, errors.CairntirError)
        assert issubclass(exc_cls, Exception)
