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

from typing import Protocol, runtime_checkable

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
    uses the return value to compute the actual ``mass_change`` it
    records in a :class:`~cairntir.reason.model.BeliefUpdate`, so
    implementations that clamp at zero still communicate the real
    move to the caller.
    """

    def reinforce(self, drawer_id: int, *, amount: float) -> float:
        """Raise belief mass by ``amount``. Return the new mass."""
        ...

    def weaken(self, drawer_id: int, *, amount: float) -> float:
        """Lower belief mass by ``amount`` (clamped at 0). Return the new mass."""
        ...


@runtime_checkable
class MemoryGateway(Protocol):
    """Narrow view of memory the loop needs: remember + recall."""

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
