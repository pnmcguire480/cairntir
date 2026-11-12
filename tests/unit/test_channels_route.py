"""Behavior of the channels command route (I03): channel-shaped drafts linked to the idea."""

from __future__ import annotations

import json
import sqlite3
import threading
import unicodedata
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from test_angles_cli import _capture, _generate, _Model
from typer.testing import CliRunner

from cairntir import cli
from cairntir.ideation_channels import _PROFILES
from cairntir.memory.embeddings import HashEmbeddingProvider

FORBIDDEN = ("available now", "guaranteed", "human-confirmed")


def _good() -> dict[str, Any]:
    return {
        "schema": "cairntir.channel-output.v1",
        "adaptations": [
            {
                "channel_id": "community-discussion",
                "format_id": "question-post",
                "hook": "Has anyone kept a decision timeline for a small shop?",
                "content": {
                    "title": "How do you track why you changed a decision?",
                    "body": "I am trying a timeline that records each reversal and its reason.",
                    "closing_question": "What would you put on yours?",
                },
                "source_ids": ["angle"],
                "assumption_ids": [],
            },
            {
                "channel_id": "newsletter",
                "format_id": "short-note",
                "hook": "One timeline can end the why-did-we-do-that hunt.",
                "content": {
                    "subject": "A timeline for decisions",
                    "preview": "Keep the reason next to the change.",
                    "body": "This week: write each reversal on one line with its date and why.",
                    "call_to_action": "Reply with your own example.",
                },
                "source_ids": ["angle"],
                "assumption_ids": [],
            },
            {
                "channel_id": "short-video",
                "format_id": "thirty-second-concept",
                "hook": "Watch a decision reverse in ten seconds.",
                "content": {
                    "spoken_opening": "Here is the note I wish I had written last month.",
                    "screen_text": "Decision. Date. Why.",
                    "visual_concept": "One page; three lines appear as they are spoken.",
                    "call_to_action": "Try it today and tell me how it went.",
                },
                "source_ids": ["angle"],
                "assumption_ids": [],
            },
        ],
        "assumptions": [],
    }


class _Channels:
    """A stand-in for the local Ollama origin that answers channel requests."""

    def __init__(self) -> None:
        self.calls = 0
        self.output = _good()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                owner.calls += 1
                self.rfile.read(int(self.headers["Content-Length"]))
                body = json.dumps(
                    {
                        "model": "fake-model",
                        "done": True,
                        "done_reason": "stop",
                        "response": json.dumps(owner.output),
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


@pytest.fixture
def env(tmp_path: Path) -> dict[str, Any]:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / ".obsidian").mkdir()
    common = ["--wing", "demo", "--vault", str(vault), "--store", str(tmp_path / "memory.db")]
    return {"common": common, "store": tmp_path / "memory.db", "vault": vault}


@pytest.fixture
def chan() -> Iterator[_Channels]:
    fake = _Channels()
    yield fake
    fake.server.shutdown()
    fake.server.server_close()


@pytest.fixture(autouse=True)
def _hash_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli, "production_embedding_provider", lambda: HashEmbeddingProvider(dimension=16)
    )


def _run(args: list[str]) -> Any:
    return CliRunner().invoke(cli.app, args)


def _channels(env: dict[str, Any], chan: _Channels, *extra: str, command: str = "generate") -> Any:
    args = ["channels", command, *env["common"]]
    if command == "generate":
        args += ["--model", "fake-model", "--endpoint", chan.endpoint]
    return _run([*args, "--json", *extra])


def _with_angles(env: dict[str, Any], model: _Model) -> dict[str, Any]:
    _capture(env)
    made: dict[str, Any] = json.loads(_generate(env, model).output)
    assert made["status"] == "provisional"
    return made


def _norm(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def _failure_rows(store: Path) -> int:
    with sqlite3.connect(store) as conn:
        return int(
            conn.execute(
                "SELECT COUNT(*) FROM drawers WHERE content LIKE '%channel-failure.v1%'"
            ).fetchone()[0]
        )


def test_each_channel_gets_its_own_fields_within_its_limits(
    env: dict[str, Any],
    model: _Model,
    chan: _Channels,
) -> None:
    _with_angles(env, model)
    result = _channels(env, chan)
    assert result.exit_code == 0, result.output
    draft = json.loads(result.output)
    profiles = {p["channel_id"]: p for p in _PROFILES}
    assert [a["channel_id"] for a in draft["adaptations"]] == list(profiles)
    hooks = set()
    for item in draft["adaptations"]:
        limits = profiles[item["channel_id"]]["limits"]
        parts = {"hook": item["hook"], **item["content"]}
        assert set(parts) == set(limits)
        for name, text in parts.items():
            assert 0 < len(text.encode("utf-8")) <= limits[name]
            assert not any(word in text.casefold() for word in FORBIDDEN)
        hooks.add(_norm(item["hook"]))
    assert len(hooks) == 3
    assert draft["origin_status"] == "manual_provisional"
    assert draft["projection_status"] == "ready"


def test_the_draft_links_back_to_the_chosen_angle_and_persists(
    env: dict[str, Any],
    model: _Model,
    chan: _Channels,
) -> None:
    made = _with_angles(env, model)
    pick = "a07"
    assert pick != made["automatic_choice"]
    chosen = _run(
        ["angles", "choose", *env["common"], "--candidate", pick, "--reason", "My readers ask"]
    )
    assert chosen.exit_code == 0, chosen.output
    first = json.loads(_channels(env, chan).output)
    angle = next(a for a in made["candidates"] if a["id"] == pick)
    assert first["idea"]["angle_id"] == pick
    assert first["idea"]["angle"] == angle["angle"]
    assert first["idea"]["hook"] == angle["hook"]
    assert first["idea"]["chosen_by"] == "person_pick"
    assert first["idea"]["angle_set_revision"] == made["revision"]

    later = json.loads(_channels(env, chan, command="show").output)
    assert later["adaptations"] == first["adaptations"]
    assert later["idea"] == first["idea"]
    assert later["projection_status"] == "ready"
    selection_note = Path(later["projection"]["selection_note"]).read_text(encoding="utf-8")
    assert angle["angle"] in selection_note and f"s{made['revision']}-{pick}" in selection_note
    version_note = Path(later["projection"]["version_note"]).read_text(encoding="utf-8")
    assert version_note.count("Origin:") == 3
    text = _run(["channels", "show", *env["common"]]).output
    assert "not confirmed by a person" in text and "your pick" in text


def test_without_a_person_pick_the_top_angle_is_used_and_labelled(
    env: dict[str, Any],
    model: _Model,
    chan: _Channels,
) -> None:
    made = _with_angles(env, model)
    draft = json.loads(_channels(env, chan).output)
    assert draft["idea"]["angle_id"] == made["automatic_choice"]
    assert draft["idea"]["chosen_by"] == "automatic_top_choice"
    assert "top-ranked" in _run(["channels", "show", *env["common"]]).output


def test_an_explicit_angle_overrides_the_default(
    env: dict[str, Any],
    model: _Model,
    chan: _Channels,
) -> None:
    _with_angles(env, model)
    draft = json.loads(_channels(env, chan, "--angle", "a03").output)
    assert draft["idea"]["angle_id"] == "a03"
    assert draft["idea"]["chosen_by"] == "person_pick"


def test_the_same_request_replays_without_calling_the_model_again(
    env: dict[str, Any],
    model: _Model,
    chan: _Channels,
) -> None:
    _with_angles(env, model)
    first = json.loads(_channels(env, chan).output)
    second = json.loads(_channels(env, chan).output)
    assert chan.calls == 1
    assert second["replayed"] is True and first["replayed"] is False
    assert second["adaptations"] == first["adaptations"]


def test_a_new_key_makes_a_new_draft(
    env: dict[str, Any],
    model: _Model,
    chan: _Channels,
) -> None:
    _with_angles(env, model)
    _channels(env, chan)
    second = json.loads(_channels(env, chan, "--key", "second-try").output)
    assert chan.calls == 2 and second["replayed"] is False


def test_the_earlier_failure_one_hook_copied_into_every_channel_is_refused(
    env: dict[str, Any],
    model: _Model,
    chan: _Channels,
) -> None:
    _with_angles(env, model)
    copied = _good()
    for item in copied["adaptations"]:
        item["hook"] = copied["adaptations"][0]["hook"]
    chan.output = copied
    result = _channels(env, chan)
    assert result.exit_code == 1
    assert _failure_rows(env["store"]) == 1
    assert _channels(env, chan, command="show").exit_code == 1
    again = _channels(env, chan)
    assert again.exit_code == 1 and chan.calls == 1


def test_a_field_over_its_limit_is_refused_and_no_draft_is_kept(
    env: dict[str, Any],
    model: _Model,
    chan: _Channels,
) -> None:
    _with_angles(env, model)
    long = _good()
    long["adaptations"][2]["content"]["screen_text"] = "x" * 174
    chan.output = long
    assert _channels(env, chan).exit_code == 1
    assert _channels(env, chan, command="show").exit_code == 1


def test_a_forbidden_claim_is_refused(
    env: dict[str, Any],
    model: _Model,
    chan: _Channels,
) -> None:
    _with_angles(env, model)
    claim = _good()
    claim["adaptations"][1]["content"]["body"] = "It is available now and guaranteed."
    chan.output = claim
    assert _channels(env, chan).exit_code == 1


def test_an_unknown_angle_or_missing_set_or_nonlocal_address_stores_nothing(
    env: dict[str, Any],
    model: _Model,
    chan: _Channels,
) -> None:
    missing = _channels(env, chan)
    assert missing.exit_code == 1 and chan.calls == 0
    _with_angles(env, model)
    unknown = _channels(env, chan, "--angle", "zzz")
    assert unknown.exit_code == 1 and chan.calls == 0
    remote = _run(
        [
            "channels",
            "generate",
            *env["common"],
            "--model",
            "m",
            "--endpoint",
            "http://example.com:1",
        ]
    )
    assert remote.exit_code == 1 and chan.calls == 0
    assert _channels(env, chan, command="show").exit_code == 1


def test_changed_source_bytes_are_not_overwritten(
    env: dict[str, Any],
    model: _Model,
    chan: _Channels,
) -> None:
    _with_angles(env, model)
    _channels(env, chan)
    root = env["vault"] / "cairntir-sync" / "demo" / "channel-sources"
    next(root.glob("angle-*.md")).write_text("tampered", encoding="utf-8")
    assert _channels(env, chan, "--key", "other").exit_code == 1


def test_a_changed_timeout_is_a_new_attempt_not_a_key_conflict(
    env: dict[str, Any],
    model: _Model,
    chan: _Channels,
) -> None:
    _with_angles(env, model)
    assert _channels(env, chan).exit_code == 0
    again = _channels(env, chan, "--timeout", "200")
    assert again.exit_code == 0, again.output
    assert chan.calls == 2
