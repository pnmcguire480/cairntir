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


def _register_user_via_claude_cli() -> tuple[bool, str]:
    """Call ``claude mcp add -s user ...`` to register Cairntir user-level.

    Returns ``(ok, message)``. Shelling out to the real Claude Code CLI
    is the only authoritative way to touch the user-level MCP list —
    writing ``~/.claude.json`` directly does not work because Claude
    Code manages its own schema/location for that registry.
    """
    import shutil
    import subprocess

    claude = shutil.which("claude")
    if claude is None:
        return (
            False,
            "could not find the `claude` CLI on PATH. Install Claude Code or "
            "register manually:\n  claude mcp add -s user cairntir -- python -m "
            "cairntir.mcp.server",
        )
    cmd = [
        claude,
        "mcp",
        "add",
        "-s",
        "user",
        "cairntir",
        "--",
        "python",
        "-m",
        "cairntir.mcp.server",
    ]
    try:
        result = subprocess.run(  # noqa: S603 — argv is fully constructed, no shell
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        return False, f"failed to invoke `claude mcp add`: {exc}"
    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        return False, f"`claude mcp add` exited {result.returncode}: {stderr}"
    return True, (result.stdout or "").strip() or "registered"


@app.command("init")
def init_cmd(
    user: bool = typer.Option(
        False,
        "--user",
        help="Register Cairntir at user level via `claude mcp add -s user`, so"
        " every Claude Code session sees it regardless of cwd. Without this"
        " flag, writes .mcp.json in the current directory.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Rewrite the project target even if Cairntir is already registered.",
    ),
) -> None:
    """Register Cairntir's MCP server with Claude Code.

    Project mode (default): writes ``.mcp.json`` in the current
    directory. Idempotent — an already-registered project is a no-op
    unless ``--force`` is passed. Other ``mcpServers`` entries are
    preserved.

    User mode (``--user``): shells out to ``claude mcp add -s user``,
    which is the only authoritative way to touch Claude Code's
    user-level MCP registry. Requires the ``claude`` CLI on PATH.
    """
    if user:
        ok, message = _register_user_via_claude_cli()
        if not ok:
            typer.echo(f"cairntir: {message}", err=True)
            raise typer.Exit(code=1)
        typer.echo("registered cairntir MCP server at user scope")
        typer.echo(message)
        typer.echo("restart Claude Code (fully quit, not just close the window) to pick it up.")
        return

    target = Path.cwd() / ".mcp.json"
    config = _load_or_init_json(target)
    config, changed = _merge_mcp_spec(config)
    if not changed and not force:
        typer.echo(f"cairntir already registered in {target}")
        return
    _write_json(target, config)
    typer.echo(f"registered cairntir MCP server (project) in {target}")
    typer.echo("restart Claude Code (fully quit, not just close the window) to pick it up.")


def main() -> None:
    """Module entry point for ``python -m cairntir``."""
    app()


if __name__ == "__main__":
    main()
