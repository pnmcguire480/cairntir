"""Agent Memory — per-skill self-memory wings (v1.1+).

Cairntir's three skills (crucible, quality, reason) each get their own
*reserved wing* under the ``agent:`` prefix. Every skill invocation —
whether through the recipe runner or the MCP backend — leaves a
self-memory drawer in its agent wing recording the case, what was
reasoned about, which originating wing it came from, and a pointer
back to the skill marker drawer in the project wing.

The compounding effect: after a skill has been invoked many times in
the same originating wing, prior cases are visible to the next
invocation. Crucible recalls assumptions it has already stress-tested.
Quality recalls patterns that earn ship-it vs block verdicts. Reason
recalls rabbit holes it has already gone down.

This module introduces no new primitives. It is convention-as-code on
top of the existing :class:`~cairntir.reason.MemoryGateway` surface
that v1.0 already shipped. Per the v1.6 plan: *"Cairntir eating its
own dog food using only the memory + recipe surface v1.0 already
shipped."*

Reserved wings:

* ``agent:crucible`` — Crucible's self-memory.
* ``agent:quality`` — Quality's self-memory.
* ``agent:reason`` — Reason's self-memory.

Drawer convention:

* ``wing`` = ``agent:<skill>`` (e.g. ``agent:crucible``).
* ``room`` = the originating wing (so ``agent:crucible/cairntir``
  collects every Crucible run that targeted the cairntir project).
* ``layer`` = ``ON_DEMAND`` so prior cases surface only when relevant.
* ``metadata`` carries ``source = "skill.<name>"``,
  ``skill_marker_id`` = the marker drawer in the project wing,
  ``originating_wing`` and ``originating_room`` for reverse lookup.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from cairntir.memory.taxonomy import Drawer, Layer
from cairntir.prompt_safety import EVIDENCE_BOUNDARY, assess_memory_content

if TYPE_CHECKING:
    from cairntir.reason.ports import MemoryGateway

# Skills that have agent memory wings reserved. Add a name here only
# when there is a concrete plan for what that skill will record. The
# v1.6 plan calls out crucible / quality / reason; nothing else.
_AGENT_SKILLS = frozenset({"crucible", "quality", "reason"})


def agent_wing_for(skill_name: str) -> str:
    """Return the reserved agent wing identifier for ``skill_name``.

    Raises :class:`ValueError` if the skill is not one of the reserved
    set. Other tools that want to record skill-like activity should
    use a normal project wing rather than expanding the agent prefix.
    """
    if skill_name not in _AGENT_SKILLS:
        raise ValueError(
            f"no agent wing for skill {skill_name!r}; reserved skills are {sorted(_AGENT_SKILLS)}"
        )
    return f"agent:{skill_name}"


def is_agent_skill(skill_name: str) -> bool:
    """Return True when ``skill_name`` has a reserved agent wing."""
    return skill_name in _AGENT_SKILLS


def record_skill_invocation(
    memory: MemoryGateway,
    *,
    skill_name: str,
    originating_wing: str,
    originating_room: str,
    skill_marker_id: int,
    summary: str,
    metadata: dict[str, Any] | None = None,
) -> int:
    """Write a self-memory drawer to the skill's agent wing.

    Returns the new drawer's id. The drawer's ``room`` is the
    originating wing — one room per project — so a Crucible run on the
    cairntir project lands in ``agent:crucible/cairntir``, while one
    on stars-2026 lands in ``agent:crucible/stars-2026``.

    The summary is the verbatim text captured at invocation time
    (typically the question + key inputs, or the proposer's drafted
    claim if reason). What the *user/LLM concluded* is a separate
    drawer the caller writes through the normal remember path; the
    invocation drawer records that the case was opened.
    """
    if not is_agent_skill(skill_name):
        raise ValueError(
            f"skill {skill_name!r} has no reserved agent wing; cannot record invocation"
        )

    # Identifier validators reject empty strings; the skill should
    # always pass a non-empty originating wing/room. Surface the
    # contract violation loudly rather than producing a malformed
    # drawer.
    if not originating_wing or not originating_room:
        raise ValueError(
            "originating_wing and originating_room must both be non-empty "
            f"to record a skill invocation; got "
            f"wing={originating_wing!r} room={originating_room!r}"
        )

    drawer = Drawer(
        wing=agent_wing_for(skill_name),
        room=originating_wing,
        content=summary,
        layer=Layer.ON_DEMAND,
        metadata={
            **(metadata or {}),
            "source": f"skill.{skill_name}",
            "skill_marker_id": skill_marker_id,
            "originating_wing": originating_wing,
            "originating_room": originating_room,
        },
    )
    return memory.remember(drawer)


def recall_skill_history(
    memory: MemoryGateway,
    *,
    skill_name: str,
    originating_wing: str,
    limit: int = 3,
) -> list[Drawer]:
    """Return the most recent prior invocations of ``skill_name`` in ``originating_wing``.

    Most-recent-first (delegates to :meth:`MemoryGateway.list_by`).
    Returns ``[]`` if the agent wing has no entries for that
    originating wing — either because the skill has never been
    invoked there, or because Agent Memory was disabled at the time
    of past runs. Either way, callers that fold the result into a
    skill prompt should handle the empty case as "no prior context."
    """
    if not is_agent_skill(skill_name):
        # Non-agent skills simply have no history — return empty
        # rather than raise. This lets the recipe runner call
        # recall_skill_history unconditionally without first checking
        # is_agent_skill, simplifying its hot path.
        return []
    return memory.list_by(
        wing=agent_wing_for(skill_name),
        room=originating_wing,
        limit=limit,
    )


def format_history_for_prompt(history: list[Drawer]) -> str:
    """Render a list of prior cases as markdown for inclusion in a skill prompt.

    Returns an empty string when ``history`` is empty so callers can
    safely concatenate the result without checking length.
    """
    if not history:
        return ""
    lines = ["## Prior cases (most recent first)", "", EVIDENCE_BOUNDARY]
    for drawer in history:
        assessment = assess_memory_content(drawer.content)
        lines.append(
            json.dumps(
                {
                    "drawer_id": drawer.id,
                    "created_at": drawer.created_at.date().isoformat(),
                    "content": drawer.content.strip()[:200],
                    "instruction_authority": "none",
                    "suspicious": assessment.suspicious,
                    "security_signals": list(assessment.signals),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    lines.append("")
    return "\n".join(lines)
