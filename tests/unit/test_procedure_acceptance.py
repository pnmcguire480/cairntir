"""Independent behavioral acceptance for evaluated local procedures."""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import re
import socket
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from cairntir.errors import CairntirError
from cairntir.learning import list_discoveries, record_discovery, transition_discovery
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.reason.model import Experiment, Hypothesis, Outcome

WING = "procedure-proof"
EVALUATOR = "local-list/v1"
ERRORS = (CairntirError, ValueError, TypeError)


@pytest.fixture
def api() -> Any:
    if importlib.util.find_spec("cairntir.procedures") is None:
        return None
    return importlib.import_module("cairntir.procedures")


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Procedure operation attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    with DrawerStore(tmp_path / "procedures.db", HashEmbeddingProvider(dimension=32)) as value:
        yield value


def _evidence(store: DrawerStore, content: str, *, wing: str = WING) -> int:
    saved = store.add(Drawer(wing=wing, room="cases", content=content))
    assert saved.id is not None
    return saved.id


class _Runner:
    def __init__(self) -> None:
        self.calls: list[Hypothesis] = []
        self.on_call: Any = None

    def run(self, hypothesis: Hypothesis) -> Outcome:
        self.calls.append(hypothesis)
        if self.on_call is not None:
            self.on_call(hypothesis)
        payload = json.loads(hypothesis.claim)
        values = json.loads(payload["input"])
        for step in payload["steps"]:
            if step == "identity":
                continue
            if step == "unique":
                values = list(dict.fromkeys(values))
            elif step == "sort-lexically":
                values = sorted(values, key=str)
            elif step == "sort-numerically":
                values = sorted(values)
            else:
                raise ValueError(f"Unknown trusted-fixture step: {step}")
        observed = json.dumps(values)
        return Outcome(
            experiment=Experiment(
                hypothesis=hypothesis, description="Execute registered list steps"
            ),
            observed=observed,
            success=observed == hypothesis.predicted_outcome,
            delta="" if observed == hypothesis.predicted_outcome else "Observed ordering differs",
        )


def _bundle(api: Any, store: DrawerStore, *, approval: Any = None, threshold: float = 0.5) -> Any:
    if api is None:
        pytest.fail("PROCEDURE_NOT_IMPLEMENTED: public evaluated-procedure API is absent")
    for name in (
        "ProcedureBook",
        "ProcedureSpec",
        "HoldoutCase",
        "EvaluationManifest",
        "RegisteredEvaluation",
        "Procedure",
        "CaseResult",
        "EvaluationReceipt",
        "ApprovalRequest",
    ):
        assert hasattr(api, name), f"PROCEDURE_NOT_IMPLEMENTED: {name} is absent"
    development = _evidence(store, "[9, 8, 9]")
    counterexample = _evidence(store, "[20, 3, 20]")
    cases = tuple(
        api.HoldoutCase(
            case_id=name, evidence_id=_evidence(store, value), expected_outcome=expected
        )
        for name, value, expected in (
            ("holdout-a", "[2, 1, 2]", "[1, 2]"),
            ("holdout-b", "[3, 1, 3]", "[1, 3]"),
            ("holdout-c", "[10, 2, 10]", "[2, 10]"),
        )
    )
    spec = api.ProcedureSpec(
        title='Deduplicate integer evidence: "preserve the source"',
        prerequisites=("Input is a list of integers.",),
        applicability="Prepare a distinct ordered list for local inspection.",
        steps=("unique", "sort-lexically"),
        expected_outcome="Return each integer once in increasing numeric order.",
        rollback=("Discard the derived list and reuse original evidence.",),
        evidence_ids=(development, counterexample),
        counterexample_ids=(counterexample,),
        development_case_ids=("development-a", "development-counterexample"),
    )
    runner = _Runner()
    manifest = api.EvaluationManifest(
        evaluator_id=EVALUATOR,
        baseline_steps=("identity",),
        cases=cases,
        metric="success_rate_delta",
        threshold=threshold,
    )
    registered = api.RegisteredEvaluation(manifest=manifest, runner=runner)
    book = api.ProcedureBook(store, evaluations={EVALUATOR: registered}, operator_approval=approval)
    return SimpleNamespace(
        api=api,
        store=store,
        book=book,
        spec=spec,
        runner=runner,
        manifest=manifest,
        registered=registered,
        cases=cases,
    )


def _candidate(bundle: Any) -> Any:
    return bundle.book.propose(wing=WING, spec=bundle.spec)


def _corroborated(bundle: Any) -> Any:
    candidate = _candidate(bundle)
    receipt = bundle.book.evaluate(candidate.drawer_id, evaluator_id=EVALUATOR)
    assert receipt.passed is True
    return receipt


def _ids(values: list[Any]) -> set[int]:
    return {value.drawer_id for value in values}


def _digest(value: str) -> None:
    assert re.fullmatch(r"[0-9a-f]{64}", value)


def test_candidate_keeps_complete_method_evidence_and_discovery_lifecycle(
    api: Any, store: DrawerStore
) -> None:
    bundle = _bundle(api, store)
    before = {drawer.id: drawer.content for drawer in store.list_by(wing=WING, limit=None)}
    candidate = _candidate(bundle)
    assert isinstance(candidate, api.Procedure)
    assert candidate.spec == bundle.spec and candidate.state == "candidate"
    assert candidate.wing == WING and candidate.supersedes_id is None
    assert candidate.evaluation_id is None
    _digest(candidate.revision_sha256)
    assert bundle.runner.calls == []
    assert bundle.book.list(wing=WING, active_only=True) == []
    assert _ids(bundle.book.list(wing=WING, active_only=False)) == {candidate.drawer_id}
    discovery = next(
        item for item in list_discoveries(store, wing=WING) if item.drawer_id == candidate.drawer_id
    )
    assert discovery.state == "candidate"
    assert set(discovery.evidence_ids) == set(bundle.spec.evidence_ids)
    assert set(discovery.counterexample_ids) == set(bundle.spec.counterexample_ids)
    assert all(store.get(drawer_id).content == content for drawer_id, content in before.items())


@pytest.mark.parametrize(
    "field,value", [("prerequisites", ()), ("steps", ()), ("rollback", ()), ("applicability", " ")]
)
def test_incomplete_methods_are_rejected(
    api: Any, store: DrawerStore, field: str, value: Any
) -> None:
    bundle = _bundle(api, store)
    with pytest.raises(ERRORS):
        bundle.book.propose(wing=WING, spec=replace(bundle.spec, **{field: value}))
    assert bundle.book.list(wing=WING, active_only=False) == []


@pytest.mark.parametrize("kind", ["missing", "foreign-wing", "counterexample-outside-evidence"])
def test_candidate_references_are_scoped_and_complete(
    api: Any, store: DrawerStore, kind: str
) -> None:
    bundle = _bundle(api, store)
    if kind == "missing":
        changed = replace(bundle.spec, evidence_ids=(*bundle.spec.evidence_ids, 999_999))
    elif kind == "foreign-wing":
        changed = replace(
            bundle.spec,
            evidence_ids=(*bundle.spec.evidence_ids, _evidence(store, "[6]", wing="other-project")),
        )
    else:
        changed = replace(bundle.spec, counterexample_ids=(bundle.cases[0].evidence_id,))
    with pytest.raises(ERRORS):
        bundle.book.propose(wing=WING, spec=changed)
    assert bundle.runner.calls == []


@pytest.mark.parametrize("kind", ["case-id", "evidence-id", "renamed-identical-evidence"])
def test_development_and_independent_holdout_cannot_overlap(
    api: Any, store: DrawerStore, kind: str
) -> None:
    bundle = _bundle(api, store)
    if kind == "case-id":
        spec = replace(bundle.spec, development_case_ids=(bundle.cases[0].case_id,))
    else:
        evidence_id = bundle.cases[0].evidence_id
        if kind == "renamed-identical-evidence":
            evidence_id = _evidence(store, store.get(evidence_id).content)
        spec = replace(bundle.spec, evidence_ids=(*bundle.spec.evidence_ids, evidence_id))
    with pytest.raises(ERRORS):
        candidate = bundle.book.propose(wing=WING, spec=spec)
        bundle.book.evaluate(candidate.drawer_id, evaluator_id=EVALUATOR)
    assert bundle.runner.calls == []
    assert bundle.book.list(wing=WING, active_only=True) == []


@pytest.mark.parametrize("threshold", [float("nan"), float("inf"), True, 0.0, -0.1, 1.1])
def test_evaluation_threshold_must_be_finite_numeric_and_predeclared(
    api: Any, store: DrawerStore, threshold: Any
) -> None:
    with pytest.raises(ERRORS):
        bundle = _bundle(api, store, threshold=threshold)
        candidate = _candidate(bundle)
        bundle.book.evaluate(candidate.drawer_id, evaluator_id=EVALUATOR)


def test_actual_registered_runner_executes_every_variant_and_retains_failed_cases(
    api: Any, store: DrawerStore
) -> None:
    bundle = _bundle(api, store)
    candidate = _candidate(bundle)
    receipt = bundle.book.evaluate(candidate.drawer_id, evaluator_id=EVALUATOR)
    assert isinstance(receipt, api.EvaluationReceipt)
    assert receipt.procedure_id == candidate.drawer_id
    assert receipt.revision_sha256 == candidate.revision_sha256
    assert receipt.evaluator_id == EVALUATOR and receipt.metric == "success_rate_delta"
    assert receipt.threshold == 0.5 and receipt.baseline_score == 0
    assert receipt.candidate_score == pytest.approx(2 / 3) and receipt.passed is True
    for value in (receipt.manifest_sha256, receipt.evaluation_sha256):
        _digest(value)
    assert len(bundle.runner.calls) == 6
    observed_calls = set()
    for hypothesis in bundle.runner.calls:
        payload = json.loads(hypothesis.claim)
        case = next(item for item in bundle.cases if item.case_id == payload["case_id"])
        expected = {
            "procedure_id": candidate.drawer_id,
            "revision_sha256": candidate.revision_sha256,
            "manifest_sha256": receipt.manifest_sha256,
            "evaluator_id": EVALUATOR,
            "case_id": case.case_id,
            "evidence_id": case.evidence_id,
            "variant": payload["variant"],
            "steps": list(
                bundle.manifest.baseline_steps
                if payload["variant"] == "baseline"
                else bundle.spec.steps
            ),
            "input": store.get(case.evidence_id).content,
        }
        assert payload == expected
        assert hypothesis.wing == WING and hypothesis.room == "procedure-evaluations"
        assert hypothesis.predicted_outcome == case.expected_outcome
        observed_calls.add((case.case_id, payload["variant"]))
    assert observed_calls == {
        (case.case_id, variant) for case in bundle.cases for variant in ("baseline", "candidate")
    }
    assert {item.case_id for item in receipt.cases} == {case.case_id for case in bundle.cases}
    failed_candidates = set()
    all_observations = set()
    for item in receipt.cases:
        assert isinstance(item, api.CaseResult)
        case = next(case for case in bundle.cases if case.case_id == item.case_id)
        assert item.evidence_id == case.evidence_id
        for variant in ("baseline", "candidate"):
            prediction = store.get(getattr(item, variant + "_prediction_id"))
            observation = store.get(getattr(item, variant + "_observation_id"))
            assert prediction.metadata["source"] == "reason.predict"
            assert observation.metadata["source"] == "reason.observe"
            assert observation.supersedes_id == prediction.id
            assert observation.claim == prediction.claim
            assert (
                observation.predicted_outcome
                == prediction.predicted_outcome
                == case.expected_outcome
            )
            assert observation.observed_outcome and observation.metadata["success"] is getattr(
                item, variant + "_success"
            )
            assert isinstance(getattr(item, variant + "_success"), bool)
            all_observations.add(observation.id)
            if variant == "candidate" and not item.candidate_success:
                failed_candidates.add(observation.id)
    assert len(failed_candidates) == 1
    discovery = next(
        item for item in list_discoveries(store, wing=WING) if item.drawer_id == receipt.current_id
    )
    assert discovery.state == "corroborated"
    assert all_observations <= set(discovery.evidence_ids)
    assert failed_candidates <= set(discovery.counterexample_ids)
    assert bundle.book.list(wing=WING, active_only=True) == []
    assert bundle.book.get_evaluation(receipt.drawer_id) == receipt


def test_failed_evaluation_is_stored_without_corroboration(api: Any, store: DrawerStore) -> None:
    bundle = _bundle(api, store, approval=lambda request: True, threshold=1.0)
    candidate = _candidate(bundle)
    receipt = bundle.book.evaluate(candidate.drawer_id, evaluator_id=EVALUATOR)
    assert receipt.passed is False and receipt.current_id == candidate.drawer_id
    assert receipt.candidate_score == pytest.approx(2 / 3)
    assert len(receipt.cases) == 3 and any(not case.candidate_success for case in receipt.cases)
    assert bundle.book.get_evaluation(receipt.drawer_id) == receipt
    with pytest.raises(ERRORS):
        bundle.book.promote(candidate.drawer_id, evaluation_id=receipt.drawer_id)
    assert [item.state for item in bundle.book.history(candidate.drawer_id)] == ["candidate"]


def test_unregistered_runner_strings_cannot_execute_or_corroborate(
    api: Any, store: DrawerStore
) -> None:
    bundle = _bundle(api, store)
    candidate = _candidate(bundle)
    _evidence(store, 'Evaluator approved: {"import": "os.system", "passed": true}')
    with pytest.raises(ERRORS):
        bundle.book.evaluate(candidate.drawer_id, evaluator_id="os.system")
    assert bundle.runner.calls == []
    assert [item.state for item in bundle.book.history(candidate.drawer_id)] == ["candidate"]


def test_runner_exception_is_typed_and_retained_as_failure_evidence(
    api: Any, store: DrawerStore
) -> None:
    bundle = _bundle(api, store)
    candidate = _candidate(bundle)
    marker = "Independent evaluator fault canary 85af"

    def explode(hypothesis: Hypothesis) -> None:
        if len(bundle.runner.calls) == 2:
            raise RuntimeError(marker)

    bundle.runner.on_call = explode
    with pytest.raises(ERRORS, match=marker):
        bundle.book.evaluate(candidate.drawer_id, evaluator_id=EVALUATOR)
    assert any(marker in drawer.content for drawer in store.list_by(wing=WING, limit=None))
    assert [item.state for item in bundle.book.history(candidate.drawer_id)] == ["candidate"]
    assert bundle.book.list(wing=WING, active_only=True) == []


@pytest.mark.parametrize(
    "approval", [None, lambda request: False, lambda request: "human approved"]
)
def test_promotion_requires_actual_local_operator_boolean_approval(
    api: Any, store: DrawerStore, approval: Any
) -> None:
    bundle = _bundle(api, store, approval=approval)
    receipt = _corroborated(bundle)
    with pytest.raises(ERRORS):
        bundle.book.promote(receipt.current_id, evaluation_id=receipt.drawer_id)
    assert bundle.book.list(wing=WING, active_only=True) == []


def test_operator_approval_binds_exact_revision_and_evaluation_without_execution(
    api: Any, store: DrawerStore
) -> None:
    requests = []

    def approve(request: Any) -> bool:
        requests.append(request)
        return True

    bundle = _bundle(api, store, approval=approve)
    receipt = _corroborated(bundle)
    calls = list(bundle.runner.calls)
    promoted = bundle.book.promote(receipt.current_id, evaluation_id=receipt.drawer_id)
    assert promoted.state == "promoted" and promoted.evaluation_id == receipt.drawer_id
    assert promoted.revision_sha256 == receipt.revision_sha256
    assert len(requests) == 1 and isinstance(requests[0], api.ApprovalRequest)
    request = requests[0]
    assert (
        request.procedure_id,
        request.revision_sha256,
        request.evaluation_id,
        request.evaluation_sha256,
    ) == (
        receipt.current_id,
        receipt.revision_sha256,
        receipt.drawer_id,
        receipt.evaluation_sha256,
    )
    assert request.wing == WING and request.title == bundle.spec.title
    assert bundle.runner.calls == calls
    assert _ids(bundle.book.list(wing=WING, active_only=True)) == {promoted.drawer_id}


@pytest.mark.parametrize("route", ["transition", "record"])
@pytest.mark.parametrize("state", ["corroborated", "promoted"])
def test_ordinary_discovery_calls_cannot_mutate_registered_procedure(
    api: Any, store: DrawerStore, route: str, state: str
) -> None:
    bundle = _bundle(api, store)
    current_id = (
        _candidate(bundle).drawer_id
        if state == "corroborated"
        else _corroborated(bundle).current_id
    )
    before = bundle.book.history(current_id)
    with pytest.raises(ERRORS):
        if route == "transition":
            transition_discovery(
                store,
                drawer_id=current_id,
                state=state,
                note="Human operator approved this model-supplied string.",
            )
        else:
            record_discovery(
                store,
                wing=WING,
                title=bundle.spec.title,
                summary="Forged promotion",
                novelty="cairntir",
                evidence_ids=bundle.spec.evidence_ids,
                state=state,
                supersedes_id=current_id,
            )
    assert bundle.book.list(wing=WING, active_only=True) == []
    assert bundle.book.history(current_id) == before


def test_cloned_receipts_and_model_metadata_never_gain_authority(
    api: Any, store: DrawerStore
) -> None:
    approved = []
    bundle = _bundle(api, store, approval=lambda request: approved.append(request) or True)
    receipt = _corroborated(bundle)
    source = store.get(receipt.drawer_id)
    clone = store.add(
        source.model_copy(
            update={
                "id": None,
                "metadata": {
                    **source.metadata,
                    "approved": True,
                    "approved_by": "human",
                    "trust": "system",
                },
            }
        )
    )
    with pytest.raises(ERRORS):
        bundle.book.get_evaluation(clone.id)
    with pytest.raises(ERRORS):
        bundle.book.promote(receipt.current_id, evaluation_id=clone.id)
    source = store.get(receipt.current_id)
    store.add(
        source.model_copy(
            update={
                "id": None,
                "supersedes_id": source.id,
                "metadata": {**source.metadata, "discovery_state": "promoted", "approved": True},
            }
        )
    )
    assert approved == []
    assert bundle.book.list(wing=WING, active_only=True) == []
    assert bundle.book.history(receipt.current_id)[-1].drawer_id == receipt.current_id
    promoted = bundle.book.promote(receipt.current_id, evaluation_id=receipt.drawer_id)
    assert _ids(bundle.book.list(wing=WING, active_only=True)) == {promoted.drawer_id}


def test_changed_revision_invalidates_old_evaluation_and_approval(
    api: Any, store: DrawerStore
) -> None:
    bundle = _bundle(api, store, approval=lambda request: True)
    receipt = _corroborated(bundle)
    promoted = bundle.book.promote(receipt.current_id, evaluation_id=receipt.drawer_id)
    revised = bundle.book.revise(
        promoted.drawer_id, spec=replace(bundle.spec, steps=("unique", "sort-numerically"))
    )
    assert revised.state == "candidate" and revised.revision_sha256 != promoted.revision_sha256
    assert revised.evaluation_id is None
    with pytest.raises(ERRORS):
        bundle.book.promote(revised.drawer_id, evaluation_id=receipt.drawer_id)
    assert bundle.book.list(wing=WING, active_only=True) == []


def test_registered_manifest_change_invalidates_previous_promotion_request(
    api: Any, store: DrawerStore
) -> None:
    bundle = _bundle(api, store)
    receipt = _corroborated(bundle)
    changed = api.RegisteredEvaluation(
        manifest=replace(bundle.manifest, threshold=0.75), runner=bundle.runner
    )
    book = api.ProcedureBook(
        store, evaluations={EVALUATOR: changed}, operator_approval=lambda request: True
    )
    with pytest.raises(ERRORS):
        book.promote(receipt.current_id, evaluation_id=receipt.drawer_id)
    assert book.list(wing=WING, active_only=True) == []


def test_revision_fingerprint_binds_every_method_field(api: Any, store: DrawerStore) -> None:
    bundle = _bundle(api, store)
    additional = _evidence(store, "[7, 5, 7]")
    changes = {
        "title": "Different title",
        "prerequisites": ("A different prerequisite.",),
        "applicability": "A different applicability boundary.",
        "steps": ("unique", "sort-numerically"),
        "expected_outcome": "A different outcome.",
        "rollback": ("A different rollback action.",),
        "evidence_ids": (*bundle.spec.evidence_ids, additional),
        "counterexample_ids": (),
        "development_case_ids": ("different-development-case",),
    }
    for field, value in changes.items():
        candidate = _candidate(bundle)
        revised = bundle.book.revise(
            candidate.drawer_id, spec=replace(bundle.spec, **{field: value})
        )
        assert revised.revision_sha256 != candidate.revision_sha256, field
        assert getattr(revised.spec, field) == value


def test_promotion_binds_every_predeclared_manifest_component(api: Any, store: DrawerStore) -> None:
    bundle = _bundle(api, store)
    receipt = _corroborated(bundle)
    first, *others = bundle.manifest.cases
    alias = _evidence(store, store.get(first.evidence_id).content)
    variants = (
        replace(bundle.manifest, evaluator_id="local-list/v2"),
        replace(bundle.manifest, baseline_steps=("unique",)),
        replace(bundle.manifest, cases=(replace(first, case_id="renamed-case"), *others)),
        replace(bundle.manifest, cases=(replace(first, evidence_id=alias), *others)),
        replace(bundle.manifest, cases=(replace(first, expected_outcome="[2, 1]"), *others)),
    )
    for manifest in variants:
        registered = api.RegisteredEvaluation(manifest=manifest, runner=bundle.runner)
        book = api.ProcedureBook(
            store,
            evaluations={manifest.evaluator_id: registered},
            operator_approval=lambda request: True,
        )
        with pytest.raises(ERRORS):
            book.promote(receipt.current_id, evaluation_id=receipt.drawer_id)
    assert bundle.book.list(wing=WING, active_only=True) == []


@pytest.mark.parametrize(
    "kind", ["duplicate-case-id", "duplicate-evidence", "single-case", "unknown-metric"]
)
def test_holdout_manifest_cannot_pad_or_change_its_declared_test(
    api: Any, store: DrawerStore, kind: str
) -> None:
    bundle = _bundle(api, store)
    first, second, third = bundle.manifest.cases
    with pytest.raises(ERRORS):
        if kind == "duplicate-case-id":
            manifest = replace(
                bundle.manifest, cases=(first, replace(second, case_id=first.case_id), third)
            )
        elif kind == "duplicate-evidence":
            manifest = replace(
                bundle.manifest,
                cases=(first, replace(second, evidence_id=first.evidence_id), third),
            )
        elif kind == "single-case":
            manifest = replace(bundle.manifest, cases=(first,))
        else:
            manifest = replace(bundle.manifest, metric="model-declared-success")
        registered = api.RegisteredEvaluation(manifest=manifest, runner=bundle.runner)
        book = api.ProcedureBook(store, evaluations={EVALUATOR: registered})
        candidate = book.propose(wing=WING, spec=bundle.spec)
        book.evaluate(candidate.drawer_id, evaluator_id=EVALUATOR)
    assert bundle.runner.calls == []


def test_malformed_or_misbound_runner_outcomes_never_corroborate(
    api: Any, store: DrawerStore
) -> None:
    bundle = _bundle(api, store)
    for kind in ("wrong-hypothesis", "nonboolean-success", "empty-observation"):

        def malformed(hypothesis: Hypothesis, kind: str = kind) -> Outcome:
            return Outcome(
                experiment=Experiment(
                    hypothesis=replace(hypothesis, claim="Different procedure")
                    if kind == "wrong-hypothesis"
                    else hypothesis,
                    description="Malformed evaluator fixture",
                ),
                observed="" if kind == "empty-observation" else "[1, 2]",
                success="yes" if kind == "nonboolean-success" else True,
            )

        bundle.runner.run = malformed
        candidate = _candidate(bundle)
        with pytest.raises(ERRORS):
            bundle.book.evaluate(candidate.drawer_id, evaluator_id=EVALUATOR)
        assert [item.state for item in bundle.book.history(candidate.drawer_id)] == ["candidate"]
    assert bundle.book.list(wing=WING, active_only=True) == []


@pytest.mark.parametrize("phase", ["runner", "operator"])
def test_changed_leaf_during_external_work_rejects_stale_final_write(
    api: Any, store: DrawerStore, phase: str
) -> None:
    bundle = _bundle(api, store)
    revised = []
    changed_spec = replace(bundle.spec, steps=("unique", "sort-numerically"))
    if phase == "runner":
        candidate = _candidate(bundle)

        def change(hypothesis: Hypothesis) -> None:
            if not revised:
                revised.append(bundle.book.revise(candidate.drawer_id, spec=changed_spec))

        bundle.runner.on_call = change
        with pytest.raises(ERRORS):
            bundle.book.evaluate(candidate.drawer_id, evaluator_id=EVALUATOR)
    else:
        receipt = _corroborated(bundle)

        def approve(request: Any) -> bool:
            revised.append(bundle.book.revise(request.procedure_id, spec=changed_spec))
            return True

        book = api.ProcedureBook(
            store, evaluations={EVALUATOR: bundle.registered}, operator_approval=approve
        )
        with pytest.raises(ERRORS):
            book.promote(receipt.current_id, evaluation_id=receipt.drawer_id)
    assert len(revised) == 1
    assert _ids(bundle.book.list(wing=WING, active_only=False)) == {revised[0].drawer_id}
    assert bundle.book.list(wing=WING, active_only=True) == []


def test_competing_local_approvals_cannot_create_two_authorized_leaves(
    api: Any, store: DrawerStore, tmp_path: Path
) -> None:
    bundle = _bundle(api, store)
    receipt = _corroborated(bundle)
    barrier = threading.Barrier(2)

    def compete() -> Any:
        with DrawerStore(
            tmp_path / "procedures.db", HashEmbeddingProvider(dimension=32)
        ) as connection:

            def approve(request: Any) -> bool:
                barrier.wait(timeout=10)
                return True

            book = api.ProcedureBook(
                connection, evaluations={EVALUATOR: bundle.registered}, operator_approval=approve
            )
            try:
                return book.promote(receipt.current_id, evaluation_id=receipt.drawer_id)
            except ERRORS as error:
                return error

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(compete) for _ in range(2)]
        outcomes = [future.result(timeout=20) for future in futures]
    successes = [outcome for outcome in outcomes if isinstance(outcome, api.Procedure)]
    assert len(successes) == 1
    assert _ids(bundle.book.list(wing=WING, active_only=True)) == {successes[0].drawer_id}
    assert [item.state for item in bundle.book.history(receipt.procedure_id)] == [
        "candidate",
        "corroborated",
        "promoted",
    ]


def test_rollback_expires_active_method_and_reopen_retains_verbatim_history(
    api: Any, store: DrawerStore, tmp_path: Path
) -> None:
    bundle = _bundle(api, store, approval=lambda request: True)
    receipt = _corroborated(bundle)
    promoted = bundle.book.promote(receipt.current_id, evaluation_id=receipt.drawer_id)
    history = bundle.book.history(promoted.drawer_id)
    originals = {item.drawer_id: store.get(item.drawer_id).content for item in history}
    retired = bundle.book.rollback(
        promoted.drawer_id, reason="Numeric ordering counterexample requires withdrawal."
    )
    assert retired.state in {"expired", "rejected"}
    assert retired.supersedes_id == promoted.drawer_id
    assert bundle.book.list(wing=WING, active_only=True) == []
    assert all(store.get(drawer_id).content == content for drawer_id, content in originals.items())
    with DrawerStore(tmp_path / "procedures.db", HashEmbeddingProvider(dimension=32)) as reopened:
        book = api.ProcedureBook(reopened, evaluations={EVALUATOR: bundle.registered})
        assert book.get_evaluation(receipt.drawer_id) == receipt
        assert [item.drawer_id for item in book.history(retired.drawer_id)] == [
            *originals,
            retired.drawer_id,
        ]
        assert book.list(wing=WING, active_only=True) == []
        with pytest.raises(ERRORS):
            book.promote(retired.drawer_id, evaluation_id=receipt.drawer_id)
    store.close()
    script = "\n".join(
        [
            "import json, socket, sys",
            "from pathlib import Path",
            "from cairntir.procedures import ProcedureBook",
            "from cairntir.memory.store import DrawerStore",
            "from cairntir.memory.embeddings import HashEmbeddingProvider",
            "def forbidden(*args, **kwargs): raise AssertionError('network attempted')",
            "socket.socket.connect = forbidden",
            "socket.create_connection = forbidden",
            "with DrawerStore(Path(sys.argv[1]), HashEmbeddingProvider(dimension=32)) as store:",
            "    book = ProcedureBook(store, evaluations={})",
            "    active = book.list(wing=sys.argv[2], active_only=True)",
            "    history = book.history(int(sys.argv[3]))",
            "    receipt = book.get_evaluation(int(sys.argv[4]))",
            "    print(json.dumps({'active': [p.drawer_id for p in active], "
            "'history': [p.drawer_id for p in history], "
            "'evaluation': receipt.evaluation_sha256}))",
        ]
    )
    result = subprocess.run(  # noqa: S603 - fixed independent reader and isolated store
        [
            sys.executable,
            "-c",
            script,
            str(tmp_path / "procedures.db"),
            WING,
            str(retired.drawer_id),
            str(receipt.drawer_id),
        ],
        capture_output=True,
        text=True,
        timeout=20,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "CAIRNTIR_HOME": str(tmp_path)},
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "active": [],
        "history": [*originals, retired.drawer_id],
        "evaluation": receipt.evaluation_sha256,
    }
