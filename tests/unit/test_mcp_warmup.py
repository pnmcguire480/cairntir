"""Tests for the post-handshake embedder warmup helper.

The warmup is the second half of the cold-start fix: ``__init__`` no
longer loads the embedder, but the *first* ``embed()`` call would
still pay the ~25s sentence-transformers cold-load. The warmup spawns
a daemon thread that triggers the load in parallel with the MCP
handshake, so the user's first ``cairntir_remember`` or
``cairntir_recall`` returns in ~0s instead of ~25s.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from cairntir.errors import EmbeddingError
from cairntir.mcp import server as mcp_server
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore


class _CountingEmbedder:
    """Minimal embedder that records every embed() call."""

    def __init__(self, *, raises: BaseException | None = None) -> None:
        self.calls: list[Sequence[str]] = []
        self._raises = raises

    @property
    def dimension(self) -> int:
        return 8

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        if self._raises is not None:
            raise self._raises
        return [[0.0] * self.dimension for _ in texts]


@pytest.fixture()
def _store_factory(tmp_path: Path) -> Any:
    def _make(embedder: Any) -> DrawerStore:
        return DrawerStore(tmp_path / "warmup.db", embedder)

    return _make


def test_warmup_disabled_returns_none(
    _store_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CAIRNTIR_DISABLE_EMBEDDER_WARMUP", "1")
    embedder = _CountingEmbedder()
    store = _store_factory(embedder)
    try:
        thread = mcp_server.warm_embedder_in_background(store)
    finally:
        store.close()
    assert thread is None
    assert embedder.calls == []


def test_warmup_disable_accepts_truthy_synonyms(
    _store_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The off switch matches the same vocabulary as the other env-var opt-outs."""
    embedder = _CountingEmbedder()
    store = _store_factory(embedder)
    try:
        for value in ("1", "true", "TRUE", "yes", "On"):
            monkeypatch.setenv("CAIRNTIR_DISABLE_EMBEDDER_WARMUP", value)
            assert mcp_server.warm_embedder_in_background(store) is None
    finally:
        store.close()
    assert embedder.calls == []


def test_warmup_spawns_thread_and_calls_embed(
    _store_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CAIRNTIR_DISABLE_EMBEDDER_WARMUP", raising=False)
    embedder = _CountingEmbedder()
    store = _store_factory(embedder)
    try:
        thread = mcp_server.warm_embedder_in_background(store)
        assert thread is not None
        assert thread.daemon, "warmup thread must be a daemon — never block process exit"
        thread.join(timeout=5)
        assert not thread.is_alive(), "warmup thread did not finish in time"
    finally:
        store.close()
    assert len(embedder.calls) == 1
    assert embedder.calls[0] == [mcp_server._WARMUP_PROBE]


def test_warmup_swallows_embedding_error(
    _store_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A warmup miss must not crash the daemon thread."""
    monkeypatch.delenv("CAIRNTIR_DISABLE_EMBEDDER_WARMUP", raising=False)
    embedder = _CountingEmbedder(raises=EmbeddingError("fake"))
    store = _store_factory(embedder)
    try:
        thread = mcp_server.warm_embedder_in_background(store)
        assert thread is not None
        thread.join(timeout=5)
        assert not thread.is_alive()
    finally:
        store.close()
    assert len(embedder.calls) == 1


def test_warmup_swallows_oserror(
    _store_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OSErrors (e.g. model cache file system issue) must also be swallowed."""
    monkeypatch.delenv("CAIRNTIR_DISABLE_EMBEDDER_WARMUP", raising=False)
    embedder = _CountingEmbedder(raises=OSError("disk full"))
    store = _store_factory(embedder)
    try:
        thread = mcp_server.warm_embedder_in_background(store)
        assert thread is not None
        thread.join(timeout=5)
        assert not thread.is_alive()
    finally:
        store.close()


def test_warmup_runs_against_hash_embedder_too(
    _store_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HashEmbeddingProvider is instant — the warmup is a no-op cost on it.

    We do not detect the embedder type; the warmup is unconditional when
    enabled. This test pins that behavior so a future refactor doesn't
    silently turn the warmup into something that only fires for the
    SentenceTransformerProvider.
    """
    monkeypatch.delenv("CAIRNTIR_DISABLE_EMBEDDER_WARMUP", raising=False)
    embedder = HashEmbeddingProvider(dimension=16)
    store = _store_factory(embedder)
    try:
        thread = mcp_server.warm_embedder_in_background(store)
        assert thread is not None
        thread.join(timeout=5)
    finally:
        store.close()
