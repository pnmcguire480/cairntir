# Evidence-driven practice review

R18 adds an opt-in Python API for reviewing R17 governed practices. A host records
source-backed observations, requests an assessment with an explicit policy, and
records an attributed decision. Recording or reviewing never edits a procedure,
promotes a candidate, changes approval, withdraws a practice, or runs a repair.
There is no background scheduler or new CLI/MCP command.

## Record evidence and review it

The host supplies an existing `ProcedureBook`, an authenticated promoted governed
`practice_id`, and a same-wing source drawer `source_id`. Observation IDs identify
events within a practice family and content revision. Declare the origin honestly:
`observed` requires a promoted revision; `simulated` and `unknown` remain separate.
Origins and reviewer names are attribution, not proof of identity or field truth.

```python
from cairntir.procedures import PracticeObservation, PracticeReviewPolicy

receipt = book.record_observation(
    practice_id,
    observation=PracticeObservation(
        event_id="source-event-42",
        observed_on="2026-09-30",
        origin="observed",
        triggered=True,
        false_positive=False,
        overridden=False,
        baseline_impact=10,
        practice_impact=14,
        impact_unit="tasks-completed",
        evidence_ids=(source_id,),
    ),
)
policy = PracticeReviewPolicy(
    minimum_observations=20,
    maximum_false_positive_rate=0.1,
    maximum_override_rate=0.2,
    minimum_mean_impact=1,
    impact_unit="tasks-completed",
)
assessment = book.assess_review(
    practice_id,
    period_start="2026-07-01",
    period_end="2026-10-01",
    as_of="2026-10-01",
    policy=policy,
)
# Present assessment.metrics, assessment.reasons and its evidence to the reviewer.
completion = book.complete_review(
    practice_id,
    assessment=assessment,
    reviewer="named local reviewer",
    decision="retain",
    rationale="Reviewed the cited evidence and retained the current practice.",
    next_review_due="2027-01-01",
)
```

These thresholds are illustrative host choices, not product defaults. A higher
impact is better: mean impact is `practice_impact - baseline_impact`. Choose an
appropriate signed measurement and one explicit unit. Source contents are bound
by raw UTF-8 SHA256; changing source content invalidates the observation rather
than silently changing its meaning.

Use `None` for missing flags or impact. False-positive and override flags apply
only to a known `triggered=True` event; otherwise they must be `None`. Impact is a
complete finite pair with a unit, or two `None` values with no unit. Events need
1–64 unique source IDs, a canonical date, and a nonblank event ID of at most 256
characters without outer whitespace. Future observed dates are rejected against
the UTC calendar date. Simulated future events can be stored, but a window excludes
events at or after its explicit `as_of`.

## Assessments and decisions

The half-open window is `[period_start, min(period_end, as_of))`. Only the latest
correction for each event and revision contributes. Assessments always expose
`observed`, `simulated`, and `unknown` cohorts, with counts of known and missing
measurements. Empty denominators or missing applicable values leave the metric
`None`. Mixed impact units or nonfinite arithmetic raise `ProcedureError`.

Trigger rate is triggered events divided by events with fully known eligibility.
False-positive and override rates use triggered events. An unknown trigger makes
those rates unknown. Mean impact requires complete pairs for every selected event.
Unknown values are never converted to zero or estimated from a measured subset.

Review reasons are ordered `due`, `trigger-rate`, `false-positive-rate`,
`override-rate`, `impact`. The due date is inclusive. Evidence reasons require the
observed cohort, the corresponding metric's declared minimum sample, and a strict
threshold breach. Equality is not a breach. Simulated data cannot establish a
measured field quarter or trigger field-evidence reasons. The caller chooses the
window; the API does not infer that every event was captured.

`complete_review` recomputes the assessment under the existing write transaction.
Stale revisions, new or corrected evidence, changed sources and forged snapshots
fail without appending a completion. Decisions are `retain`, `revise`, or `defer`;
they record an outcome only. Reviewer text (up to 256 characters) and rationale
(up to 8192) are preserved verbatim. The next due date must follow `as_of`.
Completion acknowledges the selected observation fingerprints and advances that
revision's deadline. Metrics remain visible; new or corrected observed evidence
can trigger another review.

Exact observation and completion replays return the existing receipt. To correct
an event, call `record_observation` with the changed value and
`supersedes_id=latest_receipt.drawer_id`. A stale correction or changed replay
without that reference fails. Historical promoted revisions accept late observed
events; simulated/unknown writes require the current non-withdrawn revision.
New content versions have their own review deadline and evidence cohort.

`get_observation`, `observation_history`, `get_review`, and `review_history` expose
authenticated immutable records across a family. `due_reviews(wing=...,
period_start=..., period_end=..., as_of=..., policy=...)` returns assessments with
reasons for current promoted opted-in practices. It does not schedule delivery.

## Persistence, upgrade and limits

No schema migration or live adoption is required. New records use the existing
`practice-reviews` drawer room and authenticated generic evaluation ledger, with
versioned observation/review tags. They cannot be read as holdout evaluations or
satisfy promotion. Existing procedure specifications and lifecycle records keep
their exact format. Install the qualified source in participating hosts through a
separately authorized rollout before using the new API; this feature does not
upgrade, restart, or grant access to hosts.

Existing scoped access remains authoritative. Reading a denied record or source
raises `AccessDenied`; incomplete visibility must not become complete statistics.
Malformed new records raise `ProcedureError`; existing storage exceptions remain
distinct. Metadata-only copies have no local registry origin and cannot become
observations or reviews. Portable drawer copies do not restore that origin.
Preserve the full SQLite store and its authenticated ledger when backing up this
history. The implementation reads complete room/family history without a row cap;
it does not add pagination, background aggregation, or cryptographic attestation
against a privileged database editor. Qualification uses inert synthetic stores,
not production outcomes.
