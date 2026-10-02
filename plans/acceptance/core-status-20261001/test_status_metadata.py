"""Independent real-store metadata outcomes; no runtime/model work at authoring time."""
from __future__ import annotations

import os
os.environ.setdefault("TYPER_USE_RICH", "0")

import re
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from cairntir import access, cli
from cairntir.errors import AccessDenied, EmbeddingError, EmbeddingSpaceError
from cairntir.memory import store as storage
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.taxonomy import Drawer

RUNNER = CliRunner()


def inventory(directory):
    return {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in directory.iterdir() if path.is_file()
    }


def flat(value):
    return re.sub(r"\s+", " ", value.lower())


@pytest.fixture
def bank(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    home = tmp_path / "source"
    home.mkdir()
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    database = home / "cairntir.db"
    monkeypatch.setenv("CAIRNTIR_HOME", str(home))
    monkeypatch.setenv("FASTEMBED_CACHE_PATH", str(tmp_path / "absent-models"))
    monkeypatch.delenv("CAIRNTIR_GRANT_FILE", raising=False)
    monkeypatch.setenv("CAIRNTIR_DISABLE_AUTOREGISTER", "1")
    monkeypatch.setenv("CAIRNTIR_DISABLE_UPDATE_CHECK", "1")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "fake-user"))
    # Genuine schema/vector metadata: three persisted Hash64 drawers, two wings.
    with storage.DrawerStore(database, HashEmbeddingProvider(dimension=64), backup_migrations=False) as store:
        for wing, content in [("alpha", "first evidence"), ("alpha", "second evidence"), ("beta", "third evidence")]:
            store.add(Drawer(wing=wing, room="synthetic", content=content))
    before = inventory(home)
    schema_bytes = database.read_bytes()[60:64]  # SQLite header user_version
    state = SimpleNamespace(home=home, database=database, snapshots=snapshots,
                            before=before, schema_bytes=schema_bytes, calls=[], failure=None,
                            provider_calls=[], root=tmp_path)
    monkeypatch.setattr(tempfile, "tempdir", str(snapshots))

    def forbidden(*args, **kwargs):
        raise AssertionError("UNEXPECTED_EXTERNAL_OR_WRITABLE_OPERATION")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket.socket, "bind", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(cli, "ensure_registered", forbidden)
    monkeypatch.setattr(cli, "maybe_check_in_background", forbidden)
    monkeypatch.setattr(cli, "pending_update_banner", lambda: None)
    # A status implementation must not fall back to the writable constructor.
    monkeypatch.setattr(storage.DrawerStore, "_connect", staticmethod(forbidden))
    original_run = subprocess.run

    def snapshot_run(argv, **kwargs):
        assert isinstance(argv, list) and len(argv) == 5, "UNEXPECTED_CHILD_ARGUMENTS"
        assert argv[1] == "-c" and "_copy_locked_database" in argv[2], "UNEXPECTED_CHILD_CODE"
        source, destination = Path(argv[-2]), Path(argv[-1])
        assert source.resolve() == database.resolve(), "UNEXPECTED_SNAPSHOT_SOURCE"
        assert destination.resolve().is_relative_to(snapshots.resolve()), "SNAPSHOT_ESCAPED_TEMP"
        state.calls.append((source, destination))
        if state.failure == "helper":
            destination.write_bytes(b"incomplete snapshot")
            raise subprocess.CalledProcessError(1, argv, stderr="synthetic snapshot failure")
        if state.failure == "query":
            # Genuine SQLite copy with deliberately damaged query subject.
            shutil.copyfile(source, destination)
            import sqlite3
            with sqlite3.connect(destination) as connection:
                connection.execute("DROP TABLE drawers")
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        if os.environ.get("CAIRNTIR_TEST_REAL_SNAPSHOT") == "1":
            # Parent-authorized serial integration only: unchanged actual helper.
            return original_run(argv, **kwargs)
        # Unit isolation replaces only transport for this closed synthetic DB.
        shutil.copyfile(source, destination)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", snapshot_run)
    yield state
    assert inventory(home) == before, "SOURCE_BYTES_OR_MTIME_CHANGED"
    assert database.read_bytes()[60:64] == schema_bytes, "SOURCE_SCHEMA_CHANGED"
    assert list(snapshots.iterdir()) == [], "SNAPSHOT_LEAKED"
    assert not (tmp_path / "absent-models").exists(), "MODEL_CACHE_CREATED"


def active_provider(monkeypatch, bank, dimension):
    provider = HashEmbeddingProvider(dimension=dimension)
    def forbidden_embed(*args, **kwargs):
        raise AssertionError("STATUS_MUST_NOT_EMBED")
    monkeypatch.setattr(provider, "embed", forbidden_embed)
    def factory():
        bank.provider_calls.append("factory")
        return provider
    monkeypatch.setattr(cli, "production_embedding_provider", factory)
    return provider


def assert_counts(result):
    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"
    text = flat(result.output)
    assert "wings: 2" in text and "drawers: 3" in text, "COUNTS_UNAVAILABLE"
    assert re.search(r"alpha\s+\(2 drawers\)", text)
    assert re.search(r"beta\s+\(1 drawers\)", text)


def assert_index_unverified(result):
    assert re.search(r"index.{0,55}(unverified|not assessed|not verified|mismatch)", flat(result.output)), "COUNTS_ARE_NOT_INDEX_READINESS"


@pytest.mark.parametrize("dimension", [64, 32])
def test_status_counts_compatible_and_mismatched_store(bank, monkeypatch, dimension):
    active_provider(monkeypatch, bank, dimension)
    result = RUNNER.invoke(cli.app, ["status"])
    assert_counts(result)
    assert_index_unverified(result)
    assert bank.calls, "SNAPSHOT_TRANSPORT_NOT_EXERCISED"
    assert bank.provider_calls == [], "COUNTS_SHOULD_NOT_INSTANTIATE_PROVIDER"


def test_status_counts_when_provider_is_unavailable(bank, monkeypatch):
    def unavailable():
        bank.provider_calls.append("unavailable")
        raise EmbeddingError("synthetic model/provider unavailable")
    monkeypatch.setattr(cli, "production_embedding_provider", unavailable)
    result = RUNNER.invoke(cli.app, ["status"])
    assert_counts(result)
    assert_index_unverified(result)
    assert bank.provider_calls == [], "COUNTS_DEPEND_ON_PROVIDER"


@pytest.mark.parametrize("failure", ["helper", "query"])
def test_status_failure_closes_snapshot_and_preserves_source(bank, monkeypatch, failure):
    active_provider(monkeypatch, bank, 64)
    bank.failure = failure
    result = RUNNER.invoke(cli.app, ["status"])
    assert result.exit_code != 0, "FAILED_SNAPSHOT_REPORTED_SUCCESS"
    assert "drawers: 3" not in flat(result.output)
    assert bank.calls, "SNAPSHOT_FAILURE_NOT_REACHED"
    assert "snapshot" in str(result.exception).lower() or "database" in str(result.exception).lower() or "count" in str(result.exception).lower() or "failed" in flat(result.output)
    # Cleanup/source invariants also run as fixture finalizers on failed assertions.
    assert list(bank.snapshots.iterdir()) == [], "FAILED_SNAPSHOT_LEAKED"


def test_semantic_readonly_store_still_rejects_mismatched_space(bank):
    with pytest.raises(EmbeddingSpaceError, match="semantic index"):
        storage.DrawerStore(bank.database, HashEmbeddingProvider(dimension=32), read_only=True)
    assert bank.calls
    assert list(bank.snapshots.iterdir()) == []


def test_status_restricted_administration_remains_denied(bank, monkeypatch):
    monkeypatch.setattr(access, "startup_token", lambda: "synthetic-existing-grant")
    monkeypatch.setattr(access, "validate_startup", lambda *args: None)
    result = RUNNER.invoke(cli.app, ["status"])
    assert result.exit_code != 0
    assert isinstance(result.exception, AccessDenied)
    assert "administrative command denied" in str(result.exception)
    assert "drawers: 3" not in flat(result.output)
    assert bank.calls == [], "DENIED_STATUS_OPENED_SNAPSHOT"