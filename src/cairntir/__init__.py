"""Cairntir — memory-first reasoning layer for Claude Code.

Cairntir stores verbatim drawers of memory in a wing/room taxonomy
backed by sqlite-vec, exposes a 4-layer retrieval model, and provides
three skills (crucible, quality, reason) over MCP. Its mission is to
kill cross-chat AI amnesia.

## The v1.0 contract

At v1.0 this package's ``__init__`` exposes **only** the stable seam:

* **Protocols** — :class:`Store`, :class:`EmbeddingProvider`, and the
  four reason-loop ports (:class:`HypothesisProposer`,
  :class:`ExperimentRunner`, :class:`BeliefStore`,
  :class:`MemoryGateway`).
* **Frozen value types** — :class:`Drawer`, :class:`Layer`,
  :class:`Hypothesis`, :class:`Experiment`, :class:`Outcome`,
  :class:`BeliefUpdate`.
* **Typed exceptions** — everything defined in
  :mod:`cairntir.errors`, plus :class:`CairntirDeprecationWarning`.
* ``__version__``.

Concrete implementations — ``DrawerStore``, ``HashEmbeddingProvider``,
``SentenceTransformerProvider``, ``Retriever``, ``ReasonLoop`` — live
under :mod:`cairntir.impl` and reserve the right to change. The public
surface here is the thing you depend on if you want your code to
survive Cairntir's internal refactors.

See ``docs/manifesto.md`` for the why and ``docs/concept.md`` for the
what.
"""

from __future__ import annotations

from cairntir.contracts import Store
from cairntir.errors import (
    CairntirDeprecationWarning,
    CairntirError,
    ConfigError,
    EmbeddingError,
    ExternalUrlError,
    MCPError,
    MemoryStoreError,
    PortableFormatError,
    RetrievalError,
    SkillError,
    TaxonomyError,
)
from cairntir.memory.embeddings import EmbeddingProvider
from cairntir.memory.taxonomy import Drawer, Layer
from cairntir.reason.model import BeliefUpdate, Experiment, Hypothesis, Outcome
from cairntir.reason.ports import (
    BeliefStore,
    ExperimentRunner,
    HypothesisProposer,
    MemoryGateway,
)

__version__ = "1.0.1"

__all__ = [
    "BeliefStore",
    "BeliefUpdate",
    "CairntirDeprecationWarning",
    "CairntirError",
    "ConfigError",
    "Drawer",
    "EmbeddingError",
    "EmbeddingProvider",
    "Experiment",
    "ExperimentRunner",
    "ExternalUrlError",
    "Hypothesis",
    "HypothesisProposer",
    "Layer",
    "MCPError",
    "MemoryGateway",
    "MemoryStoreError",
    "Outcome",
    "PortableFormatError",
    "RetrievalError",
    "SkillError",
    "Store",
    "TaxonomyError",
    "__version__",
]
