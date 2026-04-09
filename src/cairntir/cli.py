"""Cairntir CLI entry point.

Two commands: ``cairntir`` (umbrella / status) and ``cairntir recall`` — the
one thing a human ever needs to type. Everything else is automatic via the
daemon and MCP.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from cairntir import __version__
from cairntir.config import cairntir_home, db_path
from cairntir.mcp.backend import CairntirBackend
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import SCHEMA_VERSION, DrawerStore
from cairntir.portable import export_drawers, import_drawers

app = typer.Typer(
    name="cairntir",
    help="Memory-first reasoning layer for Claude Code. Kills cross-chat AI amnesia.",
    no_args_is_help=False,
    add_completion=False,
)


def _backend() -> CairntirBackend:
    """Open the on-disk drawer store and wrap it in a backend.

    Uses :class:`HashEmbeddingProvider` to keep the CLI startup free of the
    ~90 MB sentence-transformers model. Semantic quality comes from the daemon
    and MCP paths that use the production embedder; the CLI's ``recall`` is a
    metadata/keyword-aware passthrough suitable for quick human lookups.
    """
    store = DrawerStore(db_path(), HashEmbeddingProvider())
    return CairntirBackend(store)


@app.callback(invoke_without_command=True)
def _root(ctx: typer.Context) -> None:
    """Show a one-line status banner when invoked with no subcommand."""
    if ctx.invoked_subcommand is not None:
        return
    home = cairntir_home()
    typer.echo(f"cairntir {__version__}  home={home}")
    typer.echo("commands: version · status · recall")


@app.command()
def version() -> None:
    """Print the Cairntir version."""
    typer.echo(f"cairntir {__version__}")


@app.command()
def status() -> None:
    """Print the store location and a drawer count per wing."""
    home = cairntir_home()
    path = db_path()
    typer.echo(f"cairntir {__version__}")
    typer.echo(f"home: {home}")
    typer.echo(f"db:   {path}")
    if not path.exists():
        typer.echo("store: (not yet initialized — no drawers written)")
        return
    backend = _backend()
    drawers = backend._store.list_by(limit=10_000)
    if not drawers:
        typer.echo("store: empty")
        return
    counts: dict[str, int] = {}
    for d in drawers:
        counts[d.wing] = counts.get(d.wing, 0) + 1
    typer.echo(f"wings: {len(counts)}  drawers: {len(drawers)}")
    for wing, count in sorted(counts.items()):
        typer.echo(f"  {wing}  ({count} drawers)")


@app.command()
def recall(
    query: str,
    wing: str | None = typer.Option(None, "--wing", "-w", help="Scope to a wing (project)."),
    room: str | None = typer.Option(None, "--room", "-r", help="Scope to a room (topic)."),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results to return."),
) -> None:
    """Search stored drawers by semantic query."""
    if not db_path().exists():
        typer.echo("cairntir: no store yet — nothing to recall.", err=True)
        raise typer.Exit(code=1)
    backend = _backend()
    typer.echo(backend.recall(query=query, wing=wing, room=room, limit=limit))


@app.command("export")
def export_cmd(
    path: Path,
    wing: str | None = typer.Option(None, "--wing", "-w", help="Scope to a wing."),
    room: str | None = typer.Option(None, "--room", "-r", help="Scope to a room."),
) -> None:
    """Export drawers to a portable JSONL envelope file.

    Fails closed if any drawer references a non-cairntir URL. The
    format is content-addressed (sha256) and optionally HMAC-signed.
    """
    if not db_path().exists():
        typer.echo("cairntir: no store yet — nothing to export.", err=True)
        raise typer.Exit(code=1)
    backend = _backend()
    drawers = backend._store.list_by(wing=wing, room=room, limit=100_000)
    count = export_drawers(drawers, path)
    typer.echo(f"exported {count} drawers to {path}")


@app.command("import")
def import_cmd(path: Path) -> None:
    """Import drawers from a portable JSONL envelope file into the local store.

    Verifies each envelope's content hash before inserting. Signatures
    are not checked by default; add signature verification when the
    signed-key distribution story lands.
    """
    if not path.exists():
        typer.echo(f"cairntir: {path} does not exist.", err=True)
        raise typer.Exit(code=1)
    drawers = import_drawers(path)
    backend = _backend()
    for drawer in drawers:
        backend._store.add(drawer)
    typer.echo(f"imported {len(drawers)} drawers from {path}")


@app.command("migrate")
def migrate_cmd(
    db: Path | None = typer.Argument(None, help="Database file."),  # noqa: B008
    check: bool = typer.Option(
        False,
        "--check",
        help="Report the current schema version without applying migrations.",
    ),
) -> None:
    """Apply forward-only schema migrations to a Cairntir drawer database.

    Opening a database through :class:`DrawerStore` already runs the
    migration chain, so this command is mostly a user-facing receipt
    that reports the before/after ``PRAGMA user_version`` and fails
    fast if the database is unreadable.
    """
    import sqlite3

    import sqlite_vec

    target = db if db is not None else db_path()
    if not target.exists():
        typer.echo(f"cairntir: {target} does not exist.", err=True)
        raise typer.Exit(code=1)

    # Peek at the current schema version without going through DrawerStore
    # (which would migrate as a side effect).
    peek = sqlite3.connect(target)
    try:
        peek.enable_load_extension(True)
        sqlite_vec.load(peek)
        peek.enable_load_extension(False)
        before = peek.execute("PRAGMA user_version").fetchone()[0]
    finally:
        peek.close()

    typer.echo(f"db:               {target}")
    typer.echo(f"current version:  {before}")
    typer.echo(f"library version:  {SCHEMA_VERSION}")

    if check:
        return

    if before == SCHEMA_VERSION:
        typer.echo("already up to date — no migration needed")
        return

    # Opening through DrawerStore applies the forward-only ALTER TABLE
    # chain and stamps user_version to SCHEMA_VERSION.
    with DrawerStore(target, HashEmbeddingProvider()) as store:
        after = store._conn.execute("PRAGMA user_version").fetchone()[0]
    typer.echo(f"migrated to:      {after}")


CAIRNTIR_MCP_SPEC: dict[str, Any] = {
    "command": "python",
    "args": ["-m", "cairntir.mcp.server"],
}
"""The canonical MCP-server stanza Cairntir writes into Claude Code configs."""


def _merge_mcp_spec(config: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Merge the Cairntir MCP stanza into ``config``. Return (config, changed)."""
    servers = config.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise typer.BadParameter("mcpServers in target config is not a JSON object")
    existing = servers.get("cairntir")
    if existing == CAIRNTIR_MCP_SPEC:
        return config, False
    servers["cairntir"] = dict(CAIRNTIR_MCP_SPEC)
    return config, True


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_or_init_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(loaded, dict):
        raise typer.BadParameter(f"{path} is not a JSON object")
    return loaded


@app.command("init")
def init_cmd(
    user: bool = typer.Option(
        False,
        "--user",
        help="Register Cairntir at user level (~/.claude.json) instead of the"
        " current project's .mcp.json. User-level registration makes Cairntir"
        " available to every Claude Code session regardless of cwd.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Rewrite the target even if Cairntir is already registered.",
    ),
) -> None:
    """Register Cairntir's MCP server with Claude Code.

    Without ``--user``, writes ``.mcp.json`` in the current directory so
    Claude Code spawns the Cairntir MCP server for sessions opened in
    that project. Idempotent: an already-registered project is a no-op
    unless ``--force`` is passed.

    With ``--user``, merges the same stanza into ``~/.claude.json`` so
    every Claude Code session sees Cairntir. Other entries in the file
    are preserved.
    """
    target = Path.home() / ".claude.json" if user else Path.cwd() / ".mcp.json"
    config = _load_or_init_json(target)
    config, changed = _merge_mcp_spec(config)
    if not changed and not force:
        typer.echo(f"cairntir already registered in {target}")
        return
    _write_json(target, config)
    scope = "user" if user else "project"
    typer.echo(f"registered cairntir MCP server ({scope}) in {target}")
    typer.echo("restart Claude Code (or reload the window) to pick up the new MCP server.")


def main() -> None:
    """Module entry point for ``python -m cairntir``."""
    app()


if __name__ == "__main__":
    main()
