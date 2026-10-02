"""Independent outcome controls; synthetic side effects only, no real model/store/host."""
from __future__ import annotations

import os
os.environ.setdefault("TYPER_USE_RICH", "0")

import re
import socket
import sqlite3
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from cairntir import cli
from cairntir.errors import EmbeddingError

RUNNER = CliRunner()


def flat(text):
    return re.sub(r"\s+", " ", text.lower()).strip()


def assert_host_unverified(text):
    value = flat(text)
    assert not re.search(r"mcp\s*=\s*(ready|live|verified)\b", value), "CONFIG_IS_NOT_LIVE"
    assert re.search(r"(live|connection|connectivity|host).{0,70}(unverified|not verified|not tested|unknown)", value), "LIVE_UNVERIFIED_REQUIRED"


def assert_setup_honest(text):
    value = flat(text)
    assert "smoke test: remember + recall" not in value, "GET_IS_NOT_SEMANTIC_RECALL"
    assert "cairntir is ready." not in value, "LOCAL_SETUP_IS_NOT_HOST_PROOF"
    assert "offers to call cairntir_handoff, you're done" not in value, "OFFER_IS_NOT_RECEIPT"
    assert "write + read" in value or "write/get" in value or "write and read" in value, "LOCAL_CHECK_MUST_REMAIN_VISIBLE"
    assert re.search(r"semantic.{0,80}(not verified|not tested|unverified)", value), "SEMANTIC_LIMIT_REQUIRED"
    assert_host_unverified(text)
    assert "receipt" in value or "acknowledg" in value, "ACTUAL_SAVE_RECEIPT_REQUIRED"
    assert "task_id" in value or "task id" in value, "TASK_ID_REQUIRED"
    assert re.search(r"fresh (chat|conversation)|new (chat|conversation)", value), "FRESH_CHAT_REQUIRED"
    assert "exact" in value or "verbatim" in value, "EXACT_RECALL_REQUIRED"


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path / "absent-home"))
    monkeypatch.setenv("FASTEMBED_CACHE_PATH", str(tmp_path / "absent-cache"))
    monkeypatch.delenv("CAIRNTIR_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("CAIRNTIR_GRANT_FILE", raising=False)
    monkeypatch.setenv("CAIRNTIR_DISABLE_AUTOREGISTER", "1")
    monkeypatch.setenv("CAIRNTIR_DISABLE_UPDATE_CHECK", "1")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "fake-user"))
    calls = []

    def forbidden(*args, **kwargs):
        raise AssertionError("UNEXPECTED_REAL_SIDE_EFFECT")

    # Actual app commands still run. All external work is blocked at these seams.
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket.socket, "bind", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(threading.Thread, "start", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    monkeypatch.setattr(cli, "_open_store", forbidden)
    monkeypatch.setattr(cli, "configure_host", forbidden)
    monkeypatch.setattr(cli, "production_embedding_provider", lambda: SimpleNamespace(embed=forbidden))
    monkeypatch.setattr(cli, "ensure_registered", lambda: calls.append("registration"))
    monkeypatch.setattr(cli, "maybe_check_in_background", lambda: calls.append("update"))
    monkeypatch.setattr(cli, "pending_update_banner", lambda: None)
    monkeypatch.setattr(cli, "SUPPORTED_HOSTS", ("codex",))
    return SimpleNamespace(root=tmp_path, calls=calls, forbidden=forbidden)


def doctor_fixture(monkeypatch, isolated, *, exists=True, configured=True, stale=False):
    database = isolated.root / "absent-home" / "cairntir.db"
    if exists:
        database.parent.mkdir()
        database.write_bytes(b"synthetic sentinel: never opened as SQLite")
    report = SimpleNamespace(
        state="verified" if exists else "missing", verified=exists,
        current_space_id="synthetic-space", stored_space_id="synthetic-space" if exists else None,
        vector_dimension=32 if exists else None, stored_dimension=32 if exists else None,
        generation="synthetic-generation" if exists else None,
        drawer_count=1 if exists else 0, vector_count=1 if exists else 0,
        detail="synthetic verified index" if exists else "database does not exist",
    )
    monkeypatch.setattr(cli, "inspect_embedding_space", lambda *args, **kwargs: report)
    monkeypatch.setattr(cli, "inspect_database_integrity", lambda *args, **kwargs: SimpleNamespace(
        ok=True, foreign_key_violations=0, started_workflows=0, failed_workflows=0))
    # An old detail string is historical evidence, never a live observation.
    detail = "configured path; historical connection observation 2000-01-01" if stale else "synthetic wiring only"
    monkeypatch.setattr(cli, "inspect_host", lambda *args, **kwargs: SimpleNamespace(
        mcp_configured=configured, mcp_detail=detail,
        policy_configured=True, policy_detail="synthetic policy"))
    return database


def test_doctor_does_not_invoke_registration_or_update(isolated, monkeypatch):
    doctor_fixture(monkeypatch, isolated)
    result = RUNNER.invoke(cli.app, ["doctor"])
    assert result.exit_code == 0, result.output
    assert isolated.calls == [], "DOCTOR_INVOKED_MUTATING_CALLBACK"


def test_doctor_missing_home_is_not_created_or_healthy(isolated, monkeypatch):
    doctor_fixture(monkeypatch, isolated, exists=False)
    result = RUNNER.invoke(cli.app, ["doctor"])
    assert result.exit_code == 1, result.output
    value = flat(result.output)
    assert "missing" in value or "no store" in value or "does not exist" in value
    assert "unverified" in value or "not verified" in value, "MISSING_STORE_MUST_BE_UNVERIFIED"
    assert not (isolated.root / "absent-home").exists(), "DOCTOR_CREATED_HOME"
    assert not (isolated.root / "absent-cache").exists(), "DOCTOR_CREATED_MODEL_CACHE"


def test_doctor_gate_missing_store_preserves_skip_exit_zero(isolated, monkeypatch):
    doctor_fixture(monkeypatch, isolated, exists=False)
    result = RUNNER.invoke(cli.app, ["doctor", "--gate"])
    assert result.exit_code == 0, result.output
    assert "skip" in flat(result.output) and "no store" in flat(result.output)
    assert not (isolated.root / "absent-home").exists(), "DOCTOR_GATE_CREATED_HOME"
    assert isolated.calls == [], "DOCTOR_GATE_INVOKED_MUTATING_CALLBACK"


@pytest.mark.parametrize("configured,stale", [(True, False), (False, False), (None, False), (True, True)])
def test_doctor_configuration_cannot_prove_live_health(isolated, monkeypatch, configured, stale):
    database = doctor_fixture(monkeypatch, isolated, configured=configured, stale=stale)
    before = database.read_bytes()
    result = RUNNER.invoke(cli.app, ["doctor"])
    assert result.exit_code == 0, result.output
    assert_host_unverified(result.output)
    if configured is True:
        assert "configured" in flat(result.output), "CONFIGURATION_RESULT_MUST_REMAIN_VISIBLE"
    elif configured is False:
        assert "missing" in flat(result.output)
    else:
        assert "unknown" in flat(result.output)
    assert database.read_bytes() == before
    assert not (isolated.root / "absent-cache").exists()


def setup_fixture(monkeypatch, isolated, *, missing=False, warmup_warning=False):
    import shutil
    calls = []
    monkeypatch.setattr(shutil, "which", lambda name: None if missing else str(isolated.root / name))
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout="synthetic host 1.0", returncode=0))
    monkeypatch.setattr(cli, "cairntir_home", lambda **kwargs: isolated.root / "setup-home")
    monkeypatch.setattr(cli, "db_path", lambda **kwargs: isolated.root / "setup-home" / "cairntir.db")
    monkeypatch.setattr(cli, "model_cache_dir", lambda **kwargs: isolated.root / "setup-models")
    monkeypatch.setattr(cli, "_echo_manual_cursor_rule", lambda: None)
    monkeypatch.setattr(cli, "clear_checkpoint", lambda: calls.append("clear-checkpoint"))

    def configure(host, **kwargs):
        calls.append("configure")
        if missing:
            raise cli.HostConfigurationError("synthetic host unavailable: no CLI")
        return SimpleNamespace(registration="configured", registration_path=None,
                               policy="configured", policy_path=isolated.root / "policy")

    monkeypatch.setattr(cli, "configure_host", configure)

    class FakeStore:
        def close(self):
            calls.append("close")
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.close()
        def add(self, drawer, **kwargs):
            calls.append("add")
            self.saved = SimpleNamespace(id=17, content=drawer.content)
            return self.saved
        def get(self, drawer_id):
            assert drawer_id == 17
            calls.append("get")
            return self.saved

    monkeypatch.setattr(cli, "_open_store", lambda **kwargs: FakeStore())

    class FakeProvider:
        def embed(self, texts):
            calls.append("synthetic-warmup")
            if warmup_warning:
                raise EmbeddingError("synthetic cache unavailable")
            return [[0.0] * 32 for _ in texts]

    monkeypatch.setattr(cli, "production_embedding_provider", FakeProvider)
    return calls


def test_setup_local_roundtrip_does_not_claim_host_or_semantic_success(isolated, monkeypatch):
    calls = setup_fixture(monkeypatch, isolated)
    result = RUNNER.invoke(cli.app, ["setup", "--yes"])
    assert result.exit_code == 0, result.output
    assert "add" in calls and "get" in calls, "EXERCISE_ACTUAL_SMOKE_FUNCTION"
    assert_setup_honest(result.output)


@pytest.mark.parametrize("missing,warmup_warning", [(True, False), (False, True), (True, True)])
def test_setup_partial_prerequisites_remain_unverified(isolated, monkeypatch, missing, warmup_warning):
    setup_fixture(monkeypatch, isolated, missing=missing, warmup_warning=warmup_warning)
    result = RUNNER.invoke(cli.app, ["setup", "--yes"])
    assert result.exit_code == 0, result.output  # existing nonfatal warning semantics
    assert_setup_honest(result.output)
    value = flat(result.output)
    if missing:
        assert "unavailable" in value or "not on path" in value
    if warmup_warning:
        assert "warmup did not complete" in value
        assert "cairntir will still work" not in value, "WARNING_CANNOT_GUARANTEE_OPERATION"
        assert "downloads on demand" not in value, "OFFLINE_HOST_CANNOT_PROMISE_DOWNLOAD"


HONEST_SETUP = """Local write + read round-trip passed. Semantic recall not tested.
Native host connection unverified. Save a unique task; require the actual acknowledgement
receipt and task_id. In a fresh chat retrieve that exact task and compare verbatim content.
"""


def test_wording_oracles_accept_qualified_local_success():
    assert_setup_honest(HONEST_SETUP)
    assert_host_unverified("MCP=configured; live connection unverified")


@pytest.mark.parametrize("mutation,code", [
    ("MCP=ready; live connection unverified", "CONFIG_IS_NOT_LIVE"),
    ("MCP=configured", "LIVE_UNVERIFIED_REQUIRED"),
])
def test_host_wording_oracle_rejects_causal_optimism(mutation, code):
    with pytest.raises(AssertionError, match=code):
        assert_host_unverified(mutation)


@pytest.mark.parametrize("mutation,code", [
    ("Smoke test: remember + recall. ", "GET_IS_NOT_SEMANTIC_RECALL"),
    ("Cairntir is ready. ", "LOCAL_SETUP_IS_NOT_HOST_PROOF"),
    ("offers to call cairntir_handoff, you're done. ", "OFFER_IS_NOT_RECEIPT"),
])
def test_setup_wording_oracle_rejects_causal_optimism(mutation, code):
    with pytest.raises(AssertionError, match=code):
        assert_setup_honest(mutation + HONEST_SETUP)

def test_version_does_not_invoke_mutating_callback(isolated):
    result = RUNNER.invoke(cli.app, ["version"])
    assert result.exit_code == 0, result.output
    assert "cairntir" in flat(result.output)
    assert isolated.calls == [], "VERSION_INVOKED_MUTATING_CALLBACK"
    assert not (isolated.root / "absent-home").exists()
    assert not (isolated.root / "absent-cache").exists()


def test_status_missing_store_does_not_create_home(isolated):
    result = RUNNER.invoke(cli.app, ["status"])
    assert result.exit_code == 0, result.output
    assert "not yet initialized" in flat(result.output) or "no store" in flat(result.output)
    assert not (isolated.root / "absent-home").exists(), "STATUS_CREATED_HOME"
    assert not (isolated.root / "absent-cache").exists()
    assert isolated.calls == [], "STATUS_INVOKED_MUTATING_CALLBACK"


def test_status_existing_store_uses_readonly_boundary_and_closes(isolated, monkeypatch):
    database = isolated.root / "absent-home" / "cairntir.db"
    database.parent.mkdir()
    database.write_bytes(b"synthetic status sentinel")
    calls = []

    def backend(**kwargs):
        calls.append(kwargs)
        store = SimpleNamespace(wing_counts=lambda: {"synthetic": 2})
        # Existing close_with interface owns closure; record registration of it.
        return SimpleNamespace(_store=store)

    monkeypatch.setattr(cli, "_backend", backend)
    result = RUNNER.invoke(cli.app, ["status"])
    assert result.exit_code == 0, result.output
    assert "drawers: 2" in flat(result.output)
    assert len(calls) == 1 and calls[0].get("read_only") is True, "STATUS_OPENED_WRITABLE_BACKEND"
    assert calls[0].get("close_with") is not None, "STATUS_MISSING_CLOSE_LIFETIME"
    assert isolated.calls == [], "STATUS_INVOKED_MUTATING_CALLBACK"
    assert database.read_bytes() == b"synthetic status sentinel"