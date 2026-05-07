"""Embedding providers.

Cairntir embeds drawer content into a fixed-dimension float32 vector for
semantic search via ``sqlite-vec``. This module defines a minimal
:class:`EmbeddingProvider` protocol plus three concrete implementations:

* :class:`FastEmbedProvider` — the production default. Lazy-loads
  the same ``all-MiniLM-L6-v2`` model used by ``sentence-transformers``,
  but served via ONNX Runtime instead of PyTorch so cold start drops
  from ~2 minutes to ~5 seconds on CPU-only machines.
* :class:`SentenceTransformerProvider` — legacy production embedder kept
  for opt-in fallback. Embeds with the same model and dimension; the only
  difference is the runtime (PyTorch). Slower to import; use only if
  ``fastembed`` cannot be installed in your environment.
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


class FastEmbedProvider:
    """Production embedder backed by ``fastembed`` (ONNX Runtime).

    Drop-in replacement for :class:`SentenceTransformerProvider` with the
    same output dimension and embedding quality (uses the same
    ``all-MiniLM-L6-v2`` model under the hood, served via ONNX Runtime
    instead of PyTorch).

    Why this exists: ``import sentence_transformers`` triggers a torch
    import that takes 1-2 minutes on CPU-only machines because torch
    initializes CUDA detection, threading, and a wall of C++ extensions
    the embedder never uses. ONNX Runtime imports in seconds. Subjective
    wall-clock difference on a fresh MCP server boot, observed
    2026-05-03 on a real user box: ~127s → ~5s.

    Lazy-loads the model on first :meth:`embed` call so importing this
    module is free even on machines without ``fastembed`` installed.
    The first :meth:`embed` of a brand-new install will trigger a small
    ONNX file download from Hugging Face Hub and cache it under
    ``~/.cache/fastembed/``; subsequent loads on the same machine are
    near-instant. ``cairntir setup`` pre-warms this cache so the first
    user-facing call after install is never the slow one.

    All model loading and inference happens with ``stdout`` and ``stderr``
    silenced for the same reason documented on
    :class:`SentenceTransformerProvider`: uncontrolled writes from C
    extensions corrupt the JSON-RPC stream when this provider runs
    inside the MCP stdio server.
    """

    DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        """Create a provider; the model is loaded on first use."""
        self._model_name = model_name
        self._model: object | None = None
        self._dim: int | None = None

    def _load(self) -> None:
        _embed_trace(f"fastembed _load start model={self._model_name!r}")
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise EmbeddingError(
                "fastembed is not installed; install cairntir with the default extras"
            ) from exc
        _embed_trace("fastembed imported; constructing TextEmbedding()")
        with _silence_io():
            model = TextEmbedding(model_name=self._model_name)
        _embed_trace("fastembed TextEmbedding constructed; reading dimension via probe")
        # fastembed doesn't expose dimension directly. Embed a tiny probe
        # to read it. The probe also forces the ONNX session to warm up,
        # so subsequent embed() calls don't pay any first-use overhead.
        with _silence_io():
            probe = list(model.embed(["dimension probe"]))
        if not probe:
            raise EmbeddingError(f"model {self._model_name} returned no probe vectors")
        dim = len(probe[0])
        self._model = model
        self._dim = int(dim)
        _embed_trace(f"fastembed _load complete dim={self._dim}")

    @property
    def dimension(self) -> int:
        """Return the embedding dimension, loading the model if needed."""
        if self._dim is None:
            self._load()
        if self._dim is None:  # pragma: no cover — _load guarantees this
            raise EmbeddingError("dimension still None after _load — provider is in a broken state")
        return self._dim

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed texts using the underlying fastembed model."""
        _embed_trace(f"fastembed embed enter n={len(texts)} model_loaded={self._model is not None}")
        if self._model is None:
            self._load()
        if self._model is None:  # pragma: no cover — _load guarantees this
            raise EmbeddingError("model still None after _load — provider is in a broken state")
        try:
            _embed_trace("fastembed embed entering encode")
            with _silence_io():
                vectors = list(self._model.embed(list(texts)))  # type: ignore[attr-defined]
            _embed_trace(f"fastembed embed encode complete n_vecs={len(vectors)}")
        except Exception as exc:
            _embed_trace(f"fastembed embed encode FAILED {type(exc).__name__}: {exc}")
            raise EmbeddingError(f"fastembed encode failed: {exc}") from exc
        return [[float(x) for x in row] for row in vectors]


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
        _embed_trace(f"_load start model={self._model_name!r}")
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbeddingError(
                "sentence-transformers is not installed; install cairntir with the default extras"
            ) from exc
        _embed_trace(
            "_load sentence_transformers imported; entering silence + SentenceTransformer()"
        )
        with _silence_io():
            model = SentenceTransformer(self._model_name)
        _embed_trace("_load SentenceTransformer constructed; reading dimension")
        dim = model.get_sentence_embedding_dimension()
        if dim is None:
            raise EmbeddingError(f"model {self._model_name} reported no embedding dimension")
        self._model = model
        self._dim = int(dim)
        _embed_trace(f"_load complete dim={self._dim}")

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
        _embed_trace(f"embed enter n={len(texts)} model_loaded={self._model is not None}")
        if self._model is None:
            self._load()
        if self._model is None:  # pragma: no cover — _load guarantees this
            raise EmbeddingError("model still None after _load — provider is in a broken state")
        try:
            _embed_trace("embed entering encode")
            with _silence_io():
                vectors = self._model.encode(  # type: ignore[attr-defined]
                    list(texts),
                    normalize_embeddings=True,
                    convert_to_numpy=True,
                )
            _embed_trace(f"embed encode complete n_vecs={len(vectors)}")
        except Exception as exc:
            _embed_trace(f"embed encode FAILED {type(exc).__name__}: {exc}")
            raise EmbeddingError(f"sentence-transformers encode failed: {exc}") from exc
        return [[float(x) for x in row] for row in vectors]


def _embed_trace(message: str) -> None:
    """Best-effort diagnostic trace into the MCP server log.

    Embedder code can be reached from many call paths (CLI, MCP server,
    direct Python). Only the MCP server has a log file; in other
    contexts, fall through silently. We reuse the MCP server's
    ``_trace`` helper to keep one timeline across the whole stack.
    """
    try:
        from cairntir.mcp.server import _trace as _mcp_trace

        _mcp_trace(f"embed: {message}")
    except (ImportError, OSError):
        return


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
