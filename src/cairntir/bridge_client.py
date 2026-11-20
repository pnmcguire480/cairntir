"""Explicit participant transfers for operator-selected text or portable bundles."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

import httpx
import typer
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from cairntir.bridge import MAX_BYTES, BridgeError, app

__all__ = ["app"]


async def _call(name: str, args: dict[str, str]) -> dict[str, object]:
    url = os.environ.get("CAIRNTIR_BRIDGE_URL", "")
    token = os.environ.get("CAIRNTIR_BRIDGE_PASS", "")
    addr = urlsplit(url)
    local = addr.scheme == "http" and addr.hostname in {"localhost", "127.0.0.1", "::1"}
    if not token or not addr.hostname or (addr.scheme != "https" and not local):
        raise BridgeError("Configure a participant pass and an HTTPS (or loopback) bridge URL.")
    if addr.username or addr.password or addr.query or addr.fragment:
        raise BridgeError("Use a plain bridge endpoint URL.")
    async with (
        httpx.AsyncClient(headers={"Authorization": "Bearer " + token}, trust_env=False) as http,
        streamable_http_client(url, http_client=http) as (reader, writer, _),
        ClientSession(reader, writer) as peer,
    ):
        await peer.initialize()
        reply = await peer.call_tool(name, args)
        if reply.isError or reply.structuredContent is None:
            raise BridgeError("Peer denied the operation or returned an invalid receipt.")
        return reply.structuredContent


def _request(name: str, args: dict[str, str]) -> dict[str, object]:
    try:
        return asyncio.run(_call(name, args))
    except (BridgeError, ExceptionGroup, httpx.HTTPError, OSError) as exc:
        typer.echo(
            "Transfer unconfirmed. Check endpoint, pass, scope and expiry before retry.", err=True
        )
        raise typer.Exit(1) from exc


@app.command("send-file")
def send_file(item_id: UUID, path: Path) -> None:
    """Send exactly one explicitly selected UTF-8 file. Reuse item ID for retries."""
    with path.open("rb") as source:
        raw = source.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise typer.BadParameter("Selected file exceeds 64 KiB.")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise typer.BadParameter("Select a UTF-8 text file.") from exc
    _request("bridge_send", {"item_id": str(item_id), "text": text})
    typer.echo(str(item_id))


@app.command("receive-file")
def receive_file(item_id: UUID, path: Path) -> None:
    """Save one selected item to a new file for review before a separate import."""
    reply = _request("bridge_read", {"item_id": str(item_id)})
    text = reply.get("text")
    if not isinstance(text, str):
        raise typer.BadParameter("Peer returned an invalid handoff.")
    with path.open("xb") as destination:
        destination.write(text.encode("utf-8"))
    typer.echo(str(path))
