"""Read prior print outcomes through the installed, grant-bound Cairntir core."""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from contextlib import redirect_stdout
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from cairntir.access import AccessDenied, bind_grant, startup_token, validate_startup
from cairntir.config import db_path
from cairntir.errors import (
    CairntirError,
    ConfigError,
    EmbeddingError,
    EmbeddingSpaceError,
    MCPError,
)
from cairntir.mcp.backend import CairntirBackend
from cairntir.memory.embeddings import FastEmbedProvider, production_embedding_provider
from cairntir.memory.store import DrawerStore

REQUEST_SCHEMA = "cairntir.blender-print-recall.request.v1"
RESPONSE_SCHEMA = "cairntir.blender-print-recall.response.v1"
IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9._:-]{0,62}[a-z0-9]\Z", re.ASCII)
MAX_OUTPUT_BYTES = 65536


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError("Invalid recall arguments")


def _request(argv: list[str] | None) -> dict:
    parser = _Parser(add_help=False, allow_abbrev=False)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--wing", required=True)
    parser.add_argument("--material", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--budget-chars", type=int, default=12000)
    args = parser.parse_args(argv)
    identity = UUID(args.request_id)
    wing, room = args.wing.strip().lower(), args.material.strip().lower()
    if (
        identity.version != 4
        or str(identity) != args.request_id
        or not IDENTIFIER.fullmatch(wing)
        or not IDENTIFIER.fullmatch(room)
        or not args.query.strip()
        or len(args.query) > 512
        or not 1 <= args.limit <= 10
        or not 4096 <= args.budget_chars <= 16000
    ):
        raise ValueError("Invalid recall request")
    return {
        "schema": REQUEST_SCHEMA,
        "request_id": args.request_id,
        "wing": wing,
        "room": room,
        "query": args.query,
        "limit": args.limit,
        "budget_chars": args.budget_chars,
    }


def _compact(value: dict) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    )


def _envelope(request: dict | None, status: str) -> dict:
    return {
        "schema": RESPONSE_SCHEMA,
        "request": request,
        "observed_at": datetime.now(UTC).isoformat(),
        "status": status,
        "entries": [],
        "omitted": [],
        "eligible_count": None,
        "error": None,
    }


def _encode(reply: dict) -> tuple[str, int]:
    text = _compact(reply)
    budget = reply["request"]["budget_chars"] if reply["request"] else 12000
    if len(text) > budget or len(text.encode("utf-8")) > MAX_OUTPUT_BYTES:
        raise MCPError("Recall response exceeds its bound")
    return text, 0 if reply["error"] is None else 2


def _error(request: dict | None, status: str, code: str, message: str) -> dict:
    reply = _envelope(request, status)
    reply["error"] = {"code": code, "message": message}
    return reply


def _omission(drawer: dict) -> dict:
    return {
        "id": drawer["id"],
        "resource": drawer["resource"],
        "portable_identity": drawer["portable_identity"],
        "content_hash": drawer["content_hash"],
        "reason": "BUDGET",
    }


def _pack(request: dict, drawers: list[dict], eligible_count: int) -> dict:
    reply = _envelope(request, "omitted" if drawers else "empty")
    reply["eligible_count"] = eligible_count
    reply["omitted"] = [_omission(drawer) for drawer in drawers]
    if len(_compact(reply)) > request["budget_chars"]:
        return _error(
            request, "unavailable", "BUDGET_TOO_SMALL", "Budget cannot fit the required receipts."
        )
    for drawer in drawers:
        omitted = [row for row in reply["omitted"] if row["id"] != drawer["id"]]
        proposed = reply | {
            "entries": [*reply["entries"], {"drawer": drawer}],
            "omitted": omitted,
            "status": "omitted" if omitted else "ok",
        }
        if len(_compact(proposed)) <= request["budget_chars"]:
            reply = proposed
    return reply


def _recall(request: dict) -> tuple[str, int]:
    grant_file = os.environ.get("CAIRNTIR_GRANT_FILE")
    if not grant_file or not Path(grant_file).is_absolute():
        raise AccessDenied("An absolute read-grant file is required")
    token = startup_token()
    if token is None:
        raise AccessDenied("A read grant is required")
    home = os.environ.get("CAIRNTIR_HOME")
    cache = os.environ.get("FASTEMBED_CACHE_PATH")
    if (
        not home
        or not Path(home).is_absolute()
        or (cache is not None and not Path(cache).is_absolute())
    ):
        raise ConfigError("Recall requires absolute trusted configuration")
    path = db_path(create=False)
    validate_startup(path, token)
    provider = production_embedding_provider()
    if not isinstance(provider, FastEmbedProvider):
        raise EmbeddingError("Recall requires the cached production provider")
    provider.artifact_manifest()
    with DrawerStore(path, provider, read_only=True) as store:
        scoped = bind_grant(store, token)
        scoped.authorize("read", wing=request["wing"], room=request["room"])
        candidates = [
            drawer
            for drawer in scoped.list_by(wing=request["wing"], room=request["room"], limit=None)
            if drawer.metadata.get("source") == "blender"
            and drawer.metadata.get("kind") == "print_outcome"
        ]
        ids = [drawer.id for drawer in candidates]
        if any(type(key) is not int or key <= 0 for key in ids):
            raise MCPError("Invalid stored print identity")
        scores = scoped.context_similarities(request["query"], ids)
        selected = sorted(
            candidates, key=lambda drawer: (scores[drawer.id], drawer.id), reverse=True
        )[: request["limit"]]
        backend = CairntirBackend(scoped)
        payloads = []
        for drawer in selected:
            payload = json.loads(backend.get(drawer_id=drawer.id))
            success = payload["metadata"].get("success")
            if "success" in payload["metadata"] and type(success) is not bool:
                raise MCPError("Invalid stored print success")
            payloads.append(payload)
        reply = _pack(request, payloads, len(candidates))
        scoped.authorize("read", wing=request["wing"], room=request["room"])
        for drawer in selected:
            scoped.authorize("read", drawer_id=drawer.id)
        return _encode(reply)


def main(argv: list[str] | None = None) -> int:
    """Emit one bounded scoped recall response and its exit status."""
    for stream in (sys.stdout, sys.stderr):
        if reconfigure := getattr(stream, "reconfigure", None):
            reconfigure(encoding="utf-8", errors="strict")
    try:
        request = _request(argv)
    except (ValueError, TypeError, argparse.ArgumentError):
        text, code = _encode(_error(None, "invalid", "INVALID_REQUEST", "Invalid recall request."))
    else:
        try:
            with redirect_stdout(sys.stderr):
                text, code = _recall(request)
        except AccessDenied:
            text, code = _encode(
                _error(
                    request,
                    "denied",
                    "ACCESS_DENIED",
                    "Read grant does not authorize this request.",
                )
            )
        except EmbeddingSpaceError:
            text, code = _encode(
                _error(
                    request,
                    "unavailable",
                    "INCOMPATIBLE_INDEX",
                    "The semantic index is unavailable or incompatible.",
                )
            )
        except EmbeddingError:
            text, code = _encode(
                _error(
                    request,
                    "unavailable",
                    "LOCAL_MODEL_UNAVAILABLE",
                    "Compatible local embedding assets are unavailable.",
                )
            )
        except ConfigError:
            text, code = _encode(
                _error(
                    request,
                    "unavailable",
                    "CONFIGURATION_ERROR",
                    "Trusted recall configuration is unavailable.",
                )
            )
        except (CairntirError, OSError, sqlite3.Error):
            text, code = _encode(
                _error(
                    request,
                    "unavailable",
                    "READ_UNAVAILABLE",
                    "Stored print evidence could not be read.",
                )
            )
        except (ValueError, TypeError, KeyError, AttributeError):
            text, code = _encode(
                _error(
                    request,
                    "unavailable",
                    "INVALID_RESULT",
                    "Stored print evidence could not be verified.",
                )
            )
    sys.stdout.write(text + "\n")
    sys.stdout.flush()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
