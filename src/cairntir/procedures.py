"""Evaluated local methods with durable, operator-controlled promotion."""

from __future__ import annotations

import builtins
import hashlib
import json
import math
import re
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import UTC, date, datetime
from typing import Any, cast

from cairntir.access import AccessDenied
from cairntir.errors import CairntirError
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer, Layer
from cairntir.reason.loop import (
    _build_observation_drawer,
    _build_prediction_drawer,
    _compute_delta,
    _validate_outcome,
)
from cairntir.reason.model import Hypothesis
from cairntir.reason.ports import ExperimentRunner


class ProcedureError(CairntirError):
    """A method, evaluation, or operator decision is invalid or stale."""


@dataclass(frozen=True)
class PracticeGovernance:
    """Attributed ownership and review intent, never permission or identity proof."""

    owner: str
    version: str
    rationale: str
    review_due: str


@dataclass(frozen=True)
class ProcedureSpec:
    """The complete method and its development evidence."""

    title: str
    prerequisites: tuple[str, ...]
    applicability: str
    steps: tuple[str, ...]
    expected_outcome: str
    rollback: tuple[str, ...]
    evidence_ids: tuple[int, ...]
    counterexample_ids: tuple[int, ...] = ()
    development_case_ids: tuple[str, ...] = ()
    governance: PracticeGovernance | None = None

    def __post_init__(self) -> None:
        """Detach sequence inputs from mutable caller-owned lists."""
        for name in (
            "prerequisites",
            "steps",
            "rollback",
            "evidence_ids",
            "counterexample_ids",
            "development_case_ids",
        ):
            object.__setattr__(self, name, tuple(getattr(self, name)))


@dataclass(frozen=True)
class HoldoutCase:
    """One independently identified input and expected outcome."""

    case_id: str
    evidence_id: int
    expected_outcome: str


@dataclass(frozen=True)
class EvaluationManifest:
    """Predeclared baseline, independent cases, and passing metric."""

    evaluator_id: str
    baseline_steps: tuple[str, ...]
    cases: tuple[HoldoutCase, ...]
    metric: str = "success_rate_delta"
    threshold: float = 0.5

    def __post_init__(self) -> None:
        """Freeze caller-owned sequence inputs."""
        object.__setattr__(self, "baseline_steps", tuple(self.baseline_steps))
        object.__setattr__(self, "cases", tuple(self.cases))


@dataclass(frozen=True)
class RegisteredEvaluation:
    """A manifest bound to a runner supplied by trusted startup code."""

    manifest: EvaluationManifest
    runner: ExperimentRunner


@dataclass(frozen=True)
class Procedure:
    """One authenticated, append-only method revision or transition."""

    drawer_id: int
    wing: str
    state: str
    revision_sha256: str
    spec: ProcedureSpec
    supersedes_id: int | None
    evaluation_id: int | None


@dataclass(frozen=True)
class CaseResult:
    """Both variants' predictions, observations, and actual verdicts."""

    case_id: str
    evidence_id: int
    baseline_prediction_id: int
    baseline_observation_id: int
    candidate_prediction_id: int
    candidate_observation_id: int
    baseline_success: bool
    candidate_success: bool


@dataclass(frozen=True)
class EvaluationReceipt:
    """Authentic evidence from an executed, predeclared evaluation."""

    drawer_id: int
    procedure_id: int
    current_id: int
    revision_sha256: str
    manifest_sha256: str
    evaluation_sha256: str
    evaluator_id: str
    metric: str
    threshold: float
    baseline_score: float
    candidate_score: float
    passed: bool
    cases: tuple[CaseResult, ...]


@dataclass(frozen=True)
class ApprovalRequest:
    """The exact immutable decision presented to the local operator."""

    procedure_id: int
    wing: str
    title: str
    revision_sha256: str
    evaluation_id: int
    evaluation_sha256: str


@dataclass(frozen=True)
class PracticeValidationPolicy:
    """Explicit evaluation requirements; origin remains an attribution."""

    assigned_tier: str
    minimum_cases: int
    minimum_score: float
    evidence_ids: tuple[int, ...]
    origin: str

    def __post_init__(self) -> None:
        """Detach source references from caller-owned sequences."""
        object.__setattr__(self, "evidence_ids", tuple(self.evidence_ids))


@dataclass(frozen=True)
class PracticeLifecycleReceipt:
    """An immutable opt-in phase bound to one candidate epoch."""

    drawer_id: int
    wing: str
    root_id: int
    procedure_id: int
    epoch_id: int
    revision_sha256: str
    state: str
    assigned_tier: str | None
    effective_tier: str | None
    mode: str
    evidence_ids: tuple[int, ...]
    previous_id: int | None
    validation_policy: PracticeValidationPolicy | None
    rationale: str
    recorded_at: str
    record_sha256: str


@dataclass(frozen=True)
class PracticeScanRow:
    """Selected guidance, never an execution or approval receipt."""

    procedure_id: int
    root_id: int
    state: str
    assigned_tier: str | None
    effective_tier: str | None
    mode: str
    source_ids: tuple[int, ...]
    lifecycle_id: int | None
    applied_supersession_id: int | None


@dataclass(frozen=True)
class PracticeSupersessionReceipt:
    """A contextual masking directive or its immutable restoration."""

    drawer_id: int
    wing: str
    older_root_id: int
    replacement_root_id: int
    older_id: int
    replacement_id: int
    context: tuple[str, ...]
    status: str
    evidence_ids: tuple[int, ...]
    previous_id: int | None
    rationale: str
    recorded_at: str
    record_sha256: str


@dataclass(frozen=True)
class PracticeConflictRule:
    """Attributed severity and applicable context for one original rule."""

    procedure_id: int
    severity: str
    context: tuple[str, ...]
    evidence_id: int

    def __post_init__(self) -> None:
        """Detach caller-owned context labels."""
        try:
            object.__setattr__(self, "context", tuple(self.context))
        except TypeError as exc:
            raise ProcedureError("rule context must be a sequence") from exc


@dataclass(frozen=True)
class PracticeConflictReceipt:
    """An authenticated comparison, never a developer approval."""

    drawer_id: int
    wing: str
    first: PracticeConflictRule
    second: PracticeConflictRule
    situation: tuple[str, ...]
    conflict_evidence_id: int
    origin: str
    status: str
    winner_id: int | None
    basis: str | None
    record_sha256: str


@dataclass(frozen=True)
class PracticeObservation:
    """An attributed measurement with explicit origin and source evidence."""

    event_id: str
    observed_on: str
    origin: str
    triggered: bool | None
    false_positive: bool | None
    overridden: bool | None
    baseline_impact: float | None
    practice_impact: float | None
    impact_unit: str | None
    evidence_ids: tuple[int, ...]

    def __post_init__(self) -> None:
        """Detach caller-owned evidence sequences."""
        try:
            object.__setattr__(self, "evidence_ids", tuple(self.evidence_ids))
        except TypeError as exc:
            raise ProcedureError("observation evidence must be a sequence") from exc


@dataclass(frozen=True)
class PracticeObservationReceipt:
    """One locally registered observation or immutable correction."""

    drawer_id: int
    procedure_id: int
    root_id: int
    revision_sha256: str
    observation: PracticeObservation
    supersedes_id: int | None
    evidence_sha256: tuple[str, ...]
    record_sha256: str

    def __post_init__(self) -> None:
        """Detach caller-owned source fingerprint sequences."""
        try:
            object.__setattr__(self, "evidence_sha256", tuple(self.evidence_sha256))
        except TypeError as exc:
            raise ProcedureError("observation source hashes must be a sequence") from exc


@dataclass(frozen=True)
class PracticeReviewPolicy:
    """Explicit review thresholds; units and policy are never inferred."""

    minimum_observations: int
    minimum_trigger_rate: float | None = None
    maximum_false_positive_rate: float | None = None
    maximum_override_rate: float | None = None
    minimum_mean_impact: float | None = None
    impact_unit: str | None = None


@dataclass(frozen=True)
class PracticeMetrics:
    """One origin cohort with measured denominators and explicit unknowns."""

    origin: str
    observation_count: int
    triggered_count: int
    trigger_known: int
    trigger_unknown: int
    false_positive_known: int
    false_positive_unknown: int
    override_known: int
    override_unknown: int
    impact_known: int
    impact_unknown: int
    trigger_rate: float | None
    false_positive_rate: float | None
    override_rate: float | None
    mean_impact: float | None
    impact_unit: str | None


@dataclass(frozen=True)
class PracticeReviewAssessment:
    """A source-bound review snapshot, not execution or approval authority."""

    procedure_id: int
    root_id: int
    revision_sha256: str
    version: str
    period_start: str
    period_end: str
    as_of: str
    effective_review_due: str
    last_review_id: int | None
    policy: PracticeReviewPolicy
    metrics: tuple[PracticeMetrics, ...]
    observation_ids: tuple[int, ...]
    observation_sha256: tuple[str, ...]
    evidence_ids: tuple[int, ...]
    reasons: tuple[str, ...]
    assessment_sha256: str

    def __post_init__(self) -> None:
        """Freeze every nested sequence independently of the caller."""
        try:
            for name in (
                "metrics",
                "observation_ids",
                "observation_sha256",
                "evidence_ids",
                "reasons",
            ):
                object.__setattr__(self, name, tuple(getattr(self, name)))
        except TypeError as exc:
            raise ProcedureError("review snapshot fields must be sequences") from exc


@dataclass(frozen=True)
class PracticeReviewReceipt:
    """An immutable attributed review decision without a method transition."""

    drawer_id: int
    assessment: PracticeReviewAssessment
    reviewed_on: str
    reviewer: str
    decision: str
    rationale: str
    next_review_due: str
    receipt_sha256: str


_PRACTICE_ROOM = "practice-reviews"
_OBSERVATION = "cairntir.practice-observation.v1"
_REVIEW = "cairntir.practice-review.v1"
_CONFLICT = "cairntir.practice-conflict.v1"
_ORIGINS = ("observed", "simulated", "unknown")


def _json(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _text(value: Any, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ProcedureError(f"{name} must be nonempty text")


def _texts(values: tuple[str, ...], name: str, *, required: bool = True) -> None:
    if required and not values:
        raise ProcedureError(f"{name} must contain at least one item")
    for item in values:
        _text(item, name)


def _positive_id(value: Any) -> None:
    if type(value) is not int or value < 1:
        raise ProcedureError("evidence IDs must be positive integers")


def _validate_governance(value: PracticeGovernance) -> None:
    if type(value) is not PracticeGovernance:
        raise ProcedureError("governance must be a PracticeGovernance value")
    for name in ("owner", "version", "rationale", "review_due"):
        field = getattr(value, name)
        if type(field) is not str or not field.strip():
            raise ProcedureError(f"governance {name} must be nonblank primitive text")
        try:
            field.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ProcedureError(f"governance {name} must be valid UTF-8 text") from exc
    if value.version != value.version.strip():
        raise ProcedureError("governance version must not have outer whitespace")
    try:
        parsed = date.fromisoformat(value.review_due)
    except ValueError as exc:
        raise ProcedureError("review_due must be a valid YYYY-MM-DD date") from exc
    if parsed.isoformat() != value.review_due:
        raise ProcedureError("review_due must be a canonical YYYY-MM-DD date")


def _spec_payload(spec: ProcedureSpec) -> dict[str, Any]:
    """Keep legacy wire bytes unchanged while binding optional governance."""
    if spec.governance is not None:
        _validate_governance(spec.governance)
    result = asdict(spec)
    if spec.governance is None:
        del result["governance"]
    return result


def _procedure(value: dict[str, Any]) -> Procedure:
    try:
        payload = dict(value["spec"])
        if "governance" in payload:
            if type(payload["governance"]) is not dict:
                raise ProcedureError("stored governance must be a complete object")
            payload["governance"] = PracticeGovernance(**payload["governance"])
        result = Procedure(
            drawer_id=value["drawer_id"],
            wing=value["wing"],
            state=value["state"],
            revision_sha256=value["revision_sha256"],
            spec=ProcedureSpec(**payload),
            supersedes_id=value["supersedes_id"],
            evaluation_id=value["evaluation_id"],
        )
        revision = _hash({"wing": result.wing, "spec": _spec_payload(result.spec)})
    except (KeyError, TypeError, ValueError) as exc:
        raise ProcedureError("stored procedure specification is malformed") from exc
    if result.revision_sha256 != revision:
        raise ProcedureError("procedure revision fingerprint mismatch")
    return result


def _receipt(value: dict[str, Any]) -> EvaluationReceipt:
    return EvaluationReceipt(
        **{**value, "cases": tuple(CaseResult(**item) for item in value["cases"])}
    )


def _practice_text(value: Any, name: str, maximum: int, *, label: bool = False) -> None:
    if type(value) is not str or not value.strip() or len(value) > maximum:
        raise ProcedureError(f"{name} must be nonblank primitive text within {maximum} characters")
    if label and value != value.strip():
        raise ProcedureError(f"{name} must not have outer whitespace")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ProcedureError(f"{name} must be valid UTF-8 text") from exc


def _practice_id(value: Any) -> None:
    if type(value) is not int or not 1 <= value <= 2**63 - 1:
        raise ProcedureError("practice references must be positive signed-64-bit integers")


def _conflict_context(value: tuple[str, ...]) -> tuple[str, ...]:
    if type(value) is not tuple or not 1 <= len(value) <= 64:
        raise ProcedureError("conflict context requires 1..64 labels")
    for label in value:
        _practice_text(label, "context label", 256, label=True)
    if len(set(value)) != len(value):
        raise ProcedureError("conflict context labels must be unique")
    return tuple(sorted(value))


def _conflict_rule(value: PracticeConflictRule) -> PracticeConflictRule:
    if type(value) is not PracticeConflictRule:
        raise ProcedureError("expected a PracticeConflictRule")
    _practice_id(value.procedure_id)
    _practice_id(value.evidence_id)
    if type(value.severity) is not str or value.severity not in ("P0", "P1", "P2", "P3"):
        raise ProcedureError("conflict severity must be P0, P1, P2 or P3")
    return replace(value, context=_conflict_context(value.context))


def _conflict_decision(
    first: PracticeConflictRule, second: PracticeConflictRule
) -> tuple[str, int | None, str | None]:
    if first.severity != second.severity:
        winner = first if first.severity < second.severity else second
        return "resolved", winner.procedure_id, "severity"
    a, b = set(first.context), set(second.context)
    if a < b or b < a:
        winner = second if a < b else first
        return "resolved", winner.procedure_id, "specificity"
    return "adr_required", None, None


def _practice_date(value: Any, name: str) -> date:
    if type(value) is not str:
        raise ProcedureError(f"{name} must be a canonical YYYY-MM-DD date")
    try:
        result = date.fromisoformat(value)
    except ValueError as exc:
        raise ProcedureError(f"{name} must be a canonical YYYY-MM-DD date") from exc
    if result.isoformat() != value:
        raise ProcedureError(f"{name} must be a canonical YYYY-MM-DD date")
    return result


def _practice_number(value: Any, name: str) -> None:
    try:
        valid = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise ProcedureError(f"{name} must be a finite primitive number")


def _validate_observation(value: PracticeObservation) -> None:
    if type(value) is not PracticeObservation:
        raise ProcedureError("expected a PracticeObservation")
    _practice_text(value.event_id, "event_id", 256, label=True)
    observed = _practice_date(value.observed_on, "observed_on")
    if type(value.origin) is not str or value.origin not in _ORIGINS:
        raise ProcedureError("observation origin must be observed, simulated or unknown")
    if value.origin == "observed" and observed > datetime.now(UTC).date():
        raise ProcedureError("an observed measurement cannot have a future date")
    for flag in (value.triggered, value.false_positive, value.overridden):
        if flag is not None and type(flag) is not bool:
            raise ProcedureError("observation flags must be primitive bool or None")
    if value.triggered is not True and (
        value.false_positive is not None or value.overridden is not None
    ):
        raise ProcedureError("false-positive and override flags require a known trigger")
    if value.baseline_impact is None and value.practice_impact is None:
        if value.impact_unit is not None:
            raise ProcedureError("unknown impact must not claim a unit")
    else:
        _practice_number(value.baseline_impact, "baseline_impact")
        _practice_number(value.practice_impact, "practice_impact")
        _practice_text(value.impact_unit, "impact_unit", 64, label=True)
    if not 1 <= len(value.evidence_ids) <= 64:
        raise ProcedureError("an observation requires 1..64 source evidence references")
    for reference in value.evidence_ids:
        _practice_id(reference)
    if len(set(value.evidence_ids)) != len(value.evidence_ids):
        raise ProcedureError("observation evidence references must be unique")


def _validate_review_policy(value: PracticeReviewPolicy) -> None:
    if type(value) is not PracticeReviewPolicy:
        raise ProcedureError("expected a PracticeReviewPolicy")
    _practice_id(value.minimum_observations)
    rates = (
        value.minimum_trigger_rate,
        value.maximum_false_positive_rate,
        value.maximum_override_rate,
    )
    for threshold in rates:
        if threshold is not None:
            _practice_number(threshold, "rate threshold")
            if not 0 <= threshold <= 1:
                raise ProcedureError("review rate thresholds must lie within [0,1]")
    if value.minimum_mean_impact is not None:
        _practice_number(value.minimum_mean_impact, "impact threshold")
        _practice_text(value.impact_unit, "policy impact_unit", 64, label=True)
    elif value.impact_unit is not None:
        raise ProcedureError("an impact policy unit requires an impact threshold")
    if all(item is None for item in (*rates, value.minimum_mean_impact)):
        raise ProcedureError("review policy must declare at least one evidence threshold")


def _practice_metrics(origin: str, values: list[PracticeObservation]) -> PracticeMetrics:
    count = len(values)
    triggered = [value for value in values if value.triggered is True]
    trigger_known = sum(value.triggered is not None for value in values)
    trigger_unknown = count - trigger_known
    fp_known = sum(value.false_positive is not None for value in triggered)
    override_known = sum(value.overridden is not None for value in triggered)
    impacts = [value for value in values if value.baseline_impact is not None]
    units = {value.impact_unit for value in impacts}
    if len(units) > 1:
        raise ProcedureError("impact measurements with different units cannot be combined")
    impact = None
    if impacts and len(impacts) == count:
        try:
            deltas = []
            for value in impacts:
                if value.practice_impact is None or value.baseline_impact is None:
                    raise ProcedureError("impact measurements require a complete pair")
                deltas.append(float(value.practice_impact) - float(value.baseline_impact))
            if not all(math.isfinite(delta) for delta in deltas):
                raise ProcedureError("impact arithmetic must remain finite")
            impact = math.fsum(deltas) / count
        except (OverflowError, ValueError) as exc:
            raise ProcedureError("impact arithmetic must remain finite") from exc
        _practice_number(impact, "mean impact")
    return PracticeMetrics(
        origin,
        count,
        len(triggered),
        trigger_known,
        trigger_unknown,
        fp_known,
        len(triggered) - fp_known + trigger_unknown,
        override_known,
        len(triggered) - override_known + trigger_unknown,
        len(impacts),
        count - len(impacts),
        len(triggered) / count if count and not trigger_unknown else None,
        sum(value.false_positive is True for value in triggered) / len(triggered)
        if triggered and not trigger_unknown and fp_known == len(triggered)
        else None,
        sum(value.overridden is True for value in triggered) / len(triggered)
        if triggered and not trigger_unknown and override_known == len(triggered)
        else None,
        impact,
        next(iter(units)) if units else None,
    )


def _assessment_material(value: PracticeReviewAssessment) -> dict[str, Any]:
    result = asdict(value)
    del result["assessment_sha256"]
    return result


def _review_window(start: str, end: str, as_of: str) -> None:
    first = _practice_date(start, "period_start")
    last = _practice_date(end, "period_end")
    cutoff = _practice_date(as_of, "as_of")
    if first >= last or first >= cutoff:
        raise ProcedureError("review window requires period_start before period_end and as_of")


def _review_decision(
    assessment: PracticeReviewAssessment,
    reviewer: str,
    decision: str,
    rationale: str,
    next_review_due: str,
) -> None:
    _practice_text(reviewer, "reviewer", 256)
    _practice_text(rationale, "review rationale", 8192)
    if type(decision) is not str or decision not in ("retain", "revise", "defer"):
        raise ProcedureError("review decision must be retain, revise or defer")
    if _practice_date(next_review_due, "next_review_due") <= _practice_date(
        assessment.as_of, "as_of"
    ):
        raise ProcedureError("next review date must be strictly after the explicit review date")


class _PracticeReadView:
    def __init__(self, store: DrawerStore) -> None:
        self._store = store

    def get(self, drawer_id: int) -> Drawer | None:
        if type(self._store) is DrawerStore:
            return self._store._read_drawer(drawer_id)
        return self._store.get(drawer_id)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._store, name)


def practice_read_view(store: DrawerStore) -> DrawerStore:
    """Retain scoped reads while avoiding owner access-tracking writes."""
    if isinstance(store, _PracticeReadView):
        return store
    return cast(DrawerStore, _PracticeReadView(store))


def _lifecycle_ids(value: Any) -> tuple[int, ...]:
    if type(value) not in (tuple, list) or not 1 <= len(value) <= 512:
        raise ProcedureError("practice evidence requires 1..512 references")
    result = tuple(value)
    for key in result:
        _practice_id(key)
    if len(set(result)) != len(result):
        raise ProcedureError("practice evidence references must be unique")
    return result


def _lifecycle_context(value: tuple[str, ...]) -> tuple[str, ...]:
    if type(value) is not tuple or not 1 <= len(value) <= 64:
        raise ProcedureError("practice context requires 1..64 tokens")
    if any(
        type(item) is not str or re.fullmatch(r"[a-z][a-z0-9-]{0,63}", item) is None
        for item in value
    ) or len(set(value)) != len(value):
        raise ProcedureError("practice context requires unique lowercase ASCII tokens")
    return value


def _lifecycle_mode(
    state: str, policy: PracticeValidationPolicy | None
) -> tuple[str | None, str | None, str]:
    assigned = policy.assigned_tier if policy else None
    if state == "experimental":
        return assigned, "P3", "INFORM"
    if state in {"active", "deprecated"}:
        return assigned, assigned, "ACTIVE" if state == "active" else "INFORM"
    return assigned, None, "UNAPPLIED"


def _lifecycle_stamp(value: Any) -> None:
    _practice_text(value, "recorded_at", 64, label=True)
    try:
        stamp = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ProcedureError("invalid practice timestamp") from exc
    if stamp.tzinfo is None or stamp.isoformat() != value:
        raise ProcedureError("practice timestamp must be canonical and timezone-aware")


_LIFECYCLE = "cairntir.practice-lifecycle.v1"
_SUPERSESSION = "cairntir.practice-supersession.v1"


class ProcedureBook:
    """Record methods, run registered evaluations, and apply operator decisions."""

    def __init__(
        self,
        store: DrawerStore,
        evaluations: Mapping[str, RegisteredEvaluation],
        operator_approval: Callable[[ApprovalRequest], object] | None = None,
    ) -> None:
        """Bind the local evaluator registry and optional operator callback."""
        self._store = store
        self._evaluations = dict(evaluations)
        self._operator_approval = operator_approval
        for key, registration in self._evaluations.items():
            if (
                not isinstance(registration, RegisteredEvaluation)
                or key != registration.manifest.evaluator_id
            ):
                raise ProcedureError("registry keys must match registered evaluator identities")
            self._validate_manifest(registration.manifest)
            if not callable(getattr(registration.runner, "run", None)):
                raise ProcedureError("registered evaluator must supply a local runner")

    def _authorize(
        self,
        capability: str,
        *,
        wing: str | None = None,
        room: str | None = None,
        drawer_id: int | None = None,
    ) -> None:
        authorize = getattr(self._store, "authorize", None)
        if authorize is not None:
            authorize(capability, wing=wing, room=room, drawer_id=drawer_id)

    def _evidence(self, evidence_id: int, wing: str) -> Drawer:
        _positive_id(evidence_id)
        self._authorize("read", drawer_id=evidence_id)
        drawer = self._store.get(evidence_id)
        if drawer is None or drawer.wing != wing:
            raise ProcedureError("procedure evidence must exist in the same wing")
        return drawer

    def _validate_spec(self, wing: str, spec: ProcedureSpec) -> None:
        if not isinstance(spec, ProcedureSpec):
            raise ProcedureError("expected a ProcedureSpec")
        if spec.governance is not None:
            _validate_governance(spec.governance)
        for name in ("title", "applicability", "expected_outcome"):
            _text(getattr(spec, name), name)
        for name in ("prerequisites", "steps", "rollback"):
            _texts(getattr(spec, name), name)
        _texts(spec.development_case_ids, "development_case_ids", required=False)
        if not spec.evidence_ids or len(set(spec.evidence_ids)) != len(spec.evidence_ids):
            raise ProcedureError("procedure evidence must be nonempty and unique")
        if not set(spec.counterexample_ids) <= set(spec.evidence_ids):
            raise ProcedureError("counterexamples must be included in procedure evidence")
        if len(set(spec.counterexample_ids)) != len(spec.counterexample_ids):
            raise ProcedureError("counterexamples must be unique")
        for evidence_id in spec.evidence_ids:
            self._evidence(evidence_id, wing)

    @staticmethod
    def _validate_manifest(manifest: EvaluationManifest) -> None:
        if not isinstance(manifest, EvaluationManifest):
            raise ProcedureError("expected an EvaluationManifest")
        _text(manifest.evaluator_id, "evaluator_id")
        _texts(manifest.baseline_steps, "baseline_steps")
        threshold = manifest.threshold
        if (
            type(threshold) not in (int, float)
            or not math.isfinite(threshold)
            or not 0 < threshold <= 1
        ):
            raise ProcedureError("evaluation threshold must be finite and within (0, 1]")
        if manifest.metric != "success_rate_delta":
            raise ProcedureError("unsupported procedure evaluation metric")
        if len(manifest.cases) < 2:
            raise ProcedureError("evaluation requires at least two independent holdout cases")
        case_ids = []
        evidence_ids = []
        for case in manifest.cases:
            if not isinstance(case, HoldoutCase):
                raise ProcedureError("evaluation cases must be HoldoutCase values")
            _text(case.case_id, "case_id")
            _text(case.expected_outcome, "expected_outcome")
            _positive_id(case.evidence_id)
            case_ids.append(case.case_id)
            evidence_ids.append(case.evidence_id)
        if len(set(case_ids)) != len(case_ids) or len(set(evidence_ids)) != len(evidence_ids):
            raise ProcedureError("holdout case and evidence IDs must be unique")

    def _manifest(
        self,
        procedure: Procedure,
        registration: RegisteredEvaluation,
    ) -> tuple[str, dict[int, Drawer]]:
        manifest = registration.manifest
        self._validate_manifest(manifest)
        cases = {
            case.evidence_id: self._evidence(case.evidence_id, procedure.wing)
            for case in manifest.cases
        }
        development = {
            self._evidence(item, procedure.wing).content for item in procedure.spec.evidence_ids
        }
        if (
            set(procedure.spec.development_case_ids) & {case.case_id for case in manifest.cases}
            or set(procedure.spec.evidence_ids) & set(cases)
            or development & {drawer.content for drawer in cases.values()}
            or len({drawer.content for drawer in cases.values()}) != len(cases)
        ):
            raise ProcedureError(
                "holdout cases must be independent of development evidence and one another"
            )
        fingerprint = _hash(
            {
                "manifest": asdict(manifest),
                "evidence": {str(key): _hash(drawer.content) for key, drawer in cases.items()},
            }
        )
        return fingerprint, cases

    def _registered(self, drawer_id: int) -> tuple[Procedure, int]:
        _positive_id(drawer_id)
        self._authorize("read", drawer_id=drawer_id)
        value = self._store._procedure_record(drawer_id)
        if value is None:
            raise ProcedureError("drawer is not an authenticated local procedure")
        procedure = _procedure(value)
        return procedure, int(value["root_id"])

    def _current(self, drawer_id: int) -> Procedure:
        procedure, root_id = self._registered(drawer_id)
        records = self._store._procedure_records(procedure.wing)
        family = [row for row in records if row["root_id"] == root_id]
        parents = {row["supersedes_id"] for row in family}
        leaves = [row["drawer_id"] for row in family if row["drawer_id"] not in parents]
        if leaves != [drawer_id]:
            raise ProcedureError("procedure has changed; use the current authenticated revision")
        return procedure

    def _append(
        self,
        *,
        wing: str,
        spec: ProcedureSpec,
        state: str,
        parent: Procedure | None = None,
        evaluation_id: int | None = None,
        evidence_ids: tuple[int, ...] | None = None,
        counterexample_ids: tuple[int, ...] | None = None,
        note: str = "",
    ) -> Procedure:
        self._authorize("write", wing=wing, room="discoveries")
        spec_payload = _spec_payload(spec)
        revision = _hash({"wing": wing, "spec": spec_payload})
        content = f"Discovery: {spec.title}\nState: {state}\n\n{_json(spec_payload)}"
        if note:
            content += f"\n\n{note}"
        saved = self._store.add(
            Drawer(
                wing=wing,
                room="discoveries",
                content=content,
                layer=Layer.ESSENTIAL if state in {"corroborated", "promoted"} else Layer.ON_DEMAND,
                supersedes_id=parent.drawer_id if parent else None,
                metadata={
                    "kind": "cairntir.discovery",
                    "discovery_title": spec.title,
                    "discovery_summary": spec.applicability,
                    "discovery_state": state,
                    "novelty_scope": "cairntir",
                    "procedure_revision": revision,
                    "evidence_drawer_ids": list(
                        evidence_ids if evidence_ids is not None else spec.evidence_ids
                    ),
                    "counterexample_drawer_ids": list(
                        counterexample_ids
                        if counterexample_ids is not None
                        else spec.counterexample_ids
                    ),
                    "transition_note": note,
                },
            )
        )
        if saved.id is None:
            raise ProcedureError("procedure write returned no drawer identity")
        result = Procedure(
            saved.id,
            wing,
            state,
            revision,
            spec,
            parent.drawer_id if parent else None,
            evaluation_id,
        )
        root_id = self._registered(parent.drawer_id)[1] if parent else saved.id
        self._store._register_procedure(
            saved.id,
            root_id=root_id,
            parent_id=result.supersedes_id,
            payload={**asdict(result), "spec": spec_payload},
        )
        return result

    def propose(self, *, wing: str, spec: ProcedureSpec) -> Procedure:
        """Record a complete candidate without evaluating or executing it."""
        self._authorize("write", wing=wing, room="discoveries")
        self._validate_spec(wing, spec)
        with self._store.transaction():
            return self._append(wing=wing, spec=spec, state="candidate")

    def revise(self, drawer_id: int, *, spec: ProcedureSpec) -> Procedure:
        """Append a fresh candidate and invalidate the previous evaluation."""
        current = self._current(drawer_id)
        self._authorize("write", drawer_id=drawer_id)
        self._validate_spec(current.wing, spec)
        with self._store.transaction():
            current = self._current(drawer_id)
            if current.spec.governance is not None and spec.governance is None:
                raise ProcedureError("a governed procedure revision must retain governance")
            if spec.governance is not None:
                versions = {
                    item.spec.governance.version
                    for item in self.history(drawer_id)
                    if item.spec.governance is not None
                }
                if spec.governance.version in versions:
                    raise ProcedureError("governance version has already been used in this family")
            return self._append(wing=current.wing, spec=spec, state="candidate", parent=current)

    def _registration(self, evaluator_id: str) -> RegisteredEvaluation:
        registration = self._evaluations.get(evaluator_id)
        if registration is None:
            raise ProcedureError("evaluator is not registered by the local host")
        return registration

    def evaluate(self, drawer_id: int, *, evaluator_id: str) -> EvaluationReceipt:
        """Execute the registered baseline and candidate on every independent case."""
        current = self._current(drawer_id)
        self._authorize("write", drawer_id=drawer_id)
        self._authorize("write", wing=current.wing, room="procedure-evaluations")
        self._authorize("write", wing=current.wing, room="discoveries")
        if current.state != "candidate":
            raise ProcedureError("only a current candidate can be evaluated")
        registration = self._registration(evaluator_id)
        manifest_hash, evidence = self._manifest(current, registration)
        results = []
        observations = []
        for case in registration.manifest.cases:
            variants: dict[str, Any] = {}
            for variant, steps in (
                ("baseline", registration.manifest.baseline_steps),
                ("candidate", current.spec.steps),
            ):
                hypothesis = Hypothesis(
                    claim=_json(
                        {
                            "procedure_id": current.drawer_id,
                            "revision_sha256": current.revision_sha256,
                            "manifest_sha256": manifest_hash,
                            "evaluator_id": evaluator_id,
                            "case_id": case.case_id,
                            "evidence_id": case.evidence_id,
                            "variant": variant,
                            "steps": steps,
                            "input": evidence[case.evidence_id].content,
                        }
                    ),
                    predicted_outcome=case.expected_outcome,
                    wing=current.wing,
                    room="procedure-evaluations",
                )
                prediction = self._store.add(
                    _build_prediction_drawer(
                        hypothesis, question=current.spec.title, supersedes_id=None
                    )
                )
                if prediction.id is None:
                    raise ProcedureError("prediction write returned no drawer identity")
                try:
                    outcome = registration.runner.run(hypothesis)
                    _validate_outcome(outcome, hypothesis=hypothesis)
                except Exception as exc:
                    self._store.add(
                        Drawer(
                            wing=current.wing,
                            room="procedure-evaluations",
                            content=f"Procedure evaluator {evaluator_id} failed: {exc}",
                            metadata={
                                "source": "procedure.evaluation-failure",
                                "procedure_id": drawer_id,
                            },
                            supersedes_id=prediction.id,
                        )
                    )
                    raise ProcedureError(f"procedure evaluator failed: {exc}") from exc
                observation = self._store.add(
                    _build_observation_drawer(
                        hypothesis,
                        outcome,
                        delta=_compute_delta(hypothesis, outcome),
                        supersedes_id=prediction.id,
                    )
                )
                variants.update(
                    {
                        f"{variant}_prediction_id": prediction.id,
                        f"{variant}_observation_id": observation.id,
                        f"{variant}_success": outcome.success,
                    }
                )
                observations.append(asdict(outcome))
            results.append(CaseResult(case.case_id, case.evidence_id, **variants))
        count = len(results)
        baseline = sum(case.baseline_success for case in results) / count
        candidate = sum(case.candidate_success for case in results) / count
        passed = candidate - baseline >= registration.manifest.threshold
        material = {
            "procedure_id": drawer_id,
            "revision_sha256": current.revision_sha256,
            "manifest_sha256": manifest_hash,
            "evaluator_id": evaluator_id,
            "cases": [asdict(case) for case in results],
            "observations": observations,
        }
        receipt = EvaluationReceipt(
            0,
            drawer_id,
            drawer_id,
            current.revision_sha256,
            manifest_hash,
            _hash(material),
            evaluator_id,
            registration.manifest.metric,
            registration.manifest.threshold,
            baseline,
            candidate,
            passed,
            tuple(results),
        )
        with self._store.transaction():
            if (
                self._current(drawer_id) != current
                or self._manifest(current, self._registration(evaluator_id))[0] != manifest_hash
            ):
                raise ProcedureError("procedure or evaluator changed during evaluation")
            saved = self._store.add(
                Drawer(
                    wing=current.wing,
                    room="procedure-evaluations",
                    content=_json(asdict(receipt)),
                    metadata={
                        "kind": "procedure.evaluation",
                        "evidence_ids": [case.baseline_observation_id for case in results]
                        + [case.candidate_observation_id for case in results],
                    },
                )
            )
            if saved.id is None:
                raise ProcedureError("evaluation write returned no drawer identity")
            receipt = replace(receipt, drawer_id=saved.id)
            if passed:
                all_ids = tuple(
                    item
                    for case in results
                    for item in (case.baseline_observation_id, case.candidate_observation_id)
                )
                failed = tuple(
                    case.candidate_observation_id for case in results if not case.candidate_success
                )
                corroborated = self._append(
                    wing=current.wing,
                    spec=current.spec,
                    state="corroborated",
                    parent=current,
                    evaluation_id=saved.id,
                    evidence_ids=tuple(dict.fromkeys((*current.spec.evidence_ids, *all_ids))),
                    counterexample_ids=tuple(
                        dict.fromkeys((*current.spec.counterexample_ids, *failed))
                    ),
                    note=(
                        f"Registered evaluation {saved.id}: "
                        f"candidate {candidate:g}, baseline {baseline:g}."
                    ),
                )
                receipt = replace(receipt, current_id=corroborated.drawer_id)
            self._store._register_procedure_evaluation(
                saved.id, {"receipt": asdict(receipt), "material": material}
            )
        return receipt

    def get_evaluation(self, evaluation_id: int) -> EvaluationReceipt:
        """Read an authenticated local evaluation, rejecting copied drawer claims."""
        self._authorize("read", drawer_id=evaluation_id)
        value = self._store._procedure_evaluation(evaluation_id)
        if value is None or "kind" in value:
            raise ProcedureError("drawer is not an authenticated local evaluation")
        result = _receipt(value["receipt"])
        if result.evaluation_sha256 != _hash(value["material"]):
            raise ProcedureError("evaluation fingerprint mismatch")
        return result

    def _promotion(self, drawer_id: int, evaluation_id: int) -> tuple[Procedure, EvaluationReceipt]:
        current = self._current(drawer_id)
        receipt = self.get_evaluation(evaluation_id)
        if (
            current.state != "corroborated"
            or not receipt.passed
            or current.evaluation_id != evaluation_id
            or receipt.current_id != drawer_id
            or current.revision_sha256 != receipt.revision_sha256
        ):
            raise ProcedureError("promotion requires a matching current corroborated evaluation")
        registration = self._registration(receipt.evaluator_id)
        if self._manifest(current, registration)[0] != receipt.manifest_sha256:
            raise ProcedureError("registered evaluator manifest changed after evaluation")
        return current, receipt

    def promote(self, drawer_id: int, *, evaluation_id: int) -> Procedure:
        """Promote only after the operator approves this exact current evaluation."""
        self._authorize("approve", drawer_id=drawer_id)
        self._authorize("write", drawer_id=drawer_id)
        current, receipt = self._promotion(drawer_id, evaluation_id)
        self._authorize("write", wing=current.wing, room="discoveries")
        request = ApprovalRequest(
            drawer_id,
            current.wing,
            current.spec.title,
            current.revision_sha256,
            evaluation_id,
            receipt.evaluation_sha256,
        )
        if self._operator_approval is None:
            raise ProcedureError("promotion requires local operator approval")
        try:
            approved = self._operator_approval(request)
        except Exception as exc:
            raise ProcedureError(f"operator approval failed: {exc}") from exc
        if approved is not True:
            raise ProcedureError("operator did not approve this exact procedure and evaluation")
        with self._store.transaction():
            self._authorize("approve", drawer_id=drawer_id)
            if self._promotion(drawer_id, evaluation_id) != (current, receipt):
                raise ProcedureError("procedure changed while awaiting operator approval")
            return self._append(
                wing=current.wing,
                spec=current.spec,
                state="promoted",
                parent=current,
                evaluation_id=evaluation_id,
                note=f"Local operator approved {_json(asdict(request))}.",
            )

    def rollback(self, drawer_id: int, *, reason: str) -> Procedure:
        """Withdraw a current method while retaining its complete history."""
        _text(reason, "rollback reason")
        self._authorize("write", drawer_id=drawer_id)
        with self._store.transaction():
            current = self._current(drawer_id)
            if current.state in {"expired", "rejected"}:
                raise ProcedureError("procedure is already withdrawn")
            return self._append(
                wing=current.wing,
                spec=current.spec,
                state="expired",
                parent=current,
                evaluation_id=current.evaluation_id,
                note=f"Withdrawn: {reason}",
            )

    def history(self, drawer_id: int) -> list[Procedure]:
        """Read the authenticated revision chain in creation order."""
        current, root_id = self._registered(drawer_id)
        return [
            _procedure(row)
            for row in self._store._procedure_records(current.wing)
            if row["root_id"] == root_id
        ]

    def list(self, *, wing: str, active_only: bool = True) -> list[Procedure]:
        """Return authenticated current methods, defaulting to promoted ones."""
        self._authorize("read", wing=wing, room="discoveries")
        reader = self._lifecycle_reader()
        if active_only:
            reader._practice_entries(wing)
        records = self._store._procedure_records(wing)
        superseded = {row["supersedes_id"] for row in records}
        result = []
        for row in records:
            if row["drawer_id"] in superseded or (active_only and row["state"] != "promoted"):
                continue
            target = _procedure(row)
            if active_only:
                history = reader._lifecycle_history(target.drawer_id)
                latest = history[-1] if history else None
                if latest is not None and (
                    latest.state != "active" or latest.epoch_id != reader._practice_epoch(target)
                ):
                    continue
            result.append(target)
        return result

    def _source_hashes(self, references: tuple[int, ...], wing: str) -> tuple[str, ...]:
        try:
            return tuple(
                hashlib.sha256(self._evidence(item, wing).content.encode("utf-8")).hexdigest()
                for item in references
            )
        except UnicodeEncodeError as exc:
            raise ProcedureError("practice source evidence must be valid UTF-8") from exc

    def _practice_material(self, drawer_id: int) -> tuple[str, dict[str, Any], str] | None:
        _practice_id(drawer_id)
        self._authorize("read", drawer_id=drawer_id)
        try:
            value = self._store._procedure_evaluation(drawer_id)
            if value is None:
                drawer = self._store.get(drawer_id)
                if drawer is not None:
                    original = self._store.portable_source(drawer_id).get("drawer")
                    if not isinstance(original, dict) or not isinstance(
                        original.get("metadata"), dict
                    ):
                        raise ProcedureError("practice original is malformed")
                    kinds = (drawer.metadata.get("kind"), original["metadata"].get("kind"))
                    if any(kind in (_LIFECYCLE, _SUPERSESSION) for kind in kinds):
                        raise ProcedureError(
                            "lifecycle drawer lacks its authenticated registry entry"
                        )
                return None
            if set(value) != {"kind", "material", "drawer_id", "record_sha256"}:
                raise ProcedureError("malformed practice registry entry")
            kind, material = value["kind"], value["material"]
            if (
                type(kind) is not str
                or kind not in (_OBSERVATION, _REVIEW, _CONFLICT, _LIFECYCLE, _SUPERSESSION)
                or type(material) is not dict
            ):
                raise ProcedureError("invalid practice record kind or material")
            _practice_id(value["drawer_id"])
            fingerprint = _hash({"kind": kind, "material": material})
            if value["drawer_id"] != drawer_id or value["record_sha256"] != fingerprint:
                raise ProcedureError("practice registry fingerprint mismatch")
            drawer = self._evidence(drawer_id, material["wing"])
            if drawer.room != _PRACTICE_ROOM or drawer.content != _json(
                {"kind": kind, "material": material}
            ):
                raise ProcedureError("practice drawer does not match its authenticated record")
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ProcedureError("stored practice record is malformed") from exc
        else:
            return kind, material, fingerprint

    def _authorize_practice_history(self, wing: str) -> None:
        if getattr(self._store, "authorize", None) is not None:
            complete = getattr(self._store, "_authorize_complete_wing", None)
            if not callable(complete):
                raise AccessDenied("access denied")
            complete(wing)

    @contextmanager
    def complete_history(self, *, wing: str) -> Iterator[None]:
        """Check complete existing authority before and after a read workflow."""
        self._authorize_practice_history(wing)
        try:
            yield
        finally:
            self._authorize_practice_history(wing)

    def _practice_entries(self, wing: str) -> builtins.list[tuple[str, int]]:
        self._authorize_practice_history(wing)
        try:
            self._store._verify_practice_record_inventory(wing)
        except AccessDenied:
            raise
        except CairntirError as exc:
            raise ProcedureError("practice history inventory is incomplete") from exc
        self._authorize("read", wing=wing, room=_PRACTICE_ROOM)
        result = []
        for drawer in reversed(
            self._store.list_by(wing=wing, room=_PRACTICE_ROOM, limit=None, include_expired=True)
        ):
            if drawer.id is None:
                raise ProcedureError("practice drawer has no identity")
            value = self._practice_material(drawer.id)
            if value is not None:
                result.append((value[0], drawer.id))
        self._authorize_practice_history(wing)
        return result

    def _save_practice(
        self, kind: str, material: dict[str, Any], *, parent: int | None = None
    ) -> tuple[int, str]:
        self._authorize("write", wing=material["wing"], room=_PRACTICE_ROOM)
        fingerprint = _hash({"kind": kind, "material": material})
        saved = self._store.add(
            Drawer(
                wing=material["wing"],
                room=_PRACTICE_ROOM,
                content=_json({"kind": kind, "material": material}),
                supersedes_id=parent,
                metadata={"kind": kind},
            )
        )
        if saved.id is None:
            raise ProcedureError("practice write returned no drawer identity")
        self._store._register_procedure_evaluation(
            saved.id,
            {
                "kind": kind,
                "material": material,
                "drawer_id": saved.id,
                "record_sha256": fingerprint,
            },
        )
        return saved.id, fingerprint

    def _lifecycle_reader(self) -> ProcedureBook:
        return ProcedureBook(practice_read_view(self._store), {})

    def _practice_epoch(self, procedure: Procedure) -> int:
        seen: set[int] = set()
        root = self._registered(procedure.drawer_id)[1]
        while procedure.state != "candidate":
            if procedure.drawer_id in seen or procedure.supersedes_id is None:
                raise ProcedureError("practice candidate epoch is incomplete")
            seen.add(procedure.drawer_id)
            procedure, parent_root = self._registered(procedure.supersedes_id)
            if parent_root != root:
                raise ProcedureError("practice candidate epoch crosses families")
        return procedure.drawer_id

    def _lifecycle_sources(self, references: tuple[int, ...], wing: str) -> tuple[str, ...]:
        _lifecycle_ids(references)
        now = datetime.now(UTC)
        sources = self._store._task_drawers(references)
        hashes: list[str] = []
        for key in references:
            source = sources.get(key)
            if source is None or source[0].wing != wing:
                raise ProcedureError("procedure evidence must exist in the same wing")
            drawer, provenance = source
            if (
                provenance is None
                or (provenance.valid_from is not None and provenance.valid_from > now)
                or (provenance.valid_until is not None and provenance.valid_until <= now)
            ):
                raise ProcedureError("practice evidence is unavailable")
            try:
                hashes.append(hashlib.sha256(drawer.content.encode("utf-8")).hexdigest())
            except UnicodeEncodeError as exc:
                raise ProcedureError("practice source evidence must be valid UTF-8") from exc
        return tuple(hashes)

    def _validation_policy(
        self, value: PracticeValidationPolicy, target: Procedure
    ) -> EvaluationReceipt:
        if (
            not isinstance(value, PracticeValidationPolicy)
            or value.assigned_tier not in ("P0", "P1", "P2", "P3")
            or type(value.minimum_cases) is not int
            or value.minimum_cases < 2
            or type(value.minimum_score) not in (int, float)
            or not math.isfinite(value.minimum_score)
            or not 0 < value.minimum_score <= 1
            or value.origin not in _ORIGINS
        ):
            raise ProcedureError("invalid explicit practice validation policy")
        references = _lifecycle_ids(value.evidence_ids)
        self._lifecycle_sources(references, target.wing)
        if target.evaluation_id is None:
            raise ProcedureError("practice validation requires an executed evaluation")
        receipt = self.get_evaluation(target.evaluation_id)
        if (
            target.state not in {"corroborated", "promoted"}
            or receipt.current_id
            != (target.supersedes_id if target.state == "promoted" else target.drawer_id)
            or receipt.revision_sha256 != target.revision_sha256
            or not receipt.passed
            or len(receipt.cases) < value.minimum_cases
            or receipt.candidate_score < value.minimum_score
            or receipt.candidate_score - receipt.baseline_score < receipt.threshold
            or not {receipt.drawer_id, *(case.candidate_observation_id for case in receipt.cases)}
            <= set(references)
        ):
            raise ProcedureError("practice validation policy was not met by this revision")
        evaluated, _ = self._registered(receipt.procedure_id)
        if self._practice_epoch(evaluated) != self._practice_epoch(target):
            raise ProcedureError("evaluation belongs to another candidate epoch")
        return receipt

    def _lifecycle_history(self, procedure_id: int) -> tuple[PracticeLifecycleReceipt, ...]:
        target, root = self._registered(procedure_id)
        records: builtins.list[PracticeLifecycleReceipt] = []
        try:
            for kind, key in self._practice_entries(target.wing):
                if kind != _LIFECYCLE:
                    continue
                value = self._practice_material(key)
                if value is None:
                    raise ProcedureError("lifecycle record unavailable")
                _, material, fingerprint = value
                if material["root_id"] != root:
                    continue
                original, original_root = self._registered(material["procedure_id"])
                epoch = self._practice_epoch(original)
                previous = records[-1] if records else None
                policy_data = material["validation_policy"]
                policy = (
                    PracticeValidationPolicy(**policy_data) if policy_data is not None else None
                )
                state = material["state"]
                if (
                    material["wing"] != target.wing
                    or original_root != root
                    or material["epoch_id"] != epoch
                    or material["revision_sha256"] != original.revision_sha256
                    or material["previous_id"] != (previous.drawer_id if previous else None)
                ):
                    raise ProcedureError("lifecycle chain or revision binding is invalid")
                self._check_lifecycle_edge(original, state, previous, policy)
                references = _lifecycle_ids(material["evidence_ids"])
                if (
                    list(self._lifecycle_sources(references, target.wing))
                    != material["source_hashes"]
                ):
                    raise ProcedureError("lifecycle source evidence changed")
                evaluation = self._validation_policy(policy, original) if policy else None
                if material["evaluation_sha256"] != (
                    evaluation.evaluation_sha256 if evaluation else None
                ) or material["manifest_sha256"] != (
                    evaluation.manifest_sha256 if evaluation else None
                ):
                    raise ProcedureError("lifecycle evaluation binding changed")
                _practice_text(material["rationale"], "rationale", 16000)
                _lifecycle_stamp(material["recorded_at"])
                assigned, effective, mode = _lifecycle_mode(state, policy)
                if (material["assigned_tier"], material["effective_tier"], material["mode"]) != (
                    assigned,
                    effective,
                    mode,
                ):
                    raise ProcedureError("lifecycle phase contradicts its effective authority")
                records.append(
                    PracticeLifecycleReceipt(
                        key,
                        target.wing,
                        root,
                        original.drawer_id,
                        epoch,
                        original.revision_sha256,
                        state,
                        assigned,
                        effective,
                        mode,
                        references,
                        previous.drawer_id if previous else None,
                        policy,
                        material["rationale"],
                        material["recorded_at"],
                        fingerprint,
                    )
                )
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ProcedureError("stored lifecycle record is malformed") from exc
        return tuple(records)

    def _check_lifecycle_edge(
        self,
        target: Procedure,
        state: str,
        prior: PracticeLifecycleReceipt | None,
        policy: PracticeValidationPolicy | None,
    ) -> None:
        epoch = self._practice_epoch(target)
        if prior is None or prior.epoch_id != epoch:
            if state != "proposed" or target.state != "candidate" or policy is not None:
                raise ProcedureError("a new candidate epoch must begin proposed without authority")
            return
        edges = {
            "proposed": {"experimental"},
            "experimental": {"validated"},
            "validated": {"active"},
            "active": {"deprecated"},
            "deprecated": {"retired", "active"},
            "retired": set(),
        }
        if state not in edges.get(prior.state, set()):
            raise ProcedureError("invalid practice lifecycle transition")
        if state in {"validated", "active", "deprecated", "retired"} and policy is None:
            raise ProcedureError("validated practice phases require explicit policy")
        if state == "validated" and target.state != "corroborated":
            raise ProcedureError("validation requires the current corroborated revision")
        if state == "active" and (target.state != "promoted" or target.spec.governance is None):
            raise ProcedureError("activation requires governance and operator-approved promotion")
        if (
            state != "active"
            and prior.validation_policy is not None
            and policy != prior.validation_policy
        ):
            raise ProcedureError("validation policy cannot change outside fresh activation")

    def lifecycle_history(self, procedure_id: int) -> tuple[PracticeLifecycleReceipt, ...]:
        """Return authenticated original phases across all candidate epochs."""
        return self._lifecycle_reader()._lifecycle_history(procedure_id)

    def get_lifecycle(self, procedure_id: int) -> PracticeLifecycleReceipt | None:
        """Return the latest recorded phase; absence means genuinely unopted."""
        history = self.lifecycle_history(procedure_id)
        return history[-1] if history else None

    def transition_lifecycle(
        self,
        procedure_id: int,
        *,
        to_state: str,
        evidence_ids: tuple[int, ...],
        rationale: str,
        expected_prior_id: int | None,
        validation_policy: PracticeValidationPolicy | None = None,
    ) -> PracticeLifecycleReceipt:
        """Append an evidence-bound phase without executing or approving a rule."""
        references = _lifecycle_ids(evidence_ids)
        _practice_text(rationale, "rationale", 16000)
        if expected_prior_id is not None:
            _practice_id(expected_prior_id)
        with self._store.transaction():
            reader = self._lifecycle_reader()
            target = reader._current(procedure_id)
            root = reader._registered(procedure_id)[1]
            history = reader._lifecycle_history(procedure_id)
            prior = history[-1] if history else None
            if expected_prior_id != (prior.drawer_id if prior else None):
                raise ProcedureError("lifecycle changed; use its exact latest receipt")
            epoch = reader._practice_epoch(target)
            policy = validation_policy
            if prior is not None and epoch == prior.epoch_id and to_state != "validated":
                policy = policy or prior.validation_policy
            reader._check_lifecycle_edge(target, to_state, prior, policy)
            reader._lifecycle_sources(references, target.wing)
            if prior is not None and (
                epoch != prior.epoch_id or (prior.state == "deprecated" and to_state == "active")
            ):
                if not any(
                    key > prior.drawer_id
                    and key != target.drawer_id
                    and key not in target.spec.evidence_ids
                    for key in references
                ):
                    raise ProcedureError("reset or restoration requires fresh supporting evidence")
                if epoch == prior.epoch_id and validation_policy is None:
                    raise ProcedureError("reactivation requires a freshly declared policy")
            evaluation = reader._validation_policy(policy, target) if policy else None
            bound = tuple(
                dict.fromkeys(
                    (
                        *references,
                        *(policy.evidence_ids if policy else ()),
                        target.drawer_id,
                        *((prior.drawer_id,) if prior else ()),
                    )
                )
            )
            assigned, effective, mode = _lifecycle_mode(to_state, policy)
            material = {
                "wing": target.wing,
                "root_id": root,
                "procedure_id": target.drawer_id,
                "epoch_id": epoch,
                "revision_sha256": target.revision_sha256,
                "state": to_state,
                "assigned_tier": assigned,
                "effective_tier": effective,
                "mode": mode,
                "evidence_ids": list(bound),
                "previous_id": prior.drawer_id if prior else None,
                "validation_policy": asdict(policy) if policy else None,
                "rationale": rationale,
                "recorded_at": datetime.now(UTC).isoformat(),
                "source_hashes": list(reader._lifecycle_sources(bound, target.wing)),
                "evaluation_sha256": evaluation.evaluation_sha256 if evaluation else None,
                "manifest_sha256": evaluation.manifest_sha256 if evaluation else None,
            }
            self._save_practice(_LIFECYCLE, material, parent=expected_prior_id)
        result = self.get_lifecycle(procedure_id)
        if result is None:
            raise ProcedureError("saved lifecycle record unavailable")
        return result

    def _supersessions(self, wing: str) -> tuple[PracticeSupersessionReceipt, ...]:
        records: builtins.list[PracticeSupersessionReceipt] = []
        try:
            for kind, key in self._practice_entries(wing):
                if kind != _SUPERSESSION:
                    continue
                value = self._practice_material(key)
                if value is None:
                    raise ProcedureError("supersession record unavailable")
                _, material, fingerprint = value
                old, old_root = self._registered(material["older_id"])
                new, new_root = self._registered(material["replacement_id"])
                context = _lifecycle_context(tuple(material["context"]))
                references = _lifecycle_ids(material["evidence_ids"])
                if (
                    old.wing != wing
                    or new.wing != wing
                    or old_root == new_root
                    or material["wing"] != wing
                    or material["older_root_id"] != old_root
                    or material["replacement_root_id"] != new_root
                    or list(self._lifecycle_sources(references, wing)) != material["source_hashes"]
                ):
                    raise ProcedureError("supersession evidence or family binding changed")
                previous = material["previous_id"]
                if material["status"] == "active":
                    if previous is not None:
                        raise ProcedureError("new contextual directive cannot replace history")
                elif material["status"] == "restored":
                    originals = [item for item in records if item.drawer_id == previous]
                    if len(originals) != 1 or originals[0].status != "active":
                        raise ProcedureError("restoration lacks its original contextual directive")
                    original = originals[0]
                    if (
                        original.older_id != old.drawer_id
                        or original.replacement_id != new.drawer_id
                        or original.context != context
                        or any(item.previous_id == previous for item in records)
                    ):
                        raise ProcedureError("restoration contradicts contextual history")
                else:
                    raise ProcedureError("invalid contextual directive status")
                _practice_text(material["rationale"], "rationale", 16000)
                _lifecycle_stamp(material["recorded_at"])
                records.append(
                    PracticeSupersessionReceipt(
                        key,
                        wing,
                        old_root,
                        new_root,
                        old.drawer_id,
                        new.drawer_id,
                        context,
                        material["status"],
                        references,
                        previous,
                        material["rationale"],
                        material["recorded_at"],
                        fingerprint,
                    )
                )
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ProcedureError("stored contextual directive is malformed") from exc
        return tuple(records)

    def get_supersession(self, supersession_id: int) -> PracticeSupersessionReceipt:
        """Read the immutable original directive even after its rules change."""
        reader = self._lifecycle_reader()
        value = reader._practice_material(supersession_id)
        if value is None or value[0] != _SUPERSESSION:
            raise ProcedureError("not an authenticated contextual directive")
        for receipt in reader._supersessions(value[1]["wing"]):
            if receipt.drawer_id == supersession_id:
                return receipt
        raise ProcedureError("contextual directive unavailable")

    def supersession_history(self, older_id: int) -> tuple[PracticeSupersessionReceipt, ...]:
        """Return original contextual directives and their restoration receipts."""
        reader = self._lifecycle_reader()
        target, root = reader._registered(older_id)
        return tuple(
            item for item in reader._supersessions(target.wing) if item.older_root_id == root
        )

    def _active_lifecycle(self, procedure_id: int) -> PracticeLifecycleReceipt:
        target = self._current(procedure_id)
        history = self._lifecycle_history(procedure_id)
        latest = history[-1] if history else None
        if (
            latest is None
            or latest.state != "active"
            or target.state != "promoted"
            or latest.epoch_id != self._practice_epoch(target)
        ):
            raise ProcedureError("contextual directives require current opted-in active practices")
        return latest

    def record_contextual_supersession(
        self,
        *,
        older_id: int,
        replacement_id: int,
        context: tuple[str, ...],
        evidence_ids: tuple[int, ...],
        rationale: str,
    ) -> PracticeSupersessionReceipt:
        """Mask an archived original only in its explicitly declared context."""
        context = _lifecycle_context(context)
        references = _lifecycle_ids(evidence_ids)
        _practice_text(rationale, "rationale", 16000)
        with self._store.transaction():
            reader = self._lifecycle_reader()
            old = reader._current(older_id)
            new = reader._current(replacement_id)
            old_life = reader._active_lifecycle(older_id)
            new_life = reader._active_lifecycle(replacement_id)
            if old.wing != new.wing or old_life.root_id == new_life.root_id:
                raise ProcedureError("contextual directives require distinct same-wing families")
            reader._lifecycle_sources(references, old.wing)
            if (
                not set(references).intersection(old.spec.evidence_ids)
                or not set(references).intersection(new.spec.evidence_ids)
                or not set(references).difference((*old.spec.evidence_ids, *new.spec.evidence_ids))
            ):
                raise ProcedureError(
                    "context requires sources from both rules and distinct support"
                )
            history = reader._supersessions(old.wing)
            restored = {item.previous_id for item in history if item.status == "restored"}
            participants = {old_life.root_id, new_life.root_id}
            if any(
                item.status == "active"
                and item.drawer_id not in restored
                and participants.intersection((item.older_root_id, item.replacement_root_id))
                for item in history
            ):
                raise ProcedureError("overlapping contextual chains or cycles are not supported")
            bound = tuple(
                dict.fromkeys(
                    (
                        *references,
                        older_id,
                        replacement_id,
                        old_life.drawer_id,
                        new_life.drawer_id,
                    )
                )
            )
            material = {
                "wing": old.wing,
                "older_root_id": old_life.root_id,
                "replacement_root_id": new_life.root_id,
                "older_id": older_id,
                "replacement_id": replacement_id,
                "context": list(context),
                "status": "active",
                "evidence_ids": list(bound),
                "previous_id": None,
                "rationale": rationale,
                "recorded_at": datetime.now(UTC).isoformat(),
                "source_hashes": list(reader._lifecycle_sources(bound, old.wing)),
                "older_lifecycle_id": old_life.drawer_id,
                "replacement_lifecycle_id": new_life.drawer_id,
            }
            key, _ = self._save_practice(_SUPERSESSION, material)
        return self.get_supersession(key)

    def _check_supersession_current(self, receipt: PracticeSupersessionReceipt) -> None:
        value = self._practice_material(receipt.drawer_id)
        if value is None:
            raise ProcedureError("contextual directive unavailable")
        material = value[1]
        old = self._active_lifecycle(receipt.older_id)
        new = self._active_lifecycle(receipt.replacement_id)
        if (
            old.drawer_id != material["older_lifecycle_id"]
            or new.drawer_id != material["replacement_lifecycle_id"]
        ):
            raise ProcedureError("contextual directive participants changed")

    def restore_contextual_supersession(
        self,
        supersession_id: int,
        *,
        archived_evidence_id: int,
        new_evidence_id: int,
        rationale: str,
    ) -> PracticeSupersessionReceipt:
        """Append a restoration justified by both archived and new evidence."""
        _practice_id(archived_evidence_id)
        _practice_id(new_evidence_id)
        _practice_text(rationale, "rationale", 16000)
        with self._store.transaction():
            reader = self._lifecycle_reader()
            receipt = reader.get_supersession(supersession_id)
            reader._check_supersession_current(receipt)
            old, _ = reader._registered(receipt.older_id)
            fresh = reader._evidence(new_evidence_id, receipt.wing)
            original = reader._evidence(receipt.drawer_id, receipt.wing)
            if (
                receipt.status != "active"
                or archived_evidence_id not in old.spec.evidence_ids
                or new_evidence_id <= supersession_id
                or fresh.created_at <= original.created_at
                or new_evidence_id in receipt.evidence_ids
                or any(
                    item.previous_id == supersession_id
                    for item in reader._supersessions(receipt.wing)
                )
            ):
                raise ProcedureError(
                    "restoration requires archived context and fresh supporting evidence"
                )
            value = reader._practice_material(supersession_id)
            if value is None:
                raise ProcedureError("contextual directive unavailable")
            bound = tuple(
                dict.fromkeys(
                    (
                        *receipt.evidence_ids,
                        supersession_id,
                        archived_evidence_id,
                        new_evidence_id,
                    )
                )
            )
            material = {
                **value[1],
                "status": "restored",
                "previous_id": supersession_id,
                "evidence_ids": list(bound),
                "rationale": rationale,
                "recorded_at": datetime.now(UTC).isoformat(),
                "source_hashes": list(reader._lifecycle_sources(bound, receipt.wing)),
            }
            key, _ = self._save_practice(_SUPERSESSION, material, parent=supersession_id)
        return self.get_supersession(key)

    def _scan_practices(
        self, *, wing: str, context: tuple[str, ...]
    ) -> tuple[PracticeScanRow, ...]:
        current = self.list(wing=wing, active_only=False)
        rows: dict[int, PracticeScanRow] = {}
        for target in current:
            history = self._lifecycle_history(target.drawer_id)
            life = history[-1] if history else None
            root = self._registered(target.drawer_id)[1]
            if life is None:
                if target.state == "promoted":
                    rows[target.drawer_id] = PracticeScanRow(
                        target.drawer_id,
                        root,
                        "legacy",
                        None,
                        None,
                        "ACTIVE",
                        target.spec.evidence_ids,
                        None,
                        None,
                    )
                continue
            if life.epoch_id != self._practice_epoch(target) or target.state in {
                "expired",
                "rejected",
            }:
                continue
            if life.state not in {"experimental", "active", "deprecated"}:
                continue
            if life.state in {"active", "deprecated"} and target.state != "promoted":
                continue
            rows[target.drawer_id] = PracticeScanRow(
                target.drawer_id,
                root,
                life.state,
                life.assigned_tier,
                life.effective_tier,
                life.mode,
                life.evidence_ids,
                life.drawer_id,
                None,
            )
        directives = self._supersessions(wing)
        restored = {item.previous_id for item in directives if item.status == "restored"}
        for receipt in directives:
            if (
                receipt.status != "active"
                or receipt.drawer_id in restored
                or not set(receipt.context) <= set(context)
            ):
                continue
            self._check_supersession_current(receipt)
            rows.pop(receipt.older_id, None)
            replacement = rows.get(receipt.replacement_id)
            if replacement is None:
                raise ProcedureError("contextual replacement unavailable")
            rows[receipt.replacement_id] = replace(
                replacement, applied_supersession_id=receipt.drawer_id
            )
        return tuple(rows.values())

    def scan_practices(self, *, wing: str, context: tuple[str, ...]) -> tuple[PracticeScanRow, ...]:
        """Select current guidance using exact declared context tokens."""
        return self._lifecycle_reader()._scan_practices(
            wing=wing, context=_lifecycle_context(context)
        )

    def record_conflict(
        self,
        *,
        wing: str,
        first: PracticeConflictRule,
        second: PracticeConflictRule,
        situation: tuple[str, ...],
        conflict_evidence_id: int,
        origin: str = "observed",
    ) -> PracticeConflictReceipt:
        """Record a current-rule comparison; ambiguous ties require a developer ADR."""
        _practice_text(wing, "wing", 256, label=True)
        first, second = sorted(
            (_conflict_rule(first), _conflict_rule(second)), key=lambda rule: rule.procedure_id
        )
        situation = _conflict_context(situation)
        _practice_id(conflict_evidence_id)
        if type(origin) is not str or origin not in _ORIGINS:
            raise ProcedureError("conflict origin must be observed, simulated or unknown")
        if first.procedure_id == second.procedure_id:
            raise ProcedureError("conflict requires two distinct practices")
        if any(not set(rule.context) <= set(situation) for rule in (first, second)):
            raise ProcedureError("both rule contexts must apply to the declared situation")
        self._authorize("write", wing=wing, room=_PRACTICE_ROOM)
        with self._store.transaction():
            self._authorize_practice_history(wing)
            targets = tuple(self._current(rule.procedure_id) for rule in (first, second))
            for rule, target in zip((first, second), targets, strict=True):
                if (
                    target.wing != wing
                    or target.state != "promoted"
                    or rule.evidence_id not in target.spec.evidence_ids
                ):
                    raise ProcedureError(
                        "conflict requires current promoted rules and their evidence"
                    )
            references = tuple(
                sorted(
                    {
                        first.procedure_id,
                        second.procedure_id,
                        first.evidence_id,
                        second.evidence_id,
                        conflict_evidence_id,
                    }
                )
            )
            status, winner, basis = _conflict_decision(first, second)
            material = {
                "wing": wing,
                "first": asdict(first),
                "second": asdict(second),
                "first_revision": targets[0].revision_sha256,
                "second_revision": targets[1].revision_sha256,
                "situation": situation,
                "conflict_evidence_id": conflict_evidence_id,
                "origin": origin,
                "status": status,
                "winner_id": winner,
                "basis": basis,
                "evidence_ids": references,
                "evidence_sha256": self._source_hashes(references, wing),
            }
            fingerprint = _hash({"kind": _CONFLICT, "material": material})
            for receipt in self.list_conflicts(wing=wing):
                if receipt.record_sha256 == fingerprint:
                    return receipt
            key, _ = self._save_practice(_CONFLICT, material)
            receipt = self.get_conflict(key)
            self._authorize_practice_history(wing)
            return receipt

    def get_conflict(self, conflict_id: int) -> PracticeConflictReceipt:
        """Read the original authenticated comparison even after a rule is revised."""
        value = self._practice_material(conflict_id)
        if value is None or value[0] != _CONFLICT:
            raise ProcedureError("drawer is not an authenticated practice conflict")
        _, material, fingerprint = value
        try:
            if set(material) != {
                "wing",
                "first",
                "second",
                "first_revision",
                "second_revision",
                "situation",
                "conflict_evidence_id",
                "origin",
                "status",
                "winner_id",
                "basis",
                "evidence_ids",
                "evidence_sha256",
            }:
                raise ProcedureError("malformed practice conflict material")
            wing = material["wing"]
            _practice_text(wing, "wing", 256, label=True)
            first = _conflict_rule(PracticeConflictRule(**material["first"]))
            second = _conflict_rule(PracticeConflictRule(**material["second"]))
            situation = _conflict_context(tuple(material["situation"]))
            conflict_source = material["conflict_evidence_id"]
            _practice_id(conflict_source)
            if (
                first.procedure_id >= second.procedure_id
                or any(not set(rule.context) <= set(situation) for rule in (first, second))
                or type(material["origin"]) is not str
                or material["origin"] not in _ORIGINS
            ):
                raise ProcedureError("invalid stored conflict identity or applicability")
            for name, rule in (("first", first), ("second", second)):
                target, _ = self._registered(rule.procedure_id)
                if (
                    target.wing != wing
                    or target.state != "promoted"
                    or target.revision_sha256 != material[f"{name}_revision"]
                    or rule.evidence_id not in target.spec.evidence_ids
                ):
                    raise ProcedureError("stored conflict rule binding changed")
            references = tuple(
                sorted(
                    {
                        first.procedure_id,
                        second.procedure_id,
                        first.evidence_id,
                        second.evidence_id,
                        conflict_source,
                    }
                )
            )
            if (
                list(references) != material["evidence_ids"]
                or list(self._source_hashes(references, wing)) != material["evidence_sha256"]
            ):
                raise ProcedureError("conflict source evidence changed")
            status, winner, basis = _conflict_decision(first, second)
            if (status, winner, basis) != (
                material["status"],
                material["winner_id"],
                material["basis"],
            ):
                raise ProcedureError("stored conflict decision does not match its comparison")
            return PracticeConflictReceipt(
                conflict_id,
                wing,
                first,
                second,
                situation,
                conflict_source,
                material["origin"],
                status,
                winner,
                basis,
                fingerprint,
            )
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ProcedureError("stored practice conflict is malformed") from exc

    def list_conflicts(self, *, wing: str) -> tuple[PracticeConflictReceipt, ...]:
        """Read every authenticated conflict without hiding unresolved guidance."""
        result = tuple(
            self.get_conflict(key)
            for kind, key in self._practice_entries(wing)
            if kind == _CONFLICT
        )
        self._authorize_practice_history(wing)
        return result

    def get_observation(self, observation_id: int) -> PracticeObservationReceipt:
        """Read an authenticated observation, rejecting copied claims and tampering."""
        value = self._practice_material(observation_id)
        if value is None or value[0] != _OBSERVATION:
            raise ProcedureError("drawer is not an authenticated practice observation")
        _, material, fingerprint = value
        try:
            if set(material) != {
                "wing",
                "procedure_id",
                "root_id",
                "revision_sha256",
                "observation",
                "supersedes_id",
                "evidence_sha256",
            }:
                raise ProcedureError("malformed observation material")
            observation = PracticeObservation(**material["observation"])
            _validate_observation(observation)
            _practice_id(material["procedure_id"])
            _practice_id(material["root_id"])
            target, root_id = self._registered(material["procedure_id"])
            if target.spec.governance is None or (
                target.wing != material["wing"]
                or root_id != material["root_id"]
                or target.revision_sha256 != material["revision_sha256"]
            ):
                raise ProcedureError("observation target does not match its authenticated revision")
            parent = material["supersedes_id"]
            if parent is not None:
                _practice_id(parent)
                if parent >= observation_id:
                    raise ProcedureError("observation predecessor must precede its correction")
            hashes = self._source_hashes(observation.evidence_ids, target.wing)
            if list(hashes) != material["evidence_sha256"]:
                raise ProcedureError("observation source evidence changed")
            return PracticeObservationReceipt(
                observation_id,
                target.drawer_id,
                root_id,
                target.revision_sha256,
                observation,
                parent,
                hashes,
                fingerprint,
            )
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ProcedureError("stored observation is malformed") from exc

    def observation_history(self, drawer_id: int) -> builtins.list[PracticeObservationReceipt]:
        """Read all immutable observations and corrections across a practice family."""
        target, root = self._registered(drawer_id)
        result = [
            item
            for kind, key in self._practice_entries(target.wing)
            if kind == _OBSERVATION
            for item in (self.get_observation(key),)
            if item.root_id == root
        ]
        self._authorize_practice_history(target.wing)
        return result

    @staticmethod
    def _latest_observations(
        history: builtins.list[PracticeObservationReceipt],
    ) -> builtins.list[PracticeObservationReceipt]:
        current: dict[tuple[str, str], PracticeObservationReceipt] = {}
        for item in history:
            key = (item.revision_sha256, item.observation.event_id)
            prior = current.get(key)
            if item.supersedes_id != (prior.drawer_id if prior else None):
                raise ProcedureError(
                    "practice observation history contains a stale correction branch"
                )
            current[key] = item
        return sorted(current.values(), key=lambda item: item.drawer_id)

    def record_observation(
        self,
        drawer_id: int,
        *,
        observation: PracticeObservation,
        supersedes_id: int | None = None,
    ) -> PracticeObservationReceipt:
        """Register measurements; receipts inside caller transactions remain provisional.

        An owned transaction commits before return. An enclosing caller transaction
        must commit before the host reports durability or delivers the receipt.
        """
        _practice_id(drawer_id)
        _validate_observation(observation)
        if supersedes_id is not None:
            _practice_id(supersedes_id)
        self._authorize("write", drawer_id=drawer_id)
        with self._store.transaction():
            target, root = self._registered(drawer_id)
            self._authorize_practice_history(target.wing)
            if target.spec.governance is None:
                raise ProcedureError("practice observations require opt-in governance")
            if observation.origin == "observed":
                if target.state != "promoted":
                    raise ProcedureError("observed use requires an authenticated promoted revision")
            elif self._current(drawer_id).state in {"expired", "rejected"}:
                raise ProcedureError(
                    "withdrawn practices cannot receive new simulated observations"
                )
            self._authorize("write", wing=target.wing, room=_PRACTICE_ROOM)
            hashes = self._source_hashes(observation.evidence_ids, target.wing)
            material = {
                "wing": target.wing,
                "procedure_id": drawer_id,
                "root_id": root,
                "revision_sha256": target.revision_sha256,
                "observation": asdict(observation),
                "supersedes_id": supersedes_id,
                "evidence_sha256": list(hashes),
            }
            history = self.observation_history(drawer_id)
            fingerprint = _hash({"kind": _OBSERVATION, "material": material})
            for item in history:
                if item.record_sha256 == fingerprint:
                    self._authorize_practice_history(target.wing)
                    return item
            latest = self._latest_observations(history)
            previous = next(
                (
                    item
                    for item in latest
                    if item.revision_sha256 == target.revision_sha256
                    and item.observation.event_id == observation.event_id
                ),
                None,
            )
            if supersedes_id != (previous.drawer_id if previous else None):
                raise ProcedureError(
                    "event replay changed or correction does not use the latest observation"
                )
            key, _ = self._save_practice(_OBSERVATION, material, parent=supersedes_id)
            receipt = self.get_observation(key)
            self._authorize_practice_history(target.wing)
            return receipt

    def _load_assessment(self, value: dict[str, Any]) -> PracticeReviewAssessment:
        try:
            material = dict(value)
            material["policy"] = PracticeReviewPolicy(**material["policy"])
            material["metrics"] = tuple(PracticeMetrics(**item) for item in material["metrics"])
            assessment = PracticeReviewAssessment(**material)
            _validate_review_policy(assessment.policy)
            _review_window(assessment.period_start, assessment.period_end, assessment.as_of)
            _practice_date(assessment.effective_review_due, "effective_review_due")
            if _hash(_assessment_material(assessment)) != assessment.assessment_sha256:
                raise ProcedureError("review assessment fingerprint mismatch")
            target, root = self._registered(assessment.procedure_id)
            if target.spec.governance is None or (
                root != assessment.root_id
                or target.revision_sha256 != assessment.revision_sha256
                or target.spec.governance.version != assessment.version
            ):
                raise ProcedureError("review assessment target mismatch")
            observations = [self.get_observation(key) for key in assessment.observation_ids]
            if tuple(item.record_sha256 for item in observations) != assessment.observation_sha256:
                raise ProcedureError("review observation snapshots changed")
            if any(
                item.root_id != root
                or item.revision_sha256 != assessment.revision_sha256
                or not assessment.period_start
                <= item.observation.observed_on
                < min(assessment.period_end, assessment.as_of)
                for item in observations
            ):
                raise ProcedureError("review contains observations outside its target or window")
            metrics = tuple(
                _practice_metrics(
                    origin,
                    [
                        item.observation
                        for item in observations
                        if item.observation.origin == origin
                    ],
                )
                for origin in _ORIGINS
            )
            if _json([asdict(item) for item in metrics]) != _json(
                [asdict(item) for item in assessment.metrics]
            ):
                raise ProcedureError("stored review metrics do not match their observations")
            references = {item.drawer_id for item in observations}
            references.update(key for item in observations for key in item.observation.evidence_ids)
            if assessment.last_review_id is not None:
                _practice_id(assessment.last_review_id)
                references.add(assessment.last_review_id)
            if tuple(sorted(references)) != assessment.evidence_ids:
                raise ProcedureError("review evidence reference set is incomplete")
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ProcedureError("stored review assessment is malformed") from exc
        else:
            return assessment

    def get_review(self, review_id: int) -> PracticeReviewReceipt:
        """Read an immutable attributed decision and its exact evidence assessment."""
        value = self._practice_material(review_id)
        if value is None or value[0] != _REVIEW:
            raise ProcedureError("drawer is not an authenticated practice review")
        _, material, fingerprint = value
        try:
            if set(material) != {
                "wing",
                "assessment",
                "reviewed_on",
                "reviewer",
                "decision",
                "rationale",
                "next_review_due",
                "evidence_ids",
            }:
                raise ProcedureError("malformed practice review material")
            assessment = self._load_assessment(material["assessment"])
            _review_decision(
                assessment,
                material["reviewer"],
                material["decision"],
                material["rationale"],
                material["next_review_due"],
            )
            target, _ = self._registered(assessment.procedure_id)
            if (
                material["wing"] != target.wing
                or material["reviewed_on"] != assessment.as_of
                or material["evidence_ids"] != list(assessment.evidence_ids)
            ):
                raise ProcedureError("practice review identity or references mismatch")
            if assessment.last_review_id is not None and assessment.last_review_id >= review_id:
                raise ProcedureError("review predecessor must precede its completion")
            return PracticeReviewReceipt(
                review_id,
                assessment,
                material["reviewed_on"],
                material["reviewer"],
                material["decision"],
                material["rationale"],
                material["next_review_due"],
                fingerprint,
            )
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ProcedureError("stored practice review is malformed") from exc

    def review_history(self, drawer_id: int) -> builtins.list[PracticeReviewReceipt]:
        """Read immutable review outcomes for every version of the same family."""
        target, root = self._registered(drawer_id)
        result = [
            item
            for kind, key in self._practice_entries(target.wing)
            if kind == _REVIEW
            for item in (self.get_review(key),)
            if item.assessment.root_id == root
        ]
        self._authorize_practice_history(target.wing)
        return result

    def assess_review(
        self,
        drawer_id: int,
        *,
        period_start: str,
        period_end: str,
        as_of: str,
        policy: PracticeReviewPolicy,
    ) -> PracticeReviewAssessment:
        """Compute a complete scoped window with unknowns and explicit review reasons."""
        _practice_id(drawer_id)
        _review_window(period_start, period_end, as_of)
        _validate_review_policy(policy)
        registered, _ = self._registered(drawer_id)
        self._authorize_practice_history(registered.wing)
        target = self._current(drawer_id)
        governance = target.spec.governance
        if governance is None:
            raise ProcedureError("practice reviews require opt-in governance")
        _, root = self._registered(drawer_id)
        history = self.observation_history(drawer_id)
        observations = [
            item
            for item in self._latest_observations(history)
            if item.revision_sha256 == target.revision_sha256
            and period_start <= item.observation.observed_on < min(period_end, as_of)
        ]
        all_reviews = self.review_history(drawer_id)
        reviews = [
            item
            for item in all_reviews
            if item.assessment.revision_sha256 == target.revision_sha256
        ]
        latest = reviews[-1] if reviews else None
        if latest is not None and latest.reviewed_on > as_of:
            raise ProcedureError("review as_of precedes an already recorded completion")
        deadline = latest.next_review_due if latest else governance.review_due
        metrics = tuple(
            _practice_metrics(
                origin,
                [item.observation for item in observations if item.observation.origin == origin],
            )
            for origin in _ORIGINS
        )
        measured = metrics[0]
        if (
            measured.impact_known
            and policy.minimum_mean_impact is not None
            and measured.impact_unit != policy.impact_unit
        ):
            raise ProcedureError("observed impact unit does not match the declared review policy")
        reasons = ["due"] if deadline <= as_of else []
        acknowledged = {
            fingerprint
            for review in reviews
            for fingerprint in review.assessment.observation_sha256
        }
        fresh = any(
            item.observation.origin == "observed" and item.record_sha256 not in acknowledged
            for item in observations
        )
        comparisons = (
            (
                "trigger-rate",
                measured.trigger_rate,
                policy.minimum_trigger_rate,
                measured.trigger_known,
                True,
            ),
            (
                "false-positive-rate",
                measured.false_positive_rate,
                policy.maximum_false_positive_rate,
                measured.false_positive_known,
                False,
            ),
            (
                "override-rate",
                measured.override_rate,
                policy.maximum_override_rate,
                measured.override_known,
                False,
            ),
            (
                "impact",
                measured.mean_impact,
                policy.minimum_mean_impact,
                measured.impact_known,
                True,
            ),
        )
        if fresh:
            for name, score, threshold, denominator, lower in comparisons:
                if (
                    score is not None
                    and threshold is not None
                    and denominator >= policy.minimum_observations
                    and (score < threshold if lower else score > threshold)
                ):
                    reasons.append(name)
        references = {item.drawer_id for item in observations}
        references.update(key for item in observations for key in item.observation.evidence_ids)
        if latest is not None:
            references.add(latest.drawer_id)
        assessment = PracticeReviewAssessment(
            drawer_id,
            root,
            target.revision_sha256,
            governance.version,
            period_start,
            period_end,
            as_of,
            deadline,
            latest.drawer_id if latest else None,
            policy,
            metrics,
            tuple(item.drawer_id for item in observations),
            tuple(item.record_sha256 for item in observations),
            tuple(sorted(references)),
            tuple(reasons),
            "",
        )
        if (
            self._current(drawer_id) != target
            or self.observation_history(drawer_id) != history
            or self.review_history(drawer_id) != all_reviews
        ):
            raise ProcedureError("practice or evidence history changed during assessment")
        self._authorize_practice_history(target.wing)
        return replace(assessment, assessment_sha256=_hash(_assessment_material(assessment)))

    def complete_review(
        self,
        drawer_id: int,
        *,
        assessment: PracticeReviewAssessment,
        reviewer: str,
        decision: str,
        rationale: str,
        next_review_due: str,
    ) -> PracticeReviewReceipt:
        """Append a review; receipts inside caller transactions remain provisional.

        An owned transaction commits before return. An enclosing caller transaction
        must commit before the host reports durability or delivers the receipt.
        """
        _practice_id(drawer_id)
        if type(assessment) is not PracticeReviewAssessment:
            raise ProcedureError("expected a PracticeReviewAssessment")
        _review_decision(assessment, reviewer, decision, rationale, next_review_due)
        self._authorize("write", drawer_id=drawer_id)
        with self._store.transaction():
            registered, _ = self._registered(drawer_id)
            self._authorize_practice_history(registered.wing)
            target = self._current(drawer_id)
            self._authorize("write", wing=target.wing, room=_PRACTICE_ROOM)
            try:
                body = {
                    "wing": target.wing,
                    "assessment": asdict(assessment),
                    "reviewed_on": assessment.as_of,
                    "reviewer": reviewer,
                    "decision": decision,
                    "rationale": rationale,
                    "next_review_due": next_review_due,
                    "evidence_ids": list(assessment.evidence_ids),
                }
                fingerprint = _hash({"kind": _REVIEW, "material": body})
                if assessment.procedure_id != drawer_id:
                    raise ProcedureError("review assessment belongs to another current procedure")
                for item in self.review_history(drawer_id):
                    if item.receipt_sha256 == fingerprint:
                        self._authorize_practice_history(target.wing)
                        return item
                expected = self.assess_review(
                    drawer_id,
                    period_start=assessment.period_start,
                    period_end=assessment.period_end,
                    as_of=assessment.as_of,
                    policy=assessment.policy,
                )
                if _json(asdict(expected)) != _json(asdict(assessment)):
                    raise ProcedureError("review assessment is forged or stale")
                key, _ = self._save_practice(_REVIEW, body)
                receipt = self.get_review(key)
                self._authorize_practice_history(target.wing)
            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                raise ProcedureError("review completion has malformed assessment values") from exc
            else:
                return receipt

    def due_reviews(
        self,
        *,
        wing: str,
        period_start: str,
        period_end: str,
        as_of: str,
        policy: PracticeReviewPolicy,
    ) -> builtins.list[PracticeReviewAssessment]:
        """List due or evidence-triggered reviews of current promoted opted-in practices."""
        _review_window(period_start, period_end, as_of)
        _validate_review_policy(policy)
        self._authorize_practice_history(wing)
        result = [
            assessment
            for item in self.list(wing=wing)
            if item.spec.governance is not None
            for assessment in (
                self.assess_review(
                    item.drawer_id,
                    period_start=period_start,
                    period_end=period_end,
                    as_of=as_of,
                    policy=policy,
                ),
            )
            if assessment.reasons
        ]
        self._authorize_practice_history(wing)
        return result
