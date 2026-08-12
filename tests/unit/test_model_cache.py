"""The model cache must resolve identically for the CLI and the MCP server.

The 1.6.2 upgrade could strand a store: `cairntir reindex` ran in a login
shell, resolved fastembed's ambient default cache
(``tempfile.gettempdir()/fastembed_cache``), downloaded the model there,
rebuilt every vector and stamped the store to the model's 512-dimension
space. The MCP server then started, resolved a *different* temp directory,
found no model, and ``HF_HUB_OFFLINE=1`` forbade fetching it.
``_require_embedding_space`` gates both ``add()`` and ``search()``, so the
store failed closed for reads *and* writes — and the error text told the
user to run ``cairntir reindex``, the command that had just done this.

The fix anchors the cache to ``cairntir_home()``, the same root that already
makes both processes agree about the database path.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from cairntir.config import cairntir_home, db_path, model_cache_dir


def test_cache_is_anchored_to_cairntir_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same root as the database, so agreeing on one implies agreeing on both."""
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))
    monkeypatch.delenv("FASTEMBED_CACHE_PATH", raising=False)

    cache = model_cache_dir()
    assert cache.parent == cairntir_home() == tmp_path
    assert cache.parent == db_path().parent
    assert cache.is_dir()


def test_cache_does_not_live_in_the_ambient_temp_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The defect in one assertion: never fastembed's process-local default."""
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))
    monkeypatch.delenv("FASTEMBED_CACHE_PATH", raising=False)

    fastembed_default = Path(tempfile.gettempdir()) / "fastembed_cache"
    assert model_cache_dir() != fastembed_default


def test_two_processes_with_the_same_home_resolve_the_same_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A differing TEMP must not move the cache; that was the whole bug."""
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))
    monkeypatch.delenv("FASTEMBED_CACHE_PATH", raising=False)

    monkeypatch.setenv("TMPDIR", str(tmp_path / "shell-temp"))
    monkeypatch.setenv("TEMP", str(tmp_path / "shell-temp"))
    as_cli = model_cache_dir()

    monkeypatch.setenv("TMPDIR", str(tmp_path / "server-temp"))
    monkeypatch.setenv("TEMP", str(tmp_path / "server-temp"))
    as_server = model_cache_dir()

    assert as_cli == as_server


def test_explicit_override_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An operator who pins the cache keeps it pinned."""
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))
    override = tmp_path / "pinned"
    monkeypatch.setenv("FASTEMBED_CACHE_PATH", str(override))

    assert model_cache_dir() == override
    assert override.is_dir()
