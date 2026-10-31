"""Model-free installed-wheel smoke; not the complete release test suite."""

import argparse
import contextlib
import importlib.metadata
import io
import json
import os
import sys
import tomllib
from pathlib import Path


def _check(value, message):
    if not value:
        raise RuntimeError(message)


def main():
    """Verify the installed preview with disposable data."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    target, runtime = (args.target.resolve(), args.runtime.resolve())
    runtime.mkdir(parents=True, exist_ok=True)
    os.environ.update(
        CAIRNTIR_HOME=str(runtime / "home"),
        CAIRNTIR_DISABLE_AUTOREGISTER="1",
        CAIRNTIR_DISABLE_UPDATE_CHECK="1",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
    )
    sys.path.insert(0, str(target))
    import cairntir
    from cairntir.cli import app
    from cairntir.impl import DrawerStore, HashEmbeddingProvider
    from cairntir.mcp.backend import CairntirBackend
    from cairntir.mcp.server import _tool_specs, build_server
    from cairntir.memory.taxonomy import Drawer

    version = "2.0.0a1"
    _check(
        Path(cairntir.__file__).resolve().is_relative_to(target),
        "Alpha smoke check failed at original line 31",
    )
    _check(
        cairntir.__version__ == importlib.metadata.version("cairntir") == version,
        "Alpha smoke check failed at original line 32",
    )
    project = tomllib.loads((args.source / "pyproject.toml").read_text(encoding="utf-8"))
    plugin = json.loads((args.source / ".claude-plugin/plugin.json").read_bytes())
    _check(
        project["project"]["version"] == plugin["version"] == version,
        "Alpha smoke check failed at original line 35",
    )
    _check(plugin["commands"] == "./commands", "Alpha smoke check failed at original line 36")
    _check(
        all(
            (args.source / "commands" / (name + ".md")).is_file()
            for name in ("remember", "recall", "reason")
        ),
        "Alpha smoke check failed at original line 37",
    )
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        app(args=["version"], prog_name="cairntir", standalone_mode=False)
    _check(version in output.getvalue(), "Alpha smoke check failed at original line 41")
    path = runtime / "smoke.sqlite3"
    _check(not path.exists(), "Alpha smoke check failed at original line 43")
    store = DrawerStore(path, HashEmbeddingProvider())
    try:
        saved = store.add(
            Drawer(wing="alpha-smoke", room="memory", content="Alpha installed-wheel round trip."),
            model="smoke",
        )
        _check(
            saved.id is not None and store.get(saved.id).content == saved.content,
            "Alpha smoke check failed at original line 47",
        )
        backend = CairntirBackend(store)
        tools = _tool_specs()
        names = [tool.name for tool in tools]
        _check(
            len(names) == len(set(names))
            and {"cairntir_remember", "cairntir_recall", "cairntir_handoff"} <= set(names),
            "Alpha smoke check failed at original line 51",
        )
        options = build_server(backend).create_initialization_options()
        _check(options.server_version == version, "Alpha smoke check failed at original line 53")
    finally:
        store.close()
    reopened = DrawerStore(path, HashEmbeddingProvider())
    try:
        _check(
            reopened.get(saved.id).content == saved.content,
            "Alpha smoke check failed at original line 58",
        )
    finally:
        reopened.close()
    recipes = target / "cairntir/recipes/bundled"
    recipe_count = sum(path.is_file() for path in recipes.rglob("*"))
    _check(recipe_count == 11, "Alpha smoke check failed at original line 63")
    print(
        json.dumps(
            {
                "status": "PASS_ALPHA_PACKAGING_SMOKE_ONLY",
                "version": version,
                "import_origin": str(Path(cairntir.__file__).resolve()),
                "cli_version": output.getvalue().strip(),
                "memory_write_read_reopen": True,
                "mcp_tools": len(names),
                "recipe_files": recipe_count,
                "models_called": 0,
                "full_suite_run": False,
                "coverage_measured": False,
            }
        )
    )


if __name__ == "__main__":
    main()
