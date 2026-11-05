"""Scheduler behavior with synthetic stores and controlled PALADIN receipts."""

from __future__ import annotations

import importlib
import importlib.util
import json
import socket
import unittest
from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path

import pytest
from paladin_python_unit.fixtures import PreparedFixture
from typer.testing import CliRunner

from cairntir import cli
from cairntir.access import AccessDenied, bind_grant, issue_grant
from cairntir.errors import CairntirError
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.paladin_python import PaladinPythonError, PaladinPythonRun
from cairntir.procedures import (
    EvaluationManifest,
    HoldoutCase,
    PracticeGovernance,
    PracticeObservation,
    PracticeReviewPolicy,
    ProcedureBook,
    ProcedureError,
    ProcedureSpec,
    RegisteredEvaluation,
)
from cairntir.reason.model import Experiment, Outcome

WING = "r18-connected-proof"


@pytest.fixture(autouse=True)
def offline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("HOME", "USERPROFILE", "CAIRNTIR_HOME", "XDG_CACHE_HOME", "HF_HOME"):
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

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("R18 fixture attempted network access")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


def _scheduler(store: DrawerStore):
    assert importlib.util.find_spec("cairntir.practice_scheduler") is not None, (
        "R18_SCHEDULER_API_MISSING"
    )
    module = importlib.import_module("cairntir.practice_scheduler")
    return module.PracticeReviewScheduler(store)


def _source(store: DrawerStore, text: str, *, wing: str = WING) -> int:
    item = store.add(Drawer(wing=wing, room="cases", content=text))
    assert item.id is not None
    return item.id


class _InertEvaluator:
    def run(self, hypothesis):
        steps = json.loads(hypothesis.claim)["steps"]
        passed = "candidate" in steps
        return Outcome(
            experiment=Experiment(hypothesis=hypothesis, description="Synthetic R18 fixture"),
            observed="pass" if passed else "baseline",
            success=passed,
            delta="" if passed else "known baseline",
        )


def _promoted(store: DrawerStore, *, wing: str = WING, due: str = "2027-01-01"):
    source_id = _source(store, "Synthetic rule development case", wing=wing)
    holdout_id = _source(store, "Synthetic held-out case", wing=wing)
    second_holdout_id = _source(store, "Independent synthetic held-out case", wing=wing)
    evaluator_id = "r18-inert/v1"
    manifest = EvaluationManifest(
        evaluator_id,
        ("baseline",),
        (
            HoldoutCase("held-out-a", holdout_id, "pass"),
            HoldoutCase("held-out-b", second_holdout_id, "pass"),
        ),
    )
    book = ProcedureBook(
        store,
        {evaluator_id: RegisteredEvaluation(manifest, _InertEvaluator())},
        operator_approval=lambda _request: True,
    )
    spec = ProcedureSpec(
        "Connected review practice",
        ("local input",),
        "Synthetic workflow case",
        ("candidate",),
        "pass",
        ("return to source",),
        (source_id,),
        governance=PracticeGovernance("Fixture owner", "1", "Initial governed rule", due),
    )
    candidate = book.propose(wing=wing, spec=spec)
    evaluation = book.evaluate(candidate.drawer_id, evaluator_id=evaluator_id)
    assert evaluation.passed
    promoted = book.promote(evaluation.current_id, evaluation_id=evaluation.drawer_id)
    return book, promoted


def _policy():
    return PracticeReviewPolicy(
        minimum_observations=1,
        maximum_false_positive_rate=0.25,
    )


def _plan(path: Path, *, wing: str = WING) -> Path:
    path.write_text(
        json.dumps(
            {
                "wing": wing,
                "first_scan_on": "2027-01-01",
                "scan_interval_days": 1,
                "policy": asdict(_policy()),
            }
        ),
        encoding="utf8",
    )
    return path


def _receipt_source(store: DrawerStore, practice_id: int, *, event_id: str, false_positive):
    book = ProcedureBook(store, {})
    evidence_id = _source(
        store, f"Recorded synthetic use {event_id}: triggered; false-positive={false_positive}"
    )
    return book.record_observation(
        practice_id,
        observation=PracticeObservation(
            event_id=event_id,
            observed_on="2026-10-14",
            origin="observed",
            triggered=True,
            false_positive=false_positive,
            overridden=None,
            baseline_impact=None,
            practice_impact=None,
            impact_unit=None,
            evidence_ids=(evidence_id,),
        ),
    )


def _assert_published_assessment(
    store: DrawerStore, queue: dict, proposal: dict, *, practice_id: int
) -> None:
    expected = ProcedureBook(store, {}).assess_review(
        practice_id,
        period_start="2026-07-15",
        period_end="2026-10-15",
        as_of="2026-10-15",
        policy=_policy(),
    )
    assert proposal["assessment"] == json.loads(json.dumps(asdict(expected)))
    assert proposal["evidence_ids"] == list(expected.evidence_ids)
    for source_id in expected.evidence_ids:
        assert f"cairntir://drawer/{source_id}" in queue["rendered"]


def test_actual_stage_intake_keeps_unknowns_and_replays_without_dispatch():
    case = unittest.TestCase()
    try:
        fixture = PreparedFixture(case, modes=("normal", "normal", "normal"))
        run = PaladinPythonRun(fixture.runtime, contract=fixture.contract(0))
        stage = run.execute("unit", fixture.action("unit", 0))
        stage_id = stage["evidence"][-1]["drawer_id"]
        book, promoted = _promoted(fixture.store, wing="paladin")
        observed = PracticeObservation(
            event_id="actual-stage-use-1",
            observed_on="2026-10-14",
            origin="observed",
            triggered=None,
            false_positive=None,
            overridden=None,
            baseline_impact=None,
            practice_impact=None,
            impact_unit=None,
            evidence_ids=(),
        )
        method = getattr(run, "record_practice_observation", None)
        assert callable(method), "R18_STAGE_INTAKE_API_MISSING"
        before_effects = fixture.effects()
        saved = method("unit", promoted.drawer_id, observation=observed)
        again = method("unit", promoted.drawer_id, observation=observed)
        assert again.drawer_id == saved.drawer_id
        assert stage_id in saved.observation.evidence_ids
        assert saved.procedure_id == promoted.drawer_id
        assert saved.observation.origin == "observed"
        assert saved.observation.triggered is None
        assert saved.observation.false_positive is None
        assert saved.observation.overridden is None
        assert saved.observation.baseline_impact is None
        assert saved.observation.practice_impact is None
        row = run.check_report(observation_ids=(saved.drawer_id,))["observations"][0]
        assert row["scope"] == "stage" and row["stage_result_id"] == stage_id
        assert row["triggered"] is None and row["baseline_impact"] is None
        assert fixture.effects() == before_effects
        before_ids = {x.drawer_id for x in book.observation_history(promoted.drawer_id)}
        with pytest.raises((PaladinPythonError, ProcedureError)):
            method("integration", promoted.drawer_id, observation=observed)
        assert {x.drawer_id for x in book.observation_history(promoted.drawer_id)} == before_ids
        _other_book, other = _promoted(fixture.store, wing="other-wing")
        with pytest.raises((PaladinPythonError, ProcedureError)):
            method("unit", other.drawer_id, observation=observed)
        assert _other_book.observation_history(other.drawer_id) == []
        (fixture.outputs[0] / "unit/report.xml").write_text("tampered", encoding="utf8")
        with pytest.raises((PaladinPythonError, ProcedureError)):
            method(
                "unit",
                promoted.drawer_id,
                observation=replace(observed, event_id="tampered-stage-reuse"),
            )
        assert {x.drawer_id for x in book.observation_history(promoted.drawer_id)} == before_ids
    finally:
        case.doCleanups()


def test_quarterly_due_tick_survives_restart_and_keeps_unknown_metrics(tmp_path: Path):
    db = tmp_path / "review.db"
    with DrawerStore(db, HashEmbeddingProvider(dimension=16)) as store:
        book, promoted = _promoted(store)
        _receipt_source(store, promoted.drawer_id, event_id="due-observation", false_positive=None)
        schedule = _scheduler(store).configure(
            wing=WING, first_scan_on="2027-01-01", policy=_policy(), scan_interval_days=1
        )
        assert schedule["wing"] == WING and schedule["schedule_id"] > 0
        assert book.review_history(promoted.drawer_id) == []
    with DrawerStore(db, HashEmbeddingProvider(dimension=16)) as reopened:
        queue = _scheduler(reopened).tick(wing=WING, as_of="2027-01-01")
        proposal = next(x for x in queue["proposals"] if x["procedure_id"] == promoted.drawer_id)
        assert "due" in proposal["assessment"]["reasons"]
        assert proposal["suggested_action"] == "inspect-evidence"
        assert proposal["assessment"]["metrics"][0]["observation_count"] == 1
        assert proposal["assessment"]["metrics"][0]["false_positive_rate"] is None
        assert proposal["evidence_ids"]
        assert queue["simulated_clock"] is True
        assert "simulated" in queue["rendered"].lower()
        assert "field quarter established" not in queue["rendered"].lower()
        repeated = _scheduler(reopened).tick(wing=WING, as_of="2027-01-01")
        same = next(x for x in repeated["proposals"] if x["procedure_id"] == promoted.drawer_id)
        assert same["proposal_id"] == proposal["proposal_id"]
        live = _scheduler(reopened).tick(wing=WING)
        assert live["simulated_clock"] is False
        assert live["next_scan_on"] == "2027-01-01"
        assert not any(x["procedure_id"] == promoted.drawer_id for x in live["proposals"])
        assert ProcedureBook(reopened, {}).review_history(promoted.drawer_id) == []
        assert ProcedureBook(reopened, {}).list(wing=WING)[0].drawer_id == promoted.drawer_id


def test_schedule_change_requires_supersession_and_tampered_source_refuses_tick(tmp_path: Path):
    with DrawerStore(tmp_path / "review.db", HashEmbeddingProvider(dimension=16)) as store:
        _book, promoted = _promoted(store)
        observed = _receipt_source(
            store, promoted.drawer_id, event_id="tamper-source", false_positive=True
        )
        scheduler = _scheduler(store)
        first = scheduler.configure(wing=WING, first_scan_on="2027-01-01", policy=_policy())
        changed = PracticeReviewPolicy(minimum_observations=1, maximum_false_positive_rate=0.2)
        with pytest.raises(CairntirError):
            scheduler.configure(wing=WING, first_scan_on="2027-01-01", policy=changed)
        assert scheduler.tick(wing=WING, as_of="2026-10-15")["schedule_id"] == first["schedule_id"]
        second = scheduler.configure(
            wing=WING,
            first_scan_on="2027-01-01",
            policy=changed,
            supersedes_id=first["schedule_id"],
        )
        assert second["schedule_id"] != first["schedule_id"]
        with pytest.raises(CairntirError):
            scheduler.configure(
                wing=WING,
                first_scan_on="2027-01-01",
                policy=_policy(),
                supersedes_id=first["schedule_id"],
            )
        source_id = observed.observation.evidence_ids[0]
        store._conn.execute("UPDATE drawers SET content = ? WHERE id = ?", ("tampered", source_id))
        before = store._conn.execute(
            "SELECT COUNT(*) FROM drawers WHERE wing = ? AND room = 'practice-schedules'",
            (WING,),
        ).fetchone()[0]
        with pytest.raises(CairntirError):
            scheduler.tick(wing=WING, as_of="2026-10-15")
        after = store._conn.execute(
            "SELECT COUNT(*) FROM drawers WHERE wing = ? AND room = 'practice-schedules'",
            (WING,),
        ).fetchone()[0]
        assert after == before


def test_incomplete_wing_authority_cannot_publish_review_queue(tmp_path: Path):
    with DrawerStore(tmp_path / "review.db", HashEmbeddingProvider(dimension=16)) as store:
        _book, promoted = _promoted(store)
        scheduler = _scheduler(store)
        scheduler.configure(wing=WING, first_scan_on="2027-01-01", policy=_policy())
        token = issue_grant(
            store, scopes=[{"wing": WING, "rooms": ["discoveries"]}], capabilities=["read"]
        )
        restricted = _scheduler(bind_grant(store, token))
        before = store._conn.execute(
            "SELECT COUNT(*) FROM drawers WHERE wing = ? AND room = 'practice-schedules'",
            (WING,),
        ).fetchone()[0]
        with pytest.raises(AccessDenied) as denied:
            restricted.tick(wing=WING, as_of="2027-01-01")
        assert str(promoted.drawer_id) not in str(denied.value)
        after = store._conn.execute(
            "SELECT COUNT(*) FROM drawers WHERE wing = ? AND room = 'practice-schedules'",
            (WING,),
        ).fetchone()[0]
        assert after == before


def test_fresh_observed_breach_triggers_early_and_completion_resets(tmp_path: Path):
    with DrawerStore(tmp_path / "review.db", HashEmbeddingProvider(dimension=16)) as store:
        book, promoted = _promoted(store)
        saved = _receipt_source(
            store, promoted.drawer_id, event_id="early-false-positive", false_positive=True
        )
        scheduler = _scheduler(store)
        scheduler.configure(wing=WING, first_scan_on="2027-01-01", policy=_policy())
        queue = scheduler.tick(wing=WING, as_of="2026-10-15")
        proposal = next(x for x in queue["proposals"] if x["procedure_id"] == promoted.drawer_id)
        assert "false-positive-rate" in proposal["assessment"]["reasons"]
        assert proposal["suggested_action"] == "revise"
        assert saved.drawer_id in proposal["evidence_ids"]
        assert "1" in proposal["rationale"] and "0.25" in proposal["rationale"]
        assert f"cairntir://drawer/{saved.drawer_id}" in queue["rendered"]
        _assert_published_assessment(store, queue, proposal, practice_id=promoted.drawer_id)
        hidden = deepcopy(proposal)
        hidden["assessment"]["observation_ids"] = []
        with pytest.raises(AssertionError):
            _assert_published_assessment(store, queue, hidden, practice_id=promoted.drawer_id)
        unlinked = deepcopy(queue)
        unlinked["rendered"] = unlinked["rendered"].replace(
            f"cairntir://drawer/{saved.drawer_id}", ""
        )
        with pytest.raises(AssertionError):
            _assert_published_assessment(store, unlinked, proposal, practice_id=promoted.drawer_id)
        refreshed = scheduler.tick(wing=WING, as_of="2026-10-16")
        still = next(x for x in refreshed["proposals"] if x["procedure_id"] == promoted.drawer_id)
        assert still["proposal_id"] == proposal["proposal_id"]
        assert book.review_history(promoted.drawer_id) == []
        assessment = book.assess_review(
            promoted.drawer_id,
            period_start="2026-07-15",
            period_end="2026-10-15",
            as_of="2026-10-15",
            policy=_policy(),
        )
        book.complete_review(
            promoted.drawer_id,
            assessment=assessment,
            reviewer="Synthetic reviewer",
            decision="retain",
            rationale="Recorded evidence was reviewed; no rule changed.",
            next_review_due="2027-01-01",
        )
        after = scheduler.tick(wing=WING, as_of="2026-10-15")
        assert not any(x["procedure_id"] == promoted.drawer_id for x in after["proposals"])
        assert book.list(wing=WING)[0].drawer_id == promoted.drawer_id


def test_cli_unattended_tick_survives_restart_without_operator_action(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    db = home / "cairntir.db"
    with DrawerStore(db, HashEmbeddingProvider(dimension=16)) as store:
        _book, promoted = _promoted(store)
    monkeypatch.setenv("CAIRNTIR_HOME", str(home))
    monkeypatch.setattr(
        cli, "production_embedding_provider", lambda: HashEmbeddingProvider(dimension=16)
    )
    monkeypatch.setattr(
        cli, "ensure_registered", lambda: pytest.fail("unexpected startup registration")
    )
    monkeypatch.setattr(
        cli, "maybe_check_in_background", lambda: pytest.fail("unexpected startup update check")
    )
    plan = _plan(tmp_path / "plan.json")
    configured = CliRunner().invoke(cli.app, ["practice-review", "configure", str(plan)])
    assert configured.exit_code == 0, repr(configured.exception) + configured.output
    args = ["practice-review", "tick", "--wing", WING, "--as-of", "2027-01-01", "--json"]
    first = CliRunner().invoke(cli.app, args)
    assert first.exit_code == 0, repr(first.exception) + first.output
    report = json.loads(first.output)
    assert report["wing"] == WING and report["proposals"]
    assert report["simulated_clock"] is True
    with DrawerStore(db, HashEmbeddingProvider(dimension=16)) as store:
        assert ProcedureBook(store, {}).list(wing=WING)[0].drawer_id == promoted.drawer_id
        assert ProcedureBook(store, {}).review_history(promoted.drawer_id) == []
    second = CliRunner().invoke(cli.app, args)
    assert second.exit_code == 0
    assert (
        json.loads(second.output)["proposals"][0]["proposal_id"]
        == report["proposals"][0]["proposal_id"]
    )
    absent = CliRunner().invoke(
        cli.app, ["practice-review", "tick", "--wing", "unconfigured", "--json"]
    )
    assert absent.exit_code != 0
    assert str(promoted.drawer_id) not in absent.output
