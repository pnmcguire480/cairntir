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
from cairntir.ideation_angles import (
    MEANING_DUPLICATE_THRESHOLD,
    TOP_UP_ROUNDS,
    count_distinct_meanings,
)

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
    "budget meeting recap",
    "onboarding checklist tour",
    "customer interview digest",
    "quarterly goal reset",
    "vendor contract review",
    "photo archive cleanup",
    "weekly planning ritual",
    "support inbox triage",
    "invoice follow up script",
    "inventory count routine",
    "pricing experiment log",
    "referral thank you card",
)
VALUES = {
    "audience": "Solo makers who sell online",
    "channels": "Newsletter and short video",
    "pain": "Hours lost on repeat admin",
    "sophistication": "Knows the tools, not the method",
    "desired-outcome": "One calm hour a day",
}


def _candidates(
    count: int = 20, *, repeat_angle: bool = False, start: int = 0
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index in range(start, start + count):
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
        self.replies: list[list[dict[str, Any]]] = []
        self.prompts: list[str] = []
        self.thinking = ""
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                owner.calls += 1
                sent = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                owner.prompts.append(sent["prompt"])
                rows = (
                    owner.replies.pop(0) if owner.calls > 1 and owner.replies else owner.candidates
                )
                reply = {
                    "model": "fake-model",
                    "done": True,
                    "response": json.dumps({"candidates": rows}),
                }
                if owner.thinking:
                    reply["thinking"] = owner.thinking
                body = json.dumps(reply).encode()
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


def _angles(receipt: dict[str, Any]) -> list[str]:
    return [c["angle"] for c in receipt["candidates"]]


def _ready(env: dict[str, Any], model: _Model, *extra: str) -> dict[str, Any]:
    result = _generate(env, model, *extra)
    assert result.exit_code == 0, result.output
    return json.loads(result.output)  # type: ignore[no-any-return]


def test_a_set_of_rewordings_of_one_angle_is_refused_after_bounded_top_ups(
    env: dict[str, Any], model: _Model
) -> None:
    _capture(env)
    model.candidates = _with_rewordings(20)
    assert len({_norm(c["angle"]) for c in model.candidates}) == 20  # wording differs
    model.replies = [_with_rewordings(20)[:8] for _ in range(TOP_UP_ROUNDS)]
    result = _generate(env, model)
    assert result.exit_code == 1
    assert "only 1 distinct angle(s) found" in result.output
    assert "approximate" in result.output and "nothing was stored" in result.output
    assert model.calls == 5  # one request plus four top-ups
    assert _rows(env["store"]) == 0


def test_repeats_are_removed_and_topped_up_so_exactly_distinct_angles_are_stored(
    env: dict[str, Any], model: _Model
) -> None:
    _capture(env)
    model.candidates = _with_rewordings(8)  # 12 different ideas + 8 rewordings of one
    model.replies = [_candidates(7, start=20)]
    receipt = _ready(env, model)
    angles = _angles(receipt)
    assert len(angles) == 20
    assert sum("gardener" in a for a in angles) == 1  # the reworded angle counts once
    assert [c["rank"] for c in receipt["candidates"]] == list(range(1, 21))
    assert len(receipt["discarded_candidates"]) == 7
    assert all(d["reason"] == "same meaning" for d in receipt["discarded_candidates"])
    assert [t["round"] for t in receipt["top_up_exchanges"]] == [1]
    assert model.calls == 2
    assert "already taken" in model.prompts[1] and angles[0].split()[0] in model.prompts[1]
    shown = json.loads(_run(["angles", "show", *env["common"], "--json"]).output)
    assert _angles(shown) == angles  # persisted exactly the survivors


def test_a_repeat_among_more_than_twenty_candidates_is_dropped_not_stored(
    env: dict[str, Any], model: _Model
) -> None:
    _capture(env)
    rows = _candidates(22)
    rows[20]["angle"] = rows[3]["angle"] + " again"  # a rewording of angle #3
    model.candidates = rows
    receipt = _ready(env, model)
    assert model.calls == 1
    assert len(receipt["candidates"]) == 21
    assert rows[20]["angle"] not in _angles(receipt)
    assert [(d["id"], d["same_as"]) for d in receipt["discarded_candidates"]] == [
        (rows[20]["id"], rows[3]["id"])
    ]


def test_a_repeat_that_is_not_next_to_its_original_is_still_found(
    env: dict[str, Any], model: _Model
) -> None:
    _capture(env)
    rows = _candidates(21)
    rows[20]["angle"] = rows[10]["angle"] + " again"  # repeats #10, not the last kept (#19)
    model.candidates = rows
    receipt = _ready(env, model)
    assert len(receipt["candidates"]) == 20
    assert rows[20]["angle"] not in _angles(receipt)


def test_a_thinking_model_reply_is_accepted(env: dict[str, Any], model: _Model) -> None:
    _capture(env)
    model.thinking = "Let me think about the angles first."
    assert len(_ready(env, model)["candidates"]) == 20


def test_top_up_candidates_with_a_repeated_wording_are_dropped_and_recorded(
    env: dict[str, Any], model: _Model
) -> None:
    _capture(env)
    rows = _candidates(20)
    rows[19]["angle"] = rows[0]["angle"] + " again"  # 19 survivors in the first reply
    model.candidates = rows
    extra = _candidates(2, start=20)
    extra[0]["angle"] = rows[0]["angle"]  # same wording as a kept angle
    model.replies = [extra]
    receipt = _ready(env, model)
    assert len(receipt["candidates"]) == 20
    assert [d["reason"] for d in receipt["discarded_candidates"]] == [
        "same meaning",
        "same wording",
    ]


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


def test_the_real_embedding_model_meets_the_measured_catch_and_false_rejection_rates() -> None:
    """The rule was chosen on these labelled pairs; this keeps the measurement honest."""
    import itertools

    from cairntir.memory.embeddings import production_embedding_provider

    provider = production_embedding_provider()
    try:
        provider.embed(["probe"])
    except EmbeddingError as exc:
        pytest.skip(f"production embedding model is not available here: {exc}")
    data = json.loads(Path(__file__).with_name("angle_meaning_labels.json").read_text("utf-8"))
    caught = missed = rejected = kept = 0
    for entry in data["sets"].values():
        angles, labels = entry["angles"], entry["labels"]
        for i, j in itertools.combinations(range(len(angles)), 2):
            if labels[i] is None or labels[j] is None:
                continue
            same = count_distinct_meanings([angles[i], angles[j]], provider.embed) == 1
            if labels[i] == labels[j]:
                caught, missed = caught + same, missed + (not same)
            else:
                rejected, kept = rejected + same, kept + (not same)
    assert caught + missed == 36 and rejected + kept == 934
    assert caught / 36 >= 0.75  # measured 29/36 at the chosen line
    assert rejected / 934 <= 0.13  # measured 103/934; stricter lines drop too many ideas
    # A template rotation the checker counted as one idea.
    assert (
        count_distinct_meanings(
            [
                "The impact of sleep deprivation on mood and emotional well-being",
                "The impact of sleep deprivation on mental health",
            ],
            provider.embed,
        )
        == 1
    )


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
