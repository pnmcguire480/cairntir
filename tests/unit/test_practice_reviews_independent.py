"""Replay independent R18 frozen public API assertions with normal pytest."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from types import ModuleType

_ASSERTIONS_SHA256 = "e3d16a18750af1094dcff48dcb5169a06d605f752ea57fcc9decb26846941fa5"
_FREEZE_SHA256 = "50bf222db5501c79df88f7d93f28fa02f6f11f597f80661869e32e7b8a3fcc8e"


def _load_controls() -> ModuleType:
    """Load only tester-authored hash-bound controls from the public packet."""
    archive_path = (
        Path(__file__).resolve().parents[2]
        / "plans/acceptance/evidence-practice-review-r18/controls.zip"
    )
    if not archive_path.exists():
        archive_path = Path(__file__).resolve().with_name("controls.zip")
    with zipfile.ZipFile(archive_path) as archive:
        freeze_bytes = archive.read("freeze.json")
        assert hashlib.sha256(freeze_bytes).hexdigest() == _FREEZE_SHA256, (
            "Frozen R18 manifest drift"
        )
        frozen = json.loads(freeze_bytes)
        for name, expected in frozen["sha256"].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == expected, (
                f"Frozen R18 artifact drift: {name}"
            )
        assertions = archive.read("test_r18_controls.py")
        assert hashlib.sha256(assertions).hexdigest() == _ASSERTIONS_SHA256, (
            "Frozen R18 assertion drift"
        )
    module = ModuleType("cairntir_r18_frozen_controls")
    module.__file__ = "frozen-r18/test_r18_controls.py"
    # Execution is restricted to independently authored immutable test source.
    exec(compile(assertions, module.__file__, "exec"), module.__dict__)  # noqa: S102
    return module


_frozen_controls = _load_controls()
globals().update(
    {
        name: value
        for name, value in vars(_frozen_controls).items()
        if name.startswith("test_") or name in {"isolation", "bundle"}
    }
)
