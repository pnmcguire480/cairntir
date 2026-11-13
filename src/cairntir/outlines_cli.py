"""``cairntir outlines``: expand a selected I02 angle into outlines and next actions (I05)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

import typer

from cairntir.errors import CairntirError

outlines_app = typer.Typer(
    help="Expand your selected angle into production outlines with planned next actions.",
    no_args_is_help=True,
)


def _key(*parts: object) -> str:
    digest = hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()
    return "cli-" + digest[:32]


def _print(receipt: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        typer.echo(json.dumps(receipt, ensure_ascii=False, indent=2))
        return
    typer.echo(
        f"Outline set {receipt['ref']['drawer_id']} for angle {receipt['angle_id']} "
        f"(angle set {receipt['angle_set_revision']}; provisional, human_confirmation=false)"
    )
    if receipt.get("replayed"):
        typer.echo("Stored set returned; the model was not called again.")
    for item in receipt["outlines"]:
        outline = item["outline"]
        length = outline["finished_length"]
        typer.echo(f"\n== {item['request_id']}: {outline['title']}")
        typer.echo(f"Opening hook: {outline['opening']['text']}")
        for index, pair in enumerate(outline["key_points"], 1):
            typer.echo(f"Point {index}: {pair['point']['text']}")
            typer.echo(f"  Example: {pair['example']['text']}")
        for bridge in outline["bridges"]:
            typer.echo(
                f"Bridge {bridge['from_component_id']} -> {bridge['to_component_id']}: "
                f"{bridge['bridge']['text']}"
            )
        typer.echo(f"Close: {outline['close']['text']}")
        typer.echo(f"CTA: {outline['cta']['text']}")
        typer.echo(f"Length: about {length['estimate']} {length['unit']}")
        for note in outline["production_notes"]:
            typer.echo(f"Production note: {note['text']}")
        for action in item["actions"]:
            typer.echo(f"Next action [{action['kind']}] {action['action_id']}: {action['text']}")
            for check in action["completion_checks"]:
                typer.echo(f"  done when: {check}")
    typer.echo(f"\nNote: {receipt['set_note_path']}")


def _run(action: Callable[[Path], dict[str, Any]], store: Path | None, as_json: bool) -> None:
    from cairntir.config import db_path

    try:
        result = action(store if store is not None else db_path(create=False))
    except (CairntirError, sqlite3.Error, OSError, ValueError) as exc:
        typer.echo(f"cairntir: outlines failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    _print(result, as_json=as_json)


@outlines_app.command("generate")
def outlines_generate_cmd(
    wing: str = typer.Option(..., "--wing", "-w"),
    vault: Path = typer.Option(..., "--vault"),  # noqa: B008
    model: str = typer.Option(..., "--model", help="Local Ollama model name."),
    output_format: list[str] = typer.Option(  # noqa: B008
        [],
        "--format",
        help="Intended output as id:unit:minimum:maximum, unit words or seconds. "
        "Defaults to written-post:words:600:900 and short-video:seconds:60:90.",
    ),
    constraint: list[str] = typer.Option(  # noqa: B008
        [], "--constraint", help="Extra production constraint for every format."
    ),
    angle: str | None = typer.Option(
        None, "--angle", help="Angle id; defaults to your latest `angles choose` pick."
    ),
    revision: int | None = typer.Option(None, "--revision", help="Angle set; latest by default."),
    endpoint: str = typer.Option(
        "http://127.0.0.1:11434", "--endpoint", help="Numeric loopback Ollama address."
    ),
    timeout: float | None = typer.Option(
        None,
        "--timeout",
        min=1.0,
        max=360.0,
        help="Seconds per model call: up to 180 per section (default), "
        "up to 360 per whole outline with --single-call.",
    ),
    single_call: bool = typer.Option(
        False,
        "--single-call",
        help="Ask for each whole outline in one model call instead of one call per section.",
    ),
    key: str | None = typer.Option(
        None, "--key", help="Reuse a key to replay; a new key makes a new set."
    ),
    store: Path | None = typer.Option(  # noqa: B008
        None, "--store", help="Defaults to the Cairntir store."
    ),
    as_json: bool = typer.Option(False, "--json", help="Print the full record."),
) -> None:
    """Ask a local model to write each outline section and store complete outlines with actions."""
    from cairntir import cli
    from cairntir.ideation_angle_outlines import (
        DEFAULT_FORMATS,
        angle_context,
        generate_angle_outlines,
        parse_format,
    )
    from cairntir.ideation_outline_assembler import OllamaStagedOutlinesAdapter
    from cairntir.ideation_outlines import OllamaOutlinesAdapter

    def action(path: Path) -> dict[str, Any]:
        formats = [parse_format(value) for value in output_format or DEFAULT_FORMATS]
        seconds = timeout if timeout is not None else (360.0 if single_call else 180.0)
        adapter: OllamaOutlinesAdapter | OllamaStagedOutlinesAdapter
        if single_call:
            adapter = OllamaOutlinesAdapter(endpoint=endpoint, model=model, timeout_seconds=seconds)
        else:
            adapter = OllamaStagedOutlinesAdapter(
                endpoint=endpoint, model=model, timeout_seconds=seconds
            )
        bound = angle_context(path, vault, wing, revision=revision, angle_id=angle)
        idempotency_key = key or _key(
            wing, bound["context"], formats, constraint, model, endpoint, seconds, single_call
        )
        with cli._open_store(path, capture_path="outlines") as drawers:
            return generate_angle_outlines(
                drawers,
                path,
                vault,
                wing,
                formats=formats,
                constraints=constraint,
                adapter=adapter,
                idempotency_key=idempotency_key,
                bound=bound,
                staged=not single_call,
            )

    _run(action, store, as_json)


@outlines_app.command("show")
def outlines_show_cmd(
    wing: str = typer.Option(..., "--wing", "-w"),
    vault: Path = typer.Option(..., "--vault"),  # noqa: B008
    set_id: int | None = typer.Option(None, "--set", help="Outline set drawer id; latest."),
    store: Path | None = typer.Option(  # noqa: B008
        None, "--store", help="Defaults to the Cairntir store."
    ),
    as_json: bool = typer.Option(False, "--json", help="Print the full record."),
) -> None:
    """Reopen a stored outline set, verifying its outlines, actions and source note."""
    from cairntir import cli
    from cairntir.ideation_angle_outlines import show_angle_outlines

    def action(path: Path) -> dict[str, Any]:
        with cli._open_store(path, read_only=True) as drawers:
            return show_angle_outlines(drawers, vault, wing, set_id=set_id)

    _run(action, store, as_json)
