"""Unit tests for the v1.1 recipe runtime — contract loader + runner."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from cairntir.errors import CairntirError
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.production.adapters import (
    NullRunner,
    StoreBackedBeliefs,
    StoreBackedMemory,
)
from cairntir.reason.model import Hypothesis
from cairntir.recipes import (
    RecipeContract,
    RecipeError,
    RecipeRunner,
    discover_recipes,
    load_recipe,
    recipe_search_paths,
)

# --------- Fakes --------------------------------------------------------


@dataclass
class _StubProposer:
    """Returns a canned Hypothesis; records every call."""

    hypothesis: Hypothesis
    calls: list[dict[str, str]] = field(default_factory=list)

    def propose(self, *, question: str, wing: str, room: str) -> Hypothesis:
        self.calls.append({"question": question, "wing": wing, "room": room})
        return self.hypothesis


# --------- contract loader ---------------------------------------------


def _write_toml(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_load_recipe_happy_path(tmp_path: Path) -> None:
    toml = _write_toml(
        tmp_path / "recipe.toml",
        """
[recipe]
name = "signal-reader"
description = "structural analysis"
version = "0.1"
output_wing = "signals"
skills = ["reason", "crucible"]

[input.summary]
type = "string"
required = true
description = "the structural take"
""",
    )
    contract = load_recipe(toml)
    assert isinstance(contract, RecipeContract)
    assert contract.name == "signal-reader"
    assert contract.output_wing == "signals"
    assert contract.skills == ("reason", "crucible")
    assert contract.required_input_names() == frozenset({"summary"})
    assert contract.input_spec("summary") is not None
    assert contract.input_spec("missing") is None
    assert contract.source_path == toml.resolve()


def test_load_recipe_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(RecipeError, match="does not exist"):
        load_recipe(tmp_path / "nope.toml")


def test_load_recipe_malformed_toml_raises(tmp_path: Path) -> None:
    toml = _write_toml(tmp_path / "recipe.toml", "not = valid = toml")
    with pytest.raises(RecipeError, match="not valid TOML"):
        load_recipe(toml)


def test_load_recipe_missing_recipe_section_raises(tmp_path: Path) -> None:
    toml = _write_toml(tmp_path / "recipe.toml", 'other = "section"')
    with pytest.raises(RecipeError, match=r"\[recipe\] section"):
        load_recipe(toml)


def test_load_recipe_missing_field_raises(tmp_path: Path) -> None:
    toml = _write_toml(
        tmp_path / "recipe.toml",
        """
[recipe]
name = "foo"
description = "bar"
version = "0.1"
# output_wing missing
skills = ["reason"]
""",
    )
    with pytest.raises(RecipeError, match="output_wing"):
        load_recipe(toml)


def test_load_recipe_unknown_skill_raises(tmp_path: Path) -> None:
    toml = _write_toml(
        tmp_path / "recipe.toml",
        """
[recipe]
name = "foo"
description = "bar"
version = "0.1"
output_wing = "signals"
skills = ["reason", "mystery"]
""",
    )
    with pytest.raises(RecipeError, match="unknown skill"):
        load_recipe(toml)


def test_load_recipe_empty_skills_raises(tmp_path: Path) -> None:
    toml = _write_toml(
        tmp_path / "recipe.toml",
        """
[recipe]
name = "foo"
description = "bar"
version = "0.1"
output_wing = "signals"
skills = []
""",
    )
    with pytest.raises(RecipeError, match="non-empty list"):
        load_recipe(toml)


def test_load_recipe_invalid_input_type_raises(tmp_path: Path) -> None:
    toml = _write_toml(
        tmp_path / "recipe.toml",
        """
[recipe]
name = "foo"
description = "bar"
version = "0.1"
output_wing = "signals"
skills = ["reason"]

[input.thing]
type = "bigint"
required = true
""",
    )
    with pytest.raises(RecipeError, match="type must be one of"):
        load_recipe(toml)


# --------- discovery ---------------------------------------------------


def test_discover_recipes_finds_signal_reader(tmp_path: Path) -> None:
    """The bundled signal-reader recipe.toml must load cleanly."""
    repo_root = Path(__file__).resolve().parents[2]
    search = [repo_root / "docs" / "recipes"]
    contracts = discover_recipes(search_paths=search)
    names = {c.name for c in contracts}
    assert "signal-reader" in names


def test_discover_recipes_skips_malformed_files(tmp_path: Path) -> None:
    # Good one
    _write_toml(
        tmp_path / "good" / "recipe.toml",
        """
[recipe]
name = "good"
description = "ok"
version = "0.1"
output_wing = "signals"
skills = ["reason"]
""",
    )
    # Bad one
    _write_toml(tmp_path / "bad" / "recipe.toml", "not valid toml")

    contracts = discover_recipes(search_paths=[tmp_path])
    names = {c.name for c in contracts}
    assert names == {"good"}


def test_recipe_search_paths_is_list_of_existing_dirs(tmp_path: Path) -> None:
    paths = recipe_search_paths()
    for p in paths:
        assert p.is_dir()


# --------- runner ------------------------------------------------------


def _make_contract(tmp_path: Path, *, skills: list[str]) -> RecipeContract:
    skills_toml = ", ".join(f'"{s}"' for s in skills)
    toml = _write_toml(
        tmp_path / "recipe.toml",
        f"""
[recipe]
name = "test-recipe"
description = "runner smoke test"
version = "0.1"
output_wing = "test-wing"
skills = [{skills_toml}]

[input.topic]
type = "string"
required = true
description = "thing to reason about"
""",
    )
    return load_recipe(toml)


def test_runner_validates_required_inputs(tmp_path: Path) -> None:
    contract = _make_contract(tmp_path, skills=["crucible"])
    store = DrawerStore(tmp_path / "r.db", HashEmbeddingProvider(dimension=32))
    runner = RecipeRunner(
        memory=StoreBackedMemory(store=store),
        beliefs=StoreBackedBeliefs(store=store),
        proposer=_StubProposer(
            hypothesis=Hypothesis(
                claim="c", predicted_outcome="p", wing="test-wing", room="test-recipe"
            )
        ),
        runner=NullRunner(observed="done", success=True),
    )
    with pytest.raises(CairntirError, match="missing required input"):
        runner.run(contract, {})


def test_runner_rejects_unknown_inputs(tmp_path: Path) -> None:
    contract = _make_contract(tmp_path, skills=["crucible"])
    store = DrawerStore(tmp_path / "r.db", HashEmbeddingProvider(dimension=32))
    runner = RecipeRunner(
        memory=StoreBackedMemory(store=store),
        beliefs=StoreBackedBeliefs(store=store),
        proposer=_StubProposer(
            hypothesis=Hypothesis(
                claim="c", predicted_outcome="p", wing="test-wing", room="test-recipe"
            )
        ),
        runner=NullRunner(observed="done", success=True),
    )
    with pytest.raises(CairntirError, match="unknown input"):
        runner.run(contract, {"topic": "x", "surprise": "y"})


def test_runner_writes_seed_and_crucible_drawer(tmp_path: Path) -> None:
    contract = _make_contract(tmp_path, skills=["crucible"])
    store = DrawerStore(tmp_path / "r.db", HashEmbeddingProvider(dimension=32))
    memory = StoreBackedMemory(store=store)
    runner = RecipeRunner(
        memory=memory,
        beliefs=StoreBackedBeliefs(store=store),
        proposer=_StubProposer(
            hypothesis=Hypothesis(
                claim="c", predicted_outcome="p", wing="test-wing", room="test-recipe"
            )
        ),
        runner=NullRunner(observed="done", success=True),
    )
    result = runner.run(contract, {"topic": "inference wall"})

    assert result.recipe_name == "test-recipe"
    assert result.output_wing == "test-wing"
    assert result.seed_drawer_id > 0
    assert "crucible" in result.skill_drawer_ids
    assert len(result.skill_drawer_ids["crucible"]) == 1

    # Seed drawer content captures the invocation + inputs.
    seed = store.get(result.seed_drawer_id)
    assert seed is not None
    assert "test-recipe" in seed.content
    assert "inference wall" in seed.content
    assert seed.metadata["kind"] == "seed"

    # Crucible marker drawer supersedes the seed and embeds skill text.
    crucible_id = result.skill_drawer_ids["crucible"][0]
    crucible_drawer = store.get(crucible_id)
    assert crucible_drawer is not None
    assert crucible_drawer.supersedes_id == result.seed_drawer_id
    assert "CRUCIBLE" in crucible_drawer.content.upper()


def test_runner_runs_reason_loop(tmp_path: Path) -> None:
    contract = _make_contract(tmp_path, skills=["reason"])
    store = DrawerStore(tmp_path / "r.db", HashEmbeddingProvider(dimension=32))
    proposer = _StubProposer(
        hypothesis=Hypothesis(
            claim="inference cost is the new wall",
            predicted_outcome="asian data centers win capex share in 12 months",
            wing="test-wing",
            room="test-recipe",
        )
    )
    recipe_runner = RecipeRunner(
        memory=StoreBackedMemory(store=store),
        beliefs=StoreBackedBeliefs(store=store),
        proposer=proposer,
        runner=NullRunner(observed="validated", success=True),
    )
    result = recipe_runner.run(contract, {"topic": "ai news event"})

    assert len(result.skill_drawer_ids["reason"]) == 2
    prediction_id, observation_id = result.skill_drawer_ids["reason"]
    prediction = store.get(prediction_id)
    observation = store.get(observation_id)
    assert prediction is not None and observation is not None
    assert prediction.claim == "inference cost is the new wall"
    assert observation.supersedes_id == prediction_id

    # Proposer saw the recipe-shaped question.
    assert len(proposer.calls) == 1
    assert "test-recipe" in proposer.calls[0]["question"]
    assert "ai news event" in proposer.calls[0]["question"]
