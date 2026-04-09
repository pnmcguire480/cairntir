"""Memory subsystem: sqlite-vec store, wing/room/drawer taxonomy, 4-layer retrieval.

See :mod:`cairntir.memory.taxonomy` for the data model, :mod:`cairntir.memory.store`
for persistence, :mod:`cairntir.memory.embeddings` for embedding providers, and
:mod:`cairntir.memory.retrieval` for the 4-layer loader.
"""

from __future__ import annotations

from cairntir.memory.consolidate import (
    Contradiction,
    consolidate_room,
    demote_stale,
    detect_contradictions,
)
from cairntir.memory.embeddings import (
    EmbeddingProvider,
    HashEmbeddingProvider,
    SentenceTransformerProvider,
)
from cairntir.memory.retrieval import RetrievalResult, Retriever
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer, Layer

__all__ = [
    "Contradiction",
    "Drawer",
    "DrawerStore",
    "EmbeddingProvider",
    "HashEmbeddingProvider",
    "Layer",
    "RetrievalResult",
    "Retriever",
    "SentenceTransformerProvider",
    "consolidate_room",
    "demote_stale",
    "detect_contradictions",
]
