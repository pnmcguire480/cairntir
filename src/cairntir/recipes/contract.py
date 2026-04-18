"""RecipeContract — declarative shape of a recipe loaded from ``recipe.toml``.

A contract is a frozen dataclass plus a loader. The loader raises a
:class:`RecipeError` on any problem: missing TOML, malformed schema,
unknown skills, type mismatches. No silent coercion.

The contract does not execute anything — :class:`~cairntir.recipes.runner.RecipeRunner`
is the executor. Keeping them separate means a user can ``cairntir
recipe list`` without instantiating adapters.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from cairntir.errors import CairntirError


class RecipeError(CairntirError):
    """Raised when a recipe contract is malformed or invalid."""


_VALID_SKILLS = frozenset({"crucible", "quality", "reason"})
_VALID_INPUT_TYPES = frozenset({"string", "url", "integer", "boolean"})


@dataclass(frozen=True)
class RecipeInputSpec:
    """Spec for a single input slot declared in ``recipe.toml``."""

    name: str
    type: str
    required: bool
    description: str


@dataclass(frozen=True)
class RecipeContract:
    """The parsed, validated contents of a ``recipe.toml`` file.

    A contract is immutable once loaded. ``source_path`` is the
    absolute path to the recipe.toml file itself so downstream tools
    can surface where a recipe came from.
    """

    name: str
    description: str
    version: str
    output_wing: str
    skills: tuple[str, ...]
    inputs: tuple[RecipeInputSpec, ...]
    source_path: Path | None = field(default=None)

    def required_input_names(self) -> frozenset[str]:
        """Return the set of required input slot names."""
        return frozenset(spec.name for spec in self.inputs if spec.required)

    def input_spec(self, name: str) -> RecipeInputSpec | None:
        """Return the spec for ``name`` or ``None`` if it is not declared."""
        for spec in self.inputs:
            if spec.name == name:
                return spec
        return None


def load_recipe(path: Path) -> RecipeContract:
    """Load and validate a ``recipe.toml`` file.

    Raises :class:`RecipeError` on any structural problem. The loader
    does not prompt, coerce, or default away missing fields — recipes
    are contracts and a contract with ambiguous shape is a bug.
    """
    if not path.exists():
        raise RecipeError(f"recipe file does not exist: {path}")
    try:
        raw = path.read_bytes()
        parsed = tomllib.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise RecipeError(f"failed to read recipe file {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise RecipeError(f"recipe file is not valid TOML: {path}: {exc}") from exc

    recipe_section = parsed.get("recipe")
    if not isinstance(recipe_section, dict):
        raise RecipeError(f"recipe file {path} is missing [recipe] section")

    for field_name in ("name", "description", "version", "output_wing"):
        if field_name not in recipe_section:
            raise RecipeError(
                f"recipe file {path} [recipe] section is missing required field {field_name!r}"
            )
        if not isinstance(recipe_section[field_name], str):
            raise RecipeError(f"recipe file {path} [recipe].{field_name} must be a string")

    skills = recipe_section.get("skills")
    if not isinstance(skills, list) or not skills:
        raise RecipeError(
            f"recipe file {path} [recipe].skills must be a non-empty list of skill names"
        )
    for skill in skills:
        if not isinstance(skill, str):
            raise RecipeError(
                f"recipe file {path} [recipe].skills must contain strings, got {skill!r}"
            )
        if skill not in _VALID_SKILLS:
            raise RecipeError(
                f"recipe file {path} references unknown skill {skill!r}; "
                f"valid skills are {sorted(_VALID_SKILLS)}"
            )

    inputs_section = parsed.get("input", {})
    if not isinstance(inputs_section, dict):
        raise RecipeError(f"recipe file {path} [input] section must be a table of input specs")

    input_specs: list[RecipeInputSpec] = []
    for input_name, spec in inputs_section.items():
        if not isinstance(spec, dict):
            raise RecipeError(f"recipe file {path} [input].{input_name} must be a table")
        input_type = spec.get("type", "string")
        if not isinstance(input_type, str) or input_type not in _VALID_INPUT_TYPES:
            raise RecipeError(
                f"recipe file {path} [input].{input_name}.type must be one of "
                f"{sorted(_VALID_INPUT_TYPES)}, got {input_type!r}"
            )
        required = spec.get("required", False)
        if not isinstance(required, bool):
            raise RecipeError(f"recipe file {path} [input].{input_name}.required must be a boolean")
        description = spec.get("description", "")
        if not isinstance(description, str):
            raise RecipeError(
                f"recipe file {path} [input].{input_name}.description must be a string"
            )
        input_specs.append(
            RecipeInputSpec(
                name=input_name,
                type=input_type,
                required=required,
                description=description,
            )
        )

    return RecipeContract(
        name=recipe_section["name"],
        description=recipe_section["description"],
        version=recipe_section["version"],
        output_wing=recipe_section["output_wing"],
        skills=tuple(skills),
        inputs=tuple(input_specs),
        source_path=path.resolve(),
    )
