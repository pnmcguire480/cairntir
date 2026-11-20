"""Operator-managed cross-device inbox, physically separate from memory stores."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import time
from collections.abc import Iterator
from contextlib import closing, contextmanager
from enum import StrEnum
from pathlib import Path
from uuid import UUID, uuid4

import typer

from cairntir.config import cairntir_home
from cairntir.errors import CairntirError

app = typer.Typer(no_args_is_help=True, help="Manage explicitly shared handoff inboxes.")
MAX_BYTES = 64 * 1024
DDL = """
CREATE TABLE IF NOT EXISTS channels(id TEXT PRIMARY KEY, expires INTEGER,
                                    revoked INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS passes(hash TEXT PRIMARY KEY, channel TEXT NOT NULL, access TEXT,
                                  expires INTEGER, id TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS items(channel TEXT NOT NULL, id TEXT NOT NULL, body TEXT NOT NULL,
                                 result TEXT, PRIMARY KEY(channel,id));
"""


class BridgeError(CairntirError):
    """An exchange was denied or could not be completed."""


class Access(StrEnum):
    """Operations the recipient may perform within one inbox."""

    send = "send"
    receive = "receive"
    exchange = "exchange"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _expiry(minutes: int | None, always: bool) -> int | None:
    if always and minutes is not None:
        raise BridgeError("Choose minutes or always, not both.")
    if always:
        return None
    lifetime = 30 if minutes is None else minutes
    if not 1 <= lifetime <= 1440:
        raise BridgeError("Temporary connections last 1 to 1440 minutes.")
    return int(time.time()) + lifetime * 60


def _check_text(text: str) -> None:
    if not text.strip() or len(text.encode()) > MAX_BYTES:
        raise BridgeError("Supply nonempty text up to 64 KiB.")


class Relay:
    """A relay can access only material deliberately posted to its own database."""

    def __init__(self, path: Path) -> None:
        """Select a dedicated relay database."""
        self.path = path

    @contextmanager
    def db(self, *, setup: bool = False) -> Iterator[sqlite3.Connection]:
        """Serialize authority checks and writes in the same transaction."""
        if not setup and not self.path.is_file():
            raise BridgeError("No bridge is configured.")
        with closing(sqlite3.connect(self.path)) as conn, conn:
            if setup:
                conn.executescript(DDL)
            conn.execute("BEGIN IMMEDIATE")
            yield conn

    def connect(self, minutes: int | None, always: bool) -> str:
        """Create an empty private exchange with no participants."""
        until = _expiry(minutes, always)
        channel = str(uuid4())
        with self.db(setup=True) as db:
            db.execute("INSERT INTO channels(id,expires) VALUES (?,?)", (channel, until))
        return channel

    @staticmethod
    def _channel(db: sqlite3.Connection, channel: str) -> None:
        found = db.execute(
            "SELECT 1 FROM channels WHERE id=? AND revoked=0 AND (expires IS NULL OR expires>?)",
            (channel, int(time.time())),
        ).fetchone()
        if not found:
            raise BridgeError("Connection unavailable.")

    def invite(
        self, channel: str, access: Access, minutes: int | None, always: bool
    ) -> dict[str, str]:
        """Issue one independently revocable participant credential."""
        until = _expiry(minutes, always)
        token, handle = secrets.token_urlsafe(32), str(uuid4())
        with self.db() as db:
            self._channel(db, channel)
            db.execute(
                "INSERT INTO passes VALUES (?,?,?,?,?)",
                (_digest(token), channel, access.value, until, handle),
            )
        return {"pass_id": handle, "bearer": token}

    def revoke(self, handle: str) -> None:
        """Revoke one pass or the entire connection."""
        with self.db() as db:
            if db.execute("DELETE FROM passes WHERE id=?", (handle,)).rowcount:
                return
            if not db.execute("UPDATE channels SET revoked=1 WHERE id=?", (handle,)).rowcount:
                raise BridgeError("Unknown pass or connection.")

    @staticmethod
    def scope(db: sqlite3.Connection, token: str, need: Access | None = None) -> str:
        """Resolve scope from a live credential, never a peer-supplied channel ID."""
        row = db.execute(
            "SELECT channel,access FROM passes WHERE hash=? AND (expires IS NULL OR expires>?)",
            (_digest(token), int(time.time())),
        ).fetchone()
        if not row or (need and row[1] not in (need.value, Access.exchange.value)):
            raise BridgeError("Connection unavailable for this operation.")
        Relay._channel(db, row[0])
        return str(row[0])

    def post(self, token: str, item: UUID, text: str) -> str:
        """Publish one explicit handoff with a client-generated retry key."""
        _check_text(text)
        with self.db() as db:
            channel = self.scope(db, token, Access.send)
            args = (channel, str(item))
            prior = db.execute("SELECT body FROM items WHERE channel=? AND id=?", args).fetchone()
            if prior and prior[0] != text:
                raise BridgeError("Item ID already used for different content.")
            db.execute("INSERT OR IGNORE INTO items(channel,id,body) VALUES (?,?,?)", (*args, text))
        return str(item)

    def pending(self, token: str, after: str = "") -> list[dict[str, str]]:
        """Read up to 50 open IDs and previews, ordered by ID for pagination."""
        with self.db() as db:
            channel = self.scope(db, token, Access.receive)
            rows = db.execute(
                "SELECT id,substr(body,1,120) FROM items WHERE channel=? "
                "AND result IS NULL AND id>? ORDER BY id LIMIT 50",
                (channel, after),
            )
            return [{"id": key, "preview": body} for key, body in rows]

    def read(self, token: str, item: UUID) -> dict[str, str | None]:
        """Read one item as inert evidence; reading leaves it open."""
        with self.db() as db:
            channel = self.scope(db, token, Access.receive)
            row = db.execute(
                "SELECT body,result FROM items WHERE channel=? AND id=?", (channel, str(item))
            ).fetchone()
            if not row:
                raise BridgeError("Item unavailable.")
            return {"text": row[0], "result": row[1]}

    def finish(self, token: str, item: UUID, result: str) -> str:
        """Attach a result atomically, retaining the original evidence."""
        _check_text(result)
        with self.db() as db:
            channel = self.scope(db, token, Access.exchange)
            updated = db.execute(
                "UPDATE items SET result=? WHERE channel=? AND id=? "
                "AND (result IS NULL OR result=?)",
                (result, channel, str(item), result),
            )
            if not updated.rowcount:
                raise BridgeError("Item unavailable or already finished with another result.")
        return str(item)


def local_relay() -> Relay:
    """Point to operator-owned relay state, outside the memory database."""
    directory = cairntir_home() / "bridge"
    directory.mkdir(mode=0o700, exist_ok=True)
    if os.name == "posix" and directory.stat().st_mode & 0o077:
        raise BridgeError("Restrict the relay directory to its owner before use.")
    return Relay(directory / "inbox.sqlite3")


@app.command()
def connect(minutes: int | None = None, always: bool = False) -> None:
    """Create a connection (30 minutes by default); print its nonsecret ID."""
    typer.echo(local_relay().connect(minutes, always))


@app.command()
def invite(channel: str, access: Access, minutes: int | None = None, always: bool = False) -> None:
    """Print one pass for a single participant. Treat bearer as a secret."""
    typer.echo(json.dumps(local_relay().invite(channel, access, minutes, always)))


@app.command()
def revoke(handle: str) -> None:
    """Disconnect a participant by pass ID, or everybody by connection ID."""
    local_relay().revoke(handle)
    typer.echo("revoked")


@app.command()
def serve(port: int = 8765) -> None:
    """Run the isolated bearer-authenticated MCP relay on loopback."""
    from cairntir.bridge_server import serve_relay

    serve_relay(local_relay(), port)
