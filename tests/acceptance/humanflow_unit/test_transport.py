"""Adapter transport boundary: no redirect or ambient proxy can receive source."""

from __future__ import annotations

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

import cairntir.paladin_python as api

REPO = Path(__file__).resolve().parents[3]
assert Path(api.__file__).resolve() == REPO / "src/cairntir/paladin_python.py"

SENTINEL = "R12-PRIVATE-SOURCE-TRANSPORT-SENTINEL"


class _Capture(BaseHTTPRequestHandler):
    def _reply(self):
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 <= length <= 1_000_000:
            self.send_error(413)
            return
        self.server.events.append((self.command, self.path, self.rfile.read(length)))
        status, location = self.server.reply
        self.send_response(status)
        if location is not None:
            self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    do_GET = do_POST = do_CONNECT = _reply  # noqa: N815

    def log_message(self, *_args):
        pass


@contextmanager
def _listener(status, location=None):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Capture)
    server.events = []
    server.reply = (status, location)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def _bundle():
    return {
        "schema": "cairntir.humanflow-bundle.v1",
        "run_id": "transport-run",
        "attempt_id": "transport-attempt",
        "plan_sha256": "0" * 64,
        "checks": {"attempts": []},
        "source_spans": [
            {"attempt_id": "transport-attempt", "path": "src/flow.py", "content": SENTINEL}
        ],
        "artifacts": [],
        "anchors": [],
    }


def _generate(port):
    adapter = api.OllamaNarrationAdapter(
        endpoint=f"http://127.0.0.1:{port}", model="fixture-model", timeout_seconds=5.0
    )
    with pytest.raises(api.PaladinPythonError):
        adapter.generate(_bundle(), reader_level="beginner", max_output_chars=2048)


def test_local_adapter_refuses_redirect_and_ambient_proxy(monkeypatch):
    with _listener(502) as trap:
        other = f"http://127.0.0.1:{trap.server_port}"
        with _listener(307, f"{other}/capture") as origin:
            _generate(origin.server_port)
            assert len(origin.events) == 1
            assert SENTINEL.encode() in origin.events[0][2]
            assert trap.events == []

    with _listener(502) as proxy, _listener(503) as origin:
        proxy_url = f"http://127.0.0.1:{proxy.server_port}"
        for key in (
            "HTTP_PROXY",
            "http_proxy",
            "HTTPS_PROXY",
            "https_proxy",
            "ALL_PROXY",
            "all_proxy",
        ):
            monkeypatch.setenv(key, proxy_url)
        for key in ("NO_PROXY", "no_proxy"):
            monkeypatch.setenv(key, "")
        _generate(origin.server_port)
        assert len(origin.events) == 1
        assert SENTINEL.encode() in origin.events[0][2]
        assert proxy.events == []
