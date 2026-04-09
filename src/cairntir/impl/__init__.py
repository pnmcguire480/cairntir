"""Concrete implementations of Cairntir's protocol surface — reserved-right-to-change.

Anything under ``cairntir.impl.*`` is a working concrete backend but is
*not* part of the stable v1.0 contract. The stable contract is the
Protocol surface in :mod:`cairntir` itself (see :mod:`cairntir.contracts`
and the curated ``__init__`` re-exports). Importing from here is
allowed and supported — just know that internal refactors can rename,
reshape, or relocate these modules between minor releases without a
deprecation warning.

If you want a surface that cannot shift under you, depend on the
protocols. If you want the concrete default, depend on these.
"""

from __future__ import annotations

from cairntir.memory.embeddings import (
    HashEmbeddingProvider,
    SentenceTransformerProvider,
)
from cairntir.memory.retrieval import RetrievalResult, Retriever
from cairntir.memory.store import SCHEMA_VERSION, DrawerStore
from cairntir.reason.loop import ReasonLoop

__all__ = [
    "SCHEMA_VERSION",
    "DrawerStore",
    "HashEmbeddingProvider",
    "ReasonLoop",
    "RetrievalResult",
    "Retriever",
    "SentenceTransformerProvider",
]
