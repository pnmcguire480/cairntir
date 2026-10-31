from __future__ import annotations

import json
import sqlite3
import threading
import time
from concurrent.futures import Future
from contextlib import closing, contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from cairntir import dream
from cairntir import dream_controller as controller
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer


def provider():
    return HashEmbeddingProvider(32)


def wait_for(observe):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        value = observe()
        if value:
            return value
        time.sleep(0.05)
    pytest.fail("Expected lifecycle transition did not occur within 15 seconds")


@pytest.fixture
def lifecycle(tmp_path, monkeypatch):
    model = SimpleNamespace(
        calls=[], received=threading.Event(), release=threading.Event(), blocked=False
    )

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            model.calls.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            model.received.set()
            if model.blocked:
                model.release.wait(10)
            body = json.dumps(
                {
                    "response": json.dumps(
                        {"proposals": [{"title": "Review retry", "proposal": "Inspect the retry."}]}
                    )
                }
            ).encode()
            try:
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                model.disconnected = True

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    path = tmp_path / "cairntir.db"
    content = "Keep this failed retry and its exact evidence: café 日本語."
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))
    with DrawerStore(path, provider()) as store:
        saved = store.add(Drawer(wing="lifecycle", room="evidence", content=content))
    dream.enable(
        path,
        scope="all-local",
        model="controlled-local",
        endpoint=f"http://127.0.0.1:{server.server_port}",
        provider_factory=provider,
    )
    controller.configure(
        path,
        poll_seconds=0.1,
        retry_seconds=1,
        review_seconds=3600,
        inference_seconds=4,
        max_calls=10,
    )
    workers = []
    spawn = controller._spawn_worker

    def observed_spawn(database):
        process, pid = spawn(database)
        workers.append(process)
        return process, pid

    monkeypatch.setattr(controller, "_spawn_worker", observed_spawn)
    try:
        yield path, saved.id, content, model, workers
    finally:
        model.release.set()
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)
        for process in workers:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)


@contextmanager
def running(path):
    result = Future()

    def invoke():
        try:
            result.set_result(controller.run(path, provider))
        except BaseException as exc:  # noqa: BLE001 - Future.result re-raises the thread failure.
            result.set_exception(exc)

    thread = threading.Thread(target=invoke, daemon=True)
    thread.start()
    try:
        wait_for(lambda: controller.status(path)["running"] or result.done())
        if result.done():
            result.result()
            pytest.fail("Controller stopped before accepting a stop request")
        yield result
    finally:
        controller.stop(path)
        thread.join(timeout=10)
        assert not thread.is_alive(), "Controller retained owned work after stop"
        assert result.result(timeout=1)["status"] == "stopped"


def assert_drained(path, workers, drawer_id, content):
    state = controller.status(path)
    assert state["running"] is False and state["active_inference"] is None
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM dream_attempts WHERE done=0"
        ).fetchone() == (0,)
        assert connection.execute("SELECT id,content FROM drawers ORDER BY id").fetchall() == [
            (drawer_id, content)
        ]
    assert workers
    for process in workers:
        assert process.poll() is not None
        assert all(stream.closed for stream in (process.stdin, process.stdout, process.stderr))


def test_failed_launch_is_retained_and_same_work_retries_with_real_worker(lifecycle, monkeypatch):
    path, drawer_id, content, model, workers = lifecycle
    observed_spawn = controller._spawn_worker

    def refuse_launch(_path):
        raise OSError("controlled worker launch failure")

    monkeypatch.setattr(controller, "_spawn_worker", refuse_launch)
    with pytest.raises(OSError, match="controlled worker launch failure"):
        controller.step(path, provider, None)
    assert model.calls == []
    monkeypatch.setattr(controller, "_spawn_worker", observed_spawn)
    recovered = controller.step(path, provider, None)
    interrupted = [
        item for item in controller.receipts(path)["receipts"] if item["status"] == "interrupted"
    ]
    assert len(interrupted) == 1
    prior = interrupted[0]
    assert prior["uncertain"] is True and prior["error"]
    assert prior["evidence_ids"] == [drawer_id] and prior["candidate_id"] is None
    if recovered["status"] == "candidate":
        retried = recovered
    else:
        time.sleep(1.1)
        retried = controller.step(path, provider, None)
    assert retried["status"] == "candidate"
    assert retried["job_id"] == prior["job_id"]
    assert retried["attempt_id"] != prior["attempt_id"]
    assert prior in controller.receipts(path)["receipts"]
    assert len(model.calls) == 1 and controller.status(path)["queued_jobs"] == 0
    candidate = dream.candidate(path, retried["candidate_id"])
    assert candidate["status"] == "pending" and candidate["evidence_ids"] == [drawer_id]
    assert_drained(path, workers, drawer_id, content)


def test_stop_drains_inference_and_restart_finishes_retained_work(lifecycle):
    path, drawer_id, content, model, workers = lifecycle
    model.blocked = True
    with running(path):
        assert model.received.wait(10), "Owned worker never reached the local model"
        owner = controller.status(path)["controller_id"]
        assert controller.stop(path)["status"] == "stopped"
    interrupted = [
        item for item in controller.receipts(path)["receipts"] if item["status"] == "interrupted"
    ]
    assert len(interrupted) == 1
    prior = interrupted[0]
    assert prior["controller_id"] == owner
    assert prior["uncertain"] is True and prior["candidate_id"] is None
    assert prior["evidence_ids"] == [drawer_id]
    assert controller.status(path)["queued_jobs"] == 1
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM dream_candidates").fetchone() == (0,)
    assert_drained(path, workers, drawer_id, content)
    model.blocked = False
    model.release.set()
    with running(path):
        completed = wait_for(
            lambda: [
                item
                for item in controller.receipts(path)["receipts"]
                if item["status"] == "candidate"
            ]
        )
        assert len(completed) == 1
        retried = completed[0]
        assert retried["controller_id"] != owner
        assert retried["job_id"] == prior["job_id"]
        assert retried["attempt_id"] != prior["attempt_id"]
    assert prior in controller.receipts(path)["receipts"]
    assert len(model.calls) == 2 and controller.status(path)["queued_jobs"] == 0
    assert dream.candidate(path, retried["candidate_id"])["evidence_ids"] == [drawer_id]
    assert_drained(path, workers, drawer_id, content)
