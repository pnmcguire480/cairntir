"""Behavior of the angles command route (I02): 20+ distinct, reasoned, persisted angles."""

from __future__ import annotations

import json
import math
import re
import sqlite3
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from cairntir.audience_lock import _CAPTURE_SOURCE
from cairntir.cli import app
from cairntir.errors import EmbeddingError
from cairntir.ideation_angles import MEANING_DUPLICATE_THRESHOLD, count_distinct_meanings

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
VALUES = {
    "audience": "Solo makers who sell online",
    "channels": "Newsletter and short video",
    "pain": "Hours lost on repeat admin",
    "sophistication": "Knows the tools, not the method",
    "desired-outcome": "One calm hour a day",
}


def _candidates(count: int = 20, *, repeat_angle: bool = False) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index in range(count):
        theme = THEMES[index % len(THEMES)]
        value = 96 - index
        angle = f"How a {theme} helps"
        if repeat_angle and index == 1:
            angle = rows[0]["angle"]
        rows.append(
            {
                "id": f"a{index + 1:02d}",
                "angle": angle,
                "hook": f"Try one {theme} example today",
                "relevance": f"The audience pain connects to {theme}.",
                "source_ids": [_CAPTURE_SOURCE],
                "scores": {
                    "audience_fit": {"value": value, "reason": f"{theme} fits the stated pain."},
                    "practicality": {"value": value, "reason": f"{theme} fits one small demo."},
                },
            }
        )
    return rows


class _Model:
    """A stand-in for the local Ollama origin: same wire format, controllable output."""

    def __init__(self) -> None:
        self.calls = 0
        self.candidates = _candidates()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                owner.calls += 1
                self.rfile.read(int(self.headers["Content-Length"]))
                body = json.dumps(
                    {
                        "model": "fake-model",
                        "done": True,
                        "response": json.dumps({"candidates": owner.candidates}),
                    }
                ).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args: object) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def endpoint(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"


@pytest.fixture
def model() -> Iterator[_Model]:
    fake = _Model()
    yield fake
    fake.server.shutdown()
    fake.server.server_close()


# A tiny stand-in for the embedding model that knows which words mean the same thing.
_SAME = {
    **dict.fromkeys(("faq", "handbook", "manual", "guide", "webinar", "podcast", "talk"), "format"),
    **dict.fromkeys(("preventing", "stopping"), "prevention"),
}


def _slot(word: str) -> int:
    return sum((i + 1) * ord(c) for i, c in enumerate(word)) % 128


class _MeaningEmbedder:
    def __init__(self) -> None:
        self.calls = 0

    def embed(self, texts: Any) -> list[list[float]]:
        self.calls += 1
        vectors = []
        for text in texts:
            vec = [0.0] * 128
            for word in re.findall(r"\w+", text.casefold()):
                vec[_slot(_SAME.get(word, word))] += 1.0
            vectors.append(vec)
        return vectors


@pytest.fixture(autouse=True)
def _embedder(monkeypatch: pytest.MonkeyPatch) -> _MeaningEmbedder:
    fake = _MeaningEmbedder()
    monkeypatch.setattr("cairntir.cli.production_embedding_provider", lambda: fake)
    return fake


@pytest.fixture
def env(tmp_path: Path) -> dict[str, Any]:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / ".obsidian").mkdir()
    common = ["--wing", "demo", "--vault", str(vault), "--store", str(tmp_path / "memory.db")]
    return {"common": common, "store": tmp_path / "memory.db", "vault": vault}


def _run(args: list[str]) -> Any:
    return CliRunner().invoke(app, args)


def _capture(env: dict[str, Any]) -> None:
    args = ["audience", "capture", *env["common"]]
    for field, value in VALUES.items():
        args += [f"--{field}", value]
    assert _run(args).exit_code == 0


def _generate(env: dict[str, Any], model: _Model, *extra: str) -> Any:
    return _run(
        [
            "angles",
            "generate",
            *env["common"],
            "--brief",
            "Educational content on keeping a small shop calm",
            "--model",
            "fake-model",
            "--endpoint",
            model.endpoint,
            "--json",
            *extra,
        ]
    )


def _rows(store: Path) -> int:
    with sqlite3.connect(store) as conn:
        found = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='cairntir_angle_sets'"
        ).fetchone()
        if found is None:
            return 0
        return int(conn.execute("SELECT COUNT(*) FROM cairntir_angle_sets").fetchone()[0])


def _norm(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.casefold()))


def test_generate_stores_twenty_distinct_angles_each_with_reasons(
    env: dict[str, Any], model: _Model
) -> None:
    _capture(env)
    result = _generate(env, model)
    assert result.exit_code == 0, result.output
    receipt = json.loads(result.output)
    angles = receipt["candidates"]
    assert len(angles) >= 20
    assert len({_norm(a["angle"]) for a in angles}) == len(angles)
    assert len({_norm(a["hook"]) for a in angles}) == len(angles)
    assert [a["rank"] for a in angles] == list(range(1, len(angles) + 1))
    for angle in angles:
        assert angle["relevance"]
        assert set(angle["scores"]) == {"audience_fit", "practicality"}
        assert all(s["reason"] for s in angle["scores"].values())
    assert receipt["status"] == "provisional"


def test_angles_persist_for_a_later_process_in_the_same_order(
    env: dict[str, Any], model: _Model
) -> None:
    _capture(env)
    made = json.loads(_generate(env, model).output)
    shown = _run(["angles", "show", *env["common"], "--json"])
    assert shown.exit_code == 0, shown.output
    again = json.loads(shown.output)
    assert again["candidates"] == made["candidates"]
    assert Path(again["snapshot_path"]).is_file()
    text = _run(["angles", "show", *env["common"]]).output
    assert "audience_fit" in text and "Automatic top choice" in text


def test_choose_records_the_person_and_keeps_the_automatic_choice(
    env: dict[str, Any], model: _Model
) -> None:
    _capture(env)
    made = json.loads(_generate(env, model).output)
    top = made["automatic_choice"]
    pick = "a07"
    assert pick != top
    args = ["angles", "choose", *env["common"], "--candidate", pick, "--reason", "My readers ask"]
    first = json.loads(_run([*args, "--json"]).output)
    second = json.loads(_run([*args, "--json"]).output)
    assert first["automatic_choice"] == top
    assert [c["candidate_id"] for c in first["selection_history"]] == [pick]
    assert second["selection_history"] == first["selection_history"]
    assert first["projection_status"] == "ready"
    assert pick in Path(first["current_note_path"]).read_text(encoding="utf-8")


def test_choose_refuses_an_unknown_angle(env: dict[str, Any], model: _Model) -> None:
    _capture(env)
    _generate(env, model)
    result = _run(["angles", "choose", *env["common"], "--candidate", "zzz", "--reason", "x"])
    assert result.exit_code == 1
    shown = json.loads(_run(["angles", "show", *env["common"], "--json"]).output)
    assert shown["selection_history"] == []


def test_the_same_request_replays_without_calling_the_model_again(
    env: dict[str, Any], model: _Model
) -> None:
    _capture(env)
    first = json.loads(_generate(env, model).output)
    second = json.loads(_generate(env, model).output)
    assert model.calls == 1
    assert second["revision"] == first["revision"]
    assert _rows(env["store"]) == 1


def test_a_new_key_makes_a_new_set(env: dict[str, Any], model: _Model) -> None:
    _capture(env)
    _generate(env, model)
    second = json.loads(_generate(env, model, "--key", "second-try").output)
    assert second["revision"] == 2
    assert model.calls == 2


@pytest.mark.parametrize("bad", ["too_few", "repeated_angle"])
def test_a_bad_batch_is_refused_and_nothing_is_stored(
    env: dict[str, Any], model: _Model, bad: str
) -> None:
    _capture(env)
    model.candidates = _candidates(19) if bad == "too_few" else _candidates(repeat_angle=True)
    result = _generate(env, model)
    assert result.exit_code == 1
    assert _rows(env["store"]) == 0
    assert _run(["angles", "show", *env["common"]]).exit_code == 1


LEADS = ("Tomato blight prevention:", "Preventing tomato blight:", "Stopping tomato blight:")
FORMATS = ("FAQ", "handbook", "manual", "guide", "webinar", "podcast", "talk")


def _with_rewordings(count: int) -> list[dict[str, Any]]:
    """Valid, lexically different batches whose last `count` angles repeat one angle."""
    rows = _candidates(20)
    for index in range(20 - count, 20):
        k = index - (20 - count)
        rows[index]["angle"] = f"{LEADS[k % 3]} a gardener's {FORMATS[(k // 3) % 7]}"
    return rows


def test_angles_that_only_reword_one_angle_are_refused_and_nothing_is_stored(
    env: dict[str, Any], model: _Model
) -> None:
    _capture(env)
    model.candidates = _with_rewordings(20)
    assert len({_norm(c["angle"]) for c in model.candidates}) == 20  # wording differs
    result = _generate(env, model)
    assert result.exit_code == 1
    assert "differ in meaning" in result.output
    assert "nothing was stored" in result.output
    assert _rows(env["store"]) == 0


def test_a_padded_batch_reports_how_many_distinct_angles_it_really_has(
    env: dict[str, Any], model: _Model
) -> None:
    _capture(env)
    model.candidates = _with_rewordings(8)
    result = _generate(env, model)
    assert result.exit_code == 1
    assert "only 13 of the model's 20 angles differ in meaning" in result.output
    assert _rows(env["store"]) == 0


def test_a_failed_meaning_check_stores_nothing(
    env: dict[str, Any], model: _Model, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Broken:
        def embed(self, texts: Any) -> list[list[float]]:
            raise EmbeddingError("model not available")

    monkeypatch.setattr("cairntir.cli.production_embedding_provider", Broken)
    _capture(env)
    result = _generate(env, model)
    assert result.exit_code == 1
    assert "cannot check whether the angles differ in meaning" in result.output
    assert _rows(env["store"]) == 0


def test_the_meaning_check_does_not_run_again_on_a_replay(
    env: dict[str, Any], model: _Model, _embedder: _MeaningEmbedder
) -> None:
    _capture(env)
    _generate(env, model)
    _generate(env, model)
    assert _embedder.calls == 1


def test_count_distinct_meanings_applies_the_threshold() -> None:
    angles = ["Handbook about blight", "FAQ about blight", "Raised bed soil mix"]
    assert count_distinct_meanings(angles, _MeaningEmbedder().embed) == 2
    same = [[1.0, 0.0], [1.0, 0.0]]
    assert count_distinct_meanings(["a", "b"], lambda _t: same) == 1
    angle = math.acos(MEANING_DUPLICATE_THRESHOLD)
    just_over = [[1.0, 0.0], [math.cos(angle - 0.01), math.sin(angle - 0.01)]]
    just_under = [[1.0, 0.0], [math.cos(angle + 0.01), math.sin(angle + 0.01)]]
    assert count_distinct_meanings(["a", "b"], lambda _t: just_over) == 1
    assert count_distinct_meanings(["a", "b"], lambda _t: just_under) == 2


# Measured with the production embedder: reworded angles from a real Mistral run scored
# 0.95-0.98 against each other; different angles from other real runs at most 0.92.
REAL_REWORDED = (
    "Tomato Blight Prevention: A Gardener's Q&A",
    "Tomato Blight Prevention: A Gardener's FAQ",
    "Tomato Blight Prevention: A Gardener's Handbook",
    "Tomato Blight Prevention: A Gardener's Checklist",
    "Tomato Blight Prevention: A Gardener's Video Guide",
    "Tomato Blight Prevention: A Gardener's Podcast",
    "Tomato Blight Prevention: A Gardener's Webinar",
    "Tomato Blight Prevention: A Gardener's Forum",
    "Tomato Blight Prevention: A Gardener's Blog",
    "Tomato Blight Prevention: A Gardener's Newsletter",
    "Tomato Blight Prevention: A Gardener's Email Series",
    "Tomato Blight Prevention: A Comprehensive Guide for Gardeners",
    "The Gardener's Guide to Tomato Blight Prevention",
    "Natural Tomato Blight Prevention: A Step-by-Step Guide",
    "Tomato Blight Prevention: Tips from Fellow Gardeners",
    "Tomato Blight Prevention: A Visual Guide for Gardeners",
    "Tomato Blight Prevention: A Gardener's Success Story",
)
REAL_DIFFERENT = (
    "Utilizing Social Media Automation for Marketing Efficiency",
    "Leveraging Email Marketing for Customer Engagement",
    "Implementing a Loyalty Program for Customer Retention",
    "Utilizing SEO for Increased Online Visibility",
    "Implementing a Quality Control Process for Consistent Products",
    "Utilizing a Customer Feedback System for Improved Products",
    "Employing a Time-Tracking App for Better Time Management",
    "Automating Inventory Management for Time Savings",
    "Streamlining Packing Processes for Efficiency",
    "Implementing a Dropshipping Model for Reduced Inventory Management",
    "Adopting a Digital Payment System for Simplified Transactions",
    "Adopting a Project Management Tool for Organized Workflow",
    "Implementing a Returns Management System for Simplified Returns",
    "Adopting a Shipping Integration for Seamless Shipping",
    "Batching Orders for Improved Productivity",
    "Implementing a CRM for Customer Relationship Management",
    "Adopting a Digital Invoice System for Simplified Bookkeeping",
    "Leveraging Templates for Consistent Designs",
    "Optimizing Shipping Rates for Cost Savings",
    "Utilizing Label Printers for Organized Shipping",
)


def test_the_real_embedding_model_separates_rewordings_from_different_angles() -> None:
    from cairntir.memory.embeddings import production_embedding_provider

    provider = production_embedding_provider()
    try:
        provider.embed(["probe"])
    except EmbeddingError as exc:
        pytest.skip(f"production embedding model is not available here: {exc}")
    assert count_distinct_meanings(REAL_REWORDED, provider.embed) <= 8
    assert count_distinct_meanings(REAL_DIFFERENT, provider.embed) == 20


def test_a_non_local_model_address_is_refused_before_any_request(env: dict[str, Any]) -> None:
    _capture(env)
    args = ["angles", "generate", *env["common"], "--brief", "b", "--model", "m"]
    result = _run([*args, "--endpoint", "http://example.com:11434"])
    assert result.exit_code == 1
    assert _rows(env["store"]) == 0


def test_generate_without_a_captured_audience_stores_nothing(
    env: dict[str, Any], model: _Model
) -> None:
    result = _generate(env, model)
    assert result.exit_code == 1
    assert model.calls == 0
    assert _rows(env["store"]) == 0


def test_capture_works_on_a_store_that_already_exists_without_audience_tables(
    env: dict[str, Any],
) -> None:
    with sqlite3.connect(env["store"]) as conn:
        conn.execute("CREATE TABLE drawers (id INTEGER PRIMARY KEY)")
    _capture(env)
    status = _run(["audience", "status", *env["common"]])
    assert '"lock": "provisional"' in status.output
