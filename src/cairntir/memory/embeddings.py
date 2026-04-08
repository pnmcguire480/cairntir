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

import hashlib
import math
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from cairntir.errors import EmbeddingError

if TYPE_CHECKING:
    from collections.abc import Sequence


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
        assert self._dim is not None  # noqa: S101 — invariant after _load
        return self._dim

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed texts using the underlying sentence-transformers model."""
        if self._model is None:
            self._load()
        assert self._model is not None  # noqa: S101
        try:
            vectors = self._model.encode(  # type: ignore[attr-defined]
                list(texts),
                normalize_embeddings=True,
                convert_to_numpy=True,
            )
        except Exception as exc:
            raise EmbeddingError(f"sentence-transformers encode failed: {exc}") from exc
        return [[float(x) for x in row] for row in vectors]
