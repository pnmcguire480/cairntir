"""Protocol ports for the Reason loop — v0.6.

Four protocols. That is the whole library seam between the Reason
loop and the outside world:

* :class:`HypothesisProposer` turns a question into a hypothesis. In
  production this is almost always LLM-backed; in tests it is a
  handwritten fake that returns a canned claim.
* :class:`ExperimentRunner` carries out the experiment and returns
  an outcome. In production this may run code, prompt a model, or
  ask a human; in tests it is a dict lookup.
* :class:`BeliefStore` is how the loop reinforces or weakens a
  drawer's belief mass. :class:`~cairntir.memory.store.DrawerStore`
  already implements this shape; the protocol lets tests swap in a
  counter-backed fake.
* :class:`MemoryGateway` is the loop's narrow view of memory: it
  remembers new drawers and recalls past ones. The loop never sees
  a :class:`~cairntir.memory.store.DrawerStore` directly.

All four are runtime-checkable protocols so tests can pass duck-typed
objects without inheritance ceremony. None of them import sqlite,
networks, or LLMs — that's the whole point of v0.6.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any, Protocol, runtime_checkable

from cairntir.durability import WorkflowExecution
from cairntir.memory.taxonomy import Drawer
from cairntir.reason.model import Hypothesis, Outcome


@runtime_checkable
class HypothesisProposer(Protocol):
    """Propose a falsifiable hypothesis for a question inside a wing/room."""

    def propose(self, *, question: str, wing: str, room: str) -> Hypothesis:
        """Return a hypothesis with a claim and a predicted outcome.

        Implementations must produce a hypothesis whose
        ``predicted_outcome`` is non-empty and specific enough that
        an :class:`ExperimentRunner` can judge success or failure
        without further prompting.
        """
        ...


@runtime_checkable
class ExperimentRunner(Protocol):
    """Carry out an experiment and return an observed outcome."""

    def run(self, hypothesis: Hypothesis) -> Outcome:
        """Execute the test and return the observed :class:`Outcome`."""
        ...


@runtime_checkable
class BeliefStore(Protocol):
    """Raise or lower a drawer's belief mass.

    Both methods return the new mass after the adjustment. The loop
    records the signed adjustment it requested in
    :class:`~cairntir.reason.model.BeliefUpdate`; callers that need the
    clamped post-update mass can inspect the store.
    """

    def reinforce(self, drawer_id: int, *, amount: float) -> float:
        """Raise belief mass by ``amount``. Return the new mass."""
        ...

    def weaken(self, drawer_id: int, *, amount: float) -> float:
        """Lower belief mass by ``amount`` (clamped at 0). Return the new mass."""
        ...


@runtime_checkable
class MemoryGateway(Protocol):
    """Narrow view of memory the loop needs: remember + recall + list_by."""

    def remember(self, drawer: Drawer) -> int:
        """Persist a drawer and return its newly assigned id."""
        ...

    def recall(
        self,
        query: str,
        *,
        wing: str,
        room: str | None = None,
        limit: int = 5,
    ) -> list[Drawer]:
        """Return drawers relevant to ``query`` in ``wing``, belief-weighted if possible."""
        ...

    def list_by(
        self,
        *,
        wing: str | None = None,
        room: str | None = None,
        limit: int = 10,
    ) -> list[Drawer]:
        """Return drawers in ``wing``/``room`` ordered most-recent-first.

        Non-semantic — pure metadata filter. Used by Agent Memory
        (v1.1+) to walk a skill's prior invocations in the
        ``agent:<skill>`` wing for the originating project, where
        recency matters more than relevance.
        """
        ...


@runtime_checkable
class DurableMemoryGateway(MemoryGateway, Protocol):
    """Optional production extension for atomic, idempotent memory workflows."""

    def atomic(self) -> AbstractContextManager[None]:
        """Return a nestable unit of work spanning memory and beliefs."""
        ...

    def execute_once(
        self,
        *,
        idempotency_key: str,
        operation: str,
        request: dict[str, Any],
        action: Callable[[], dict[str, Any]],
    ) -> WorkflowExecution:
        """Execute ``action`` once and replay its committed result on retry."""
        ...


@runtime_checkable
class LearningMemoryGateway(MemoryGateway, Protocol):
    """Optional hook that derives conservative patterns after an episode."""

    def reflect(self, *, wing: str) -> list[int]:
        """Return discovery drawer ids proposed from repeated episodes."""
        ...
