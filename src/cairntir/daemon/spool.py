"""Spool directory: the durable hand-off between capture sites and the daemon.

Anything that wants to persist a drawer without blocking on embedding or
SQLite simply drops a JSON file in ``{cairntir_home}/spool``. The daemon
polls the spool, turns each file into a :class:`~cairntir.memory.taxonomy.Drawer`,
persists it, and deletes the file. Malformed files are quarantined to
``spool/failed`` with a sibling ``.error`` note so they never poison the loop.

The spool format is JSON with this shape::

    {
      "wing":    "cairntir",
      "room":    "decisions",
      "content": "…verbatim…",
      "layer":   "on_demand",
      "metadata": {"source": "reason"}
    }

``layer`` and ``metadata`` are optional.
"""

from __future__ import annotations

import itertools
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Final

_seq = itertools.count()

from cairntir.errors import MCPError
from cairntir.memory.taxonomy import Drawer, Layer

SPOOL_SUBDIR: Final[str] = "spool"
FAILED_SUBDIR: Final[str] = "failed"
_SUFFIX: Final[str] = ".json"


def spool_dir(cairntir_home: Path) -> Path:
    """Return (and create) the spool directory under ``cairntir_home``."""
    path = cairntir_home / SPOOL_SUBDIR
    path.mkdir(parents=True, exist_ok=True)
    (path / FAILED_SUBDIR).mkdir(exist_ok=True)
    return path


def write_capture(
    spool: Path,
    *,
    wing: str,
    room: str,
    content: str,
    layer: str = "on_demand",
    metadata: dict[str, Any] | None = None,
) -> Path:
    """Write a capture event to ``spool`` atomically. Returns the final path."""
    payload: dict[str, Any] = {
        "wing": wing,
        "room": room,
        "content": content,
        "layer": layer,
    }
    if metadata:
        payload["metadata"] = metadata
    # Monotonic timestamp + process-local sequence preserves arrival order even
    # when the clock's resolution is coarser than the call rate (hi, Windows).
    name = (
        f"{time.time_ns():020d}-{next(_seq):08d}-{uuid.uuid4().hex[:8]}{_SUFFIX}"
    )
    tmp = spool / f".{name}.tmp"
    final = spool / name
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, final)
    return final


def pending_files(spool: Path) -> list[Path]:
    """Return ready-to-process spool files in arrival order."""
    files = [
        p
        for p in spool.iterdir()
        if p.is_file() and p.suffix == _SUFFIX and not p.name.startswith(".")
    ]
    files.sort(key=lambda p: p.name)
    return files


def parse_capture(path: Path) -> Drawer:
    """Parse a spool file into a :class:`Drawer`, raising :class:`MCPError` on failure."""
    try:
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise MCPError(f"unreadable spool file {path.name}: {exc}") from exc
    if not isinstance(payload, dict):
        raise MCPError(f"spool file {path.name} is not a JSON object")
    try:
        return Drawer(
            wing=str(payload["wing"]),
            room=str(payload["room"]),
            content=str(payload["content"]),
            layer=Layer(payload.get("layer", "on_demand")),
            metadata=dict(payload.get("metadata") or {}),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise MCPError(f"spool file {path.name} has invalid shape: {exc}") from exc


def quarantine(path: Path, spool: Path, reason: str) -> Path:
    """Move a malformed spool file into ``failed/`` with an ``.error`` sibling."""
    failed_dir = spool / FAILED_SUBDIR
    failed_dir.mkdir(exist_ok=True)
    target = failed_dir / path.name
    os.replace(path, target)
    (failed_dir / f"{path.name}.error").write_text(reason, encoding="utf-8")
    return target
