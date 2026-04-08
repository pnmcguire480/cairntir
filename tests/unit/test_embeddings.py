"""Unit tests for embedding providers."""

from __future__ import annotations

import math

import pytest

from cairntir.errors import EmbeddingError
from cairntir.memory.embeddings import EmbeddingProvider, HashEmbeddingProvider


def test_hash_embedder_is_deterministic() -> None:
    emb = HashEmbeddingProvider(dimension=32)
    a = emb.embed(["cairntir"])[0]
    b = emb.embed(["cairntir"])[0]
    assert a == b
    assert len(a) == 32


def test_hash_embedder_different_inputs_differ() -> None:
    emb = HashEmbeddingProvider(dimension=32)
    a, b = emb.embed(["one", "two"])
    assert a != b


def test_hash_embedder_vectors_are_unit_norm() -> None:
    emb = HashEmbeddingProvider(dimension=16)
    (vec,) = emb.embed(["anything"])
    norm = math.sqrt(sum(x * x for x in vec))
    assert math.isclose(norm, 1.0, rel_tol=1e-6)


def test_hash_embedder_rejects_bad_dimension() -> None:
    with pytest.raises(EmbeddingError):
        HashEmbeddingProvider(dimension=0)


def test_hash_embedder_satisfies_protocol() -> None:
    emb: EmbeddingProvider = HashEmbeddingProvider(dimension=8)
    assert emb.dimension == 8
    assert len(emb.embed(["x"])[0]) == 8
