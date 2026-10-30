"""Invalid Dream controller policies refuse atomically without worker/model calls."""

from __future__ import annotations

import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace

import pytest

from . import observations as old

POLICIES = [
    ("unknown", {"unexpected": 1}),
    ("max_calls_zero", {"max_calls": 0}),
    ("max_calls_bool", {"max_calls": True}),
    ("max_pending_float", {"max_pending": 1.5}),
    ("poll_zero", {"poll_seconds": 0}),
    ("review_too_short", {"review_seconds": 0.01}),
    ("retry_nan", {"retry_seconds": float("nan")}),
    ("inference_over_max", {"inference_seconds": 61}),
    ("inference_inf", {"inference_seconds": float("inf")}),
    ("exclude_string", {"exclude_wings": "alpha"}),
    ("exclude_blank", {"exclude_wings": [""]}),
    ("exclude_nonstring", {"exclude_wings": [1]}),
]


@pytest.mark.parametrize("name,changes", POLICIES, ids=[x[0] for x in POLICIES])
def test_invalid_policy_is_atomic_and_launches_nothing(tmp_path, name, changes):
    from cairntir import dream
    from cairntir import dream_controller as controller
    from cairntir.memory.embeddings import HashEmbeddingProvider
    from cairntir.memory.store import DrawerStore
    from cairntir.memory.taxonomy import Drawer
    from cairntir.provenance import WriteProvenance

    calls = []
    children = []

    class Model(BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append(self.path)
            self.send_response(500)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Model)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    db = tmp_path / "cairntir.db"
    original = controller.subprocess

    def popen(*args, **kwargs):
        child = subprocess.Popen(*args, **kwargs)  # noqa: S603 - Spy on the configured local child.
        children.append(child)
        return child

    try:
        with DrawerStore(db, HashEmbeddingProvider(32)) as store:
            store.add(
                Drawer(
                    wing="policy", room="fixture", content="Preserve this original policy evidence."
                ),
                provenance=WriteProvenance.create(host="acceptance", capture_path="fixture"),
            )
        dream.enable(
            db,
            scope="all-local",
            model="policy-fixture",
            endpoint=f"http://127.0.0.1:{server.server_port}",
            provider_factory=lambda: HashEmbeddingProvider(32),
        )
        controller.configure(db, max_calls=3, max_pending=9, inference_seconds=2)
        tables = (
            "drawers",
            "dream_config",
            "dream_control",
            "dream_work",
            "dream_reviews",
            "dream_turns",
            "dream_attempts",
            "dream_candidates",
            "dream_receipts",
        )
        before = {t: old.rows(db, t) for t in tables}
        controller.subprocess = SimpleNamespace(
            **{k: v for k, v in vars(subprocess).items() if k != "Popen"}, Popen=popen
        )
        with pytest.raises(dream.DreamError):
            controller.configure(db, **changes)
        after = {t: old.rows(db, t) for t in tables}
        old.save(
            tmp_path / "POLICY.json",
            {
                "case": name,
                "before": before,
                "after": after,
                "worker_launches": len(children),
                "model_calls": calls,
            },
        )
        assert after == before and not children and not calls
    finally:
        controller.subprocess = original
        for child in children:
            if child.stdin and not child.stdin.closed:
                child.stdin.close()
            child.wait(timeout=15)
            for pipe in (child.stdin, child.stdout, child.stderr):
                if pipe and not pipe.closed:
                    pipe.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()
