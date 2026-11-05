"""Original valid local model and a source-bound ordinary CLI compatibility adapter."""

import json
import threading
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import test_dream_pilot_r1 as pilot
from dream_response_unit.fixture import Harness as ResponseHarness

from . import oracles


def utc():
    return datetime.now(UTC).isoformat()


def save(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


class Model:
    def __init__(self, root, mode="proposal", port=0):
        self.root, self.mode, self.calls = root, mode, []
        self.gate = threading.Event()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                request = json.loads(raw)
                prompt = json.loads(request["prompt"])
                row = {
                    "index": len(owner.calls),
                    "start": time.time(),
                    "utc": utc(),
                    "path": self.path,
                    "body": request,
                    "prompt": prompt,
                    "end": None,
                    "disconnected": False,
                    "mode": owner.mode,
                }
                owner.calls.append(row)
                mode = owner.mode
                try:
                    if mode == "hold":
                        owner.gate.wait(15)
                    if mode == "failure":
                        self.send_response(503)
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    if mode == "redirect":
                        self.send_response(302)
                        self.send_header(
                            "Location", f"http://127.0.0.1:{owner.sink.server_port}/leak"
                        )
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    result = (
                        {"proposals": []}
                        if mode == "quiet"
                        else {
                            "proposals": [
                                {
                                    "title": "Review the observed retry",
                                    "proposal": (
                                        "SYNTHETIC_CANDIDATE: examine the supplied evidence; "
                                        "no approval is implied."
                                    ),
                                    "evidence_ids": [999999],
                                }
                            ]
                        }
                    )
                    payload = json.dumps(
                        {"model": request["model"], "done": True, "response": json.dumps(result)}
                    ).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    if mode == "drip":
                        for byte in payload:
                            self.wfile.write(bytes([byte]))
                            self.wfile.flush()
                            time.sleep(0.08)
                    else:
                        self.wfile.write(payload)
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    row["disconnected"] = True
                finally:
                    row["end"] = time.time()
                    save(owner.root / f"model-call-{row['index']:03}.json", row)

            def log_message(self, *_):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.endpoint = f"http://127.0.0.1:{self.server.server_port}"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.gate.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)


class Harness(ResponseHarness):
    def seed(self, *items):
        return [pilot._seed(self.home, value["wing"], value["content"]) for value in items]

    def cli(self, *args):
        if args and args[0] == "dream":
            args = args[1:]
        return super().cli(*args)

    def configure(self, **config):
        args = []
        for key, value in config.items():
            if key == "exclude_wings":
                for wing in value:
                    args.extend(["--exclude-wing", wing])
            else:
                args.extend(["--" + key.replace("_", "-"), str(value)])
        return self.cli("dream", "configure", *args)

    def status(self):
        value = self.cli("dream", "status")
        oracles.status(value)
        return value
