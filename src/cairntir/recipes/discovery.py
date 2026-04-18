"""Find ``recipe.toml`` files under the project docs dir + the user's home.

The CLI uses this to power ``cairntir recipe list``. Two well-known
locations are scanned:

1. ``<repo-root>/docs/recipes/**/recipe.toml`` — recipes shipped with
   Cairntir or with the consumer's project.
2. ``~/.claude/recipes/**/recipe.toml`` — recipes the user has
   installed for their own use.

Both locations are walked with :meth:`pathlib.Path.rglob` so any depth
of subdirectories works — authors can group recipes by domain.
"""

from __future__ import annotations

from pathlib import Path

from cairntir.recipes.contract import RecipeContract, RecipeError, load_recipe


def recipe_search_paths() -> list[Path]:
    """Return the ordered list of directories the discoverer will scan.

    The first-match-wins semantic means project recipes shadow user
    recipes when the names collide. This is intentional — a project
    should be able to override a user-level recipe by shipping one
    with the same name.
    """
    paths: list[Path] = []
    # Project-local: walk up from cwd until we find docs/recipes or hit root.
    cwd = Path.cwd()
    for parent in (cwd, *cwd.parents):
        candidate = parent / "docs" / "recipes"
        if candidate.is_dir():
            paths.append(candidate)
            break
    # User-level.
    user_dir = Path.home() / ".claude" / "recipes"
    if user_dir.is_dir():
        paths.append(user_dir)
    return paths


def discover_recipes(
    *, search_paths: list[Path] | None = None
) -> list[RecipeContract]:
    """Find every ``recipe.toml`` under the search paths and return parsed contracts.

    Malformed recipe files are skipped silently *from the list* but
    are not raised: a single broken recipe in ``~/.claude/recipes``
    should not kill the ``cairntir recipe list`` command. The caller
    that wants to strict-load a specific recipe should use
    :func:`load_recipe` directly.
    """
    paths = search_paths if search_paths is not None else recipe_search_paths()
    seen_names: set[str] = set()
    contracts: list[RecipeContract] = []
    for root in paths:
        for recipe_file in sorted(root.rglob("recipe.toml")):
            try:
                contract = load_recipe(recipe_file)
            except RecipeError:
                # Skipped — a broken recipe file under the user's home
                # should not hide the working recipes next to it. The
                # `cairntir recipe run <name>` path uses load_recipe
                # directly, which does raise on error.
                continue
            if contract.name in seen_names:
                continue  # first wins (earlier search paths shadow later)
            seen_names.add(contract.name)
            contracts.append(contract)
    return contracts
