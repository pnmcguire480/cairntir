"""Behavior of the outlines route (I05): selected I02 angle -> complete outlines + actions."""

from __future__ import annotations

import itertools
import json
import threading
import time
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from tests.acceptance.ideation_outlines_unit import provider_fixture as provider
from typer.testing import CliRunner

from cairntir.audience_lock import _CAPTURE_SOURCE
from cairntir.cli import app
from cairntir.memory.embeddings import HashEmbeddingProvider

VALUES = {
    "audience": "Solo makers who sell online",
    "channels": "Newsletter and short video",
    "pain": "Hours lost on repeat admin",
    "sophistication": "Knows the tools, not the method",
    "desired-outcome": "One calm hour a day",
}
MODEL = "fake-outline-model"


@pytest.fixture(autouse=True)
def _test_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "cairntir.cli.production_embedding_provider", lambda: HashEmbeddingProvider(dimension=384)
    )


def _angles() -> list[dict[str, Any]]:
    themes = [f"routine number {n} for the shop" for n in range(1, 21)]
    return [
        {
            "id": f"a{index:02d}",
            "angle": f"How {theme} saves an hour",
            "hook": f"Try {theme} before lunch",
            "relevance": f"The pain of repeat admin connects to {theme}.",
            "source_ids": [_CAPTURE_SOURCE],
            "scores": {
                "audience_fit": {"value": 97 - index, "reason": f"{theme} fits the pain."},
                "practicality": {"value": 97 - index, "reason": f"{theme} is one small demo."},
            },
        }
        for index, theme in enumerate(themes, 1)
    ]


def _fill(schema: dict[str, Any], label: str) -> Any:
    """Answer one staged writing job from its own reply schema with distinct prose."""
    kind = schema["type"]
    if kind == "object":
        return {key: _fill(child, f"{label} {key}") for key, child in schema["properties"].items()}
    if kind == "array":
        return [_fill(schema["items"], f"{label} item {i}") for i in range(schema["minItems"])]
    if kind == "integer":
        return (schema["minimum"] + schema["maximum"]) // 2
    words = label.translate(str.maketrans("0123456789", "abcdefghij"))
    text = f"Written wording for {words}: a calm routine that keeps shop admin short."
    while len(text) < schema["minLength"]:
        text += " It stays practical for a solo maker."
    return text[: schema["maxLength"]]


class _Ollama:
    """Loopback stand-in for Ollama: angle replies, then outline replies built per request."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.jobs: list[str] = []
        self.bodies: list[dict[str, Any]] = []
        self.mutate: Callable[[dict[str, Any]], None] | None = None
        self.staged_mutate: Callable[[str, dict[str, Any]], None] | None = None
        self.delay: dict[str, float] = {}
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                prompt = body.get("prompt", "")
                if prompt.startswith("I05 (i05.staged."):
                    owner.calls.append("outline")
                    job = json.loads(prompt.split("\n", 1)[1])
                    owner.jobs.append(job["node_id"])
                    owner.bodies.append(body)
                    time.sleep(owner.delay.get(job["job"], 0))
                    output = _fill(body["format"], job["node_id"])
                    if owner.staged_mutate is not None:
                        owner.staged_mutate(job["job"], output)
                    raw = json.dumps(
                        {
                            "model": MODEL,
                            "done": True,
                            "done_reason": "stop",
                            "response": json.dumps(output),
                        }
                    ).encode()
                elif prompt.startswith("I05"):
                    owner.calls.append("outline")
                    request = json.loads(prompt.split("\n", 1)[1])["request"]
                    source = request_source(body)
                    output = provider.output_for(request, source_ids=(source,))
                    if owner.mutate is not None:
                        owner.mutate(output["outline"])
                    raw = provider.envelope(output, model=MODEL)
                else:
                    owner.calls.append("angles")
                    raw = json.dumps(
                        {
                            "model": MODEL,
                            "done": True,
                            "response": json.dumps({"candidates": _angles()}),
                        }
                    ).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *_args: object) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def endpoint(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"

    @property
    def outline_calls(self) -> int:
        return self.calls.count("outline")


def request_source(body: dict[str, Any]) -> str:
    enum = body["format"]["properties"]["outline"]["properties"]["opening"]["properties"]
    return str(enum["source_ids"]["items"]["enum"][0])


@pytest.fixture
def ollama() -> Iterator[_Ollama]:
    fake = _Ollama()
    yield fake
    fake.server.shutdown()
    fake.server.server_close()


@pytest.fixture
def env(tmp_path: Path, ollama: _Ollama) -> dict[str, Any]:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / ".obsidian").mkdir()
    common = ["--wing", "demo", "--vault", str(vault), "--store", str(tmp_path / "memory.db")]
    capture = ["audience", "capture", *common]
    for field, value in VALUES.items():
        capture += [f"--{field}", value]
    assert _run(capture).exit_code == 0
    made = _run(
        [
            "angles",
            "generate",
            *common,
            "--brief",
            "Keeping a small online shop calm",
            "--model",
            MODEL,
            "--endpoint",
            ollama.endpoint,
        ]
    )
    assert made.exit_code == 0, made.output
    return {"common": common, "vault": vault}


def _run(args: list[str]) -> Any:
    return CliRunner().invoke(app, args)


def _choose(env: dict[str, Any], candidate: str) -> None:
    args = ["angles", "choose", *env["common"], "--candidate", candidate, "--reason", "fits me"]
    assert _run(args).exit_code == 0


def _generate(env: dict[str, Any], ollama: _Ollama, *extra: str) -> Any:
    return _run(
        [
            "outlines",
            "generate",
            *env["common"],
            "--model",
            MODEL,
            "--endpoint",
            ollama.endpoint,
            "--json",
            *extra,
        ]
    )


def _show(env: dict[str, Any]) -> Any:
    return _run(["outlines", "show", *env["common"], "--json"])


def _components(outline: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        outline["opening"],
        *(part for pair in outline["key_points"] for part in (pair["point"], pair["example"])),
        *(bridge["bridge"] for bridge in outline["bridges"]),
        outline["close"],
        outline["cta"],
        outline["finished_length"]["basis"],
        *outline["production_notes"],
    ]


def test_selected_angle_becomes_complete_outlines_with_linked_actions(
    env: dict[str, Any], ollama: _Ollama
) -> None:
    _choose(env, "a03")
    _choose(env, "a07")
    result = _generate(env, ollama)
    assert result.exit_code == 0, result.output
    receipt = json.loads(result.output)
    assert receipt["angle_id"] == "a07" and receipt["selection"] == "person_pick"
    assert receipt["context"]["human_confirmation"] is False
    assert receipt["set_note_exists"] is True
    units = {item["request_id"]: item["outline"]["finished_length"] for item in receipt["outlines"]}
    assert (
        units["written-post"]["unit"] == "words" and 600 <= units["written-post"]["estimate"] <= 900
    )
    assert (
        units["short-video"]["unit"] == "seconds" and 60 <= units["short-video"]["estimate"] <= 90
    )
    for item in receipt["outlines"]:
        outline = item["outline"]
        assert outline["opening"]["text"] and outline["close"]["text"] and outline["cta"]["text"]
        assert 3 <= len(outline["key_points"]) <= 6
        assert all(pair["example"]["text"] for pair in outline["key_points"])
        order = [
            outline["opening"]["id"],
            *(pair["point"]["id"] for pair in outline["key_points"]),
            outline["close"]["id"],
        ]
        edges = [(b["from_component_id"], b["to_component_id"]) for b in outline["bridges"]]
        assert edges == list(itertools.pairwise(order))
        assert 2 <= len(outline["production_notes"]) <= 4
        for part in _components(outline):
            assert (part["idea_id"], part["hook_id"]) == ("a07", "a07.hook")
        assert len(item["actions"]) >= 2
        ids = {part["id"] for part in _components(outline)}
        for action in item["actions"]:
            assert action["status"] == "planned" and action["completion_checks"]
            assert set(action["component_ids"]) <= ids
            assert action["ref"]["drawer_id"] != item["ref"]["drawer_id"]
        verify = [action for action in item["actions"] if action["kind"] == "verification"]
        assert verify and set(verify[0]["component_ids"]) == ids  # every part can be checked
    points = {
        item["request_id"]: len(item["outline"]["key_points"]) for item in receipt["outlines"]
    }
    assert points == {"written-post": 4, "short-video": 3}
    assert ollama.outline_calls == 15  # one call per section job: 8 + 7
    note = Path(receipt["set_note_path"]).read_text(encoding="utf-8")
    for link in [line[2:-2] for line in note.splitlines() if line.startswith("[[")]:
        assert (env["vault"] / f"{link}.md").is_file()


def test_outlines_reopen_identically_in_a_later_process(
    env: dict[str, Any], ollama: _Ollama
) -> None:
    _choose(env, "a05")
    made = json.loads(_generate(env, ollama).output)
    shown = _show(env)
    assert shown.exit_code == 0, shown.output
    again = json.loads(shown.output)
    assert again["ref"] == made["ref"]
    assert again["outlines"] == made["outlines"]
    assert again["angle_id"] == "a05" and again["set_note_exists"] is True
    text = _run(["outlines", "show", *env["common"]]).output
    assert "Opening hook:" in text and "Bridge " in text and "done when:" in text


def test_identical_request_replays_without_calling_the_model(
    env: dict[str, Any], ollama: _Ollama
) -> None:
    _choose(env, "a02")
    first = json.loads(_generate(env, ollama).output)
    second = _generate(env, ollama)
    assert second.exit_code == 0, second.output
    replay = json.loads(second.output)
    assert replay["replayed"] is True and replay["ref"] == first["ref"]
    assert ollama.outline_calls == 15


def test_named_angle_and_custom_format(env: dict[str, Any], ollama: _Ollama) -> None:
    result = _generate(env, ollama, "--angle", "a11", "--format", "newsletter:words:300:500")
    assert result.exit_code == 0, result.output
    receipt = json.loads(result.output)
    assert receipt["selection"] == "named" and receipt["angle_id"] == "a11"
    assert [item["request_id"] for item in receipt["outlines"]] == ["newsletter"]
    assert ollama.outline_calls == 8


def _drop_bridge(outline: dict[str, Any]) -> None:
    outline["bridges"].pop(1)


def _repeat_point(outline: dict[str, Any]) -> None:
    outline["key_points"][1]["point"]["text"] = outline["key_points"][0]["point"]["text"]


def _bad_length(outline: dict[str, Any]) -> None:
    outline["finished_length"]["estimate"] = 5


def test_single_call_route_still_makes_complete_outlines(
    env: dict[str, Any], ollama: _Ollama
) -> None:
    _choose(env, "a08")
    result = _generate(env, ollama, "--single-call")
    assert result.exit_code == 0, result.output
    receipt = json.loads(result.output)
    assert receipt["schema"] == "cairntir.outline-set-receipt.v1"
    assert ollama.outline_calls == 2
    assert json.loads(_show(env).output)["ref"] == receipt["ref"]


@pytest.mark.parametrize("mutate", [_drop_bridge, _repeat_point, _bad_length])
def test_incomplete_single_call_outline_stores_no_outline_set(
    env: dict[str, Any], ollama: _Ollama, mutate: Callable[[dict[str, Any]], None]
) -> None:
    _choose(env, "a04")
    ollama.mutate = mutate
    result = _generate(env, ollama, "--single-call")
    assert result.exit_code == 1
    assert "outlines failed" in result.output
    missing = _show(env)
    assert missing.exit_code == 1 and "no accepted outline set" in missing.output


def test_no_selected_angle_is_refused_before_any_model_call(
    env: dict[str, Any], ollama: _Ollama
) -> None:
    result = _generate(env, ollama)
    assert result.exit_code == 1 and "angles choose" in result.output
    assert ollama.outline_calls == 0
    unknown = _generate(env, ollama, "--angle", "zz99")
    assert unknown.exit_code == 1 and ollama.outline_calls == 0


def test_non_local_model_address_is_refused(env: dict[str, Any], ollama: _Ollama) -> None:
    _choose(env, "a01")
    result = _run(
        [
            "outlines",
            "generate",
            *env["common"],
            "--model",
            MODEL,
            "--endpoint",
            "http://example.com:11434",
        ]
    )
    assert result.exit_code == 1
    assert ollama.outline_calls == 0
    assert _show(env).exit_code == 1


def test_changed_snapshot_note_is_refused(env: dict[str, Any], ollama: _Ollama) -> None:
    _choose(env, "a06")
    shown = json.loads(_run(["angles", "show", *env["common"], "--json"]).output)
    snapshot = Path(shown["snapshot_path"])
    snapshot.write_bytes(snapshot.read_bytes().replace(b"saves an hour", b"saves a day", 1))
    result = _generate(env, ollama)
    assert result.exit_code == 1
    assert ollama.outline_calls == 0
    assert _show(env).exit_code == 1


def test_bad_format_spec_is_refused(env: dict[str, Any], ollama: _Ollama) -> None:
    _choose(env, "a01")
    for spec in ("post:pages:1:2", "post:words:9:3", "post:words"):
        result = _generate(env, ollama, "--format", spec)
        assert result.exit_code == 1, spec
    assert ollama.outline_calls == 0


def _short_bridges(job: str, output: dict[str, Any]) -> None:
    if job == "bridges":
        output["bridges"].pop()


def _no_actions(job: str, output: dict[str, Any]) -> None:
    if job == "production":
        output["actions"] = []


def _length_outside(job: str, output: dict[str, Any]) -> None:
    if job == "production":
        output["finished_length_estimate"] = 5


def _same_point() -> Callable[[str, dict[str, Any]], None]:
    first: dict[str, str] = {}

    def mutate(job: str, output: dict[str, Any]) -> None:
        if job == "point":
            output["point"] = first.setdefault("point", output["point"])

    return mutate


@pytest.mark.parametrize(
    "mutate",
    [_short_bridges, _no_actions, _length_outside, _same_point()],
    ids=["missing-bridge", "no-actions", "length", "repeated-point"],
)
def test_incomplete_staged_section_stores_no_outline_set(
    env: dict[str, Any], ollama: _Ollama, mutate: Callable[[str, dict[str, Any]], None]
) -> None:
    _choose(env, "a09")
    ollama.staged_mutate = mutate
    result = _generate(env, ollama)
    assert result.exit_code == 1
    assert "outlines failed" in result.output
    missing = _show(env)
    assert missing.exit_code == 1 and "no accepted outline set" in missing.output


def test_staged_section_over_its_time_limit_stores_nothing(
    env: dict[str, Any], ollama: _Ollama
) -> None:
    _choose(env, "a10")
    ollama.delay = {"production": 3.0}
    result = _generate(env, ollama, "--timeout", "1")
    assert result.exit_code == 1 and "outlines failed" in result.output
    assert ollama.jobs[-1] == "written-post.production"
    assert _show(env).exit_code == 1


def test_staged_limit_above_180_seconds_is_refused_before_any_call(
    env: dict[str, Any], ollama: _Ollama
) -> None:
    _choose(env, "a10")
    result = _generate(env, ollama, "--timeout", "200")
    assert result.exit_code == 1 and "180 seconds" in result.output
    assert ollama.outline_calls == 0


def test_staged_requests_turn_thinking_off_and_ask_for_declared_numbers(
    env: dict[str, Any], ollama: _Ollama
) -> None:
    _choose(env, "a12")
    assert _generate(env, ollama).exit_code == 0
    assert len(ollama.bodies) == 15
    for body in ollama.bodies:
        assert body["think"] is False
        assert body["prompt"].startswith("I05 (i05.staged.v3)")
        assert "Do not invent figures" in body["prompt"]


def _figure(declared: bool) -> Callable[[str, dict[str, Any]], None]:
    def mutate(job: str, output: dict[str, Any]) -> None:
        if job == "point" and not getattr(mutate, "done", False):
            output["example"] += " It saves 40% of admin time."
            if declared:
                output["assumptions"] = ["A routine like this saves 40% of admin time."]
            mutate.done = True  # type: ignore[attr-defined]

    return mutate


def test_undeclared_generated_number_is_refused(env: dict[str, Any], ollama: _Ollama) -> None:
    _choose(env, "a13")
    ollama.staged_mutate = _figure(declared=False)
    result = _generate(env, ollama)
    assert result.exit_code == 1 and "number is not declared" in result.output
    assert _show(env).exit_code == 1


def test_declared_generated_number_is_kept_with_its_verification_action(
    env: dict[str, Any], ollama: _Ollama
) -> None:
    _choose(env, "a14")
    ollama.staged_mutate = _figure(declared=True)
    result = _generate(env, ollama)
    assert result.exit_code == 0, result.output
    outline = json.loads(result.output)["outlines"][0]
    claims = outline["outline"]["assumptions"]
    assert [a["claim"] for a in claims] == ["A routine like this saves 40% of admin time."]
    verify = next(a for a in outline["actions"] if a["kind"] == "verification")
    assert claims[0]["verification_action_id"] == verify["action_id"]
