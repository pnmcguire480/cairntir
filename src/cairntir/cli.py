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


_PRODUCTION_DIM = 384
"""Embedding dimension the MCP server's ``all-MiniLM-L6-v2`` model produces.

The CLI uses :class:`HashEmbeddingProvider` at the same dimension so the
``vec_drawers`` virtual table shape matches regardless of which code path
touched the database first. The hash embedder is deterministic and
dimension-independent, so the only cost of 384 vs 64 is a few extra
floats per insert — negligible.
"""


def _backend() -> CairntirBackend:
    """Open the on-disk drawer store and wrap it in a backend.

    Uses :class:`HashEmbeddingProvider` at the production dimension
    (384) to keep the CLI startup free of the ~90 MB
    sentence-transformers model while staying shape-compatible with
    the MCP server's ``SentenceTransformerProvider``.
    """
    store = DrawerStore(db_path(), HashEmbeddingProvider(dimension=_PRODUCTION_DIM))
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


def _mcp_spec() -> dict[str, Any]:
    """Return the canonical Cairntir MCP stanza pinned to the *current* Python.

    Pinning to ``sys.executable`` at registration time is the fix for
    the Windows venv trap: Claude Code spawns MCP servers outside any
    activated venv, so bare ``python`` resolves to whatever happens to
    be first on PATH — usually the system interpreter, which does not
    have Cairntir installed. The spawned process dies silently and the
    user sees an empty tool list in every folder except the one where
    they originally activated the venv.

    ``sys.executable`` always points at the interpreter currently
    running this command, which by definition has Cairntir installed
    (it is the one running the CLI right now). That path is stable
    across cwd changes and survives fresh shells.
    """
    import sys

    return {
        "command": sys.executable,
        "args": ["-m", "cairntir.mcp.server"],
    }


def _merge_mcp_spec(config: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Merge the Cairntir MCP stanza into ``config``. Return (config, changed)."""
    servers = config.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise typer.BadParameter("mcpServers in target config is not a JSON object")
    spec = _mcp_spec()
    existing = servers.get("cairntir")
    if existing == spec:
        return config, False
    servers["cairntir"] = spec
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


def _run_claude(claude: str, *args: str) -> tuple[int, str, str]:
    """Invoke the claude CLI. Returns ``(returncode, stdout, stderr)``."""
    import subprocess

    try:
        result = subprocess.run(  # noqa: S603 — argv is fully constructed, no shell
            [claude, *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        return 1, "", f"failed to invoke `claude`: {exc}"
    return result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip()


def _register_user_via_claude_cli(*, force: bool) -> tuple[bool, str]:
    """Call ``claude mcp add -s user ...`` to register Cairntir user-level.

    Returns ``(ok, message)``. If ``force`` is true and a prior
    registration already exists, runs ``claude mcp remove -s user
    cairntir`` first so the new ``sys.executable``-pinned spec replaces
    the old one. Idempotent on "already exists" when ``force`` is
    false.
    """
    import shutil
    import sys

    claude = shutil.which("claude")
    if claude is None:
        return (
            False,
            "could not find the `claude` CLI on PATH. Install Claude Code or "
            "register manually:\n  claude mcp add -s user cairntir -- "
            f"{sys.executable} -m cairntir.mcp.server",
        )

    python = sys.executable
    add_args = ("mcp", "add", "-s", "user", "cairntir", "--", python, "-m", "cairntir.mcp.server")

    if force:
        # Best-effort remove. Failure here is not fatal — the add below
        # will either succeed or report the real reason.
        _run_claude(claude, "mcp", "remove", "-s", "user", "cairntir")

    code, stdout, stderr = _run_claude(claude, *add_args)
    if code == 0:
        return True, stdout or "registered"

    combined = (stderr or stdout).lower()
    if "already exists" in combined and not force:
        return (
            True,
            "cairntir is already registered at user scope. "
            "If it is pointing at the wrong Python, re-register with:\n"
            "  cairntir init --user --force",
        )

    return False, f"`claude mcp add` exited {code}: {stderr or stdout}"


GREETING_BEGIN_MARKER: str = "<!-- cairntir:begin -->"
GREETING_END_MARKER: str = "<!-- cairntir:end -->"

GREETING_BODY: str = """# Cairntir — memory-first reasoning layer

You have access to a persistent memory system via the `cairntir_*` MCP tools.
At the start of every conversation:

1. Call `cairntir_session_start` with the wing matching the current project.
   Use the lowercase folder name in cwd as the wing (e.g. `stars-2026`,
   `cairntir`). If unsure, ask the user.
2. Read the identity and essential drawers it returns *before* answering
   anything substantive.
3. When a decision is made or a fact is learned that future sessions will
   need, call `cairntir_remember` to persist it verbatim.
4. When the user asks about past decisions, call `cairntir_recall` first
   before reasoning from scratch. Cite drawer ids inline.
5. For load-bearing assumptions, invoke `cairntir_crucible` before committing
   to them. For ship-readiness checks, invoke `cairntir_audit`.

If `cairntir_session_start` returns empty for a wing, either the wing is new
(write the first drawer) or the MCP server is misconfigured (tell the user so
they can run `cairntir init --user --force`).

This is not optional. A Claude Code session that does not check Cairntir
memory at the start of a chat is hallucinating by default.
"""
"""The user-level CLAUDE.md preamble Cairntir installs on `init --user`."""


def _render_greeting_block() -> str:
    return f"{GREETING_BEGIN_MARKER}\n{GREETING_BODY}{GREETING_END_MARKER}\n"


def _upsert_greeting(path: Path, *, body: str = GREETING_BODY) -> str:
    """Idempotently install the Cairntir greeting into a user CLAUDE.md.

    Returns one of ``"created"``, ``"appended"``, ``"updated"``, or
    ``"unchanged"`` so the CLI can report what happened. Never clobbers
    existing non-Cairntir content: the greeting is delimited by HTML
    comment markers and everything outside the markers is preserved
    byte-for-byte.
    """
    block = f"{GREETING_BEGIN_MARKER}\n{body}{GREETING_END_MARKER}\n"

    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(block, encoding="utf-8")
        return "created"

    existing = path.read_text(encoding="utf-8")
    begin = existing.find(GREETING_BEGIN_MARKER)
    end = existing.find(GREETING_END_MARKER)

    if begin == -1 or end == -1 or end < begin:
        # No markers — append the block, preserving everything that was
        # already in the file. A blank line separates prior content from
        # the new block if the file didn't end with one.
        if existing.endswith("\n\n"):
            separator = ""
        elif existing.endswith("\n"):
            separator = "\n"
        else:
            separator = "\n\n"
        path.write_text(existing + separator + block, encoding="utf-8")
        return "appended"

    # Markers found — replace the delimited block only.
    end_of_end = end + len(GREETING_END_MARKER)
    # Include the trailing newline after the end marker if present.
    if end_of_end < len(existing) and existing[end_of_end] == "\n":
        end_of_end += 1
    new_contents = existing[:begin] + block + existing[end_of_end:]
    if new_contents == existing:
        return "unchanged"
    path.write_text(new_contents, encoding="utf-8")
    return "updated"


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
        help="Re-register even if Cairntir is already present. In --user mode,"
        " removes the existing user-scope entry and re-adds it — use this to"
        " fix a registration pointing at the wrong Python interpreter.",
    ),
    no_greeting: bool = typer.Option(
        False,
        "--no-greeting",
        help="Skip installing the user-level CLAUDE.md preamble that tells"
        " every Claude Code session to call cairntir_session_start on the"
        " first turn. Only meaningful with --user.",
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

    Both modes pin the server command to ``sys.executable`` — the
    absolute path of the Python interpreter running this CLI — so
    Claude Code spawns the server against the interpreter that
    actually has Cairntir installed, regardless of cwd or which venv
    (if any) is active in the session that reads the registration.
    """
    if user:
        ok, message = _register_user_via_claude_cli(force=force)
        if not ok:
            typer.echo(f"cairntir: {message}", err=True)
            raise typer.Exit(code=1)
        typer.echo("registered cairntir MCP server at user scope")
        typer.echo(message)

        if not no_greeting:
            greeting_path = Path.home() / ".claude" / "CLAUDE.md"
            action = _upsert_greeting(greeting_path)
            typer.echo(f"greeting preamble {action} at {greeting_path}")

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
