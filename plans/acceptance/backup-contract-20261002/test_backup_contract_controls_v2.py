"""Real subprocess controls for diagnostic purity and writable owner backup startup."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

LEGACY_SHA256 = "8339755f367d8e9a91013651b28f69b53b6e95662da465b4cfffb6801b4a6da5"


@pytest.fixture()
def backup_contract_case(
    request: pytest.FixtureRequest,
    tmp_cairntir_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Any:
    path = Path(request.config.rootpath) / "tests/acceptance/test_automatic_backups.py"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == LEGACY_SHA256
    spec = importlib.util.spec_from_file_location("_independent_backup_contract_legacy", path)
    assert spec is not None and spec.loader is not None
    legacy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(legacy)
    # Reuse the unchanged synthetic fixture and actual CLI/copy helpers.
    case = legacy.case.__wrapped__(tmp_cairntir_home, monkeypatch)
    return legacy, tuple(case)


def test_due_backup_does_not_make_status_mutating(backup_contract_case: Any) -> None:
    legacy, (api, db, destination, _) = backup_contract_case
    api.configure(db, destination)
    policy = api.status(db)
    assert policy["enabled"] is True and policy["snapshots"] == []
    assert not policy["last_success_at"]
    before = legacy._tree(db.parent.parent)
    result = legacy._cli("status")
    assert result.returncode == 0, result.stderr
    assert legacy.WING in result.stdout
    assert "index readiness: unverified" in result.stdout.lower()
    assert api.status(db) == policy, "STATUS_CHANGED_DUE_BACKUP_POLICY"
    assert legacy._tree(db.parent.parent) == before, "STATUS_CREATED_OR_CHANGED_FILES"
    assert not destination.exists(), "STATUS_CREATED_BACKUP_DESTINATION"


def test_owner_get_still_activates_exactly_one_complete_due_backup(
    backup_contract_case: Any,
) -> None:
    legacy, (api, db, destination, _) = backup_contract_case
    api.configure(db, destination)
    before = legacy._state(db)
    result = legacy._cli("get", "1")
    assert result.returncode == 0, result.stderr
    returned = json.loads(result.stdout)
    assert type(returned["id"]) is int and returned["id"] == 1
    assert returned["wing"] == legacy.WING
    state = api.status(db)
    assert len(state["snapshots"]) == 1, "WRITABLE_OWNER_STARTUP_DID_NOT_BACK_UP"
    copied = legacy._snapshot({"status": "created", "snapshot": state["snapshots"][0]})
    assert copied.is_relative_to(destination)
    assert legacy._state(copied, standalone=True) == before
    again = legacy._cli("get", "1")
    assert again.returncode == 0, again.stderr
    assert json.loads(again.stdout) == returned
    assert api.status(db)["snapshots"] == state["snapshots"], "OWNER_GET_IGNORED_CADENCE"
