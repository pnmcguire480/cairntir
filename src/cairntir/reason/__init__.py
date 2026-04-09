"""Reason loop through clean ports — v0.6.

This package is the *library* shape of the Reason skill: a testable loop
over four ports — :class:`HypothesisProposer`, :class:`ExperimentRunner`,
:class:`BeliefStore`, and :class:`MemoryGateway` — that can be exercised
without LLMs, networks, or sqlite. Production wiring (real proposers
backed by Claude, real runners executing code, real stores talking to
sqlite-vec) lives *outside* the library in adapters the user provides.

This is the round table's discipline applied to code layout: the loop
is pure, the substrate is pluggable, and the unit tests never require
anything heavier than a dictionary.
"""

from __future__ import annotations

from cairntir.reason.loop import ReasonLoop
from cairntir.reason.model import BeliefUpdate, Experiment, Hypothesis, Outcome
from cairntir.reason.ports import (
    BeliefStore,
    ExperimentRunner,
    HypothesisProposer,
    MemoryGateway,
)

__all__ = [
    "BeliefStore",
    "BeliefUpdate",
    "Experiment",
    "ExperimentRunner",
    "Hypothesis",
    "HypothesisProposer",
    "MemoryGateway",
    "Outcome",
    "ReasonLoop",
]
