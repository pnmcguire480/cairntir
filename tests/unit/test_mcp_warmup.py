"""Tests for the post-handshake embedder warmup helper.

The warmup is **opt-in** as of 2026-04-25. Setting
``CAIRNTIR_ENABLE_EMBEDDER_WARMUP=1`` re-enables the daemon thread that
loads the embedder model in parallel with the MCP handshake. Without
that env var the helper is a no-op — see the docstring on
``warm_embedder_in_background`` for the production hang that drove the
default flip.
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


def test_warmup_default_off_returns_none(
    _store_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without the opt-in env var the warmup must NOT spawn a thread.

    Regression: pre-2026-04-25 the warmup was on by default and wedged
    `cairntir_session_start` for 20+ minutes per session because the
    daemon thread raced with the synchronous embed() the retriever
    triggers on a queried session_start. Default-off restores the
    pre-91a8350 behavior.
    """
    monkeypatch.delenv("CAIRNTIR_ENABLE_EMBEDDER_WARMUP", raising=False)
    embedder = _CountingEmbedder()
    store = _store_factory(embedder)
    try:
        thread = mcp_server.warm_embedder_in_background(store)
    finally:
        store.close()
    assert thread is None
    assert embedder.calls == []


def test_warmup_enable_accepts_truthy_synonyms(
    _store_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The on switch matches the same vocabulary as the other env-var opt-ins."""
    embedder = _CountingEmbedder()
    store = _store_factory(embedder)
    try:
        for value in ("1", "true", "TRUE", "yes", "On"):
            monkeypatch.setenv("CAIRNTIR_ENABLE_EMBEDDER_WARMUP", value)
            thread = mcp_server.warm_embedder_in_background(store)
            assert thread is not None
            thread.join(timeout=5)
    finally:
        store.close()
    # Five enabled invocations -> five embed calls.
    assert len(embedder.calls) == 5


def test_warmup_when_enabled_spawns_thread_and_calls_embed(
    _store_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CAIRNTIR_ENABLE_EMBEDDER_WARMUP", "1")
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
    monkeypatch.setenv("CAIRNTIR_ENABLE_EMBEDDER_WARMUP", "1")
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


def test_warmup_swallows_oserror(_store_factory: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """OSErrors (e.g. model cache file system issue) must also be swallowed."""
    monkeypatch.setenv("CAIRNTIR_ENABLE_EMBEDDER_WARMUP", "1")
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
    """When opted in, the warmup fires regardless of embedder type."""
    monkeypatch.setenv("CAIRNTIR_ENABLE_EMBEDDER_WARMUP", "1")
    embedder = HashEmbeddingProvider(dimension=16)
    store = _store_factory(embedder)
    try:
        thread = mcp_server.warm_embedder_in_background(store)
        assert thread is not None
        thread.join(timeout=5)
    finally:
        store.close()
