"""Independent synthetic R18 acceptance. Frozen before runtime implementation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError, asdict, replace

import pytest
from practice_scope_unit import fixtures as _shared

from cairntir import procedures as api
from cairntir.access import AccessDenied, bind_grant, issue_grant
from cairntir.errors import MemoryStoreError
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer

WING = _shared.WING
isolation = _shared.isolation
InertRunner = _shared.InertRunner
bundle = _shared.bundle
obs = _shared.obs
policy = _shared.policy
assess = _shared.assess
complete = _shared.complete


def test_r18_public_api_structure():
    for name in (
        "PracticeObservation",
        "PracticeReviewPolicy",
        "PracticeObservationReceipt",
        "PracticeMetrics",
        "PracticeReviewAssessment",
        "PracticeReviewReceipt",
    ):
        assert hasattr(api, name), f"STRUCTURAL_MISSING_API: {name}"
    for name in (
        "record_observation",
        "get_observation",
        "observation_history",
        "assess_review",
        "complete_review",
        "get_review",
        "review_history",
        "due_reviews",
    ):
        assert hasattr(api.ProcedureBook, name), f"STRUCTURAL_MISSING_API: ProcedureBook.{name}"


def snapshot(b):
    # Bytes are a preservation oracle; not an alternate way to accept telemetry.
    return (
        tuple(
            b.store._conn.execute(
                "SELECT drawer_id,payload FROM procedure_records ORDER BY drawer_id"
            ).fetchall()
        ),
        tuple(
            (d.id, d.content)
            for d in b.store.list_by(
                wing=WING, room="discoveries", limit=None, include_expired=True
            )
        ),
        tuple(b.book.history(b.promoted.drawer_id)),
        b.runner.calls,
        len(b.approvals),
    )


def counts(b):
    return tuple(
        b.store._conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]  # noqa: S608 - fixed fixture table names
        for table in ("drawers", "procedure_records", "procedure_evaluations")
    )


def test_record_replay_correction_stale_branch_and_original_bytes(bundle):
    b = bundle
    before = snapshot(b)
    value = obs(b)
    first = b.book.record_observation(b.promoted.drawer_id, observation=value)
    first_bytes = b.store.get(first.drawer_id).content
    after_first = counts(b)
    assert b.book.record_observation(b.promoted.drawer_id, observation=value) == first
    assert counts(b) == after_first
    with pytest.raises(api.ProcedureError):
        b.book.record_observation(
            b.promoted.drawer_id, observation=replace(value, practice_impact=12)
        )
    changed = replace(value, practice_impact=12)
    second = b.book.record_observation(
        b.promoted.drawer_id, observation=changed, supersedes_id=first.drawer_id
    )
    assert (
        b.book.record_observation(
            b.promoted.drawer_id, observation=changed, supersedes_id=first.drawer_id
        )
        == second
    )
    with pytest.raises(api.ProcedureError):
        b.book.record_observation(
            b.promoted.drawer_id,
            observation=replace(value, practice_impact=20),
            supersedes_id=first.drawer_id,
        )
    assert b.book.get_observation(first.drawer_id) == first
    assert b.store.get(first.drawer_id).content == first_bytes
    assert b.book.observation_history(b.promoted.drawer_id) == [first, second]
    assert snapshot(b) == before


@pytest.mark.parametrize(
    "changes",
    [
        {"event_id": " "},
        {"event_id": True},
        {"event_id": "bad\ud800"},
        {"observed_on": "20260201"},
        {"observed_on": "2026-02-30"},
        {"observed_on": "2026-02-01 "},
        {"origin": "field"},
        {"triggered": 1},
        {"false_positive": 0},
        {"overridden": "false"},
        {"triggered": False, "false_positive": False},
        {"triggered": None, "overridden": False},
        {"baseline_impact": None},
        {"practice_impact": float("nan")},
        {"practice_impact": float("inf")},
        {"baseline_impact": True},
        {"impact_unit": None},
        {"impact_unit": " "},
        {"impact_unit": "bad\ud800"},
        {"baseline_impact": None, "practice_impact": None},
        {"evidence_ids": ()},
        {"evidence_ids": (True,)},
        {"evidence_ids": (0,)},
        {"evidence_ids": (999999,)},
    ],
)
def test_invalid_observation_is_typed_atomic(bundle, changes):
    b = bundle
    before = counts(b)
    with pytest.raises(api.ProcedureError):
        b.book.record_observation(b.promoted.drawer_id, observation=obs(b, **changes))
    assert counts(b) == before


@pytest.mark.parametrize(
    "changes",
    [
        {"minimum_observations": True},
        {"minimum_observations": 0},
        {"minimum_trigger_rate": -0.1},
        {"maximum_override_rate": 1.1},
        {"maximum_false_positive_rate": True},
        {"minimum_mean_impact": float("nan")},
        {"impact_unit": None},
        {
            "minimum_trigger_rate": None,
            "maximum_false_positive_rate": None,
            "maximum_override_rate": None,
            "minimum_mean_impact": None,
            "impact_unit": None,
        },
    ],
)
def test_invalid_policy_typed_and_assessment_read_only(bundle, changes):
    b = bundle
    before = counts(b)
    with pytest.raises(api.ProcedureError):
        assess(b, policy=policy(**changes))
    assert counts(b) == before


@pytest.mark.parametrize(
    "changes",
    [
        {"period_start": "20260101"},
        {"period_end": "2026-01-01"},
        {"as_of": "2026-01-01"},
        {"as_of": "2026-04-01T00:00:00Z"},
        {"period_start": "2026-02-30"},
    ],
)
def test_calendar_validation_is_read_only(bundle, changes):
    before = counts(bundle)
    with pytest.raises(api.ProcedureError):
        assess(bundle, **changes)
    assert counts(bundle) == before


def test_copied_room_record_is_not_authenticated_and_cannot_promote(bundle):
    b = bundle
    receipt = b.book.record_observation(b.promoted.drawer_id, observation=obs(b))
    original = b.store.get(receipt.drawer_id)
    copied = b.store.add(
        Drawer(
            wing=WING,
            room="practice-reviews",
            content=original.content,
            metadata=dict(original.metadata),
        )
    )
    with pytest.raises(api.ProcedureError):
        b.book.get_observation(copied.id)
    assert b.book.observation_history(b.promoted.drawer_id) == [receipt]
    with pytest.raises(api.ProcedureError):
        b.book.get_evaluation(receipt.drawer_id)
    candidate = b.book.propose(wing=WING, spec=replace(b.spec, governance=None))
    with pytest.raises(api.ProcedureError):
        b.book.promote(candidate.drawer_id, evaluation_id=receipt.drawer_id)


def test_source_evidence_same_wing_and_caller_sequence_detached(bundle):
    b = bundle
    foreign = b.store.add(
        Drawer(wing="foreign-proof", room="cases", content="foreign inert source")
    )
    with pytest.raises(api.ProcedureError):
        b.book.record_observation(
            b.promoted.drawer_id, observation=obs(b, evidence_ids=(foreign.id,))
        )
    with pytest.raises(api.ProcedureError):
        b.book.record_observation(
            b.promoted.drawer_id, observation=obs(b, evidence_ids=(b.evidence, b.evidence))
        )
    source = [b.evidence]
    value = obs(b, evidence_ids=source)
    source.append(foreign.id)
    assert value.evidence_ids == (b.evidence,)
    receipt = b.book.record_observation(b.promoted.drawer_id, observation=value)
    with pytest.raises((FrozenInstanceError, AttributeError)):
        receipt.drawer_id = 999


@pytest.mark.parametrize("fail_at", ["add", "_register_procedure_evaluation"])
def test_observation_write_failure_rolls_back_and_clean_retry(bundle, monkeypatch, fail_at):
    b = bundle
    original = getattr(b.store, fail_at)  # noqa: F841 - preserve original frozen case
    before = counts(b)

    def failed(*args, **kwargs):
        raise MemoryStoreError("injected inert write failure")

    with monkeypatch.context() as patch:
        patch.setattr(b.store, fail_at, failed)
        with pytest.raises(MemoryStoreError):
            b.book.record_observation(b.promoted.drawer_id, observation=obs(b))
    assert counts(b) == before
    assert b.book.observation_history(b.promoted.drawer_id) == []
    receipt = b.book.record_observation(b.promoted.drawer_id, observation=obs(b))
    assert b.book.get_observation(receipt.drawer_id) == receipt


def test_scoped_denial_and_partial_visibility_are_authoritative(bundle):
    b = bundle
    receipt = b.book.record_observation(b.promoted.drawer_id, observation=obs(b))
    token = issue_grant(
        b.store,
        scopes=[{"wing": WING, "rooms": ["discoveries", "cases", "procedure-evaluations"]}],
        capabilities=["read", "write"],
    )
    limited = api.ProcedureBook(bind_grant(b.store, token), {})
    before = counts(b)
    for action in (
        lambda: limited.record_observation(b.promoted.drawer_id, observation=obs(b, "new")),
        lambda: limited.get_observation(receipt.drawer_id),
        lambda: limited.assess_review(
            b.promoted.drawer_id,
            period_start="2026-01-01",
            period_end="2026-04-01",
            as_of="2026-04-01",
            policy=policy(),
        ),
    ):
        with pytest.raises(AccessDenied):
            action()
    assert counts(b) == before
    readonly = issue_grant(b.store, scopes=[{"wing": WING}], capabilities=["read"])
    reader = api.ProcedureBook(bind_grant(b.store, readonly), {})
    assert reader.get_observation(receipt.drawer_id) == receipt
    with pytest.raises(AccessDenied):
        reader.record_observation(b.promoted.drawer_id, observation=obs(b, "readonly"))


def metric(assessment, origin="observed"):
    assert tuple(m.origin for m in assessment.metrics) == ("observed", "simulated", "unknown")
    return next(m for m in assessment.metrics if m.origin == origin)


def test_exact_metrics_origin_separation_and_strict_breaches(bundle):
    b = bundle
    for value in (
        obs(b, "a"),
        obs(b, "b", false_positive=True, overridden=True, practice_impact=10),
        obs(b, "c", triggered=False, false_positive=None, overridden=None, practice_impact=12),
        obs(
            b, "sim", origin="simulated", false_positive=True, overridden=True, practice_impact=-100
        ),
        obs(
            b,
            "unknown",
            origin="unknown",
            triggered=None,
            false_positive=None,
            overridden=None,
            baseline_impact=None,
            practice_impact=None,
            impact_unit=None,
        ),
    ):
        b.book.record_observation(b.promoted.drawer_id, observation=value)
    before = counts(b)
    assessment = assess(b, as_of="2026-03-01")
    m = metric(assessment)
    assert (m.observation_count, m.triggered_count, m.trigger_known, m.trigger_unknown) == (
        3,
        2,
        3,
        0,
    )
    assert (
        m.false_positive_known,
        m.false_positive_unknown,
        m.override_known,
        m.override_unknown,
    ) == (2, 0, 2, 0)
    assert (m.impact_known, m.impact_unknown, m.impact_unit) == (3, 0, "minutes")
    assert m.trigger_rate == pytest.approx(2 / 3)
    assert m.false_positive_rate == 0.5
    assert m.override_rate == 0.5
    assert m.mean_impact == 2.0
    assert assessment.reasons == ("trigger-rate", "false-positive-rate", "override-rate", "impact")
    assert metric(assessment, "simulated").observation_count == 1
    assert metric(assessment, "simulated").mean_impact == -110
    u = metric(assessment, "unknown")
    assert (
        u.observation_count,
        u.trigger_unknown,
        u.false_positive_unknown,
        u.override_unknown,
        u.impact_unknown,
    ) == (1, 1, 1, 1, 1)
    assert (u.trigger_rate, u.false_positive_rate, u.override_rate, u.mean_impact) == (
        None,
        None,
        None,
        None,
    )
    equality = assess(
        b,
        as_of="2026-03-01",
        policy=policy(
            minimum_trigger_rate=2 / 3,
            maximum_false_positive_rate=0.5,
            maximum_override_rate=0.5,
            minimum_mean_impact=2,
        ),
    )
    assert equality.reasons == ()
    assert counts(b) == before


def test_all_missing_stays_unknown_and_zero_trigger_denominators(bundle):
    b = bundle
    empty = metric(assess(b))
    assert (empty.observation_count, empty.trigger_known, empty.impact_known) == (0, 0, 0)
    assert (
        empty.trigger_rate,
        empty.false_positive_rate,
        empty.override_rate,
        empty.mean_impact,
        empty.impact_unit,
    ) == (None, None, None, None, None)
    b.book.record_observation(
        b.promoted.drawer_id,
        observation=obs(
            b,
            "false",
            triggered=False,
            false_positive=None,
            overridden=None,
            baseline_impact=None,
            practice_impact=None,
            impact_unit=None,
        ),
    )
    m = metric(assess(b))
    assert m.trigger_rate == 0
    assert (m.false_positive_rate, m.override_rate, m.mean_impact) == (None, None, None)
    b.book.record_observation(
        b.promoted.drawer_id,
        observation=obs(b, "missing", triggered=None, false_positive=None, overridden=None),
    )
    m = metric(assess(b))
    assert (m.trigger_rate, m.false_positive_rate, m.override_rate, m.mean_impact) == (
        None,
        None,
        None,
        None,
    )
    assert (
        m.trigger_known,
        m.trigger_unknown,
        m.false_positive_unknown,
        m.override_unknown,
        m.impact_known,
        m.impact_unknown,
    ) == (1, 1, 1, 1, 1, 1)


def test_unknown_eligibility_or_applicable_flag_keeps_rates_unknown(bundle):
    b = bundle
    b.book.record_observation(b.promoted.drawer_id, observation=obs(b, "known"))
    b.book.record_observation(
        b.promoted.drawer_id, observation=obs(b, "partial", false_positive=None, overridden=None)
    )
    m = metric(assess(b))
    assert m.trigger_rate == 1
    assert (m.false_positive_rate, m.override_rate) == (None, None)
    assert (
        m.false_positive_known,
        m.false_positive_unknown,
        m.override_known,
        m.override_unknown,
    ) == (1, 1, 1, 1)
    b.book.record_observation(
        b.promoted.drawer_id,
        observation=obs(
            b, "eligible-unknown", triggered=None, false_positive=None, overridden=None
        ),
    )
    m = metric(assess(b))
    assert (m.trigger_rate, m.false_positive_rate, m.override_rate) == (None, None, None)
    assert (m.false_positive_unknown, m.override_unknown) == (2, 2)


def test_half_open_calendar_windows_corrections_and_no_field_quarter_claim(bundle):
    b = bundle
    receipts = []
    for event, day, origin in (
        ("before", "2025-12-31", "observed"),
        ("start", "2026-01-01", "observed"),
        ("mid", "2026-02-28", "observed"),
        ("asof", "2026-03-01", "observed"),
        ("end", "2026-04-01", "observed"),
        ("future-sim", "2099-01-01", "simulated"),
    ):
        receipts.append(
            b.book.record_observation(
                b.promoted.drawer_id, observation=obs(b, event, observed_on=day, origin=origin)
            )
        )
    correction = b.book.record_observation(
        b.promoted.drawer_id,
        observation=replace(receipts[2].observation, practice_impact=16),
        supersedes_id=receipts[2].drawer_id,
    )
    partial = assess(b, as_of="2026-03-01")
    assert partial.observation_ids == (receipts[1].drawer_id, correction.drawer_id)
    assert metric(partial).observation_count == 2
    assert metric(partial).mean_impact == 5
    assert partial.period_end == "2026-04-01" and partial.as_of == "2026-03-01"
    assert "due" not in partial.reasons
    assert assess(b).observation_ids == (
        receipts[1].drawer_id,
        receipts[3].drawer_id,
        correction.drawer_id,
    )


def test_each_metric_uses_own_adequate_denominator_and_nonobserved_never_alerts(bundle):
    b = bundle
    for i in range(3):
        b.book.record_observation(
            b.promoted.drawer_id,
            observation=obs(
                b,
                f"sim-{i}",
                origin="simulated",
                false_positive=True,
                overridden=True,
                practice_impact=-100,
            ),
        )
        b.book.record_observation(
            b.promoted.drawer_id,
            observation=obs(
                b,
                f"unknown-{i}",
                origin="unknown",
                false_positive=True,
                overridden=True,
                practice_impact=-100,
            ),
        )
    assert assess(b, as_of="2026-03-01").reasons == ()
    b.book.record_observation(
        b.promoted.drawer_id,
        observation=obs(b, "one-trigger", false_positive=True, overridden=True, practice_impact=0),
    )
    b.book.record_observation(
        b.promoted.drawer_id,
        observation=obs(
            b,
            "non-trigger",
            triggered=False,
            false_positive=None,
            overridden=None,
            practice_impact=0,
        ),
    )
    a = assess(b, as_of="2026-03-01")
    assert metric(a).false_positive_rate == 1 and metric(a).override_rate == 1
    assert a.reasons == ("trigger-rate", "impact")


def test_mixed_units_and_nonfinite_aggregate_fail_typed_read_only(bundle):
    b = bundle
    b.book.record_observation(b.promoted.drawer_id, observation=obs(b, "minutes"))
    b.book.record_observation(
        b.promoted.drawer_id, observation=obs(b, "seconds", impact_unit="seconds")
    )
    before = counts(b)
    with pytest.raises(api.ProcedureError):
        assess(b)
    assert counts(b) == before
    other = b.book.propose(
        wing=WING, spec=replace(b.spec, governance=replace(b.spec.governance, version="other"))
    )
    b.book.record_observation(
        other.drawer_id,
        observation=obs(
            b, "overflow", origin="simulated", baseline_impact=-1e308, practice_impact=1e308
        ),
    )
    with pytest.raises(api.ProcedureError):
        b.book.assess_review(
            other.drawer_id,
            period_start="2026-01-01",
            period_end="2026-04-01",
            as_of="2026-04-01",
            policy=policy(),
        )


def test_review_acknowledges_evidence_retains_metrics_and_uses_explicit_next_due(bundle):
    b = bundle
    baseline = snapshot(b)
    original = b.book.record_observation(
        b.promoted.drawer_id,
        observation=obs(b, "a", false_positive=True, overridden=True, practice_impact=0),
    )
    b.book.record_observation(
        b.promoted.drawer_id,
        observation=obs(b, "b", false_positive=True, overridden=True, practice_impact=0),
    )
    assessment = assess(b)
    receipt = complete(b, assessment)
    assert receipt.assessment == assessment
    assert (
        receipt.reviewed_on,
        receipt.reviewer,
        receipt.rationale,
        receipt.decision,
        receipt.next_review_due,
    ) == (
        "2026-04-01",
        "  Reviewer attribution  ",
        "Evidence checked\nverbatim  ",
        "retain",
        "2026-07-01",
    )
    before_replay = counts(b)
    assert complete(b, assessment) == receipt
    assert counts(b) == before_replay
    assert b.book.get_review(receipt.drawer_id) == receipt
    assert b.book.review_history(b.promoted.drawer_id) == [receipt]
    fresh = assess(b)
    assert fresh.metrics == assessment.metrics
    assert fresh.reasons == ()
    assert fresh.last_review_id == receipt.drawer_id and fresh.effective_review_due == "2026-07-01"
    assert assess(b, as_of="2026-07-01").reasons == ("due",)
    b.book.record_observation(
        b.promoted.drawer_id,
        observation=replace(original.observation, practice_impact=-1),
        supersedes_id=original.drawer_id,
    )
    assert assess(b).reasons == ("false-positive-rate", "override-rate", "impact")
    assert snapshot(b) == baseline
    with pytest.raises(api.ProcedureError):
        b.book.get_evaluation(receipt.drawer_id)


@pytest.mark.parametrize("decision", ["retain", "revise", "defer"])
def test_every_review_decision_is_immutable_attributed_and_not_execution(bundle, decision):
    b = bundle
    before = snapshot(b)
    receipt = complete(b, decision=decision)
    assert receipt.decision == decision
    assert snapshot(b) == before
    with pytest.raises((FrozenInstanceError, AttributeError)):
        receipt.decision = "retain"
    assert b.book.list(wing=WING) == [b.promoted]


@pytest.mark.parametrize(
    "changes",
    [
        {"decision": "promote"},
        {"reviewer": " "},
        {"reviewer": "bad\ud800"},
        {"reviewer": True},
        {"rationale": " "},
        {"rationale": "bad\udfff"},
        {"next_review_due": "2026-04-01"},
        {"next_review_due": "2026-03-01"},
        {"next_review_due": "20260701"},
    ],
)
def test_invalid_completion_typed_and_atomic(bundle, changes):
    before = counts(bundle)
    with pytest.raises(api.ProcedureError):
        complete(bundle, **changes)
    assert counts(bundle) == before


def test_stale_new_same_metric_evidence_forged_counts_and_review_race_reject(bundle):
    b = bundle
    b.book.record_observation(b.promoted.drawer_id, observation=obs(b))
    initial = assess(b)
    b.book.record_observation(b.promoted.drawer_id, observation=obs(b, "same-metric"))
    before = counts(b)
    with pytest.raises(api.ProcedureError):
        complete(b, initial)
    assert counts(b) == before
    current = assess(b)
    changed_metrics = (replace(current.metrics[0], observation_count=500),) + current.metrics[1:]  # noqa: RUF005 - preserve original case AST
    for forged in (
        replace(current, metrics=changed_metrics),
        replace(current, assessment_sha256="0" * 64),
        replace(current, reasons=()),
        replace(current, observation_ids=()),
    ):
        with pytest.raises(api.ProcedureError):
            complete(b, forged)
        assert counts(b) == before
    completed = complete(b, current)
    after = counts(b)
    with pytest.raises(api.ProcedureError):
        complete(b, current, decision="defer")
    assert counts(b) == after
    assert b.book.review_history(b.promoted.drawer_id) == [completed]


@pytest.mark.parametrize("fail_at", ["add", "_register_procedure_evaluation"])
def test_completion_failed_write_retains_history_and_clean_retry(bundle, monkeypatch, fail_at):
    b = bundle
    assessment = assess(b)
    before = counts(b)

    def failed(*args, **kwargs):
        raise MemoryStoreError("injected review write failure")

    with monkeypatch.context() as patch:
        patch.setattr(b.store, fail_at, failed)
        with pytest.raises(MemoryStoreError):
            complete(b, assessment)
    assert counts(b) == before and b.book.review_history(b.promoted.drawer_id) == []
    receipt = complete(b, assessment)
    assert b.book.get_review(receipt.drawer_id) == receipt


def test_governed_revision_history_late_observation_and_queue_boundaries(bundle):
    b = bundle
    first = b.book.record_observation(b.promoted.drawer_id, observation=obs(b))
    review = complete(b)
    old = b.promoted
    new_spec = replace(
        b.spec,
        steps=("changed candidate",),
        governance=replace(b.spec.governance, version="2", review_due="2026-05-01"),
    )
    new = b.book.revise(old.drawer_id, spec=new_spec)
    with pytest.raises(api.ProcedureError):
        b.book.record_observation(new.drawer_id, observation=obs(b, "not-promoted"))
    late = b.book.record_observation(
        old.drawer_id, observation=obs(b, "late", observed_on="2026-03-01")
    )
    simulated = b.book.record_observation(
        new.drawer_id, observation=obs(b, "event-1", origin="simulated")
    )
    assert b.book.observation_history(new.drawer_id) == [first, late, simulated]
    assert b.book.review_history(new.drawer_id) == [review]
    a = b.book.assess_review(
        new.drawer_id,
        period_start="2026-01-01",
        period_end="2026-04-01",
        as_of="2026-04-01",
        policy=policy(),
    )
    assert a.observation_ids == (simulated.drawer_id,) and a.version == "2"
    assert a.effective_review_due == "2026-05-01" and a.last_review_id is None
    assert (
        b.book.due_reviews(
            wing=WING,
            period_start="2026-01-01",
            period_end="2026-04-01",
            as_of="2026-04-01",
            policy=policy(),
        )
        == []
    )
    b.book.rollback(new.drawer_id, reason="withdrawn inert revision")
    with pytest.raises(api.ProcedureError):
        b.book.record_observation(new.drawer_id, observation=obs(b, "withdrawn", origin="unknown"))


def test_due_queue_current_promoted_only_and_legacy_wire_preservation(bundle):
    b = bundle
    legacy = b.book.propose(wing=WING, spec=replace(b.spec, governance=None))
    original = b.store.get(legacy.drawer_id).content
    payload = asdict(legacy.spec)
    payload.pop("governance")
    wire = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )
    assert original == f"Discovery: Evidence review\nState: candidate\n\n{wire}"
    expected_hash = hashlib.sha256(
        json.dumps(
            {"wing": WING, "spec": payload},
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    assert legacy.revision_sha256 == expected_hash
    with pytest.raises(api.ProcedureError):
        b.book.record_observation(
            legacy.drawer_id, observation=obs(b, "legacy", origin="simulated")
        )
    queue = b.book.due_reviews(
        wing=WING,
        period_start="2026-01-01",
        period_end="2026-04-01",
        as_of="2026-04-01",
        policy=policy(),
    )
    assert (
        len(queue) == 1
        and queue[0].procedure_id == b.promoted.drawer_id
        and queue[0].reasons == ("due",)
    )
    assert b.store.get(legacy.drawer_id).content == original


@pytest.mark.parametrize(
    "tamper", ["source", "observation-payload", "observation-content", "review-payload"]
)
def test_source_or_stored_record_tamper_surfaces_typed_without_writes(bundle, tamper):
    b = bundle
    recorded = b.book.record_observation(b.promoted.drawer_id, observation=obs(b))
    assessment = assess(b)
    reviewed = complete(b, assessment) if tamper == "review-payload" else None
    with b.store.transaction():
        if tamper == "source":
            b.store._conn.execute(
                "UPDATE drawers SET content=? WHERE id=?",
                ("deliberately altered inert source", b.evidence),
            )
        elif tamper == "observation-content":
            b.store._conn.execute(
                "UPDATE drawers SET content=? WHERE id=?",
                ("copied or damaged record", recorded.drawer_id),
            )
        else:
            target = reviewed.drawer_id if reviewed else recorded.drawer_id
            b.store._conn.execute(
                "UPDATE procedure_evaluations SET payload=? WHERE drawer_id=?",
                ('{"kind":"forged","receipt":{}}', target),
            )
    before = counts(b)
    if reviewed:
        with pytest.raises(api.ProcedureError):
            b.book.get_review(reviewed.drawer_id)
    else:
        with pytest.raises(api.ProcedureError):
            b.book.get_observation(recorded.drawer_id)
        with pytest.raises(api.ProcedureError):
            complete(b, assessment)
    assert counts(b) == before


def test_receipt_hashes_complete_reference_binding_and_reopen(bundle):
    b = bundle
    recorded = b.book.record_observation(b.promoted.drawer_id, observation=obs(b))
    assessment = assess(b)
    receipt = complete(b, assessment)
    assert recorded.procedure_id == b.promoted.drawer_id
    assert recorded.revision_sha256 == b.promoted.revision_sha256
    assert len(recorded.evidence_sha256) == 1
    for fingerprint in (
        recorded.record_sha256,
        *recorded.evidence_sha256,
        assessment.assessment_sha256,
        *assessment.observation_sha256,
        receipt.receipt_sha256,
    ):
        assert len(fingerprint) == 64 and set(fingerprint) <= set("0123456789abcdef")
    assert assessment.observation_sha256 == (recorded.record_sha256,)
    assert assessment.evidence_ids == tuple(sorted((b.evidence, recorded.drawer_id)))
    acknowledged = assess(b)
    assert acknowledged.evidence_ids == tuple(
        sorted((b.evidence, recorded.drawer_id, receipt.drawer_id))
    )
    b.store.checkpoint()
    with DrawerStore(b.path, HashEmbeddingProvider(dimension=16)) as reopened:
        book = api.ProcedureBook(reopened, {})
        assert book.get_observation(recorded.drawer_id) == recorded
        assert book.get_review(receipt.drawer_id) == receipt
        assert book.observation_history(b.promoted.drawer_id) == [recorded]
        assert book.review_history(b.promoted.drawer_id) == [receipt]


@pytest.mark.parametrize(
    "changes",
    [
        {"event_id": "x" * 257},
        {"event_id": " event"},
        {"impact_unit": "x" * 65},
        {"impact_unit": "minutes "},
        {"evidence_ids": (2**63,)},
        {"observed_on": "2099-01-01"},
    ],
)
def test_exact_bounds_and_observed_future_rejection(bundle, changes):
    before = counts(bundle)
    with pytest.raises(api.ProcedureError):
        bundle.book.record_observation(
            bundle.promoted.drawer_id, observation=obs(bundle, **changes)
        )
    assert counts(bundle) == before
