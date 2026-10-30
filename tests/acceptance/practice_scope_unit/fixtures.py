"""Original inert R18 fixtures for scope and transaction-composition controls."""

from __future__ import annotations

import json
import socket
from types import SimpleNamespace

import pytest

from cairntir import procedures as api
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.reason.model import Experiment, Outcome

WING = "r18-proof"


@pytest.fixture(autouse=True)
def isolation(tmp_path, monkeypatch):
    for name in (
        "HOME",
        "USERPROFILE",
        "CAIRNTIR_HOME",
        "XDG_CACHE_HOME",
        "HF_HOME",
        "TRANSFORMERS_CACHE",
    ):
        target = tmp_path / name.lower()
        target.mkdir()
        monkeypatch.setenv(name, str(target))
    for name in (
        "CAIRNTIR_DISABLE_AUTOREGISTER",
        "CAIRNTIR_DISABLE_UPDATE_CHECK",
        "HF_HUB_OFFLINE",
        "TRANSFORMERS_OFFLINE",
    ):
        monkeypatch.setenv(name, "1")

    def forbidden(*args, **kwargs):
        pytest.fail("OFFLINE_GUARD: network or model inference attempted")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    from cairntir.memory import embeddings

    monkeypatch.setattr(embeddings, "production_embedding_provider", forbidden)
    monkeypatch.setattr(embeddings.FastEmbedProvider, "__init__", forbidden)
    monkeypatch.setattr(embeddings.SentenceTransformerProvider, "__init__", forbidden)


class InertRunner:
    def __init__(self):
        self.calls = 0

    def run(self, hypothesis):
        self.calls += 1
        passed = json.loads(hypothesis.claim)["variant"] == "candidate"
        return Outcome(
            experiment=Experiment(hypothesis=hypothesis, description="inert acceptance fixture"),
            observed="pass" if passed else "baseline",
            success=passed,
            delta="" if passed else "known baseline",
        )


@pytest.fixture
def bundle(tmp_path):
    with DrawerStore(tmp_path / "inert.db", HashEmbeddingProvider(dimension=16)) as store:
        ids = [
            store.add(Drawer(wing=WING, room="cases", content=f"inert evidence {i}")).id
            for i in range(4)
        ]
        runner = InertRunner()
        registration = api.RegisteredEvaluation(
            api.EvaluationManifest(
                "inert/v1",
                ("baseline",),
                tuple(api.HoldoutCase(f"holdout-{i}", ids[i], "pass") for i in (1, 2)),
            ),
            runner,
        )
        approvals = []

        def approve(request):
            approvals.append(request)
            return True

        book = api.ProcedureBook(store, {"inert/v1": registration}, operator_approval=approve)
        spec = api.ProcedureSpec(
            "Evidence review",
            ("inert",),
            "fixture",
            ("candidate",),
            "pass",
            ("reuse input",),
            (ids[0],),
            governance=api.PracticeGovernance(
                "Fixture owner", "1", "Explicit opt in", "2026-04-01"
            ),
        )
        candidate = book.propose(wing=WING, spec=spec)
        evaluation = book.evaluate(candidate.drawer_id, evaluator_id="inert/v1")
        promoted = book.promote(evaluation.current_id, evaluation_id=evaluation.drawer_id)
        yield SimpleNamespace(
            store=store,
            book=book,
            spec=spec,
            promoted=promoted,
            evidence=ids[3],
            runner=runner,
            approvals=approvals,
            registration=registration,
            path=tmp_path / "inert.db",
        )


def obs(b, event="event-1", **changes):
    return api.PracticeObservation(
        **{
            "event_id": event,
            "observed_on": "2026-02-01",
            "origin": "observed",
            "triggered": True,
            "false_positive": False,
            "overridden": False,
            "baseline_impact": 10.0,
            "practice_impact": 14.0,
            "impact_unit": "minutes",
            "evidence_ids": (b.evidence,),
            **changes,
        }
    )


def policy(**changes):
    return api.PracticeReviewPolicy(
        **{
            "minimum_observations": 2,
            "minimum_trigger_rate": 0.75,
            "maximum_false_positive_rate": 0.4,
            "maximum_override_rate": 0.4,
            "minimum_mean_impact": 3,
            "impact_unit": "minutes",
            **changes,
        }
    )


def assess(b, **changes):
    return b.book.assess_review(
        b.promoted.drawer_id,
        **{
            "period_start": "2026-01-01",
            "period_end": "2026-04-01",
            "as_of": "2026-04-01",
            "policy": policy(),
            **changes,
        },
    )


def complete(b, assessment=None, **changes):
    return b.book.complete_review(
        b.promoted.drawer_id,
        **{
            "assessment": assessment or assess(b),
            "reviewer": "  Reviewer attribution  ",
            "decision": "retain",
            "rationale": "Evidence checked\nverbatim  ",
            "next_review_due": "2026-07-01",
            **changes,
        },
    )
