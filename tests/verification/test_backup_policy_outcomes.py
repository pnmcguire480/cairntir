from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from test_recovery_outcomes import contents

from cairntir import backups
from cairntir.errors import BackupError


@pytest.fixture()
def policy(seeded, tmp_path):
    database, _, _ = seeded
    backups.configure(database, tmp_path / "copies")
    configuration = database.with_name(database.name + ".backups.json")
    return database, configuration


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("format", "unknown"),
        ("database", "another-store.db"),
        ("owner", "not-a-uuid"),
        ("enabled", 1),
        ("destination", "relative"),
        ("snapshots", {}),
        ("interval_hours", True),
        ("interval_hours", "12"),
        ("interval_hours", 10**100),
        ("last_success_at", "2026-09-07T10:00:00"),
        ("last_success_at", "9999-12-31T23:59:59+00:00"),
        ("last_error", []),
    ],
)
def test_damaged_policy_is_reported_without_rewriting_it_or_the_store(policy, field, value):
    database, configuration = policy
    state = json.loads(configuration.read_text(encoding="utf-8"))
    state[field] = value
    configuration.write_text(json.dumps(state), encoding="utf-8")
    damaged = configuration.read_bytes()
    before = contents(database)
    for action in (backups.status, backups.run, backups.disable):
        with pytest.raises(BackupError):
            action(database)
    assert configuration.read_bytes() == damaged
    assert contents(database) == before
    assert not list(configuration.parent.rglob("snapshot.db"))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("path", "relative.db"),
        ("size_bytes", 0),
        ("size_bytes", True),
        ("sha256", "f" * 63),
        ("created_at", "not-a-date"),
    ],
)
def test_invalid_snapshot_receipt_cannot_claim_a_usable_backup(policy, field, value):
    database, configuration = policy
    state = json.loads(configuration.read_text(encoding="utf-8"))
    item = {
        "path": str(database),
        "size_bytes": 1,
        "sha256": "a" * 64,
        "created_at": "2026-09-07T00:00:00+00:00",
    }
    item[field] = value
    state["snapshots"] = [item]
    configuration.write_text(json.dumps(state), encoding="utf-8")
    before = contents(database)
    with pytest.raises(BackupError):
        backups.status(database)
    assert contents(database) == before


@pytest.mark.parametrize("failure", ["replace", "fsync"])
def test_failed_policy_write_preserves_previous_settings_and_cleans_temporary_file(
    policy, monkeypatch, failure
):
    database, configuration = policy
    before = configuration.read_bytes(), contents(database)
    files = set(database.parent.iterdir())

    def denied(*args):
        raise OSError("injected destination write failure")

    with monkeypatch.context() as patch:
        patch.setattr(os, failure, denied)
        with pytest.raises(BackupError, match="cannot save backup configuration"):
            backups.disable(database)
    assert (configuration.read_bytes(), contents(database)) == before
    assert set(database.parent.iterdir()) == files
    assert backups.status(database)["enabled"]
    assert not backups.disable(database)["enabled"]


def test_unwritable_policy_reports_both_write_and_cleanup_failures(policy, monkeypatch):
    database, configuration = policy
    before = configuration.read_bytes(), contents(database)
    original_unlink = Path.unlink

    def denied_replace(*args):
        raise OSError("replace denied")

    def denied_cleanup(path, *args, **kwargs):
        if path.name.startswith(f".{configuration.name}."):
            raise OSError("cleanup denied")
        return original_unlink(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(os, "replace", denied_replace)
        patch.setattr(Path, "unlink", denied_cleanup)
        with (
            pytest.warns(backups.BackupWarning, match="cleanup failed: cleanup denied"),
            pytest.raises(BackupError, match="replace denied"),
        ):
            backups.disable(database)
    assert (configuration.read_bytes(), contents(database)) == before
    assert backups.status(database)["enabled"]


def test_policy_read_failure_is_explicit_and_keeps_source_usable(policy):
    database, configuration = policy
    saved = configuration.with_suffix(".saved")
    configuration.rename(saved)
    configuration.mkdir()
    before = contents(database)
    with pytest.raises(BackupError, match="cannot read backup configuration"):
        backups.status(database)
    assert contents(database) == before
    configuration.rmdir()
    saved.rename(configuration)
    assert backups.status(database)["enabled"]


def test_reconfigure_during_backup_keeps_original_policy(policy, tmp_path):
    database, configuration = policy
    before = configuration.read_bytes(), contents(database)
    with backups._lock(database, create=True) as acquired:
        assert acquired
        with pytest.raises(BackupError, match="in progress"):
            backups.configure(database, tmp_path / "elsewhere")
    assert (configuration.read_bytes(), contents(database)) == before


def test_missing_source_and_self_destination_fail_without_creating_a_snapshot(tmp_path):
    database = tmp_path / "missing.db"
    with pytest.raises(BackupError, match="must differ"):
        backups.configure(database, database)
    backups.configure(database, tmp_path / "copies")
    with pytest.raises(BackupError):
        backups.run(database)
    assert not database.exists()
    status = backups.status(database)
    assert status["last_error"] and status["last_success_at"] is None
    assert status["snapshots"] == [] and not list(tmp_path.rglob("snapshot.db"))


@pytest.mark.parametrize(
    "unowned",
    [
        "unexpected-file",
        "bad-marker",
        "foreign-owner",
        "foreign-database",
        "missing-marker",
        "subdirectory",
    ],
)
def test_cleanup_preserves_staging_whose_ownership_cannot_be_proved(policy, unowned):
    database, configuration = policy
    state = json.loads(configuration.read_text(encoding="utf-8"))
    directory = backups._namespace(state) / (".partial-" + "a" * 32)
    directory.mkdir(parents=True)
    claim = directory.with_name(directory.name + ".lock")
    claim.touch()
    marker = {
        "format": "cairntir.backup-pending.v1",
        "owner": state["owner"],
        "database": str(database),
    }
    if unowned == "foreign-owner":
        marker["owner"] = "somebody-else"
    if unowned == "foreign-database":
        marker["database"] = str(database.with_name("other.db"))
    if unowned == "unexpected-file":
        (directory / "user-notes.txt").write_text("never delete this", encoding="utf-8")
    if unowned == "subdirectory":
        (directory / "snapshot.db").mkdir()
    if unowned != "missing-marker":
        (directory / "pending.json").write_text(
            "[]" if unowned == "bad-marker" else json.dumps(marker), encoding="utf-8"
        )
    files = {path: path.read_bytes() for path in directory.iterdir() if path.is_file()}
    if unowned == "missing-marker":
        with pytest.warns(backups.BackupWarning, match="cleanup deferred"):
            backups._clean_partial(directory, state)
    else:
        backups._clean_partial(directory, state)
    assert directory.is_dir() and claim.is_file()
    assert {path: path.read_bytes() for path in directory.iterdir() if path.is_file()} == files


@pytest.mark.parametrize("damage", ["receipt", "snapshot", "extra-file", "missing-file"])
def test_retention_never_deletes_an_archive_that_no_longer_matches_its_receipt(
    policy, tmp_path, damage
):
    database, configuration = policy
    state = json.loads(configuration.read_text(encoding="utf-8"))
    now = datetime(2026, 9, 7, tzinfo=UTC)
    namespace = backups._namespace(state)
    archive = namespace / ("20260101T000000000000Z-" + "b" * 32)
    archive.mkdir(parents=True)
    snapshot = archive / "snapshot.db"
    shutil.copyfile(database, snapshot)
    item = {
        "path": str(snapshot),
        "created_at": (now - timedelta(days=100)).isoformat(),
        "size_bytes": snapshot.stat().st_size,
        "sha256": backups._hash(snapshot, time.monotonic() + 10),
    }
    receipt = archive / "receipt.json"
    receipt.write_text(json.dumps(backups._receipt(state, item)), encoding="utf-8")
    if damage == "receipt":
        receipt.write_text("[]", encoding="utf-8")
    elif damage == "snapshot":
        with snapshot.open("ab") as handle:
            handle.write(b"changed")
    elif damage == "extra-file":
        (archive / "user-notes.txt").write_text("owned by user", encoding="utf-8")
    else:
        snapshot.unlink()
    before = {path: path.read_bytes() for path in archive.iterdir()}
    state["snapshots"] = [item]
    for week in range(2, 6):
        created = now - timedelta(weeks=week)
        newer = namespace / (created.strftime("%Y%m%dT%H%M%S%fZ") + "-" + "c" * 32)
        newer.mkdir()
        copy = newer / "snapshot.db"
        shutil.copyfile(database, copy)
        record = {
            "path": str(copy),
            "created_at": created.isoformat(),
            "size_bytes": copy.stat().st_size,
            "sha256": backups._hash(copy, time.monotonic() + 10),
        }
        (newer / "receipt.json").write_text(
            json.dumps(backups._receipt(state, record)), encoding="utf-8"
        )
        state["snapshots"].append(record)
    expected = list(state["snapshots"])
    result = backups._prune(state, now, time.monotonic() + 10)
    assert result["snapshots"] == expected
    assert {path: path.read_bytes() for path in archive.iterdir()} == before
    assert contents(database)


@pytest.mark.parametrize(
    "failure", ["bad-json", "nonobject", "exit", "timeout", "missing-executable"]
)
def test_actual_worker_failure_preserves_previous_recovery_point_and_reports_failure(
    policy, tmp_path, monkeypatch, failure
):
    database, _ = policy
    first = backups.run(database)["snapshot"]
    snapshot = Path(first["path"])
    before = contents(database), snapshot.read_bytes()
    execute = subprocess.run

    def broken_worker(args, **kwargs):
        replacement = list(args)
        if failure == "bad-json":
            replacement[2] = "print('not json')"
        elif failure == "nonobject":
            replacement[2] = "print('[]')"
        elif failure == "exit":
            replacement[2] = "raise SystemExit(7)"
        elif failure == "timeout":
            replacement[2] = "import time; time.sleep(5)"
            kwargs["timeout"] = 0.05
        else:
            replacement[0] = str(tmp_path / "missing-python")
        return execute(replacement, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(subprocess, "run", broken_worker)
        with pytest.raises(BackupError):
            backups.run(database)
    state = backups.status(database)
    assert state["last_success_at"] == first["created_at"]
    assert state["last_error"] and state["snapshots"] == [first]
    assert (contents(database), snapshot.read_bytes()) == before
    recovered = backups.run(database)
    assert recovered["status"] == "created" and recovered["last_error"] is None
    assert contents(Path(recovered["snapshot"]["path"]), standalone=True) == before[0]


def test_worker_warning_is_visible_without_losing_a_successful_snapshot(policy, monkeypatch):
    database, _ = policy
    before = contents(database)
    execute = subprocess.run

    def noisy_worker(args, **kwargs):
        replacement = list(args)
        replacement[2] = (
            "import sys; print('worker cleanup warning', file=sys.stderr); " + replacement[2]
        )
        return execute(replacement, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(subprocess, "run", noisy_worker)
        with pytest.warns(backups.BackupWarning, match="worker cleanup warning"):
            result = backups.run(database)
    assert result["status"] == "created"
    assert contents(Path(result["snapshot"]["path"]), standalone=True) == before
    assert contents(database) == before


def test_retention_failure_preserves_old_and_new_backups_and_can_be_retried(policy, monkeypatch):
    database, _ = policy
    first = backups.run(database)["snapshot"]
    old = Path(first["path"]).read_bytes()
    before = contents(database)
    execute = subprocess.run

    def interrupted_retention(args, **kwargs):
        replacement = list(args)
        if json.loads(kwargs["input"])["operation"] == "prune":
            replacement[2] = "raise RuntimeError('retention unavailable')"
        return execute(replacement, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(subprocess, "run", interrupted_retention)
        with pytest.warns(backups.BackupWarning, match="backup succeeded; retention deferred"):
            result = backups.run(database)
    assert result["status"] == "created"
    assert Path(first["path"]).read_bytes() == old
    assert contents(Path(result["snapshot"]["path"]), standalone=True) == before
    assert len(backups.status(database)["snapshots"]) == 2
    assert backups.run(database)["status"] == "created"
    assert contents(database) == before
