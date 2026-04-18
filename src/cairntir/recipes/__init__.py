"""Recipes — declarative protocols that chain the three skills.

v1.1 introduces an executable recipe runtime so protocols like
Signal Reader stop being seven-step walkthroughs in Markdown and start
being one command. The three skills stay locked — recipes are the
escape valve when a user wants a repeatable chain.

A recipe lives in a ``recipe.toml`` file alongside its README. At
runtime, :class:`RecipeContract` loads and validates the TOML, and
:class:`RecipeRunner` executes the recipe against the four reason-loop
adapters (memory, beliefs, proposer, runner), writing prediction-bound
drawers to the recipe's ``output_wing`` and returning a
:class:`RecipeResult` listing every drawer id it wrote.
"""

from __future__ import annotations

from cairntir.recipes.contract import RecipeContract, RecipeError, load_recipe
from cairntir.recipes.discovery import discover_recipes, recipe_search_paths
from cairntir.recipes.runner import RecipeResult, RecipeRunner

__all__ = [
    "RecipeContract",
    "RecipeError",
    "RecipeResult",
    "RecipeRunner",
    "discover_recipes",
    "load_recipe",
    "recipe_search_paths",
]
