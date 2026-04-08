"""Three skills: crucible, quality, reason.

Each skill is a markdown prompt shipped alongside this package. The
:func:`load_skill` helper reads one by name; the MCP backend uses it to
return skill text when the Crucible or Quality tools are invoked.
"""

from __future__ import annotations

from importlib.resources import files
from typing import Final

from cairntir.errors import SkillError

_SKILL_NAMES: Final[frozenset[str]] = frozenset({"crucible", "quality", "reason"})


def available_skills() -> frozenset[str]:
    """Return the set of bundled skill names."""
    return _SKILL_NAMES


def load_skill(name: str) -> str:
    """Return the verbatim markdown text of the named skill.

    Args:
        name: One of ``"crucible"``, ``"quality"``, or ``"reason"``.

    Raises:
        SkillError: if ``name`` is not a bundled skill or the file is missing.
    """
    if name not in _SKILL_NAMES:
        raise SkillError(f"unknown skill {name!r}; available: {sorted(_SKILL_NAMES)}")
    try:
        resource = files("cairntir.skills").joinpath(f"{name}.md")
        return resource.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        raise SkillError(f"failed to load skill {name!r}: {exc}") from exc
