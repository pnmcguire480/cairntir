import copy
import hashlib
import json
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

import pytest

from cairntir.errors import ProjectionError
from cairntir.ideation_angles import (
    OllamaAnglesAdapter,
    generate_angle_set,
    get_angle_set,
    project_angle_set,
    steer_angle_set,
)
from cairntir.ideation_audience import get_audience_revision, publish_audience_revision

THEMES = (
    "decision reversal timeline",
    "context handoff map",
    "failed test autopsy",
    "release evidence trail",
    "private memory boundary",
    "old plan excavation",
    "human note preservation",
    "source citation check",
    "dependency drift watch",
    "abandoned approach diary",
    "pair review dialogue",
    "local model fallback",
    "cross tool continuity",
    "migration before after",
    "risk register walkthrough",
    "task ownership history",
    "unknown practice laboratory",
    "reproducible bug postcard",
    "project question queue",
    "retired rule restoration",
)
OBJECTIVES = [
    {"id": "audience_fit", "criterion": "Relevant to solo developers", "weight": 60},
    {"id": "practicality", "criterion": "Demonstrable with a small workflow", "weight": 40},
]
FIELDS = ("audience", "channels", "pain", "sophistication", "desired_outcome")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _candidates():
    rows = []
    for index, theme in enumerate(THEMES, 1):
        value = 96 - index
        rows.append(
            {
                "id": f"a{index:02d}",
                "angle": f"How a {theme} clarifies assistant-assisted coding",
                "hook": f"Try a concrete {theme} example from one small project",
                "relevance": (
                    f"The provisional audience's decision-tracking pain connects to {theme}."
                ),
                "source_ids": ["inference-1"],
                "scores": {
                    "audience_fit": {
                        "value": value,
                        "reason": (
                            f"This theme addresses the inferred decision pain through {theme}."
                        ),
                    },
                    "practicality": {
                        "value": value,
                        "reason": (
                            f"A short project can demonstrate {theme} "
                            "without a promise of reliability."
                        ),
                    },
                },
            }
        )
    return rows


class FixtureAdapter:
    identity: ClassVar[dict[str, str]] = {
        "kind": "fixture",
        "model_id": "fixture:angles",
        "prompt_version": "i02-fixture-v1",
    }

    def __init__(self, candidates=None, on_generate=None):
        self.candidates = copy.deepcopy(candidates if candidates is not None else _candidates())
        self.on_generate = on_generate
        self.calls = 0
        self.bundles = []

    def generate(self, bundle):
        self.calls += 1
        self.bundles.append(copy.deepcopy(bundle))
        if self.on_generate is not None:
            self.on_generate()
        payload = {"actual_model": "fixture:angles", "done": True, "candidates": self.candidates}
        return {
            **payload,
            "raw_request_sha256": _sha(_canonical(bundle)),
            "raw_response_sha256": _sha(_canonical(payload)),
        }


@pytest.fixture
def prepared(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / ".obsidian").mkdir()
    human_spec = vault / "SPEC.md"
    human_spec.write_bytes(b"# Human SPEC\n\nDo not rewrite this text.\n")
    store = tmp_path / "memory.db"
    audience = {
        "store_path": store,
        "vault_path": vault,
        "wing": "project-alpha",
        "profile": {
            "audience": {
                "value": "solo developers and small software teams",
                "source_ids": ["inference-1"],
            },
            "channels": {
                "value": "technical articles and short demos",
                "source_ids": ["inference-1"],
            },
            "pain": {
                "value": "losing technical decisions across coding assistants",
                "source_ids": ["inference-1"],
            },
            "sophistication": {
                "value": "comfortable with code, new to memory tools",
                "source_ids": ["inference-1"],
            },
            "desired_outcome": {
                "value": "trace decisions and reversals with evidence",
                "source_ids": ["inference-1"],
            },
        },
        "evidence": {
            "inference-1": {
                "kind": "inferred",
                "content": (
                    "Synthetic inference: solo developers and small teams lose decisions "
                    "when switching coding assistants; articles and short demos may help."
                ),
                "supports": list(FIELDS),
            }
        },
        "idempotency_key": "audience-1",
    }
    audience_receipt = publish_audience_revision(**audience)
    assert audience_receipt["status"] == "provisional"
    assert audience_receipt["projection_status"] == "ready"
    return {
        "store": store,
        "vault": vault,
        "wing": "project-alpha",
        "human_spec": human_spec,
        "audience": audience,
        "audience_receipt": audience_receipt,
    }


def _request(prepared, adapter, *, key="angles-1"):
    return {
        "store_path": prepared["store"],
        "vault_path": prepared["vault"],
        "wing": prepared["wing"],
        "brief": (
            "Educational content on retaining technical decisions while coding with assistants."
        ),
        "objectives": copy.deepcopy(OBJECTIVES),
        "idempotency_key": key,
        "adapter": adapter,
    }


def _angle_rows(store):
    with sqlite3.connect(store) as conn:
        if (
            conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='cairntir_angle_sets'"
            ).fetchone()
            is None
        ):
            return 0
        return conn.execute("SELECT COUNT(*) FROM cairntir_angle_sets").fetchone()[0]


def _assert_ranked(receipt):
    candidates = receipt["candidates"]
    assert len(candidates) >= 20
    assert len({item["id"] for item in candidates}) == len(candidates)
    assert [item["rank"] for item in candidates] == list(range(1, len(candidates) + 1))
    expected = sorted(
        candidates,
        key=lambda item: (
            -sum(
                objective["weight"] * item["scores"][objective["id"]]["value"]
                for objective in receipt["objectives"]
            ),
            item["id"],
        ),
    )
    assert [item["id"] for item in candidates] == [item["id"] for item in expected]
    for item in candidates:
        assert item["weighted_score_numerator"] == sum(
            objective["weight"] * item["scores"][objective["id"]]["value"]
            for objective in receipt["objectives"]
        )
    assert receipt["automatic_choice"] == candidates[0]["id"]


def test_connected_twenty_ranked_provisional_angles_reopen_and_replay(prepared):
    adapter = FixtureAdapter()
    request = _request(prepared, adapter)
    result = generate_angle_set(**request)
    assert adapter.calls == 1
    bundle = adapter.bundles[0]
    assert bundle["schema"] == "cairntir.angle-input.v1"
    assert bundle["audience_revision"] == prepared["audience_receipt"]["revision"]
    assert bundle["audience_snapshot_sha256"] == prepared["audience_receipt"]["snapshot_sha256"]
    assert bundle["profile"] == prepared["audience_receipt"]["profile"]
    assert bundle["evidence"] == prepared["audience_receipt"]["evidence"]
    assert result["status"] == "provisional"
    assert result["projection_status"] == "ready"
    assert result["currentness"] == "current"
    assert result["adapter"] == adapter.identity
    assert result["model_exchange"]["actual_model"] == "fixture:angles"
    _assert_ranked(result)
    assert result["automatic_choice"] == "a01"
    version = Path(result["snapshot_path"])
    current = Path(result["current_note_path"])
    assert version.is_file() and current.is_file()
    note = current.read_text(encoding="utf-8")
    assert "[[" in note and "provisional" in note.lower()
    assert "a01" in note and "a20" in note
    assert "fixture:angles" in note
    assert prepared["audience_receipt"]["snapshot_sha256"] in version.name + note
    assert prepared["human_spec"].read_bytes() == b"# Human SPEC\n\nDo not rewrite this text.\n"
    reopened = get_angle_set(prepared["store"], prepared["vault"], prepared["wing"])
    _assert_ranked(reopened)
    assert reopened["revision"] == result["revision"]
    assert reopened["automatic_choice"] == result["automatic_choice"]
    replay = generate_angle_set(**request)
    assert replay["revision"] == result["revision"]
    assert adapter.calls == 1
    changed = {**request, "brief": request["brief"] + " A changed brief."}
    with pytest.raises(ProjectionError):
        generate_angle_set(**changed)
    assert adapter.calls == 1
    assert _angle_rows(prepared["store"]) == 1


def test_optional_steering_appends_without_erasing_original_rank(prepared):
    result = generate_angle_set(**_request(prepared, FixtureAdapter()))
    original = Path(result["snapshot_path"]).read_bytes()
    selected = steer_angle_set(
        prepared["store"],
        prepared["vault"],
        prepared["wing"],
        set_revision=result["revision"],
        candidate_id="a07",
        reason="Try the human-note example first",
        idempotency_key="steer-1",
    )
    assert selected["candidate_id"] == "a07"
    assert selected["status"] == "caller_steering"
    assert not selected["replayed"]
    assert steer_angle_set(
        prepared["store"],
        prepared["vault"],
        prepared["wing"],
        set_revision=result["revision"],
        candidate_id="a07",
        reason="Try the human-note example first",
        idempotency_key="steer-1",
    )["replayed"]
    with pytest.raises(ProjectionError):
        steer_angle_set(
            prepared["store"],
            prepared["vault"],
            prepared["wing"],
            set_revision=result["revision"],
            candidate_id="a08",
            reason="Changed selection under reused key",
            idempotency_key="steer-1",
        )
    reopened = get_angle_set(prepared["store"], prepared["vault"], prepared["wing"])
    assert reopened["automatic_choice"] == "a01"
    _assert_ranked(reopened)
    assert [entry["candidate_id"] for entry in reopened["selection_history"]] == ["a07"]
    project_angle_set(prepared["store"], prepared["vault"], prepared["wing"])
    current_note = Path(reopened["current_note_path"]).read_text(encoding="utf-8")
    assert "a07" in current_note and "Try the human-note example first" in current_note
    assert Path(result["snapshot_path"]).read_bytes() == original
    with pytest.raises(ProjectionError):
        steer_angle_set(
            prepared["store"],
            prepared["vault"],
            prepared["wing"],
            set_revision=result["revision"],
            candidate_id="not-a-candidate",
            reason="Wrong",
            idempotency_key="steer-2",
        )
    assert (
        get_angle_set(prepared["store"], prepared["vault"], prepared["wing"])["selection_history"]
        == reopened["selection_history"]
    )


@pytest.mark.parametrize(
    "damage",
    ("nineteen", "duplicate", "missing_source", "missing_score", "incomplete", "wrong_model"),
)
def test_bad_complete_model_batch_cannot_commit_any_angle(prepared, damage):
    candidates = _candidates()
    if damage == "nineteen":
        candidates.pop()
    elif damage == "duplicate":
        candidates[1]["angle"] = candidates[0]["angle"]
        candidates[1]["hook"] = candidates[0]["hook"]
    elif damage == "missing_source":
        candidates[0]["source_ids"] = ["invented-evidence"]
    elif damage == "missing_score":
        del candidates[0]["scores"]["audience_fit"]
    adapter = FixtureAdapter(candidates)
    if damage in {"incomplete", "wrong_model"}:
        original = adapter.generate

        def broken(bundle):
            result = original(bundle)
            result["done"] = damage != "incomplete"
            if damage == "wrong_model":
                result["actual_model"] = "different-model"
            return result

        adapter.generate = broken
    before = {
        p.relative_to(prepared["vault"]): p.read_bytes() for p in prepared["vault"].rglob("*.md")
    }
    with pytest.raises(ProjectionError):
        generate_angle_set(**_request(prepared, adapter))
    assert _angle_rows(prepared["store"]) == 0
    assert {
        p.relative_to(prepared["vault"]): p.read_bytes() for p in prepared["vault"].rglob("*.md")
    } == before


@pytest.mark.parametrize("damage", ("weights", "oversized_brief", "wrong_vault"))
def test_bad_composed_input_refuses_before_model_dispatch(prepared, tmp_path, damage):
    adapter = FixtureAdapter()
    request = _request(prepared, adapter)
    if damage == "weights":
        request["objectives"][0]["weight"] = 101
    elif damage == "oversized_brief":
        request["brief"] = "x" * 100_000
    else:
        other = tmp_path / "other-vault"
        other.mkdir()
        (other / ".obsidian").mkdir()
        request["vault_path"] = other
    with pytest.raises(ProjectionError):
        generate_angle_set(**request)
    assert adapter.calls == 0
    assert _angle_rows(prepared["store"]) == 0


def test_audience_revision_during_generation_refuses_before_i02_commit(prepared):
    def advance_audience():
        request = copy.deepcopy(prepared["audience"])
        request["idempotency_key"] = "audience-2"
        request["profile"]["pain"]["value"] = "a newly observed distribution problem"
        publish_audience_revision(**request)

    adapter = FixtureAdapter(on_generate=advance_audience)
    with pytest.raises(ProjectionError):
        generate_angle_set(**_request(prepared, adapter))
    assert adapter.calls == 1
    assert (
        get_audience_revision(prepared["store"], prepared["vault"], prepared["wing"])["revision"]
        == 2
    )
    assert _angle_rows(prepared["store"]) == 0
    assert not (prepared["vault"] / "cairntir-sync" / prepared["wing"] / "ideation").exists()


def test_reprojection_marks_old_audience_stale_and_keeps_human_bytes(prepared):
    result = generate_angle_set(**_request(prepared, FixtureAdapter()))
    current = Path(result["current_note_path"])
    human = b"\n## My Notes\nA human selected a different headline.\n"
    current.write_bytes(current.read_bytes() + human)
    request = copy.deepcopy(prepared["audience"])
    request["idempotency_key"] = "audience-2"
    request["profile"]["pain"]["value"] = "a new observed pain"
    publish_audience_revision(**request)
    reopened = get_angle_set(prepared["store"], prepared["vault"], prepared["wing"])
    assert reopened["currentness"] == "historical"
    project_angle_set(prepared["store"], prepared["vault"], prepared["wing"])
    note = current.read_bytes()
    assert note.endswith(human)
    assert b"stale" in note.lower() or b"unavailable" in note.lower()
    assert b"a01" not in note.split(b"## My Notes")[0]
    assert prepared["human_spec"].read_bytes() == b"# Human SPEC\n\nDo not rewrite this text.\n"


def test_wrong_vault_and_corrupt_generated_snapshot_are_never_ready(prepared, tmp_path):
    result = generate_angle_set(**_request(prepared, FixtureAdapter()))
    other = tmp_path / "other-vault"
    other.mkdir()
    with pytest.raises(ProjectionError):
        get_angle_set(prepared["store"], other, prepared["wing"])
    version = Path(result["snapshot_path"])
    version.write_bytes(version.read_bytes() + b"\nmanual overwrite of generated bytes\n")
    reread = get_angle_set(prepared["store"], prepared["vault"], prepared["wing"])
    assert reread["projection_status"] == "conflict"
    assert len(reread["candidates"]) == 20
    with pytest.raises(ProjectionError):
        project_angle_set(prepared["store"], prepared["vault"], prepared["wing"])
    assert b"manual overwrite" in version.read_bytes()


def test_rank_and_omission_oracle_catches_deliberately_broken_public_outputs(prepared):
    actual = generate_angle_set(**_request(prepared, FixtureAdapter()))
    _assert_ranked(actual)
    missing = copy.deepcopy(actual)
    missing["candidates"].pop()
    with pytest.raises(AssertionError):
        _assert_ranked(missing)
    wrong_choice = copy.deepcopy(actual)
    wrong_choice["automatic_choice"] = "a20"
    with pytest.raises(AssertionError):
        _assert_ranked(wrong_choice)
    wrong_rank = copy.deepcopy(actual)
    wrong_rank["candidates"][0]["weighted_score_numerator"] += 1
    with pytest.raises(AssertionError):
        _assert_ranked(wrong_rank)


def test_ollama_adapter_refuses_remote_endpoint_without_request():
    with pytest.raises(ProjectionError):
        OllamaAnglesAdapter(endpoint="https://example.com:443", model="qwen2.5-coder:7b")


def test_ollama_adapter_does_not_follow_redirect_or_ambient_proxy(monkeypatch):
    seen = {"origin": 0, "trap": 0}
    mode = {"redirect": True}

    class Trap(BaseHTTPRequestHandler):
        def do_POST(self):
            seen["trap"] += 1
            self.send_response(204)
            self.end_headers()

        def log_message(self, *_args):
            pass

    trap = ThreadingHTTPServer(("127.0.0.1", 0), Trap)

    class Origin(BaseHTTPRequestHandler):
        def do_POST(self):
            seen["origin"] += 1
            self.rfile.read(int(self.headers["Content-Length"]))
            if mode["redirect"]:
                self.send_response(307)
                self.send_header("Location", f"http://127.0.0.1:{trap.server_port}/trap")
                self.end_headers()
                return
            response = {
                "model": "qwen2.5-coder:7b",
                "done": True,
                "response": json.dumps({"candidates": _candidates()}),
            }
            body = _canonical(response)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    origin = ThreadingHTTPServer(("127.0.0.1", 0), Origin)
    threads = [
        threading.Thread(target=server.serve_forever, daemon=True) for server in (trap, origin)
    ]
    for thread in threads:
        thread.start()
    try:
        adapter = OllamaAnglesAdapter(
            endpoint=f"http://127.0.0.1:{origin.server_port}", model="qwen2.5-coder:7b"
        )
        with pytest.raises(ProjectionError):
            adapter.generate(
                {"schema": "cairntir.angle-input.v1", "brief": "private-source-sentinel"}
            )
        assert seen == {"origin": 1, "trap": 0}
        mode["redirect"] = False
        monkeypatch.setenv("HTTP_PROXY", f"http://127.0.0.1:{trap.server_port}")
        monkeypatch.setenv("HTTPS_PROXY", f"http://127.0.0.1:{trap.server_port}")
        monkeypatch.setenv("NO_PROXY", "")
        monkeypatch.setenv("no_proxy", "")
        result = adapter.generate(
            {"schema": "cairntir.angle-input.v1", "brief": "private-source-sentinel"}
        )
        assert result["actual_model"] == "qwen2.5-coder:7b"
        assert result["done"]
        assert seen == {"origin": 2, "trap": 0}
    finally:
        for server in (origin, trap):
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=5)
