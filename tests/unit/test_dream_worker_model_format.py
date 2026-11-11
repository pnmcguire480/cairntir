"""Dream must ask a real local model for the reply shape it parses.

Found by packet 3 (10 November 2026): a real ``mistral:latest`` served by Ollama
0.40.3 answered Dream's request in plain prose. The worker only accepts a JSON
``{"proposals": [...]}`` reply, so every real answer was recorded as
``model_unavailable`` and no real run could ever produce a candidate. The
synthetic test servers always replied in the exact JSON shape, which hid this.

The fake server below behaves like the real one: without an Ollama ``format``
schema it answers in prose (the reply recorded from the real run); with a schema
that requires ``proposals`` it answers in that shape.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from cairntir.dream_worker import infer_http

# Verbatim reply from the real packet-3 run (proxy log, first request).
REAL_PROSE_REPLY = (
    " Based on the evidence provided, one potential review item could be:\n\n"
    "Review the accuracy and reliability of the free open-meteo forecast API for "
    "frost warnings, compared to the national weather API, for your specific zip code."
)

EVIDENCE = [
    {
        "id": 3,
        "content": "Open question: should frost warnings use the national weather API "
        "or the free open-meteo forecast?",
    }
]


def _requires_proposals(schema: Any) -> bool:
    if not isinstance(schema, dict) or "proposals" not in schema.get("required", []):
        return False
    proposals = schema.get("properties", {}).get("proposals", {})
    item = proposals.get("items", {})
    return (
        proposals.get("type") == "array"
        and {"title", "proposal"} <= set(item.get("required", []))
        and all(
            item.get("properties", {}).get(key, {}).get("type") == "string"
            for key in ("title", "proposal")
        )
    )


@contextmanager
def _ollama_like(*, answer: dict[str, Any]) -> Iterator[tuple[str, list[dict[str, Any]]]]:
    requests: list[dict[str, Any]] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_: object) -> None:
            return

        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(body)
            text = (
                json.dumps(answer) if _requires_proposals(body.get("format")) else REAL_PROSE_REPLY
            )
            raw = json.dumps({"model": body["model"], "done": True, "response": text}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_real_model_reply_becomes_a_proposal() -> None:
    answer = {"proposals": [{"title": "Check open-meteo", "proposal": "Compare forecasts."}]}
    with _ollama_like(answer=answer) as (endpoint, requests):
        result = infer_http(endpoint, "mistral:latest", "garden-app", EVIDENCE, 5)
    assert result == ("Check open-meteo", "Compare forecasts.")
    assert len(requests) == 1
    assert requests[0]["stream"] is False


def test_real_model_may_still_return_no_proposal() -> None:
    with _ollama_like(answer={"proposals": []}) as (endpoint, _):
        assert infer_http(endpoint, "mistral:latest", "garden-app", EVIDENCE, 5) is None


def test_instruction_names_the_reply_shape() -> None:
    with _ollama_like(answer={"proposals": []}) as (endpoint, requests):
        infer_http(endpoint, "mistral:latest", "garden-app", EVIDENCE, 5)
    prompt = json.loads(requests[0]["prompt"])
    assert prompt["evidence"] == EVIDENCE
    assert '"proposals"' in prompt["instruction"]
    assert '"title"' in prompt["instruction"] and '"proposal"' in prompt["instruction"]
