"""Cairntir CLI entry point.

Two commands only: ``cairntir`` (umbrella / status) and ``cairntir recall``
(the one thing a human ever needs to type). Everything else is automatic via
the daemon and MCP.
"""

from __future__ import annotations

import typer

from cairntir import __version__

app = typer.Typer(
    name="cairntir",
    help="Memory-first reasoning layer for Claude Code. Kills cross-chat AI amnesia.",
    no_args_is_help=True,
    add_completion=False,
)


@app.command()
def version() -> None:
    """Print the Cairntir version."""
    typer.echo(f"cairntir {__version__}")


@app.command()
def recall(query: str, wing: str | None = None, limit: int = 10) -> None:
    """Search stored drawers by semantic query.

    Args:
        query: Natural-language search string.
        wing: Optional wing (project) to scope the search.
        limit: Maximum number of results to return.
    """
    # Phase 2 stub — implemented after memory layer lands in Phase 1.
    typer.echo(f"[stub] recall query={query!r} wing={wing!r} limit={limit}")
    raise typer.Exit(code=0)


def main() -> None:
    """Module entry point for ``python -m cairntir``."""
    app()


if __name__ == "__main__":
    main()
