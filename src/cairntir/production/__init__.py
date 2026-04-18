"""Concrete adapters that wire the pure Reason loop to the real world — v1.1.

Where :mod:`cairntir.reason` is the library seam — four protocol ports
with a zero-import loop — this module is the production wiring. Four
stdlib-only classes:

* :class:`StoreBackedMemory` — implements
  :class:`~cairntir.reason.MemoryGateway` over any :class:`cairntir.Store`.
* :class:`StoreBackedBeliefs` — implements
  :class:`~cairntir.reason.BeliefStore` over any :class:`cairntir.Store`.
* :class:`NullRunner` — a zero-cost
  :class:`~cairntir.reason.ExperimentRunner` that records a caller-supplied
  verdict. Useful for recipes where the "experiment" is a human reading
  the output.
* :class:`ManualProposer` — a
  :class:`~cairntir.reason.HypothesisProposer` that returns a hypothesis
  the caller built itself. The Reason loop is a discipline for
  structuring predictions — the claim and predicted outcome come from
  wherever you like (a human at a terminal, an LLM session that is
  *already running* outside Cairntir, a file on disk, a local Gemma).

No network calls. No external APIs. No billed tokens. If you want to
wire a local inference engine (Gemma 4 via llama.cpp is the path on
the roadmap), build a proposer that implements
:class:`~cairntir.reason.HypothesisProposer` and pass it in — the
library does not care.
"""

from __future__ import annotations

from cairntir.production.adapters import (
    ManualProposer,
    NullRunner,
    StoreBackedBeliefs,
    StoreBackedMemory,
)

__all__ = [
    "ManualProposer",
    "NullRunner",
    "StoreBackedBeliefs",
    "StoreBackedMemory",
]
