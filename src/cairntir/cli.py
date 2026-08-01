"""Cairntir's host-neutral memory, reasoning, learning, and setup CLI."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from io import TextIOWrapper
from pathlib import Path
from typing import Any

import typer

from cairntir import __version__
from cairntir.config import cairntir_home, db_path
from cairntir.errors import EmbeddingError, MCPError, MemoryStoreError, ProjectionError
from cairntir.hosts import (
    MEMORY_POLICY,
    POLICY_BEGIN_MARKER,
    POLICY_END_MARKER,
    SUPPORTED_HOSTS,
    HostConfigurationError,
    HostName,
    HostScope,
    configure_host,
    inspect_host,
    upsert_marked_policy,
)
from cairntir.mcp.backend import CairntirBackend
from cairntir.memory.embeddings import production_embedding_provider
from cairntir.memory.store import (
    SCHEMA_VERSION,
    DrawerStore,
    backup_database,
    inspect_database_integrity,
    inspect_embedding_space,
    reindex_database,
)
from cairntir.memory.taxonomy import Drawer
from cairntir.portable import export_drawers, import_drawers
from cairntir.provenance import TrustLevel, WriteProvenance
from cairntir.register import clear_checkpoint, ensure_registered
from cairntir.update import maybe_check_in_background, pending_update_banner


def _configure_windows_stdio() -> None:
    """Keep Unicode CLI output safe when Windows redirects through cp1252.

    Typer renders help before invoking the root callback, so this boundary
    must run while the console-script module is imported. Test runners replace
    stdout/stderr with in-memory streams, which are intentionally left alone.
    """
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, TextIOWrapper):
            stream.reconfigure(encoding="utf-8", errors="replace")


_configure_windows_stdio()

app = typer.Typer(
    name="cairntir",
    help="Host-neutral memory-first reasoning layer. Kills cross-chat AI amnesia.",
    no_args_is_help=False,
    add_completion=False,
)


def _backend() -> CairntirBackend:
    """Open the on-disk drawer store and wrap it in a backend.

    Every production entry point uses the same provider factory. Equal
    dimensions do not make two embedding spaces compatible.
    """
    store = _open_store()
    return CairntirBackend(store)


def _open_store(
    path: Path | None = None,
    *,
    capture_path: str = "cli",
) -> DrawerStore:
    return DrawerStore(
        path or db_path(),
        production_embedding_provider(),
        provenance=WriteProvenance.create(
            host="cli",
            capture_path=capture_path,
            trust=TrustLevel.USER_ASSERTED,
        ),
    )


@app.callback(invoke_without_command=True)
def _root(ctx: typer.Context) -> None:
    """Show a one-line status banner when invoked with no subcommand.

    Side effect: every CLI invocation kicks off the silent self-heal
    registration check and the background update check. Both are
    fail-silent — they never block, never raise, and surface only
    through the optional banner appended at end of command output.
    """
    # Best-effort self-heal: TRUE-until-FALSE registration. Once
    # cairntir is installed, every CLI run guarantees the user-scope
    # MCP entry exists. Uninstalling the package removes the
    # ``cairntir-mcp`` console script and Claude Code surfaces the
    # missing command — the FALSE state is visible by construction.
    ensure_registered()
    # Spawn the background PyPI check so the next invocation sees the
    # latest-version cache. The current process prints whatever the
    # previous check already wrote.
    maybe_check_in_background()

    if ctx.invoked_subcommand is not None:
        ctx.call_on_close(_print_update_banner)
        return
    home = cairntir_home()
    typer.echo(f"cairntir {__version__}  home={home}")
    typer.echo("commands: status · doctor · recall · get · discoveries · learning-log")
    _print_update_banner()


def _print_update_banner() -> None:
    """Print the pending-update banner, if any. Always safe to call."""
    banner = pending_update_banner()
    if banner is not None:
        typer.echo(banner)


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
def doctor() -> None:
    """Inspect semantic-index and agent-host wiring without modifying either."""
    path = db_path()
    provider = production_embedding_provider()
    try:
        report = inspect_embedding_space(path, provider)
    except MemoryStoreError as exc:
        typer.echo(f"cairntir: doctor failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"db:                 {path}")
    typer.echo(f"state:              {report.state}")
    typer.echo(f"active space:       {report.current_space_id}")
    typer.echo(f"stored space:       {report.stored_space_id or '(unknown)'}")
    typer.echo(f"stored dimension:   {report.stored_dimension or '(unknown)'}")
    typer.echo(f"vector dimension:   {report.vector_dimension or '(unknown)'}")
    typer.echo(f"index generation:   {report.generation or '(unknown)'}")
    typer.echo(f"drawers / vectors:  {report.drawer_count} / {report.vector_count}")
    typer.echo(f"detail:             {report.detail}")
    try:
        integrity = inspect_database_integrity(path)
    except MemoryStoreError as exc:
        typer.echo(f"cairntir: integrity check failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"sqlite integrity:   {'ok' if integrity.ok else 'FAILED'}")
    typer.echo(f"foreign-key errors: {integrity.foreign_key_violations}")
    typer.echo(f"workflows started:  {integrity.started_workflows}")
    typer.echo(f"workflows failed:   {integrity.failed_workflows}")
    if not integrity.ok:
        raise typer.Exit(code=1)
    if not report.verified:
        typer.echo("semantic reads and writes are disabled until `cairntir reindex` succeeds.")
        raise typer.Exit(code=1)

    typer.echo()
    typer.echo("agent hosts (read-only):")
    for scope in ("user", "project"):
        for host in SUPPORTED_HOSTS:
            status = inspect_host(
                host,
                scope=scope,
                root=Path.cwd(),
                home=Path.home(),
            )
            mcp = (
                "unknown"
                if status.mcp_configured is None
                else "ready"
                if status.mcp_configured
                else "missing"
            )
            policy = (
                "manual"
                if status.policy_configured is None
                else "ready"
                if status.policy_configured
                else "missing"
            )
            typer.echo(f"  {scope:7} {host:7} MCP={mcp:7} policy={policy}")
            if not status.mcp_configured:
                typer.echo(f"           MCP: {status.mcp_detail}")
            if not status.policy_configured:
                typer.echo(f"           policy: {status.policy_detail}")


@app.command()
def reindex(
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Confirm the explicit semantic-index rebuild without prompting.",
    ),
    backup: Path | None = typer.Option(  # noqa: B008
        None,
        "--backup",
        help="Backup path. Defaults to a timestamped sibling of the database.",
    ),
    batch_size: int = typer.Option(64, "--batch-size", min=1),
) -> None:
    """Back up the store, rebuild every vector, and stamp its embedding identity."""
    path = db_path()
    if not path.exists():
        typer.echo(f"cairntir: {path} does not exist.", err=True)
        raise typer.Exit(code=1)

    provider = production_embedding_provider()
    try:
        before = inspect_embedding_space(path, provider)
    except MemoryStoreError as exc:
        typer.echo(f"cairntir: reindex inspection failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"current state: {before.state} — {before.detail}")
    if not yes and not typer.confirm(
        f"Back up and re-embed all {before.drawer_count} drawers?",
        default=False,
    ):
        typer.echo("reindex cancelled; no changes made.")
        raise typer.Exit()

    if backup is None:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        backup = path.with_name(f"{path.stem}.backup-{stamp}{path.suffix}")
    try:
        created_backup = backup_database(path, backup)
        result = reindex_database(path, provider, batch_size=batch_size)
    except (EmbeddingError, MemoryStoreError, ValueError) as exc:
        typer.echo(f"cairntir: reindex failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"backup:      {created_backup}")
    typer.echo(f"drawers:     {result.drawer_count}")
    typer.echo(f"dimension:   {result.dimension}")
    typer.echo(f"space:       {result.space_id}")
    typer.echo(f"generation:  {result.generation}")


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


@app.command("get")
def get_cmd(drawer_id: int) -> None:
    """Print one complete, verbatim drawer as structured JSON."""
    if not db_path().exists():
        typer.echo("cairntir: no store yet — nothing to fetch.", err=True)
        raise typer.Exit(code=1)
    backend = _backend()
    try:
        typer.echo(backend.get(drawer_id=drawer_id))
    except (MCPError, MemoryStoreError) as exc:
        typer.echo(f"cairntir: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@app.command("anchor")
def anchor_cmd(
    drawer_id: int,
    path: list[str] = typer.Option(  # noqa: B008 — Typer declares options at import time
        ..., "--path", "-p", help="Repo-relative code path. Repeat for several."
    ),
    symbol: str | None = typer.Option(
        None, "--symbol", "-s", help="Optional function/class name, applied to every --path."
    ),
) -> None:
    """Attach structural anchors to an existing drawer.

    Anchored drawers surface from `cairntir recall-for-change` when those
    files change. New drawers can carry anchors at write time; this is the
    retroactive path for a corpus written before anchors existed.

    Append-only: existing anchors are kept, duplicates collapse, and the
    drawer's verbatim content is never touched.
    """
    if not db_path().exists():
        typer.echo("cairntir: no store yet — nothing to anchor.", err=True)
        raise typer.Exit(code=1)
    entries: list[dict[str, Any]] = []
    for raw in path:
        entry: dict[str, Any] = {"path": raw}
        if symbol:
            entry["symbol"] = symbol
        entries.append(entry)
    try:
        merged = _open_store().add_anchors(drawer_id, entries)
    except MemoryStoreError as exc:
        typer.echo(f"cairntir: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Drawer #{drawer_id} now carries {len(merged)} anchor(s):")
    for item in merged:
        label = item["path"] if not item.get("symbol") else f"{item['path']}:{item['symbol']}"
        typer.echo(f"  {label}")


@app.command("recall-for-change")
def recall_for_change_cmd(
    files: list[str],
    wing: str | None = typer.Option(None, "--wing", "-w", help="Scope to a wing (project)."),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results to return."),
) -> None:
    """Surface drawers anchored to the files a change touches.

    Structural recall: answers the question you did not think to ask. Only
    drawers carrying anchors participate, so empty output means nothing was
    ever written about those files.
    """
    if not db_path().exists():
        typer.echo("cairntir: no store yet — nothing to recall.", err=True)
        raise typer.Exit(code=1)
    backend = _backend()
    try:
        typer.echo(backend.recall_for_change(files=files, wing=wing, limit=limit))
    except (MCPError, MemoryStoreError) as exc:
        typer.echo(f"cairntir: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@app.command("cross-recall")
def cross_recall_cmd(
    query: str,
    limit: int = typer.Option(10, "--limit", "-n", help="Max results to return."),
) -> None:
    """Search drawers across every wing, annotated by wing-of-origin."""
    if not db_path().exists():
        typer.echo("cairntir: no store yet — nothing to recall.", err=True)
        raise typer.Exit(code=1)
    backend = _backend()
    typer.echo(backend.cross_recall(query=query, limit=limit))


@app.command("discover")
def discover_cmd(
    title: str,
    summary: str,
    wing: str = typer.Option(..., "--wing", "-w"),
    novelty: str = typer.Option(
        ...,
        "--novelty",
        help="Novelty scope: user, cairntir, or general.",
    ),
    evidence: list[int] = typer.Option(  # noqa: B008
        ...,
        "--evidence",
        "-e",
        help="Evidence drawer id. Repeat for multiple drawers.",
    ),
    state: str = typer.Option("signal", "--state"),
) -> None:
    """Record an evidence-backed emergent pattern in the Discovery Ledger."""
    try:
        typer.echo(
            _backend().discover(
                wing=wing,
                title=title,
                summary=summary,
                novelty=novelty,
                evidence_ids=evidence,
                state=state,
            )
        )
    except (MCPError, MemoryStoreError) as exc:
        typer.echo(f"cairntir: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@app.command("discovery-transition")
def discovery_transition_cmd(
    drawer_id: int,
    state: str,
    note: str = typer.Option(..., "--note", "-n"),
) -> None:
    """Append a reviewed lifecycle transition for a discovery."""
    try:
        typer.echo(
            _backend().transition_discovery(
                drawer_id=drawer_id,
                state=state,
                note=note,
            )
        )
    except (MCPError, MemoryStoreError) as exc:
        typer.echo(f"cairntir: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@app.command("discoveries")
def discoveries_cmd(
    wing: str | None = typer.Option(None, "--wing", "-w"),
    state: str | None = typer.Option(None, "--state"),
    limit: int = typer.Option(100, "--limit", "-n", min=1),
) -> None:
    """Read the current leaves of the append-only Discovery Ledger."""
    try:
        typer.echo(_backend().discoveries(wing=wing, state=state, limit=limit))
    except (MCPError, MemoryStoreError) as exc:
        typer.echo(f"cairntir: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@app.command("learning-log")
def learning_log_cmd(
    wing: str | None = typer.Option(None, "--wing", "-w"),
    include_candidates: bool = typer.Option(
        True,
        "--include-candidates/--promoted-only",
    ),
    limit: int = typer.Option(100, "--limit", "-n", min=1),
) -> None:
    """Read Cairntir's easy-to-access Human Learning Log."""
    try:
        typer.echo(
            _backend().learning_log(
                wing=wing,
                include_candidates=include_candidates,
                limit=limit,
            )
        )
    except (MCPError, MemoryStoreError) as exc:
        typer.echo(f"cairntir: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@app.command("discover-scan")
def discover_scan_cmd(
    wing: str = typer.Option(..., "--wing", "-w"),
    min_observations: int = typer.Option(3, "--min-observations", min=2),
    confidence_threshold: float = typer.Option(
        0.8,
        "--confidence-threshold",
        min=0.5,
        max=1.0,
    ),
) -> None:
    """Propose reviewable patterns from repeated prediction episodes."""
    try:
        typer.echo(
            _backend().discover_scan(
                wing=wing,
                min_observations=min_observations,
                confidence_threshold=confidence_threshold,
            )
        )
    except (MCPError, MemoryStoreError) as exc:
        typer.echo(f"cairntir: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@app.command("calibration")
def calibration_cmd(
    wing: str = typer.Option(..., "--wing", "-w"),
) -> None:
    """Show whether Cairntir's recorded predictions are actually holding."""
    try:
        typer.echo(_backend().calibration(wing=wing))
    except (MCPError, MemoryStoreError) as exc:
        typer.echo(f"cairntir: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@app.command("obsidian-project")
def obsidian_project_cmd(
    vault: Path = typer.Argument(..., help="Path to the Obsidian vault."),  # noqa: B008
    wing: str | None = typer.Option(None, "--wing", "-w"),
) -> None:
    """Project the learning log and CodeGlass notes one-way into Obsidian."""
    from cairntir.obsidian import project_to_obsidian

    store = _open_store(capture_path="cli.obsidian-project")
    try:
        try:
            result = project_to_obsidian(store, vault=vault, wing=wing)
        except ProjectionError as exc:
            typer.echo(f"cairntir: {exc}", err=True)
            raise typer.Exit(code=1) from exc
    finally:
        store.close()
    typer.echo(f"projected learning log to {result.learning_log}")
    typer.echo(f"projected {len(result.codeglass_notes)} CodeGlass note(s)")
    typer.echo(f"projected {len(result.receipt_notes)} drawer receipt note(s)")
    typer.echo("SQLite remains authoritative; text outside generated markers was preserved.")


_VALID_PROPOSERS = ("manual", "ollama")
_DEFAULT_OLLAMA_MODEL = "gemma2:2b"
_DEFAULT_OLLAMA_ENDPOINT = "http://localhost:11434"


def _build_proposer(
    proposer_kind: str,
    *,
    question: str,
    wing: str,
    room: str,
    claim: str | None,
    predicted: str | None,
    ollama_model: str,
    ollama_endpoint: str,
) -> object:
    """Construct the configured proposer, possibly invoking it for the draft.

    Returns either a :class:`ManualProposer` (with claim+predicted set,
    either from CLI flags or from Ollama's draft) or \u2014 when the loop
    has not yet been instantiated \u2014 raises a typer.Exit with a clear
    error message.

    The Ollama path runs the proposer *eagerly* here so the user sees
    the drafted claim + predicted_outcome and can confirm/override
    before the loop commits a drawer. Cairntir is a memory layer, not
    a black box; every load-bearing piece of generated text gets
    surfaced before it lands in the store.
    """
    from cairntir.production import (
        ManualProposer,
        OllamaError,
        OllamaProposer,
    )

    if proposer_kind == "manual":
        if claim is None:
            claim = typer.prompt(f"claim (for question {question!r})")
        if predicted is None:
            predicted = typer.prompt("predicted outcome")
        return ManualProposer(claim=claim, predicted_outcome=predicted)

    if proposer_kind == "ollama":
        ollama = OllamaProposer(model=ollama_model, endpoint=ollama_endpoint)
        try:
            drafted = ollama.propose(question=question, wing=wing, room=room)
        except OllamaError as exc:
            typer.echo(f"cairntir: local model proposer failed: {exc}", err=True)
            raise typer.Exit(code=1) from exc

        typer.echo()
        typer.echo(typer.style(f"--- {ollama_model} drafted ---", fg=typer.colors.CYAN))
        typer.echo(f"  claim:     {drafted.claim}")
        typer.echo(f"  predicted: {drafted.predicted_outcome}")
        typer.echo()

        # Caller may override either field. Defaults preserve the
        # draft. Empty input keeps the draft (Typer's prompt returns
        # the typed string; if the user just hits Enter, default is
        # returned untouched).
        if claim is None:
            claim = typer.prompt(
                "claim (Enter to accept draft)",
                default=drafted.claim,
            )
        if predicted is None:
            predicted = typer.prompt(
                "predicted (Enter to accept draft)",
                default=drafted.predicted_outcome,
            )
        return ManualProposer(claim=claim, predicted_outcome=predicted)

    typer.echo(
        f"cairntir: unknown proposer {proposer_kind!r}. "
        f"Valid choices: {', '.join(_VALID_PROPOSERS)}",
        err=True,
    )
    raise typer.Exit(code=1)


@app.command("reason")
def reason_cmd(
    question: str,
    wing: str = typer.Option(..., "--wing", "-w", help="Wing the prediction belongs to."),
    room: str = typer.Option("predictions", "--room", "-r", help="Room inside the wing."),
    claim: str | None = typer.Option(
        None,
        "--claim",
        help="The falsifiable claim. Prompted if omitted (or drafted by --proposer ollama).",
    ),
    predicted: str | None = typer.Option(
        None,
        "--predicted",
        help="The predicted outcome. Prompted if omitted (or drafted by --proposer ollama).",
    ),
    observed: str | None = typer.Option(
        None,
        "--observed",
        help="The observed outcome. Prompted if omitted.",
    ),
    success: bool | None = typer.Option(
        None,
        "--success/--fail",
        help="Verdict: did the prediction hold? Prompted if omitted.",
    ),
    proposer: str = typer.Option(
        "manual",
        "--proposer",
        case_sensitive=False,
        help="How to source the claim + predicted_outcome. "
        "'manual' (default) prompts you or uses --claim/--predicted. "
        "'ollama' drafts both via a local model (requires `ollama serve`).",
    ),
    ollama_model: str = typer.Option(
        _DEFAULT_OLLAMA_MODEL,
        "--ollama-model",
        help="Ollama model tag, e.g. gemma2:2b. Pull with `ollama pull <tag>`.",
    ),
    ollama_endpoint: str = typer.Option(
        _DEFAULT_OLLAMA_ENDPOINT,
        "--ollama-endpoint",
        help="Ollama HTTP endpoint. Defaults to localhost:11434.",
    ),
    idempotency_key: str | None = typer.Option(
        None,
        "--idempotency-key",
        help="Stable retry key. Reusing it replays the committed result without duplicate writes.",
    ),
) -> None:
    """Run one Reason loop step: predict \u2192 observe \u2192 update belief.

    Cairntir does not call cloud LLMs. The observed outcome and
    verdict always come from the caller (you saw what happened, not
    the model). With --proposer ollama, the *claim* and
    *predicted_outcome* are drafted by a locally-running Ollama
    model \u2014 still no network \u2014 and surfaced for confirmation before
    the loop commits.
    """
    if not db_path().exists():
        typer.echo("cairntir: no store yet \u2014 run `cairntir setup` first.", err=True)
        raise typer.Exit(code=1)

    from cairntir.production import (
        NullRunner,
        StoreBackedBeliefs,
        StoreBackedMemory,
    )
    from cairntir.reason.loop import ReasonLoop

    proposer_obj = _build_proposer(
        proposer.lower(),
        question=question,
        wing=wing,
        room=room,
        claim=claim,
        predicted=predicted,
        ollama_model=ollama_model,
        ollama_endpoint=ollama_endpoint,
    )

    if observed is None:
        observed = typer.prompt("observed outcome")
    if success is None:
        success = typer.confirm("did the prediction hold?", default=False)

    store = _open_store(capture_path="cli.reason")
    try:
        loop = ReasonLoop(
            proposer=proposer_obj,  # type: ignore[arg-type]
            runner=NullRunner(observed=observed, success=success),
            beliefs=StoreBackedBeliefs(store=store),
            memory=StoreBackedMemory(store=store),
        )
        update = loop.step(
            question=question,
            wing=wing,
            room=room,
            idempotency_key=idempotency_key,
        )
    finally:
        store.close()

    typer.echo()
    typer.echo(f"prediction drawer:  #{update.prediction_id}")
    typer.echo(f"observation drawer: #{update.observation_id}")
    typer.echo(f"mass_change:        {update.mass_change:+.1f}")
    if update.delta:
        typer.echo(f"delta:              {update.delta}")


@app.command("replay")
def replay_cmd(
    decision_drawer_id: int = typer.Argument(
        ...,
        help="Drawer id of the past decision to replay. Must carry claim + predicted_outcome.",
    ),
    evidence: str | None = typer.Option(
        None,
        "--evidence",
        "-e",
        help="What you've observed since the original prediction. Prompted if omitted.",
    ),
    horizon_months: int | None = typer.Option(
        None,
        "--horizon-months",
        help="Re-prediction horizon in months. Defaults to the original.",
    ),
    observed: str | None = typer.Option(
        None,
        "--observed",
        help="The actual outcome of the original prediction, in your words. Prompted if omitted.",
    ),
    success: bool | None = typer.Option(
        None,
        "--success/--fail",
        help="Verdict: did the original prediction hold? Prompted if omitted.",
    ),
    proposer: str = typer.Option(
        "manual",
        "--proposer",
        case_sensitive=False,
        help="'manual' (default) re-uses the original chain leaf's claim + predicted. "
        "'ollama' drafts a refreshed framing via a local model (requires `ollama serve`); "
        "useful when the original claim was poorly framed and the replay is also a re-statement.",
    ),
    ollama_model: str = typer.Option(
        _DEFAULT_OLLAMA_MODEL,
        "--ollama-model",
        help="Ollama model tag, e.g. gemma2:2b. Pull with `ollama pull <tag>`.",
    ),
    ollama_endpoint: str = typer.Option(
        _DEFAULT_OLLAMA_ENDPOINT,
        "--ollama-endpoint",
        help="Ollama HTTP endpoint. Defaults to localhost:11434.",
    ),
    idempotency_key: str | None = typer.Option(
        None,
        "--idempotency-key",
        help="Stable retry key. Reusing it cannot extend the decision chain twice.",
    ),
) -> None:
    """Replay a past decision against today's evidence.

    Walks the supersedes chain from ``decision_drawer_id``, pulls the
    chain leaf's claim + predicted_outcome to seed the reason step, and
    runs the ``decision-replay`` recipe with ``supersedes_id`` set to
    the leaf — so the new prediction extends the original chain instead
    of starting a new one.

    Cairntir does not call cloud LLMs. The observed outcome and the
    verdict come from you. With --proposer ollama, the *claim* and
    *predicted_outcome* are re-drafted by a locally-running model
    (still no network), surfaced for confirmation. The default
    'manual' proposer re-uses the original chain leaf's claim
    verbatim — the right call for closing a prediction window.
    """
    from cairntir.memory.temporal import walk_supersedes
    from cairntir.production import (
        ManualProposer,
        NullRunner,
        OllamaError,
        OllamaProposer,
        StoreBackedBeliefs,
        StoreBackedMemory,
    )
    from cairntir.recipes import RecipeError, RecipeRunner, discover_recipes

    if not db_path().exists():
        typer.echo("cairntir: no store yet — run `cairntir setup` first.", err=True)
        raise typer.Exit(code=1)

    contracts = {c.name: c for c in discover_recipes()}
    contract = contracts.get("decision-replay")
    if contract is None:
        typer.echo(
            "cairntir: decision-replay recipe not found. "
            "Reinstall cairntir to restore the bundled recipes.",
            err=True,
        )
        raise typer.Exit(code=1)

    store = _open_store(capture_path="cli.replay")
    try:
        try:
            chain = walk_supersedes(store, decision_drawer_id)
        except MemoryStoreError as exc:
            typer.echo(f"cairntir: {exc}", err=True)
            raise typer.Exit(code=1) from exc

        leaf = chain[-1]
        if not (leaf.claim and leaf.predicted_outcome):
            typer.echo(
                f"cairntir: drawer #{leaf.id} (chain leaf for #{decision_drawer_id}) "
                "has no claim/predicted_outcome — Decision Replay only works on "
                "prediction-bound drawers.",
                err=True,
            )
            raise typer.Exit(code=1)
        if leaf.id is None:
            # Defensive — store.get returns drawers with ids, so this branch
            # is structural, not a runtime failure path. Surface it loudly
            # if it ever happens.
            raise MemoryStoreError(f"chain leaf for drawer #{decision_drawer_id} has no id")

        typer.echo(
            f"replaying decision #{decision_drawer_id} "
            f"(chain leaf #{leaf.id}, length {len(chain)}):"
        )
        typer.echo(f"  wing/room:  {leaf.wing}/{leaf.room}")
        typer.echo(f"  claim:      {leaf.claim}")
        typer.echo(f"  predicted:  {leaf.predicted_outcome}")
        typer.echo()

        if evidence is None:
            evidence = typer.prompt("current evidence (what you've observed since)")
        if observed is None:
            observed = typer.prompt("observed outcome of the original prediction")
        if success is None:
            success = typer.confirm("did the original prediction hold?", default=False)

        inputs: dict[str, object] = {
            "decision_drawer_id": decision_drawer_id,
            "current_evidence": evidence,
        }
        if horizon_months is not None:
            inputs["horizon_months"] = horizon_months

        proposer_kind = proposer.lower()
        if proposer_kind not in _VALID_PROPOSERS:
            typer.echo(
                f"cairntir: unknown proposer {proposer!r}. "
                f"Valid choices: {', '.join(_VALID_PROPOSERS)}",
                err=True,
            )
            raise typer.Exit(code=1)

        if proposer_kind == "ollama":
            replay_question = (
                f"Replay decision: should the prediction "
                f"{leaf.claim!r} -> {leaf.predicted_outcome!r} still hold "
                f"given the new evidence: {evidence!r}? "
                "Restate the claim and predicted_outcome, sharpening the "
                "framing if the new evidence reveals it was poorly framed."
            )
            ollama_proposer = OllamaProposer(model=ollama_model, endpoint=ollama_endpoint)
            try:
                drafted = ollama_proposer.propose(
                    question=replay_question, wing=leaf.wing, room=leaf.room
                )
            except OllamaError as exc:
                typer.echo(f"cairntir: local model proposer failed: {exc}", err=True)
                raise typer.Exit(code=1) from exc

            typer.echo()
            typer.echo(
                typer.style(
                    f"--- {ollama_model} drafted (replay reframe) ---",
                    fg=typer.colors.CYAN,
                )
            )
            typer.echo(f"  claim:     {drafted.claim}")
            typer.echo(f"  predicted: {drafted.predicted_outcome}")
            typer.echo()
            new_claim = typer.prompt("claim (Enter to accept draft)", default=drafted.claim)
            new_predicted = typer.prompt(
                "predicted (Enter to accept draft)",
                default=drafted.predicted_outcome,
            )
            replay_proposer = ManualProposer(claim=new_claim, predicted_outcome=new_predicted)
        else:
            # Manual mode: re-use the original chain leaf's claim verbatim.
            # The default for closing a prediction window — the whole point
            # of replay is to test the original commitment.
            replay_proposer = ManualProposer(
                claim=leaf.claim,
                predicted_outcome=leaf.predicted_outcome,
            )

        recipe_runner = RecipeRunner(
            memory=StoreBackedMemory(store=store),
            beliefs=StoreBackedBeliefs(store=store),
            proposer=replay_proposer,
            runner=NullRunner(observed=observed, success=success),
        )
        try:
            result = recipe_runner.run(
                contract,
                inputs,
                supersedes_id=leaf.id,
                idempotency_key=idempotency_key,
            )
        except (RecipeError, ValueError) as exc:
            typer.echo(f"cairntir: replay failed: {exc}", err=True)
            raise typer.Exit(code=1) from exc
    finally:
        store.close()

    typer.echo()
    typer.echo(f"replay committed (recipe {result.recipe_name}):")
    typer.echo(f"  seed drawer:   #{result.seed_drawer_id} in wing {result.output_wing!r}")
    for skill, drawer_ids in result.skill_drawer_ids.items():
        ids = ", ".join(f"#{i}" for i in drawer_ids)
        typer.echo(f"  {skill}: {ids}")
    reason_drawers = result.skill_drawer_ids.get("reason", [])
    if reason_drawers:
        new_prediction_id = reason_drawers[0]
        typer.echo(f"  chain extended: #{leaf.id} <- #{new_prediction_id} (new prediction)")


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
def import_cmd(
    path: Path,
    idempotency_key: str | None = typer.Option(
        None,
        "--idempotency-key",
        help="Override the content-derived retry key.",
    ),
) -> None:
    """Import drawers from a portable JSONL envelope file into the local store.

    Verifies each envelope's content hash before inserting. Signatures
    are not checked by default; add signature verification when the
    signed-key distribution story lands.
    """
    if not path.exists():
        typer.echo(f"cairntir: {path} does not exist.", err=True)
        raise typer.Exit(code=1)
    raw_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    drawers = import_drawers(path)
    store = _open_store(capture_path="cli.import")
    try:
        execution = store.execute_once(
            idempotency_key=idempotency_key or f"import:{raw_hash}",
            operation="portable.import",
            request={"sha256": raw_hash, "drawer_count": len(drawers)},
            action=lambda: _import_batch(store, drawers),
        )
    finally:
        store.close()
    replay_note = " (already imported; replayed receipt)" if execution.replayed else ""
    typer.echo(f"imported {len(drawers)} drawers from {path}{replay_note}")


def _import_batch(store: DrawerStore, drawers: list[Drawer]) -> dict[str, object]:
    ids: list[int] = []
    for drawer in drawers:
        saved = store.add(drawer)
        if saved.id is None:
            raise MemoryStoreError("portable import produced a drawer without an id")
        ids.append(saved.id)
    return {"drawer_ids": ids, "drawer_count": len(ids)}


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
    with _open_store(target, capture_path="cli.migrate") as store:
        after = store._conn.execute("PRAGMA user_version").fetchone()[0]
    typer.echo(f"migrated to:      {after}")


def _mcp_spec() -> dict[str, Any]:
    """Return the canonical Cairntir MCP stanza using the stable shim.

    The ``cairntir-mcp`` console script is installed on PATH by pip
    (see ``[project.scripts]`` in ``pyproject.toml``). Pip writes a
    launcher that hard-pins the interpreter that installed Cairntir,
    so registering the *script* — not ``sys.executable`` — gives us
    one stable pointer that survives venv changes, shell restarts,
    cwd shifts, and Python upgrades. ``pip uninstall cairntir``
    removes the launcher; that vanish is the user-visible signal
    that Cairntir is gone, which is exactly the FALSE we want.
    """
    return {
        "command": "cairntir-mcp",
        "args": [],
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

    Returns ``(ok, message)``. The registered command is the stable
    ``cairntir-mcp`` console script — pip's launcher hard-pins the
    interpreter that installed Cairntir, so we do not have to. If
    ``force`` is true and a prior registration already exists, runs
    ``claude mcp remove -s user cairntir`` first so the new spec
    replaces the old one cleanly. Idempotent on "already exists" when
    ``force`` is false.
    """
    import shutil

    claude = shutil.which("claude")
    if claude is None:
        return (
            False,
            "could not find the `claude` CLI on PATH. Install Claude Code or "
            "register manually:\n  claude mcp add -s user cairntir -- cairntir-mcp",
        )

    add_args = ("mcp", "add", "-s", "user", "cairntir", "--", "cairntir-mcp")

    if force:
        # Best-effort remove. Failure here is not fatal — the add below
        # will either succeed or report the real reason.
        _run_claude(claude, "mcp", "remove", "-s", "user", "cairntir")
        # The checkpoint is bound to the prior registration; clear it
        # so the next CLI invocation re-verifies through `claude mcp
        # list` rather than trusting a stale flag.
        clear_checkpoint()

    code, stdout, stderr = _run_claude(claude, *add_args)
    if code == 0:
        return True, stdout or "registered"

    combined = (stderr or stdout).lower()
    if "already exists" in combined and not force:
        return (
            True,
            "cairntir is already registered at user scope. "
            "If it is pointing at the wrong launcher, re-register with:\n"
            "  cairntir init --user --force",
        )

    return False, f"`claude mcp add` exited {code}: {stderr or stdout}"


GREETING_BEGIN_MARKER: str = POLICY_BEGIN_MARKER
GREETING_END_MARKER: str = POLICY_END_MARKER
GREETING_BODY: str = MEMORY_POLICY
"""Backward-compatible names for the now host-neutral memory policy."""


def _upsert_greeting(path: Path, *, body: str = GREETING_BODY) -> str:
    """Idempotently install the host-neutral policy into a Markdown file."""
    return upsert_marked_policy(path, body=body)


@app.command("init")
def init_cmd(
    host: str = typer.Option(
        "claude",
        "--host",
        help="Agent host to configure: claude, codex, cursor, or all.",
    ),
    user: bool = typer.Option(
        False,
        "--user",
        help="Configure the selected host(s) at user scope. Without this flag,"
        " configuration is project-local.",
    ),
    force: bool = typer.Option(
        False, "--force", help="Refresh Cairntir-owned entries even when already present."
    ),
    no_greeting: bool = typer.Option(
        False,
        "--no-greeting",
        "--no-policy",
        help="Skip installing the memory-first startup policy. --no-greeting"
        " remains as a backward-compatible alias.",
    ),
) -> None:
    """Connect Claude Code, Codex, Cursor, or all three to one Cairntir store.

    Existing JSON, TOML, and instruction-file content is preserved. Cairntir
    only replaces blocks carrying its own markers and refuses ambiguous
    conflicts.
    """
    requested = host.strip().lower()
    if requested == "all":
        hosts: tuple[HostName, ...] = SUPPORTED_HOSTS
    elif requested in SUPPORTED_HOSTS:
        hosts = (requested,)
    else:
        choices = ", ".join((*SUPPORTED_HOSTS, "all"))
        typer.echo(f"cairntir: unknown host {host!r}; choose {choices}", err=True)
        raise typer.Exit(code=2)

    scope: HostScope = "user" if user else "project"
    failures = 0
    for selected in hosts:
        try:
            result = configure_host(
                selected,
                scope=scope,
                root=Path.cwd(),
                home=Path.home(),
                force=force,
                install_policy=not no_greeting,
            )
        except HostConfigurationError as exc:
            failures += 1
            typer.echo(f"cairntir: {selected} configuration failed: {exc}", err=True)
            continue

        location = f" in {result.registration_path}" if result.registration_path else ""
        if selected == "claude" and result.registration == "unchanged":
            typer.echo(f"cairntir already registered at {scope} scope{location}")
        else:
            typer.echo(
                f"registered cairntir MCP server for {selected} "
                f"at {scope} scope{location} ({result.registration})"
            )
            if selected == "claude" and result.registration == "already registered":
                typer.echo(
                    "If its launcher is stale, refresh it with "
                    "`cairntir init --user --force --host claude`."
                )
        if selected == "claude" and result.policy_path is not None:
            typer.echo(f"greeting preamble {result.policy} at {result.policy_path}")
        elif result.policy_path is None:
            typer.echo(f"{selected}: policy {result.policy}")
        else:
            typer.echo(f"{selected}: policy {result.policy} at {result.policy_path}")
        if selected == "claude" and force:
            clear_checkpoint()

    if failures:
        raise typer.Exit(code=1)
    typer.echo("restart the configured agent host(s) so they reload MCP and policy settings.")


def _setup_smoke_test() -> None:
    """Write a drawer, read it back, fail loudly if anything is off."""
    from cairntir.memory.taxonomy import Drawer, Layer

    with _open_store(capture_path="cli.setup") as store:
        saved = store.add(
            Drawer(
                wing="cairntir",
                room="setup",
                content="cairntir setup smoke test — if you can read this, it works",
                layer=Layer.ESSENTIAL,
                metadata={"source": "setup"},
            )
        )
        if saved.id is None:
            raise RuntimeError("store.add returned no id")
        fetched = store.get(saved.id)
        if fetched is None or "smoke test" not in fetched.content:
            raise RuntimeError("smoke test drawer did not round-trip")


def _emoji_step(num: int, total: int, title: str) -> None:
    """Print a numbered step header (plain ASCII for terminal compatibility)."""
    typer.echo()
    typer.echo(typer.style(f"[{num}/{total}] {title}", fg=typer.colors.CYAN, bold=True))


def _emoji_ok(message: str) -> None:
    typer.echo(typer.style(f"  ok   {message}", fg=typer.colors.GREEN))


def _emoji_warn(message: str) -> None:
    typer.echo(typer.style(f"  warn {message}", fg=typer.colors.YELLOW))


def _emoji_fail(message: str) -> None:
    typer.echo(typer.style(f"  fail {message}", fg=typer.colors.RED))


def _emoji_tip(message: str) -> None:
    typer.echo(typer.style(f"  tip  {message}", fg=typer.colors.BLUE))


@app.command("setup")
def setup_cmd(
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Accept every default without prompting. Use in scripts and CI.",
    ),
    home: Path | None = typer.Option(None, "--home", help="Override the Cairntir home directory."),  # noqa: B008
) -> None:
    """Interactive setup wizard. The one command a new user ever types.

    Walks you through: checking Claude Code is installed, confirming which
    Python interpreter will be pinned, choosing where Cairntir's memory
    lives, registering the MCP server at user scope, installing the
    greeting preamble so every session actually uses the memory, running
    a smoke test, and telling you exactly what to do next.

    This is the command the docs and the README both point at. If you
    only ever run one Cairntir command in your life, this is it.
    """
    import os
    import shutil
    import subprocess
    import sys

    total = 8

    # ---- Step 1: claude CLI ------------------------------------------------
    _emoji_step(1, total, "Checking Claude Code is installed")
    claude = shutil.which("claude")
    if claude is None:
        _emoji_fail("the `claude` CLI is not on your PATH")
        _emoji_tip("install Claude Code from https://claude.com/claude-code")
        _emoji_tip("then run `cairntir setup` again")
        raise typer.Exit(code=1)
    try:
        version = subprocess.run(  # noqa: S603
            [claude, "--version"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
    except OSError as exc:
        _emoji_fail(f"could not run `claude --version`: {exc}")
        raise typer.Exit(code=1) from exc
    _emoji_ok(f"found {version or 'claude CLI'}")

    # ---- Step 2: Python interpreter ---------------------------------------
    _emoji_step(2, total, "Confirming Python interpreter")
    python = sys.executable
    _emoji_ok(f"pinning to {python}")
    in_venv = hasattr(sys, "real_prefix") or sys.prefix != sys.base_prefix
    if in_venv:
        _emoji_warn("this Python lives inside a virtual environment")
        _emoji_tip(
            "Cairntir will register this exact absolute path, so Claude Code "
            "will find it regardless of which venv is active. If you delete or "
            "move this venv, re-run `cairntir setup`."
        )

    # ---- Step 3: cairntir_home --------------------------------------------
    _emoji_step(3, total, "Choosing where Cairntir's memory lives")
    if home is not None:
        os.environ["CAIRNTIR_HOME"] = str(home)
    resolved_home = cairntir_home()
    _emoji_ok(f"memory directory: {resolved_home}")
    if home is not None:
        _emoji_tip(
            "to make this override permanent, set the CAIRNTIR_HOME environment "
            "variable in your shell profile."
        )
    else:
        _emoji_tip(
            "to move this later, set the CAIRNTIR_HOME environment variable "
            "before launching Claude Code."
        )

    # ---- Step 4: register MCP server user-level ---------------------------
    _emoji_step(4, total, "Registering the MCP server at user scope")
    if not yes:
        confirm = typer.confirm(
            "This will run `claude mcp add -s user cairntir` (replacing any "
            "existing entry). Proceed?",
            default=True,
        )
        if not confirm:
            _emoji_warn("skipped MCP registration — you can run `cairntir init --user` later.")
        else:
            ok, message = _register_user_via_claude_cli(force=True)
            if not ok:
                _emoji_fail(message)
                raise typer.Exit(code=1)
            _emoji_ok("registered")
            for line in message.splitlines():
                typer.echo(f"       {line}")
    else:
        ok, message = _register_user_via_claude_cli(force=True)
        if not ok:
            _emoji_fail(message)
            raise typer.Exit(code=1)
        _emoji_ok("registered")

    # ---- Step 5: greeting preamble ----------------------------------------
    _emoji_step(5, total, "Installing the greeting preamble")
    greeting_path = Path.home() / ".claude" / "CLAUDE.md"
    action = _upsert_greeting(greeting_path)
    _emoji_ok(f"{action} at {greeting_path}")
    _emoji_tip(
        "this file tells every Claude Code session to check Cairntir memory "
        "before answering — without it, the MCP server is wired but silent."
    )

    # ---- Step 6: initialize / migrate the store --------------------------
    _emoji_step(6, total, "Initializing the memory store")
    try:
        _open_store(capture_path="cli.setup").close()
    except MemoryStoreError as exc:
        _emoji_fail(f"could not initialize store: {exc}")
        raise typer.Exit(code=1) from exc
    _emoji_ok(f"store ready at {db_path()}")

    # ---- Step 7: pre-warm the production embedder ------------------------
    _emoji_step(7, total, "Pre-warming the embedder model (one-time download)")
    _emoji_tip(
        "this downloads the ONNX MiniLM model used for semantic search "
        "(~25 MB) and caches it under ~/.cache/fastembed/. After this, "
        "every fresh MCP server boot starts in seconds instead of minutes."
    )
    try:
        provider = production_embedding_provider()
        provider.embed(["cairntir setup warmup probe"])
    except Exception as exc:  # noqa: BLE001 — we want to log + continue, not crash setup
        _emoji_warn(f"embedder warmup did not complete: {type(exc).__name__}: {exc}")
        _emoji_tip(
            "this is not fatal — Cairntir will still work. The first "
            "remember/recall in your next chat may be slow (~10-30s) "
            "while the model downloads on demand. Re-run `cairntir setup` "
            "later to retry the warmup."
        )
    else:
        _emoji_ok("embedder model cached and ready")

    # ---- Step 8: smoke test -----------------------------------------------
    _emoji_step(8, total, "Smoke test: remember + recall")
    try:
        _setup_smoke_test()
    except (MemoryStoreError, RuntimeError) as exc:
        _emoji_fail(f"smoke test failed: {exc}")
        raise typer.Exit(code=1) from exc
    _emoji_ok("write + read round-trip passed")

    # ---- Done -------------------------------------------------------------
    typer.echo()
    typer.echo(typer.style("Cairntir is ready.", fg=typer.colors.GREEN, bold=True))
    typer.echo()
    typer.echo("Next:")
    typer.echo("  1. Fully quit Claude Code — not just close the window.")
    typer.echo("  2. Reopen it in any folder.")
    typer.echo('  3. Ask the fresh chat: "what is cairntir?"')
    typer.echo()
    typer.echo(
        "  If Claude answers with real knowledge and offers to call "
        "cairntir_session_start, you're done."
    )
    typer.echo()
    typer.echo("Learn more:  docs/cairntir-for-dummies.md")
    typer.echo("Troubleshoot: cairntir status     # shows wings + drawer counts")


@app.command("recipe-list")
def recipe_list_cmd() -> None:
    """List every recipe discovered under docs/recipes/ and ~/.claude/recipes/."""
    from cairntir.recipes import discover_recipes, recipe_search_paths

    paths = recipe_search_paths()
    typer.echo(f"search paths ({len(paths)}):")
    for p in paths:
        typer.echo(f"  {p}")
    contracts = discover_recipes()
    if not contracts:
        typer.echo("no recipes found.")
        return
    typer.echo(f"\n{len(contracts)} recipe(s):")
    for c in contracts:
        typer.echo(f"  {c.name} v{c.version}  -> {c.output_wing}")
        typer.echo(f"    {c.description}")
        if c.source_path is not None:
            typer.echo(f"    source: {c.source_path}")


@app.command("recipe-run")
def recipe_run_cmd(
    name: str,
    input_args: list[str] = typer.Option(  # noqa: B008
        [],
        "--input",
        "-i",
        help="Input as KEY=VALUE. Repeat for multiple inputs.",
    ),
    claim: str | None = typer.Option(
        None,
        "--claim",
        help="Falsifiable claim for the reason step. Prompted if the recipe"
        " chains reason and this is omitted.",
    ),
    predicted: str | None = typer.Option(
        None,
        "--predicted",
        help="Predicted outcome for the reason step. Prompted if omitted.",
    ),
    observed: str | None = typer.Option(
        None,
        "--observed",
        help="Observed outcome for the reason step. Prompted if omitted.",
    ),
    success: bool | None = typer.Option(
        None,
        "--success/--fail",
        help="Verdict for the reason step. Prompted if omitted.",
    ),
    idempotency_key: str | None = typer.Option(
        None,
        "--idempotency-key",
        help="Stable retry key. Reusing it replays the recipe result without duplicate writes.",
    ),
) -> None:
    """Execute a named recipe with the given inputs.

    Zero network calls. If the recipe chains the ``reason`` skill, the
    CLI collects the claim / predicted / observed / verdict via flags
    or interactive prompts \u2014 no LLM runs inside Cairntir.
    """
    from cairntir.recipes import RecipeError, RecipeRunner, discover_recipes

    if not db_path().exists():
        typer.echo("cairntir: no store yet \u2014 run `cairntir setup` first.", err=True)
        raise typer.Exit(code=1)

    contracts = {c.name: c for c in discover_recipes()}
    contract = contracts.get(name)
    if contract is None:
        typer.echo(
            f"cairntir: recipe {name!r} not found. Known: {sorted(contracts) or '(none)'}",
            err=True,
        )
        raise typer.Exit(code=1)

    inputs: dict[str, object] = {}
    for raw in input_args:
        if "=" not in raw:
            typer.echo(f"cairntir: --input {raw!r} must be KEY=VALUE", err=True)
            raise typer.Exit(code=1)
        key, value = raw.split("=", 1)
        spec = contract.input_spec(key.strip())
        if spec is None:
            typer.echo(
                f"cairntir: recipe {name!r} has no input named {key!r}",
                err=True,
            )
            raise typer.Exit(code=1)
        inputs[key.strip()] = _coerce_input(value, spec.type)

    from cairntir.production import (
        ManualProposer,
        NullRunner,
        StoreBackedBeliefs,
        StoreBackedMemory,
    )

    needs_reason = "reason" in contract.skills
    if needs_reason:
        if claim is None:
            claim = typer.prompt(f"claim (for recipe {contract.name!r})")
        if predicted is None:
            predicted = typer.prompt("predicted outcome")
        if observed is None:
            observed = typer.prompt("observed outcome")
        if success is None:
            success = typer.confirm("did the prediction hold?", default=False)
    else:
        # Crucible / quality-only recipes don't drive the reason loop;
        # the runner still needs a proposer and runner to satisfy the
        # constructor, but they are never called. Use placeholders.
        claim = claim or ""
        predicted = predicted or ""
        observed = observed or ""
        success = success if success is not None else True

    store = _open_store(capture_path="cli.recipe")
    try:
        recipe_runner = RecipeRunner(
            memory=StoreBackedMemory(store=store),
            beliefs=StoreBackedBeliefs(store=store),
            proposer=ManualProposer(
                claim=claim or "(no claim)",
                predicted_outcome=predicted or "(no predicted outcome)",
            ),
            runner=NullRunner(observed=observed, success=success),
        )
        try:
            result = recipe_runner.run(
                contract,
                inputs,
                idempotency_key=idempotency_key,
            )
        except (RecipeError, ValueError) as exc:
            typer.echo(f"cairntir: recipe execution failed: {exc}", err=True)
            raise typer.Exit(code=1) from exc
    finally:
        store.close()

    typer.echo(f"recipe {result.recipe_name} executed.")
    typer.echo(f"  seed drawer: #{result.seed_drawer_id} in wing {result.output_wing!r}")
    for skill, drawer_ids in result.skill_drawer_ids.items():
        ids = ", ".join(f"#{i}" for i in drawer_ids)
        typer.echo(f"  {skill}: {ids}")


def _coerce_input(raw: str, type_name: str) -> object:
    """Turn a CLI string into the type the recipe declared.

    The recipe contract accepts ``string``, ``url``, ``integer``,
    ``boolean``. Unknown types would have been rejected at load time.
    """
    if type_name in ("string", "url"):
        return raw
    if type_name == "integer":
        try:
            return int(raw)
        except ValueError as exc:
            raise typer.BadParameter(f"expected integer, got {raw!r}: {exc}") from exc
    if type_name == "boolean":
        truthy = {"1", "true", "yes", "on", "y", "t"}
        falsy = {"0", "false", "no", "off", "n", "f"}
        lowered = raw.strip().lower()
        if lowered in truthy:
            return True
        if lowered in falsy:
            return False
        raise typer.BadParameter(f"expected boolean, got {raw!r}")
    raise typer.BadParameter(f"unknown input type {type_name!r}")


def main() -> None:
    """Module entry point for ``python -m cairntir``."""
    app()


if __name__ == "__main__":
    main()
