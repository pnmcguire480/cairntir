"""Portable original local model and a narrow public CLI/store adapter."""

import hashlib
import json
import os
import sqlite3
import threading
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import test_dream_pilot_r1 as pilot

import cairntir
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore


def utc():
    return datetime.now(UTC).isoformat()


def save(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)


class Model:
    def __init__(self, root, mode="good", db=None):
        self.root, self.mode, self.db = root, mode, db
        self.calls = []
        self.releases = threading.Event()

    def __enter__(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                request = self.rfile.read(int(self.headers["Content-Length"]))
                call = {
                    "start": time.monotonic(),
                    "utc": utc(),
                    "body": request.decode(),
                    "end": None,
                }
                if owner.db is not None:
                    with sqlite3.connect(f"{owner.db.as_uri()}?mode=ro", uri=True) as connection:
                        call["claims"] = connection.execute("SELECT * FROM dream_claims").fetchall()
                owner.calls.append(call)
                try:
                    mode = owner.mode
                    if mode == "redirect":
                        self.send_response(302)
                        self.send_header("Location", owner.redirect)
                        self.end_headers()
                        return
                    self.send_response(200)
                    self.end_headers()
                    if mode == "drip":
                        while not owner.releases.is_set():
                            self.wfile.write(b" ")
                            self.wfile.flush()
                            time.sleep(0.02)
                        return
                    if mode == "oversized":
                        body = b"x" * 65537
                    elif mode == "malformed":
                        body = b"{"
                    elif mode == "invalid-proposals":
                        body = json.dumps({"response": json.dumps({"proposals": "wrong"})}).encode()
                    else:
                        body = json.dumps(
                            {
                                "response": json.dumps(
                                    {
                                        "proposals": [
                                            {
                                                "title": "Bounded proposal",
                                                "proposal": "Review the recorded retry.",
                                            }
                                        ]
                                    }
                                )
                            }
                        ).encode()
                    self.wfile.write(body)
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    call["disconnected"] = True
                finally:
                    call["end"] = time.monotonic()
                    save(
                        owner.root / f"model-{len(owner.calls):03d}-{threading.get_ident()}.json",
                        call,
                    )

            def log_message(self, *_args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.endpoint = f"http://127.0.0.1:{self.server.server_port}"
        return self

    def __exit__(self, *_args):
        self.releases.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)


class Harness:
    def __init__(self, root):
        self.root = root
        self.home = root / "home"
        self.home.mkdir(parents=True)
        self.db = self.home / "cairntir.db"
        assert Path(cairntir.__file__).resolve().parent == pilot.ROOT / "src/cairntir"
        self.package = (pilot.ROOT / "src/cairntir").resolve()
        self.modules = {
            path.relative_to(self.package).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(self.package.rglob("*.py"))
        }
        self.expected = root / "EXPECTED-ORIGIN.json"
        save(self.expected, {"package": str(self.package), "modules": self.modules})
        self.sequence = 0

    def seed(self):
        self.content = "LATENCY_SOURCE: the retry failed after its third attempt."
        self.source_id = pilot._seed(self.home, "alpha", self.content)

    def cli(self, *args):
        return self._invoke(args)

    def _invoke(self, args, check=True):
        self.sequence += 1
        prefix = self.root / f"call-{self.sequence:02}"
        provider = pilot.ROOT / "tests/acceptance/dream_status_unit/provider"
        with patch.dict(
            os.environ,
            {
                "DREAM_STATUS_EXPECTED": str(self.expected),
                "DREAM_STATUS_IMPORT": str(prefix.with_suffix(".import.json")),
                "PYTHONPATH": str(provider),
                "PYTHONDONTWRITEBYTECODE": "1",
                "CAIRNTIR_DISABLE_AUTOREGISTER": "1",
            },
        ):
            result = (pilot._json if check else pilot._run)(self.home, "dream", *args, timeout=15)
        origins = [
            json.loads(path.read_bytes()) for path in self.root.glob(prefix.name + ".import-*.json")
        ]
        assert origins
        assert all(
            origin["package"] == str(self.package) and origin["modules"] == self.modules
            for origin in origins
        )
        return result

    def enable(self, endpoint, configured=False, timeout=6):
        self.cli(
            "enable", "--scope", "all-local", "--model", "latency-fixture", "--endpoint", endpoint
        )
        if configured:
            self.cli(
                "configure",
                "--poll-seconds",
                "0.2",
                "--retry-seconds",
                "1",
                "--inference-seconds",
                str(timeout),
                "--max-calls",
                "8",
                "--window-seconds",
                "60",
            )

    def snapshot(self):
        with DrawerStore(self.db, HashEmbeddingProvider(32), read_only=True) as store:
            return [
                {
                    "drawer": drawer.model_dump(mode="json"),
                    "provenance": store.get_provenance(drawer.id).to_dict(),
                    "identity": store.portable_identity(drawer.id),
                }
                for drawer in store.list_by(limit=None)
            ]

    def candidates(self):
        return self.cli("status")["pending_candidates"]

    def cleanup(self):
        self._invoke(("stop",), check=False)
