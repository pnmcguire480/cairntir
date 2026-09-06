"""Evaluated local methods with durable, operator-controlled promotion."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, replace
from typing import Any

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


def _procedure(value: dict[str, Any]) -> Procedure:
    return Procedure(
        drawer_id=value["drawer_id"],
        wing=value["wing"],
        state=value["state"],
        revision_sha256=value["revision_sha256"],
        spec=ProcedureSpec(**value["spec"]),
        supersedes_id=value["supersedes_id"],
        evaluation_id=value["evaluation_id"],
    )


def _receipt(value: dict[str, Any]) -> EvaluationReceipt:
    return EvaluationReceipt(
        **{**value, "cases": tuple(CaseResult(**item) for item in value["cases"])}
    )


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
        if procedure.revision_sha256 != _hash(
            {"wing": procedure.wing, "spec": asdict(procedure.spec)}
        ):
            raise ProcedureError("procedure revision fingerprint mismatch")
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
        revision = _hash({"wing": wing, "spec": asdict(spec)})
        content = f"Discovery: {spec.title}\nState: {state}\n\n{_json(asdict(spec))}"
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
            saved.id, root_id=root_id, parent_id=result.supersedes_id, payload=asdict(result)
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
        if value is None:
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
        records = self._store._procedure_records(wing)
        superseded = {row["supersedes_id"] for row in records}
        return [
            _procedure(row)
            for row in records
            if row["drawer_id"] not in superseded
            and (not active_only or row["state"] == "promoted")
        ]
