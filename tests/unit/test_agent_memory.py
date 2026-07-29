"""Unit tests for Agent Memory — per-skill self-memory wings (v1.1+)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.production.adapters import (
    NullRunner,
    StoreBackedBeliefs,
    StoreBackedMemory,
)
from cairntir.reason.model import Hypothesis
from cairntir.recipes import RecipeContract, RecipeRunner, load_recipe
from cairntir.skills.memory import (
    agent_wing_for,
    format_history_for_prompt,
    is_agent_skill,
    recall_skill_history,
    record_skill_invocation,
)

# --------- helpers reused from test_recipes ---------------------------


@dataclass
class _StubProposer:
    hypothesis: Hypothesis
    calls: list[dict[str, str]] = field(default_factory=list)

    def propose(self, *, question: str, wing: str, room: str) -> Hypothesis:
        self.calls.append({"question": question, "wing": wing, "room": room})
        return self.hypothesis


def _write_recipe(tmp_path: Path, *, skills: list[str]) -> RecipeContract:
    skills_toml = ", ".join(f'"{s}"' for s in skills)
    body = f"""
[recipe]
name = "test-agent-recipe"
description = "Agent Memory exerciser"
version = "0.1"
output_wing = "test-wing"
skills = [{skills_toml}]

[input.topic]
type = "string"
required = true
description = "thing"
"""
    path = tmp_path / "recipe.toml"
    path.write_text(body, encoding="utf-8")
    return load_recipe(path)


# --------- pure helpers ------------------------------------------------


def test_agent_wing_for_returns_reserved_format() -> None:
    assert agent_wing_for("crucible") == "agent:crucible"
    assert agent_wing_for("quality") == "agent:quality"
    assert agent_wing_for("reason") == "agent:reason"


def test_agent_wing_for_rejects_unknown_skill() -> None:
    with pytest.raises(ValueError, match="reserved skills"):
        agent_wing_for("invented")


def test_is_agent_skill() -> None:
    assert is_agent_skill("crucible")
    assert is_agent_skill("quality")
    assert is_agent_skill("reason")
    assert not is_agent_skill("invented")


def test_taxonomy_accepts_colon_in_wing() -> None:
    """The relaxed regex must accept the agent: prefix."""
    drawer = Drawer(
        wing="agent:crucible",
        room="cairntir",
        content="self-memory smoke test",
    )
    assert drawer.wing == "agent:crucible"


def test_format_history_empty_returns_empty_string() -> None:
    assert format_history_for_prompt([]) == ""


def test_format_history_renders_recent_cases(tmp_path: Path) -> None:
    store = DrawerStore(tmp_path / "h.db", HashEmbeddingProvider(dimension=32))
    drawers = [
        store.add(
            Drawer(
                wing="agent:crucible",
                room="cairntir",
                content=f"prior case #{i}",
            )
        )
        for i in range(2)
    ]
    rendered = format_history_for_prompt(drawers)
    assert "Prior cases" in rendered
    assert "prior case #0" in rendered
    assert "prior case #1" in rendered


# --------- record + recall ---------------------------------------------


def test_record_and_recall_roundtrip(tmp_path: Path) -> None:
    store = DrawerStore(tmp_path / "rr.db", HashEmbeddingProvider(dimension=32))
    memory = StoreBackedMemory(store=store)

    invocation_id = record_skill_invocation(
        memory,
        skill_name="crucible",
        originating_wing="cairntir",
        originating_room="journey",
        skill_marker_id=42,
        summary="stress test of fastembed default",
    )

    assert invocation_id > 0
    drawer = store.get(invocation_id)
    assert drawer is not None
    assert drawer.wing == "agent:crucible"
    assert drawer.room == "cairntir"
    assert drawer.metadata["source"] == "skill.crucible"
    assert drawer.metadata["skill_marker_id"] == 42
    assert drawer.metadata["originating_wing"] == "cairntir"

    history = recall_skill_history(
        memory, skill_name="crucible", originating_wing="cairntir", limit=10
    )
    assert len(history) == 1
    assert history[0].id == invocation_id


def test_recall_only_returns_matching_originating_wing(tmp_path: Path) -> None:
    store = DrawerStore(tmp_path / "scope.db", HashEmbeddingProvider(dimension=32))
    memory = StoreBackedMemory(store=store)

    record_skill_invocation(
        memory,
        skill_name="crucible",
        originating_wing="cairntir",
        originating_room="journey",
        skill_marker_id=1,
        summary="cairntir case",
    )
    record_skill_invocation(
        memory,
        skill_name="crucible",
        originating_wing="stars-2026",
        originating_room="phase-2",
        skill_marker_id=2,
        summary="stars-2026 case",
    )

    cairntir_history = recall_skill_history(
        memory, skill_name="crucible", originating_wing="cairntir"
    )
    assert len(cairntir_history) == 1
    assert "cairntir case" in cairntir_history[0].content

    stars_history = recall_skill_history(
        memory, skill_name="crucible", originating_wing="stars-2026"
    )
    assert len(stars_history) == 1
    assert "stars-2026 case" in stars_history[0].content


def test_record_rejects_non_agent_skill(tmp_path: Path) -> None:
    store = DrawerStore(tmp_path / "x.db", HashEmbeddingProvider(dimension=32))
    memory = StoreBackedMemory(store=store)
    with pytest.raises(ValueError, match="no reserved agent wing"):
        record_skill_invocation(
            memory,
            skill_name="invented",
            originating_wing="cairntir",
            originating_room="journey",
            skill_marker_id=1,
            summary="x",
        )


def test_recall_returns_empty_for_non_agent_skill(tmp_path: Path) -> None:
    """Non-agent skills don't raise — they have no history by design."""
    store = DrawerStore(tmp_path / "x.db", HashEmbeddingProvider(dimension=32))
    memory = StoreBackedMemory(store=store)
    assert recall_skill_history(memory, skill_name="invented", originating_wing="cairntir") == []


def test_record_rejects_empty_originating_wing(tmp_path: Path) -> None:
    store = DrawerStore(tmp_path / "x.db", HashEmbeddingProvider(dimension=32))
    memory = StoreBackedMemory(store=store)
    with pytest.raises(ValueError, match="non-empty"):
        record_skill_invocation(
            memory,
            skill_name="crucible",
            originating_wing="",
            originating_room="journey",
            skill_marker_id=1,
            summary="x",
        )


# --------- recipe runner integration -----------------------------------


def test_recipe_runner_writes_agent_drawer_for_crucible(tmp_path: Path) -> None:
    contract = _write_recipe(tmp_path, skills=["crucible"])
    store = DrawerStore(tmp_path / "rec.db", HashEmbeddingProvider(dimension=32))
    runner = RecipeRunner(
        memory=StoreBackedMemory(store=store),
        beliefs=StoreBackedBeliefs(store=store),
        proposer=_StubProposer(
            hypothesis=Hypothesis(
                claim="c", predicted_outcome="p", wing="test-wing", room="test-agent-recipe"
            )
        ),
        runner=NullRunner(observed="o", success=True),
    )
    runner.run(contract, {"topic": "first stress test"})

    crucible_drawers = store.list_by(wing="agent:crucible", limit=10)
    assert len(crucible_drawers) == 1
    drawer = crucible_drawers[0]
    assert drawer.room == "test-wing"
    assert drawer.metadata["originating_wing"] == "test-wing"
    assert drawer.metadata["recipe"] == "test-agent-recipe"


def test_recipe_runner_includes_prior_cases_in_skill_marker(tmp_path: Path) -> None:
    """A second invocation surfaces the first invocation's content in the marker."""
    contract = _write_recipe(tmp_path, skills=["crucible"])
    store = DrawerStore(tmp_path / "rec2.db", HashEmbeddingProvider(dimension=32))
    runner = RecipeRunner(
        memory=StoreBackedMemory(store=store),
        beliefs=StoreBackedBeliefs(store=store),
        proposer=_StubProposer(
            hypothesis=Hypothesis(
                claim="c", predicted_outcome="p", wing="test-wing", room="test-agent-recipe"
            )
        ),
        runner=NullRunner(observed="o", success=True),
    )

    first = runner.run(contract, {"topic": "first stress test"})
    second = runner.run(contract, {"topic": "second stress test"})

    second_marker_id = second.skill_drawer_ids["crucible"][0]
    second_marker = store.get(second_marker_id)
    assert second_marker is not None
    # The second marker's content includes the first invocation's
    # summary under the Prior cases section.
    assert "Prior cases" in second_marker.content
    assert "first stress test" in second_marker.content
    # The first marker had no prior cases.
    first_marker_id = first.skill_drawer_ids["crucible"][0]
    first_marker = store.get(first_marker_id)
    assert first_marker is not None
    assert "Prior cases" not in first_marker.content


def test_recipe_runner_writes_agent_drawer_for_reason(tmp_path: Path) -> None:
    contract = _write_recipe(tmp_path, skills=["reason"])
    store = DrawerStore(tmp_path / "rr.db", HashEmbeddingProvider(dimension=32))
    runner = RecipeRunner(
        memory=StoreBackedMemory(store=store),
        beliefs=StoreBackedBeliefs(store=store),
        proposer=_StubProposer(
            hypothesis=Hypothesis(
                claim="reason claim",
                predicted_outcome="reason predicted",
                wing="test-wing",
                room="test-agent-recipe",
            )
        ),
        runner=NullRunner(observed="reason observed", success=True),
    )
    runner.run(contract, {"topic": "reason exercise"})

    reason_drawers = store.list_by(wing="agent:reason", limit=10)
    assert len(reason_drawers) == 1
    drawer = reason_drawers[0]
    assert drawer.room == "test-wing"
    assert "reason exercise" in drawer.content
    assert drawer.metadata["originating_wing"] == "test-wing"


def test_agent_drawers_do_not_recurse_when_recipe_targets_agent_wing(
    tmp_path: Path,
) -> None:
    """If a recipe's output_wing is itself an agent wing, no agent drawer is written.

    Cairntir's memory is local; the agent: prefix is not a fractal.
    """
    body = """
[recipe]
name = "agent-targeting-recipe"
description = "Recipe that writes directly into an agent wing"
version = "0.1"
output_wing = "agent:reason"
skills = ["reason"]

[input.topic]
type = "string"
required = true
description = "thing"
"""
    path = tmp_path / "recipe.toml"
    path.write_text(body, encoding="utf-8")
    contract = load_recipe(path)

    store = DrawerStore(tmp_path / "fractal.db", HashEmbeddingProvider(dimension=32))
    runner = RecipeRunner(
        memory=StoreBackedMemory(store=store),
        beliefs=StoreBackedBeliefs(store=store),
        proposer=_StubProposer(
            hypothesis=Hypothesis(
                claim="c",
                predicted_outcome="p",
                wing="agent:reason",
                room="agent-targeting-recipe",
            )
        ),
        runner=NullRunner(observed="o", success=True),
    )
    runner.run(contract, {"topic": "agent-targeting"})

    # Only the recipe's own drawers exist in agent:reason — nothing
    # extra written by the agent-memory hook.
    reason_drawers = store.list_by(wing="agent:reason", limit=100)
    # A reason recipe writes: 1 seed + 2 reason drawers (prediction +
    # observation). No bonus self-memory drawer.
    assert len(reason_drawers) == 3
