"""Collect independent controls for due-backup diagnostic and owner boundaries."""

import hashlib
import runpy
from pathlib import Path

_PACKET = Path(__file__).resolve().parents[2] / "plans/acceptance/backup-contract-20261002"
_CONTROLS = _PACKET / "test_backup_contract_controls_v2.py"
assert hashlib.sha256(_CONTROLS.read_bytes()).hexdigest() == (
    "b9e2a2b5711864511eab70c2d9dc437d0eef6cad3e64cf5623b0e6d4a0df5efd"
)
_namespace = runpy.run_path(str(_CONTROLS))
globals().update(
    {
        name: value
        for name, value in _namespace.items()
        if name.startswith("test_") or name == "backup_contract_case"
    }
)
