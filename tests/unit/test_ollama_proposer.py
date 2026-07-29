"""Unit tests for the OllamaProposer adapter — local-AI proposer for the Reason loop.

Every test mocks ``urllib.request.urlopen`` so no network call ever
escapes the suite. The adapter is otherwise stdlib-only, so the mocks
cover its full surface.
"""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from typing import Any

import pytest

from cairntir.production import (
    OllamaInvalidResponseError,
    OllamaModelMissingError,
    OllamaProposer,
    OllamaUnavailableError,
)
from cairntir.reason.model import Hypothesis
from cairntir.reason.ports import HypothesisProposer


def _fake_response(payload: dict[str, Any]) -> io.BytesIO:
    """Build the kind of response object urllib.request.urlopen returns."""
    return io.BytesIO(json.dumps(payload).encode("utf-8"))


# --------- protocol conformance ----------------------------------------


def test_ollama_proposer_satisfies_hypothesis_proposer_protocol() -> None:
    proposer = OllamaProposer(model="gemma2:2b")
    assert isinstance(proposer, HypothesisProposer)


# --------- happy path --------------------------------------------------


def test_propose_returns_hypothesis_from_drafted_json(monkeypatch: object) -> None:
    """A well-formed Ollama response yields a Hypothesis with stripped fields."""
    captured: list[urllib.request.Request] = []

    def _fake_urlopen(req: urllib.request.Request, **_: object) -> io.BytesIO:
        captured.append(req)
        return _fake_response(
            {
                "response": json.dumps(
                    {
                        "claim": "  fastembed default kills cold-start hang  ",
                        "predicted_outcome": "MCP cold-start under 5s on every install\n",
                    }
                ),
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)  # type: ignore[attr-defined]

    proposer = OllamaProposer(model="gemma2:2b")
    hypothesis = proposer.propose(
        question="did the cold-start fix hold?",
        wing="cairntir",
        room="journey",
    )

    assert isinstance(hypothesis, Hypothesis)
    assert hypothesis.claim == "fastembed default kills cold-start hang"
    assert hypothesis.predicted_outcome == "MCP cold-start under 5s on every install"
    # Wing/room come from the loop's call, not the model's output.
    assert hypothesis.wing == "cairntir"
    assert hypothesis.room == "journey"

    # The request landed at /api/generate on the configured endpoint, with
    # the model + JSON-mode body.
    assert len(captured) == 1
    req = captured[0]
    assert req.full_url == "http://localhost:11434/api/generate"
    body = json.loads(req.data.decode("utf-8"))  # type: ignore[union-attr]
    assert body["model"] == "gemma2:2b"
    assert body["stream"] is False
    assert body["format"] == "json"
    assert "did the cold-start fix hold?" in body["prompt"]


def test_propose_uses_custom_endpoint(monkeypatch: object) -> None:
    captured: list[str] = []

    def _fake_urlopen(req: urllib.request.Request, **_: object) -> io.BytesIO:
        captured.append(req.full_url)
        return _fake_response({"response": json.dumps({"claim": "x", "predicted_outcome": "y"})})

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)  # type: ignore[attr-defined]
    proposer = OllamaProposer(model="m", endpoint="http://10.0.0.5:9999/")
    proposer.propose(question="q", wing="w", room="r1")
    assert captured == ["http://10.0.0.5:9999/api/generate"]


# --------- error paths -------------------------------------------------


def test_unreachable_daemon_raises_unavailable(monkeypatch: object) -> None:
    def _refuse(_req: urllib.request.Request, **_: object) -> io.BytesIO:
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", _refuse)  # type: ignore[attr-defined]
    proposer = OllamaProposer(model="gemma2:2b")
    with pytest.raises(OllamaUnavailableError, match="could not reach Ollama"):
        proposer.propose(question="q", wing="w", room="r1")


def test_timeout_raises_unavailable(monkeypatch: object) -> None:
    def _timeout(_req: urllib.request.Request, **_: object) -> io.BytesIO:
        raise TimeoutError("daemon hung")

    monkeypatch.setattr(urllib.request, "urlopen", _timeout)  # type: ignore[attr-defined]
    proposer = OllamaProposer(model="gemma2:2b", timeout=0.1)
    with pytest.raises(OllamaUnavailableError, match="did not respond within"):
        proposer.propose(question="q", wing="w", room="r1")


def test_model_not_pulled_raises_model_missing(monkeypatch: object) -> None:
    """Ollama wraps 'model not found' inside a 200 response with an 'error' key."""

    def _model_missing(_req: urllib.request.Request, **_: object) -> io.BytesIO:
        return _fake_response({"error": "model 'gemma2:2b' not found, try pulling it first"})

    monkeypatch.setattr(urllib.request, "urlopen", _model_missing)  # type: ignore[attr-defined]
    proposer = OllamaProposer(model="gemma2:2b")
    with pytest.raises(OllamaModelMissingError, match="ollama pull gemma2:2b"):
        proposer.propose(question="q", wing="w", room="r1")


def test_ollama_internal_error_raises_invalid_response(monkeypatch: object) -> None:
    """Errors that aren't model-missing surface as OllamaInvalidResponse."""

    def _other_error(_req: urllib.request.Request, **_: object) -> io.BytesIO:
        return _fake_response({"error": "GPU out of memory"})

    monkeypatch.setattr(urllib.request, "urlopen", _other_error)  # type: ignore[attr-defined]
    proposer = OllamaProposer(model="m")
    with pytest.raises(OllamaInvalidResponseError, match="GPU out of memory"):
        proposer.propose(question="q", wing="w", room="r1")


def test_non_json_envelope_raises_invalid_response(monkeypatch: object) -> None:
    def _bad_json(_req: urllib.request.Request, **_: object) -> io.BytesIO:
        return io.BytesIO(b"<html>500 oops</html>")

    monkeypatch.setattr(urllib.request, "urlopen", _bad_json)  # type: ignore[attr-defined]
    proposer = OllamaProposer(model="m")
    with pytest.raises(OllamaInvalidResponseError, match="non-JSON"):
        proposer.propose(question="q", wing="w", room="r1")


def test_envelope_without_response_field_raises(monkeypatch: object) -> None:
    def _no_response_field(_req: urllib.request.Request, **_: object) -> io.BytesIO:
        return _fake_response({"done": True})  # no 'response' key

    monkeypatch.setattr(urllib.request, "urlopen", _no_response_field)  # type: ignore[attr-defined]
    proposer = OllamaProposer(model="m")
    with pytest.raises(OllamaInvalidResponseError, match="missing 'response' field"):
        proposer.propose(question="q", wing="w", room="r1")


def test_response_field_is_not_json_raises(monkeypatch: object) -> None:
    def _non_json_inner(_req: urllib.request.Request, **_: object) -> io.BytesIO:
        return _fake_response({"response": "this isn't JSON at all"})

    monkeypatch.setattr(urllib.request, "urlopen", _non_json_inner)  # type: ignore[attr-defined]
    proposer = OllamaProposer(model="m")
    with pytest.raises(OllamaInvalidResponseError, match="not valid JSON"):
        proposer.propose(question="q", wing="w", room="r1")


def test_response_field_json_not_object_raises(monkeypatch: object) -> None:
    def _list_inner(_req: urllib.request.Request, **_: object) -> io.BytesIO:
        return _fake_response({"response": json.dumps(["claim", "predicted"])})

    monkeypatch.setattr(urllib.request, "urlopen", _list_inner)  # type: ignore[attr-defined]
    proposer = OllamaProposer(model="m")
    with pytest.raises(OllamaInvalidResponseError, match="not an object"):
        proposer.propose(question="q", wing="w", room="r1")


def test_missing_claim_field_raises(monkeypatch: object) -> None:
    def _no_claim(_req: urllib.request.Request, **_: object) -> io.BytesIO:
        return _fake_response({"response": json.dumps({"predicted_outcome": "x"})})

    monkeypatch.setattr(urllib.request, "urlopen", _no_claim)  # type: ignore[attr-defined]
    proposer = OllamaProposer(model="m")
    with pytest.raises(OllamaInvalidResponseError, match="'claim'"):
        proposer.propose(question="q", wing="w", room="r1")


def test_missing_predicted_outcome_field_raises(monkeypatch: object) -> None:
    def _no_predicted(_req: urllib.request.Request, **_: object) -> io.BytesIO:
        return _fake_response({"response": json.dumps({"claim": "x"})})

    monkeypatch.setattr(urllib.request, "urlopen", _no_predicted)  # type: ignore[attr-defined]
    proposer = OllamaProposer(model="m")
    with pytest.raises(OllamaInvalidResponseError, match="'predicted_outcome'"):
        proposer.propose(question="q", wing="w", room="r1")


def test_empty_claim_field_raises(monkeypatch: object) -> None:
    def _empty_claim(_req: urllib.request.Request, **_: object) -> io.BytesIO:
        return _fake_response({"response": json.dumps({"claim": "   ", "predicted_outcome": "y"})})

    monkeypatch.setattr(urllib.request, "urlopen", _empty_claim)  # type: ignore[attr-defined]
    proposer = OllamaProposer(model="m")
    with pytest.raises(OllamaInvalidResponseError, match="'claim'"):
        proposer.propose(question="q", wing="w", room="r1")
