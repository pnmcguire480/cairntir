"""Replay independently frozen R18 scope repair assertions with ordinary pytest."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from types import ModuleType

_ASSERTIONS_SHA256 = "94738fae1dd2533cfad1925f66ebb58488bd6ce8f6f0500220f30fbf0ad80ed6"
_FREEZE_SHA256 = "c6833aea50a760569903f06ee4912c689b2245bd5f75a73f9f2ced33ba15233a"


def _load_controls() -> ModuleType:
    """Execute only the independent, pre-repair hash-bound assertion source."""
    archive_path = (
        Path(__file__).resolve().parents[2]
        / "plans/acceptance/evidence-practice-review-r18/repair-controls.zip"
    )
    if not archive_path.exists():
        archive_path = Path(__file__).resolve().with_name("repair-controls.zip")
    with zipfile.ZipFile(archive_path) as archive:
        freeze_bytes = archive.read("repair-round2/freeze.json")
        assert hashlib.sha256(freeze_bytes).hexdigest() == _FREEZE_SHA256
        frozen = json.loads(freeze_bytes)
        for name, expected in frozen["sha256"].items():
            assert hashlib.sha256(archive.read(f"repair-round2/{name}")).hexdigest() == expected
        original = archive.read("controls.zip")
        assert hashlib.sha256(original).hexdigest() == frozen["original_packet_sha256"]
        assertions = archive.read("repair-round2/test_r18_scope_repair.py")
        assert hashlib.sha256(assertions).hexdigest() == _ASSERTIONS_SHA256
    module = ModuleType("cairntir_r18_scope_frozen_controls")
    # The original fixture archive resolves relative to this real adapter path.
    module.__file__ = __file__
    exec(compile(assertions, "frozen-r18/repair-round2.py", "exec"), module.__dict__)  # noqa: S102
    return module


_frozen_controls = _load_controls()
globals().update(
    {
        name: value
        for name, value in vars(_frozen_controls).items()
        if name.startswith("test_") or name in {"bundle", "isolation"}
    }
)
