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
    ``predicted_outcome`` held. ``delta`` is optional surprise evidence
    about how reality differed, independent of that verdict: a prediction
    may hold through an unexpected route. The loop does not second-guess
    either judgement, but it validates that the outcome is bound to the
    hypothesis it committed.
    """

    experiment: Experiment
    observed: str
    success: bool
    delta: str = ""


@dataclass(frozen=True)
class BeliefUpdate:
    """The record of what a single Reason step changed in memory.

    ``prediction_id`` is the drawer that originally recorded the
    hypothesis. ``observation_id`` is the follow-up drawer that
    supersedes it with the real outcome. ``mass_change`` is the
    scalar the belief store was nudged by: positive on success,
    negative on failure, zero if the loop decided to abstain.
    ``delta`` is the free-form surprise note. It is independent of
    the verdict: a prediction may hold through an unexpected path.
    """

    prediction_id: int
    observation_id: int
    mass_change: float
    delta: str
