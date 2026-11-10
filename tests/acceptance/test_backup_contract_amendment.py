"""Collect independent controls for due-backup diagnostic and owner boundaries."""

import hashlib
import importlib.util
import runpy
from pathlib import Path
from typing import Any

import pytest

_PACKET = Path(__file__).resolve().parents[2] / "plans/acceptance/backup-contract-20261002"
_CONTROLS = _PACKET / "test_backup_contract_controls_v2.py"
assert hashlib.sha256(_CONTROLS.read_bytes()).hexdigest() == (
    "b9e2a2b5711864511eab70c2d9dc437d0eef6cad3e64cf5623b0e6d4a0df5efd"
)
_namespace = runpy.run_path(str(_CONTROLS))
globals().update({name: value for name, value in _namespace.items() if name.startswith("test_")})


@pytest.fixture()
def backup_contract_case(
    request: pytest.FixtureRequest,
    tmp_cairntir_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Any:
    root = Path(request.config.rootpath)
    relative = "tests/acceptance/test_automatic_backups.py"
    checker = runpy.run_path(str(root / "scripts/check_verification_preservation.py"))
    assert checker["_accepted_alpha_test_amendment"](root, relative, _namespace["LEGACY_SHA256"]), (
        "UNAPPROVED_BACKUP_CONTRACT_CHANGE"
    )
    spec = importlib.util.spec_from_file_location(
        "_independent_backup_contract_v2", root / relative
    )
    assert spec is not None and spec.loader is not None
    current = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(current)
    return current, tuple(current.case.__wrapped__(tmp_cairntir_home, monkeypatch))
