"""Collect independently amended real-store controls with immutable hash pins."""

import hashlib
import runpy
from pathlib import Path

_PACKET = Path(__file__).resolve().parents[2] / "plans/acceptance/core-status-20261001"
_PINS = {
    "FROZEN.json": "a0fd71e5ddcea39356d0c9ef5e9b8acbbbf558d179546e5b5f7f220f79a7d21f",
    "FIXTURE-AMENDMENT.json": "64fe9f9701e62a47f2272535537a2656c262ed94fd8cb38f19334ef4ef7e2247",
    "FIXTURE-CLOSE-AMENDMENT.json": (
        "de29da00b15b63740f3998c5fd6903fc9a982f8f16703281bbb9b93ce6098585"
    ),
    "test_status_metadata_v3.py": (
        "b85f114e488887f3d1317ec4b4602d1ee28d4feab70b8bfa1eff2b9c6e317c22"
    ),
}
for _name, _expected in _PINS.items():
    assert hashlib.sha256((_PACKET / _name).read_bytes()).hexdigest() == _expected

_namespace = runpy.run_path(str(_PACKET / "test_status_metadata_v3.py"))
globals().update(
    {
        name: value
        for name, value in _namespace.items()
        if name.startswith("test_") or name == "bank"
    }
)
