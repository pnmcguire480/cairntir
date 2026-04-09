"""Frozen value types that flow through the Reason loop — v0.6.

These are the shapes every adapter agrees on. They are deliberately
small, frozen, and stdlib-only. No pydantic, no sqlite, no LLM text —
the types carry the *meaning* of a reasoning step, and the adapters
decide how that meaning lands in the real world.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Hypothesis:
    """A falsifiable claim the loop is about to commit to.

    Every Reason step begins by writing one of these to memory as a
    prediction drawer (v0.2 contract). The ``predicted_outcome`` is
    what the next observation will be measured against; if it turns
    out wrong, the surprise is the load-bearing learning signal
    (v0.4).
    """

    claim: str
    predicted_outcome: str
    wing: str
    room: str


@dataclass(frozen=True)
class Experiment:
    """A description of how a hypothesis will be tested.

    This is intentionally just the hypothesis plus a human-readable
    protocol. Production runners may encode this as code, a prompt,
    or a manual checklist — the library does not care.
    """

    hypothesis: Hypothesis
    description: str


@dataclass(frozen=True)
class Outcome:
    """The observation an :class:`ExperimentRunner` produced.

    ``success`` is the runner's verdict on whether the hypothesis's
    ``predicted_outcome`` held. The loop does not second-guess it —
    that judgement is the runner's job and the test of whether the
    runner is trustworthy is whether it calls successes correctly.
    """

    experiment: Experiment
    observed: str
    success: bool


@dataclass(frozen=True)
class BeliefUpdate:
    """The record of what a single Reason step changed in memory.

    ``prediction_id`` is the drawer that originally recorded the
    hypothesis. ``observation_id`` is the follow-up drawer that
    supersedes it with the real outcome. ``mass_change`` is the
    scalar the belief store was nudged by: positive on success,
    negative on failure, zero if the loop decided to abstain.
    ``delta`` is the free-form surprise note — empty when the
    prediction held exactly, populated when the observation
    diverged.
    """

    prediction_id: int
    observation_id: int
    mass_change: float
    delta: str
