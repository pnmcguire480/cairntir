"""Local-AI proposer adapters — v1.1+.

The Reason loop's :class:`~cairntir.reason.HypothesisProposer` port
accepts any object that turns ``(question, wing, room)`` into a
:class:`~cairntir.reason.model.Hypothesis`. This module ships the first
inference-backed implementation: :class:`OllamaProposer`, which calls a
locally-running Ollama daemon (``http://localhost:11434`` by default)
to draft the claim + predicted outcome.

Local-first by construction:

* Ollama runs on the user's machine. No cloud API. No billed tokens.
  No telemetry leaving the box.
* Stdlib only. No new Cairntir dependencies. The whole adapter is
  ``urllib.request`` + ``json`` + a tiny prompt template.
* Transport-isolated. The Reason loop sees a ``Hypothesis``; it does
  not know an HTTP call happened. Fakes can swap this proposer out
  without changing the loop.

If Ollama is not running or the requested model is not pulled, the
adapter raises :class:`OllamaUnavailableError` with a message that explains
exactly what to do — never a silent fallback to garbage.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from cairntir.errors import CairntirError
from cairntir.reason.model import Hypothesis


class OllamaError(CairntirError):
    """Raised on any failure talking to a local Ollama daemon.

    Subclasses surface specific recovery hints; callers that just want
    "did the proposer work?" can catch this base class.
    """


class OllamaUnavailableError(OllamaError):
    """The Ollama daemon is not reachable at the configured endpoint."""


class OllamaModelMissingError(OllamaError):
    """The requested model is not installed locally."""


class OllamaInvalidResponseError(OllamaError):
    """The daemon returned a body Cairntir cannot parse into a Hypothesis."""


_PROMPT_TEMPLATE = """\
You are a structured reasoning assistant for the Cairntir memory system.
Your task is to turn a question into a falsifiable scientific hypothesis.

Cairntir's prediction-bound drawer schema requires two fields:

  - claim: a precise, falsifiable statement about the world. State a
    proposition that can be verified or refuted by future evidence. Do
    not hedge.
  - predicted_outcome: a concrete, observable consequence that should
    follow if the claim is true. Specific enough that a later observer
    can decide whether it occurred. Avoid vague projections like "this
    will be important"; prefer "X will happen by Y" or "metric A will
    move to value B in conditions C".

Wing context (the Cairntir project this hypothesis belongs to):
{wing}

Room context (the topic within that project):
{room}

Question:
{question}

Respond with EXACTLY one JSON object on a single line and nothing else.
The object must have these keys and only these keys:

{{"claim": "<falsifiable statement>", "predicted_outcome": "<concrete observable consequence>"}}

Do not include code fences. Do not include any prose before or after the JSON.
"""


@dataclass
class OllamaProposer:
    """Implements :class:`~cairntir.reason.HypothesisProposer` over a local Ollama daemon.

    Constructor parameters:

    * ``model`` — the Ollama model tag (e.g. ``"gemma2:2b"``,
      ``"llama3.1:8b"``). Must already be pulled with
      ``ollama pull <model>`` before use.
    * ``endpoint`` — base URL of the Ollama HTTP API. Defaults to
      ``http://localhost:11434``, which is Ollama's standard.
    * ``timeout`` — request timeout in seconds. Defaults to 120.
      Generation on a small model is fast; the timeout exists to keep
      a hung daemon from blocking the Reason loop forever.

    The proposer is stateless. Calling :meth:`propose` repeatedly is
    safe and concurrent calls each open their own HTTP request.
    """

    model: str
    endpoint: str = "http://localhost:11434"
    timeout: float = 120.0

    def propose(self, *, question: str, wing: str, room: str) -> Hypothesis:
        """Ask the local model to draft a hypothesis for ``question``.

        Returns a :class:`~cairntir.reason.model.Hypothesis` whose
        ``wing`` and ``room`` match the loop's call (the model's
        suggestions for those fields, if any, are ignored — Cairntir
        owns the taxonomy, not the LLM).

        Raises:
            OllamaUnavailableError: the daemon did not answer the request.
            OllamaModelMissingError: the daemon answered but reported the
                requested model is not pulled.
            OllamaInvalidResponseError: the daemon answered but returned a
                body Cairntir cannot parse into a hypothesis.
        """
        prompt = _PROMPT_TEMPLATE.format(question=question, wing=wing, room=room)
        body = json.dumps(
            {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                # JSON output mode: Ollama 0.1.30+ honors this and
                # constrains generation to a single JSON object.
                "format": "json",
                # Low temperature keeps the JSON shape stable.
                "options": {"temperature": 0.2},
            }
        ).encode("utf-8")

        url = self.endpoint.rstrip("/") + "/api/generate"
        # Endpoint is a caller-controlled URL (defaults to localhost:11434);
        # the schemes Cairntir accepts are http/https only by virtue of how
        # Ollama is deployed. The S310 warning targets file:/// and custom
        # schemes, which are out-of-band here.
        request = urllib.request.Request(  # noqa: S310
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                raw = response.read().decode("utf-8")
        except urllib.error.URLError as exc:
            # Connection refused, host unreachable, DNS failure — every
            # variant lands here. Surface a clear message that names
            # the endpoint so the user can check `ollama serve`.
            raise OllamaUnavailableError(
                f"could not reach Ollama at {self.endpoint}: {exc}. "
                "Is the daemon running? Try `ollama serve` (or "
                "`ollama list` to confirm models are available)."
            ) from exc
        except TimeoutError as exc:
            raise OllamaUnavailableError(
                f"Ollama at {self.endpoint} did not respond within "
                f"{self.timeout}s — the daemon may be hung."
            ) from exc

        try:
            envelope = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise OllamaInvalidResponseError(
                f"Ollama returned non-JSON response: {raw[:200]!r}"
            ) from exc

        # Ollama wraps every model error inside a normal 200 envelope
        # under the "error" key — surface it as a typed exception.
        if "error" in envelope:
            err_text = str(envelope["error"])
            if "not found" in err_text.lower() or "no such" in err_text.lower():
                raise OllamaModelMissingError(
                    f"Ollama reports model {self.model!r} is not pulled. "
                    f"Run `ollama pull {self.model}` and try again. "
                    f"(daemon said: {err_text})"
                )
            raise OllamaInvalidResponseError(f"Ollama error: {err_text}")

        response_text = envelope.get("response")
        if not isinstance(response_text, str) or not response_text.strip():
            raise OllamaInvalidResponseError(
                f"Ollama envelope missing 'response' field: {envelope!r}"
            )

        try:
            payload = json.loads(response_text)
        except json.JSONDecodeError as exc:
            raise OllamaInvalidResponseError(
                f"Ollama 'response' is not valid JSON: {response_text[:200]!r}"
            ) from exc

        if not isinstance(payload, dict):
            raise OllamaInvalidResponseError(
                f"Ollama JSON payload is not an object: {payload!r}"
            )

        claim = payload.get("claim")
        predicted = payload.get("predicted_outcome")
        if not isinstance(claim, str) or not claim.strip():
            raise OllamaInvalidResponseError(
                f"Ollama JSON payload missing/empty 'claim' field: {payload!r}"
            )
        if not isinstance(predicted, str) or not predicted.strip():
            raise OllamaInvalidResponseError(
                f"Ollama JSON payload missing/empty 'predicted_outcome' field: {payload!r}"
            )

        return Hypothesis(
            claim=claim.strip(),
            predicted_outcome=predicted.strip(),
            wing=wing,
            room=room,
        )
