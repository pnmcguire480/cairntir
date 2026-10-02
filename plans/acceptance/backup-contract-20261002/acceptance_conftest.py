"""Load the explicit, hash-bound amendment for one legacy backup startup probe."""

import hashlib
import runpy
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_PACKET = _ROOT / "plans/acceptance/backup-contract-20261002"
_LEGACY = _ROOT / "tests/acceptance/test_automatic_backups.py"
assert hashlib.sha256(_LEGACY.read_bytes()).hexdigest() == (
    "8339755f367d8e9a91013651b28f69b53b6e95662da465b4cfffb6801b4a6da5"
)
_ADAPTER = _PACKET / "backup_probe_adapter.py"
assert hashlib.sha256(_ADAPTER.read_bytes()).hexdigest() == (
    "a2c8310a90c37dd2509025f0c842303ca04f39fc429c0b78bebffeaad56f30a2"
)
approved_owner_backup_probe = runpy.run_path(str(_ADAPTER))["approved_owner_backup_probe"]
