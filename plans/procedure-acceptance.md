# Evaluated procedures: independent acceptance contract

Tester: `/root/foundation_tester`. Coordinator API and complete-suite review
passed before freeze. Scope is trusted local evaluation and operator-controlled
promotion of evidence-backed methods. No method executes automatically during
recall, import, handoff or promotion. No new MCP tool or dependency is required.

## Python API

`cairntir.procedures` exposes frozen dataclasses with these fields:

```python
ProcedureSpec(
    title: str,
    prerequisites: tuple[str, ...],
    applicability: str,
    steps: tuple[str, ...],
    expected_outcome: str,
    rollback: tuple[str, ...],
    evidence_ids: tuple[int, ...],
    counterexample_ids: tuple[int, ...] = (),
    development_case_ids: tuple[str, ...] = (),
)
HoldoutCase(case_id: str, evidence_id: int, expected_outcome: str)
EvaluationManifest(
    evaluator_id: str,
    baseline_steps: tuple[str, ...],
    cases: tuple[HoldoutCase, ...],
    metric: str = "success_rate_delta",
    threshold: float = 0.5,
)
RegisteredEvaluation(manifest: EvaluationManifest, runner: ExperimentRunner)
Procedure(
    drawer_id: int, wing: str, state: str, revision_sha256: str,
    spec: ProcedureSpec, supersedes_id: int | None, evaluation_id: int | None,
)
CaseResult(
    case_id: str, evidence_id: int,
    baseline_prediction_id: int, baseline_observation_id: int,
    candidate_prediction_id: int, candidate_observation_id: int,
    baseline_success: bool, candidate_success: bool,
)
EvaluationReceipt(
    drawer_id: int, procedure_id: int, current_id: int,
    revision_sha256: str, manifest_sha256: str, evaluation_sha256: str,
    evaluator_id: str, metric: str, threshold: float,
    baseline_score: float, candidate_score: float, passed: bool,
    cases: tuple[CaseResult, ...],
)
ApprovalRequest(
    procedure_id: int, wing: str, title: str, revision_sha256: str,
    evaluation_id: int, evaluation_sha256: str,
)
```

The local host constructs
`ProcedureBook(store, evaluations: Mapping[str, RegisteredEvaluation], operator_approval=None)`.
Registry keys equal evaluator IDs. The optional callback accepts an immutable
`ApprovalRequest` and must return the actual boolean `True` to authorize
promotion. Missing callback, `False`, truthy text or model-supplied approval
metadata cannot authorize. Registry and callback are trusted startup code,
never strings resolved through drawer contents, imports or tool arguments.

Methods:

```python
book.propose(wing=..., spec=...) -> Procedure
book.revise(drawer_id, *, spec=...) -> Procedure
book.evaluate(drawer_id, *, evaluator_id=...) -> EvaluationReceipt
book.promote(drawer_id, *, evaluation_id=...) -> Procedure
book.rollback(drawer_id, *, reason=...) -> Procedure
book.list(*, wing=..., active_only=True) -> list[Procedure]
book.history(drawer_id) -> list[Procedure]
book.get_evaluation(evaluation_id) -> EvaluationReceipt
```

`propose` creates a candidate Discovery. `revise` appends a new candidate;
`evaluate` accepts a current candidate and appends authentic evaluation
evidence, then a corroborated Discovery only if the fixed metric passes.
Receipt `procedure_id` is the evaluated candidate; `current_id` is its resulting
corroborated leaf on pass, otherwise the unchanged candidate. Promotion takes
that current leaf and the matching receipt. Rollback appends an expired or
rejected leaf. `active_only=True` returns promoted reusable methods only;
`False` returns every current leaf. History retains all authenticated revisions
and transitions in oldest-first order. Existing Discovery listing also sees
the authentic lifecycle drawers.

## Evaluation and identity

All fields must be meaningfully populated; step/prerequisite/rollback tuples
are nonempty. Referenced evidence must exist in the same wing; counterexamples
are a subset of evidence. Holdout IDs are unique, do not overlap declared
development case IDs, and their evidence IDs/content must be disjoint from
candidate development evidence. Aliasing the same case text under another
drawer ID does not establish independence. Imported or ordinary drawer
metadata never establishes an evaluation or operator receipt.

Only metric `success_rate_delta` is required: candidate successes divided by
case count, minus baseline successes divided by case count, must be at least
the predeclared threshold. Threshold is finite, numeric, non-boolean and in
`(0, 1]`. Manifest has at least two independent cases and baseline steps.
It binds evaluator identity, cases/expected outcomes and their original
evidence hashes, baseline steps, metric and threshold. A candidate revision
hash binds its wing and entire spec; lifecycle-only transitions retain that
revision hash. Evaluation hashes additionally bind all observations and the
evaluated candidate ID. SHA-256 strings are 64 lowercase hexadecimal digits;
canonical encoding is an implementation choice, but identities must be
deterministic and sensitive to every bound field.

For every holdout case, the registered `ExperimentRunner.run(Hypothesis)` is
actually invoked once for baseline and once for candidate. Its `claim` is a
JSON object with exactly these semantic fields (key order is irrelevant):

```json
{
  "procedure_id": 123,
  "revision_sha256": "...",
  "manifest_sha256": "...",
  "evaluator_id": "trusted-local-runner/v1",
  "case_id": "holdout-a",
  "evidence_id": 456,
  "variant": "baseline",
  "steps": ["identity"],
  "input": "verbatim original case evidence"
}
```

Candidate calls use `variant="candidate"` and spec steps. Hypothesis wing is
the procedure wing, room is `procedure-evaluations`, and predicted outcome is
the case's exact expected outcome. The returned existing Reason `Outcome`
must bind the same hypothesis, contain nonempty experiment/observation text
and an actual boolean success. Existing Reason prediction/observation drawers
retain each success and failure, with the observation superseding its exact
prediction. Aggregate success cannot erase failed holdout evidence. An
unregistered runner ID cannot cause any execution.

Corroborated Discovery evidence includes every baseline/candidate observation;
its counterexamples include each failed candidate observation. If a registered
runner raises, retain explanatory failure evidence, surface a typed error and
leave the candidate uncorroborated. Invalid or misbound Outcomes cannot count
as passing cases.

## Authority, concurrency and persistence

Privileged procedure registrations and authentic evaluation/promotion receipts
need durable origin outside ordinary drawer metadata. The coordinator owns
the schema-v7 migration and table design; acceptance prescribes no private
column names. Cloning a valid receipt/procedure drawer, supplying trust/system
metadata, or using ordinary `record_discovery`/`transition_discovery` must not
create an authorized state or supersede a registered procedure. Historical
unregistered Discovery behavior remains compatible.

Runner execution and operator callbacks can be slow. After either returns,
the final write atomically rechecks the current authenticated leaf, complete
revision, manifest and evaluation identity. Concurrent revision/rollback makes
the pending operation stale. Competing transitions cannot create two current
authorized leaves. Callback approval is bound to the exact immutable request;
changing a procedure or evaluator manifest invalidates prior approval.

Rollback hides the method from active queries without deleting/replacing old
text, evidence or approvals. Reopening a store preserves authentic history;
reconstructing a book without an operator callback cannot authorize another
promotion. Validation/stale/unauthorized failures are surfaced typed errors,
not silent success. Existing MCP 21-tool/public snapshots remain unchanged.

## Verification budget

The tester will author real-store behavioral tests using a deterministic
trusted evaluator that executes a small local list-processing procedure.
No snapshot/lifecycle/transaction implementation is mocked. The final quarter
of the milestone is reserved for verification; at most two repair rounds.
All old frozen artifacts remain immutable history. This generation will bind
its owned tests/contract/baseline and selected unchanged regression tests;
it will record, rather than permanently freeze, schema/version/dependency
configuration fingerprints. All new artifacts use LF bytes.

The 43-case suite maps the contract to complete candidate validation; scoped
references; disjoint holdout identity; finite metric thresholds; actual runner
calls and bound Reason evidence; failed/exceptional evaluations; strict local
approval; ordinary Discovery and cloned-receipt forgery; every revision and
manifest field; stale external work; competing approvals; and rollback/history
loaded again in a fresh Python process. The trusted fixture executes identity,
deduplication and sorting operations: baseline succeeds on zero of three
holdout cases, the lexical candidate succeeds on two, and its remaining
numeric-order failure must stay visible.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_procedure_acceptance.py --no-cov -q --tb=line
.\.venv\Scripts\python.exe -m pytest tests/unit/test_learning.py tests/unit/test_reason_loop.py tests/unit/test_mcp_server.py tests/integration/test_mcp_backend.py --no-cov -q
.\.venv\Scripts\python.exe -m ruff check tests/unit/test_procedure_acceptance.py
.\.venv\Scripts\python.exe -m ruff format --check tests/unit/test_procedure_acceptance.py
```

[Baseline JSON](procedure-baseline.json) records exact counts, source HEAD and
fingerprints, actual fixture outcomes and raw evidence hashes. The complete
four-file regression selection above preserves existing Discovery, Reason and
MCP behavior; the wider release gate additionally includes the unchanged
foundation/concurrency suites. [Freeze manifest](procedure-freeze.json) binds
the acceptance artifacts and test inputs. It excludes its own externally
reported hash, and deliberately does not permanently bind version/schema
configuration or dependency-lock files. Those are recorded as baseline
provenance. Future acceptance records must preserve this baseline, verify all
bound hashes and identify the exact runtime tested.

Final preimplementation baseline: **43 failed in 1.41s**, all because the API
is absent; **118 existing regression cases passed in 4.50s**. No collection,
setup or infrastructure error occurred. Source fingerprints stayed identical
during the baseline. The independent fixture executed all six baseline/candidate
cases with the expected zero-versus-two successes; its fresh-process reader
script compiles. Ruff and format checks pass. Artifact readiness is PASS;
implementation acceptance remains FAIL until independent postimplementation
verification.
