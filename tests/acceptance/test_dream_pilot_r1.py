"""Public CLI acceptance for the opt-in, unattended local Dream pilot."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any

import pytest

from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.provenance import Sensitivity, TrustLevel, WriteProvenance

ROOT = Path(__file__).resolve().parents[2]
BOOT = (
    "from cairntir.memory.embeddings import HashEmbeddingProvider; "
    "import cairntir.cli as cli; "
    "cli.production_embedding_provider=lambda:HashEmbeddingProvider(32); "
    "cli.main()"
)
MODEL = "dream-test-local"
PROPOSAL = {
    "proposals": [
        {
            "title": "Review retry policy",
            "proposal": "Review the recorded retry failure before changing policy.",
            "evidence_ids": [999_999],
        }
    ]
}


def _run(home: Path, *args: str, timeout: float = 12) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        CAIRNTIR_HOME=str(home),
        CAIRNTIR_DISABLE_UPDATE_CHECK="1",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        HTTP_PROXY="",
        HTTPS_PROXY="",
        ALL_PROXY="",
        NO_PROXY="127.0.0.1,localhost",
        PYTHONPATH=str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", ""),
    )
    return subprocess.run(  # noqa: S603 - fixed Python executable invokes the public CLI
        [sys.executable, "-c", BOOT, *args],
        cwd=ROOT,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _json(home: Path, *args: str, timeout: float = 12) -> dict[str, Any]:
    result = _run(home, *args, timeout=timeout)
    if result.returncode:
        message = next(
            (line.strip() for line in result.stderr.splitlines() if "No such command" in line),
            result.stderr[-200:],
        )
        pytest.fail(
            f"{' '.join(args)} exited {result.returncode}: {message}",
            pytrace=False,
        )
    value = json.loads(result.stdout)
    assert isinstance(value, dict), value
    return value


def _seed(
    home: Path,
    wing: str,
    content: str,
    *,
    sensitivity: Sensitivity = Sensitivity.NORMAL,
) -> int:
    home.mkdir(parents=True, exist_ok=True)
    provenance = WriteProvenance.create(
        host="dream-test",
        capture_path="fixture",
        trust=TrustLevel.USER_ASSERTED,
        sensitivity=sensitivity,
    )
    with DrawerStore(home / "cairntir.db", HashEmbeddingProvider(32)) as store:
        saved = store.add(Drawer(wing=wing, room="notes", content=content), provenance=provenance)
    assert saved.id is not None
    return saved.id


def _drawer_ids(home: Path) -> list[int]:
    with DrawerStore(home / "cairntir.db", HashEmbeddingProvider(32), read_only=True) as store:
        return [drawer.id for drawer in store.list_by(limit=None) if drawer.id is not None]


def _enable(home: Path, endpoint: str) -> dict[str, Any]:
    receipt = _json(
        home,
        "dream",
        "enable",
        "--scope",
        "all-local",
        "--model",
        MODEL,
        "--endpoint",
        endpoint,
    )
    assert receipt["schema"] == "cairntir.dream-config.v1"
    assert receipt["status"] == "enabled"
    assert receipt["scope"] == "all-local"
    return receipt


def _tick(home: Path, *args: str, timeout: float = 12) -> dict[str, Any]:
    receipt = _json(home, "dream", "tick", *args, timeout=timeout)
    assert receipt["schema"] == "cairntir.dream-tick.v1"
    assert isinstance(receipt["receipt_id"], str) and receipt["receipt_id"]
    return receipt


def _status(home: Path) -> dict[str, Any]:
    status = _json(home, "dream", "status")
    assert status["schema"] == "cairntir.dream-status.v1"
    return status


@contextmanager
def _server(
    response: dict[str, Any] | None = None,
    *,
    port: int = 0,
    delay_seconds: float = 0,
) -> Iterator[tuple[str, list[dict[str, Any]]]]:
    calls: list[dict[str, Any]] = []
    model_response = PROPOSAL if response is None else response

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            size = int(self.headers.get("Content-Length", "0"))
            request = json.loads(self.rfile.read(size))
            calls.append({"path": self.path, "body": request})
            if delay_seconds:
                time.sleep(delay_seconds)
            payload = json.dumps(
                {
                    "model": request.get("model", MODEL),
                    "response": json.dumps(model_response),
                    "done": True,
                }
            ).encode()
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *_args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def test_dream_is_disabled_by_default_without_creating_a_store(tmp_path: Path) -> None:
    home = tmp_path / "home"
    assert _run(home, "version").stdout.startswith("cairntir ")
    status = _status(home)
    assert status["enabled"] is False
    assert status["last_tick"] is None
    tick = _tick(home)
    assert tick["status"] == "disabled"
    assert tick["candidate_id"] is None
    assert not (home / "cairntir.db").exists()


def test_enable_rejects_non_loopback_endpoints_without_enabling(tmp_path: Path) -> None:
    home = tmp_path / "home"
    for endpoint in (
        "https://api.example.test/v1",
        "http://0.0.0.0:11434",
        "http://127.0.0.1@api.example.test:11434",
        "http://127.0.0.1.evil.example:11434",
    ):
        result = _run(
            home,
            "dream",
            "enable",
            "--scope",
            "all-local",
            "--model",
            MODEL,
            "--endpoint",
            endpoint,
        )
        assert result.returncode != 0
        assert _status(home)["enabled"] is False


def test_empty_enabled_store_emits_durable_no_work_without_model_call(tmp_path: Path) -> None:
    home = tmp_path / "home"
    with _server() as (endpoint, calls):
        _enable(home, endpoint)
        tick = _tick(home)
        assert tick["status"] == "no_work"
        assert tick["wing"] is None
        assert tick["evidence_ids"] == []
        assert tick["candidate_id"] is None
        assert calls == []
        status = _status(home)
        assert status["last_tick"]["receipt_id"] == tick["receipt_id"]
        assert status["pending_candidates"] == 0


def test_unselected_local_evidence_yields_sourced_pending_candidate(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source_id = _seed(home, "alpha", "Retry failed after the third attempt.")
    with _server() as (endpoint, calls):
        _enable(home, endpoint)
        tick = _tick(home)
        assert tick["status"] == "candidate"
        assert tick["wing"] == "alpha"
        assert tick["evidence_ids"] == [source_id]
        assert isinstance(tick["candidate_id"], str) and tick["candidate_id"]
        assert tick["candidate_id"] != str(source_id)
        assert len(calls) == 1
        assert calls[0]["path"] == "/api/generate"
        assert calls[0]["body"]["model"] == MODEL
        assert calls[0]["body"]["stream"] is False
        candidate = _json(home, "dream", "candidate", tick["candidate_id"])
        assert candidate["schema"] == "cairntir.dream-candidate.v1"
        assert candidate["candidate_id"] == tick["candidate_id"]
        assert candidate["status"] == "pending"
        assert candidate["wing"] == "alpha"
        assert candidate["evidence_ids"] == [source_id]
        assert 999_999 not in candidate["evidence_ids"]
        assert "Review the recorded retry failure" in candidate["proposal"]
        assert _drawer_ids(home) == [source_id]
        handoff = _run(home, "handoff", "alpha")
        assert handoff.returncode == 0, handoff.stderr
        assert candidate["proposal"] not in handoff.stdout
        recall = _run(home, "recall", "Review the recorded retry failure", "--wing", "alpha")
        assert recall.returncode == 0, recall.stderr
        assert candidate["proposal"] not in recall.stdout
        assert _json(home, "get", str(source_id))["content"] == (
            "Retry failed after the third attempt."
        )


def test_model_can_return_no_useful_proposal_with_visible_receipt(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source_id = _seed(home, "alpha", "A settled issue needs no further action.")
    with _server({"proposals": []}) as (endpoint, calls):
        _enable(home, endpoint)
        tick = _tick(home)
        assert tick["status"] == "no_work"
        assert tick["wing"] == "alpha"
        assert tick["evidence_ids"] == [source_id]
        assert tick["candidate_id"] is None
        assert len(calls) == 1
        assert _status(home)["last_tick"]["receipt_id"] == tick["receipt_id"]


def test_two_wings_get_separate_turns_and_secret_evidence_stays_out(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    alpha = "Alpha retry incident sentinel"
    beta = "Beta backup incident sentinel"
    protected_marker = "PROTECTED_EVALUATOR_PRIVATE_SENTINEL"
    source_ids = {
        "alpha": _seed(home, "alpha", alpha),
        "beta": _seed(home, "beta", beta),
    }
    _seed(home, "alpha", protected_marker, sensitivity=Sensitivity.SECRET)
    with _server() as (endpoint, calls):
        _enable(home, endpoint)
        ticks = [_tick(home), _tick(home)]
        assert {item["wing"] for item in ticks} == {"alpha", "beta"}
        assert len(calls) == 2
        for item, call in zip(ticks, calls, strict=True):
            assert item["evidence_ids"] == [source_ids[item["wing"]]]
            body = json.dumps(call["body"])
            assert (alpha if item["wing"] == "alpha" else beta) in body
            assert (beta if item["wing"] == "alpha" else alpha) not in body
            assert protected_marker not in body


def test_replayed_tick_deduplicates_then_processes_new_evidence(tmp_path: Path) -> None:
    home = tmp_path / "home"
    first_id = _seed(home, "alpha", "Retry policy evidence one.")
    with _server() as (endpoint, calls):
        _enable(home, endpoint)
        first = _tick(home)
        assert first["status"] == "candidate"
        assert first["evidence_ids"] == [first_id]
        replay = _tick(home)
        assert replay["status"] == "no_work"
        assert replay["candidate_id"] is None
        assert len(calls) == 1
        second_id = _seed(home, "alpha", "Retry policy evidence two.")
        second = _tick(home)
        assert second["status"] == "candidate"
        assert second["evidence_ids"] == [second_id]
        assert second["candidate_id"] != first["candidate_id"]
        assert len(calls) == 2
        assert _status(home)["pending_candidates"] == 2
        assert set(_drawer_ids(home)) == {first_id, second_id}


def test_offline_model_keeps_memory_and_pending_work_for_retry(tmp_path: Path) -> None:
    home = tmp_path / "home"
    content = "Keep this decision even when the local model is offline."
    source_id = _seed(home, "alpha", content)
    port = _free_port()
    endpoint = f"http://127.0.0.1:{port}"
    _enable(home, endpoint)
    unavailable = _tick(home)
    assert unavailable["status"] == "model_unavailable"
    assert unavailable["evidence_ids"] == [source_id]
    assert unavailable["candidate_id"] is None
    assert _json(home, "get", str(source_id))["content"] == content
    assert _status(home)["queued_wings"] >= 1
    with _server(port=port) as (_, calls):
        retry = _tick(home)
        assert retry["status"] == "candidate"
        assert retry["evidence_ids"] == [source_id]
        assert len(calls) == 1


def test_tick_limits_inference_and_returns_before_slow_model(tmp_path: Path) -> None:
    home = tmp_path / "home"
    for wing in ("alpha", "beta", "gamma"):
        _seed(home, wing, f"{wing} has unresolved evidence.")
    with _server(delay_seconds=6) as (endpoint, calls):
        _enable(home, endpoint)
        started = time.monotonic()
        tick = _tick(home, "--max-wings", "1", "--timeout-seconds", "1", timeout=5)
        elapsed = time.monotonic() - started
        assert tick["status"] == "model_unavailable"
        assert elapsed < 4
        assert len(calls) <= 1
        assert _status(home)["queued_wings"] >= 2
