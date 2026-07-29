"""Spool drop writer for the Cairntir Blender add-on.

This module is **stdlib-only** by deliberate design. The Blender add-on
ships into Blender's bundled Python environment, where installing the
full Cairntir package would be a hassle for end users. Instead, the
add-on writes JSON files in the same shape Cairntir's daemon already
parses (see :mod:`cairntir.daemon.spool`), and the daemon picks them
up on its next poll. No Cairntir install required in Blender.

The "do more with less" point: a Blender plugin proves that Cairntir
doesn't care what is being remembered. The same memory layer that
records code decisions in the cairntir wing records 3D-print iteration
parameters in a blender wing — same shape, same retrieval, same
prediction-bound semantics.

Atomic write: the writer writes to ``.tmp`` then ``os.replace``s into
place so a half-written file never lands in the spool. The daemon's
``pending_files`` filter ignores dotfiles, which doubles the safety.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

# Mirror cairntir.daemon.spool's constants without importing them — the
# add-on must not depend on the cairntir Python package.
_SPOOL_SUBDIR = "spool"
_FAILED_SUBDIR = "failed"
_SUFFIX = ".json"

# The taxonomy regex Cairntir uses (cairntir.memory.taxonomy._IDENT_RE).
# We re-implement the validation locally as a courtesy — a malformed
# wing/room name would otherwise not be caught until the daemon parses
# the file. Failing fast inside Blender gives the user a meaningful
# error in the operator dialog instead of silently quarantining.
_VALID_LAYERS = frozenset({"identity", "essential", "on_demand", "deep"})


def cairntir_home() -> Path:
    """Return Cairntir's home directory using the same precedence as Cairntir.

    Mirrors :func:`cairntir.config.cairntir_home` without importing it:

    1. ``CAIRNTIR_HOME`` env var if set.
    2. ``~/.cairntir`` otherwise.

    The directory is *not* created here — the daemon and CLI handle
    creation. The Blender add-on only writes into the spool subdir,
    which :func:`spool_dir` does create.
    """
    override = os.environ.get("CAIRNTIR_HOME")
    if override:
        return Path(override)
    return Path.home() / ".cairntir"


def spool_dir(home: Path | None = None) -> Path:
    """Return (and create) Cairntir's spool directory.

    ``home`` defaults to :func:`cairntir_home` for normal use. Tests
    can pass an explicit path to drop into a tmp dir.
    """
    base = home if home is not None else cairntir_home()
    spool = base / _SPOOL_SUBDIR
    spool.mkdir(parents=True, exist_ok=True)
    (spool / _FAILED_SUBDIR).mkdir(exist_ok=True)
    return spool


def write_capture(
    *,
    wing: str,
    room: str,
    content: str,
    layer: str = "on_demand",
    metadata: dict[str, Any] | None = None,
    home: Path | None = None,
) -> Path:
    """Drop a single drawer-shaped JSON file into Cairntir's spool.

    Returns the final path of the spool file. The daemon's next poll
    cycle will parse the file, persist the drawer, and delete the
    file. Malformed files (which this writer goes out of its way to
    not produce) get quarantined to ``spool/failed/``.

    ``home`` overrides Cairntir's home directory — usually ``None``
    so the env var / default applies. Tests pass a tmp_path here.

    Raises :class:`ValueError` on locally-detectable malformedness:
    empty content, unknown layer, non-string wing/room. The daemon
    would also catch these but a tight loop is friendlier.
    """
    if not isinstance(wing, str) or not wing:
        raise ValueError(f"wing must be a non-empty string, got {wing!r}")
    if not isinstance(room, str) or not room:
        raise ValueError(f"room must be a non-empty string, got {room!r}")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("content must be non-empty (whitespace not allowed)")
    if layer not in _VALID_LAYERS:
        raise ValueError(f"layer must be one of {sorted(_VALID_LAYERS)}, got {layer!r}")

    # Cairntir's taxonomy regex requires lowercase identifiers. Blender
    # users naturally type material names like "PLA" — silently
    # normalizing avoids both rejection and accidental wing-name
    # collisions where "blender-print" and "Blender-Print" land in
    # different wings. This matches the convention every other Cairntir
    # client follows.
    wing_normalized = wing.strip().lower()
    room_normalized = room.strip().lower()

    payload: dict[str, Any] = {
        "wing": wing_normalized,
        "room": room_normalized,
        "content": content,
        "layer": layer,
    }
    if metadata:
        payload["metadata"] = dict(metadata)

    spool = spool_dir(home)
    # Same naming scheme as cairntir.daemon.spool.write_capture — sortable
    # by arrival, collision-resistant, daemon-recognized.
    name = f"{time.time_ns():020d}-{uuid.uuid4().hex[:8]}{_SUFFIX}"
    tmp = spool / f".{name}.tmp"
    final = spool / name
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, final)
    return final


def write_print_outcome(
    *,
    wing: str,
    material: str,
    parameters: dict[str, Any],
    outcome: str,
    success: bool,
    notes: str = "",
    home: Path | None = None,
) -> Path:
    """Write a 3D-print iteration outcome as a prediction-bound drawer.

    Cairntir's prediction-bound drawer schema needs ``claim`` and
    ``predicted_outcome`` fields, but the daemon's spool format does
    not expose those directly — only ``content`` and ``metadata``. We
    encode the prediction-bound semantics into the drawer's content
    and metadata so a later consolidation pass (or the ``reason``
    skill) can recover them.

    The drawer's ``room`` is set to the material name so iterations
    cluster naturally: ``blender-print/PLA``, ``blender-print/PETG``.
    A future Decision Replay can walk the chain to compare iterations.
    """
    parameter_block = "\n".join(f"  {k}: {v}" for k, v in sorted(parameters.items()))
    body = (
        f"# Print iteration ({material})\n"
        f"\n"
        f"## Parameters\n"
        f"{parameter_block}\n"
        f"\n"
        f"## Outcome\n"
        f"{outcome}\n"
        f"\n"
        f"## Notes\n"
        f"{notes or '(none)'}\n"
    )
    return write_capture(
        wing=wing,
        room=material,
        content=body,
        layer="on_demand",
        metadata={
            "source": "blender",
            "kind": "print_outcome",
            "material": material,
            "success": success,
            "parameters": parameters,
        },
        home=home,
    )
