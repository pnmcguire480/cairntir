"""Embedding providers.

Cairntir embeds drawer content into a fixed-dimension float32 vector for
semantic search via ``sqlite-vec``. This module defines a minimal
:class:`EmbeddingProvider` protocol plus two concrete implementations:

* :class:`SentenceTransformerProvider` — the production default, lazy-loads
  a local ``sentence-transformers`` model.
* :class:`HashEmbeddingProvider` — a deterministic, dependency-free fallback
  used by the unit tests so they never touch the network or load a 90 MB
  model on every CI run.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import math
import os
import sys
from collections.abc import Iterator, Sequence
from typing import Protocol, runtime_checkable

from cairntir.errors import EmbeddingError


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Protocol implemented by every embedding backend."""

    @property
    def dimension(self) -> int:
        """Return the embedding dimension."""
        ...

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a batch of texts. Must return one vector per input, length == dimension."""
        ...


class HashEmbeddingProvider:
    """Deterministic hash-based embedder for tests and offline dev.

    Not semantically meaningful. Same input always maps to the same vector,
    which is all the store tests need to verify round-tripping.
    """

    def __init__(self, dimension: int = 64) -> None:
        """Create a hash embedder with the given output dimension."""
        if dimension <= 0:
            raise EmbeddingError(f"dimension must be positive, got {dimension}")
        self._dim = dimension

    @property
    def dimension(self) -> int:
        """Return the configured dimension."""
        return self._dim

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed each text as a unit-norm vector derived from its SHA-256 digest."""
        out: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            # Expand digest to dimension by cycling bytes.
            raw = [digest[i % len(digest)] for i in range(self._dim)]
            # Center around zero and normalize.
            centered = [(b - 127.5) / 127.5 for b in raw]
            norm = math.sqrt(sum(x * x for x in centered)) or 1.0
            out.append([x / norm for x in centered])
        return out


class SentenceTransformerProvider:
    """Production embedder backed by ``sentence-transformers``.

    Lazy-loads the model on first :meth:`embed` call so importing this module
    is free even on machines without the heavy dependency installed.

    All model loading and inference happens with ``stdout``/``stderr``
    silenced. ``sentence-transformers``, ``transformers``, and ``torch``
    write progress bars and architecture-mismatch tables directly to
    ``stdout`` during ``__init__`` (see "BertModel LOAD REPORT" in the
    upstream code). When this provider runs inside the MCP stdio server,
    that output corrupts the JSON-RPC stream Claude Code is reading,
    which wedges every subsequent tool call indefinitely (observed
    2026-04-25 on a real user box: 20+ minutes per stuck session).
    Silencing fixes the corruption at the source — production callers
    never want progress bars in their tool responses anyway.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        """Create a provider; the model is loaded on first use."""
        self._model_name = model_name
        self._model: object | None = None
        self._dim: int | None = None

    def _load(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbeddingError(
                "sentence-transformers is not installed; install cairntir with the default extras"
            ) from exc
        with _silence_io():
            model = SentenceTransformer(self._model_name)
        dim = model.get_sentence_embedding_dimension()
        if dim is None:
            raise EmbeddingError(f"model {self._model_name} reported no embedding dimension")
        self._model = model
        self._dim = int(dim)

    @property
    def dimension(self) -> int:
        """Return the embedding dimension, loading the model if needed."""
        if self._dim is None:
            self._load()
        if self._dim is None:  # pragma: no cover — _load guarantees this
            raise EmbeddingError("dimension still None after _load — provider is in a broken state")
        return self._dim

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed texts using the underlying sentence-transformers model."""
        if self._model is None:
            self._load()
        if self._model is None:  # pragma: no cover — _load guarantees this
            raise EmbeddingError("model still None after _load — provider is in a broken state")
        try:
            with _silence_io():
                vectors = self._model.encode(  # type: ignore[attr-defined]
                    list(texts),
                    normalize_embeddings=True,
                    convert_to_numpy=True,
                )
        except Exception as exc:
            raise EmbeddingError(f"sentence-transformers encode failed: {exc}") from exc
        return [[float(x) for x in row] for row in vectors]


@contextlib.contextmanager
def _silence_io() -> Iterator[None]:
    """Redirect stdout and stderr to /dev/null at the OS file-descriptor level.

    ``contextlib.redirect_stdout`` only swaps ``sys.stdout``; it doesn't
    catch direct writes to fd 1 from C extensions like ``torch`` and
    ``transformers``. We dup the real fds, point fd 1/2 at devnull,
    yield, then restore. Failure to restore would silence the rest of
    the process — guarded with ``try/finally``.
    """
    saved_stdout_fd = os.dup(1)
    saved_stderr_fd = os.dup(2)
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    # Also redirect the Python-level streams so any Python code that
    # writes via sys.stdout (rather than the raw fd) also goes nowhere.
    saved_sys_stdout = sys.stdout
    saved_sys_stderr = sys.stderr
    try:
        os.dup2(devnull_fd, 1)
        os.dup2(devnull_fd, 2)
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        yield
    finally:
        sys.stdout = saved_sys_stdout
        sys.stderr = saved_sys_stderr
        os.dup2(saved_stdout_fd, 1)
        os.dup2(saved_stderr_fd, 2)
        os.close(saved_stdout_fd)
        os.close(saved_stderr_fd)
        os.close(devnull_fd)
