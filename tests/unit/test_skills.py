"""Unit tests for the skill loader."""

from __future__ import annotations

import pytest

from cairntir.errors import SkillError
from cairntir.skills import available_skills, load_skill


def test_three_skills_are_bundled() -> None:
    assert available_skills() == frozenset({"crucible", "quality", "reason"})


@pytest.mark.parametrize("name", ["crucible", "quality", "reason"])
def test_load_skill_returns_nonempty_markdown(name: str) -> None:
    text = load_skill(name)
    assert text.startswith("---")
    assert f"name: {name}" in text
    assert len(text) > 500


def test_load_skill_unknown_raises() -> None:
    with pytest.raises(SkillError):
        load_skill("nope")
