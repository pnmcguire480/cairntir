"""Collect independent controls for due-backup diagnostic and owner boundaries."""

import hashlib
import runpy
from pathlib import Path

_PACKET = Path(__file__).resolve().parents[2] / "plans/acceptance/backup-contract-20261002"
_CONTROLS = _PACKET / "test_backup_contract_controls.py"
assert hashlib.sha256(_CONTROLS.read_bytes()).hexdigest() == (
    "b76de2e63073ccee2c35aa41edf98af433343e5273902e4fc3deae482f11e496"
)
_namespace = runpy.run_path(str(_CONTROLS))
globals().update(
    {
        name: value
        for name, value in _namespace.items()
        if name.startswith("test_") or name == "backup_contract_case"
    }
)
