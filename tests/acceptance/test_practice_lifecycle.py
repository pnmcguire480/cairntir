"""Independent R20 behavior controls; synthetic evidence is explicitly labeled."""

from __future__ import annotations

import json
import socket
import sqlite3
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from cairntir import codeglass, learning, procedures
from cairntir.access import AccessDenied, bind_grant, issue_grant
from cairntir.errors import ProjectionError
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.obsidian import project_to_obsidian
from cairntir.reason.model import Experiment, Outcome

WING = "r20-lifecycle-proof"
EVALUATOR = "r20-inert/v1"
BEGIN = "<!-- cairntir:generated:begin -->"
END = "<!-- cairntir:generated:end -->"


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
    ):
        monkeypatch.setenv(name, "1")

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("R20 fixture attempted network access")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


class InertRunner:
    def run(self, hypothesis: object) -> Outcome:
        passed = "candidate" in json.loads(hypothesis.claim)["steps"]
        return Outcome(
            experiment=Experiment(hypothesis=hypothesis, description="SIMULATED R20 holdout"),
            observed="pass" if passed else "baseline",
            success=passed,
            delta="",
        )


def fixture(tmp_path: Path, *, approval: bool = True) -> SimpleNamespace:
    store = DrawerStore(tmp_path / "practice.db", HashEmbeddingProvider(dimension=16))
    sources = [
        store.add(Drawer(wing=WING, room="sources", content=f"SIMULATED R20 source {i}"))
        for i in range(1, 6)
    ]
    assert all(item.id is not None for item in sources)
    manifest = procedures.EvaluationManifest(
        EVALUATOR,
        ("baseline",),
        tuple(
            procedures.HoldoutCase(f"holdout-{i}", item.id, "pass")
            for i, item in enumerate(sources[2:4], 1)
        ),
    )
    requests: list[object] = []

    def authorize(request: object) -> bool:
        requests.append(request)
        return approval

    book = procedures.ProcedureBook(
        store,
        {EVALUATOR: procedures.RegisteredEvaluation(manifest, InertRunner())},
        operator_approval=authorize,
    )
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    return SimpleNamespace(
        store=store,
        path=tmp_path / "practice.db",
        book=book,
        source_ids=tuple(item.id for item in sources),
        requests=requests,
        vault=vault,
    )


def spec(
    b: SimpleNamespace, title: str, source_id: int, *, governed: bool = True, version: str = "1"
) -> procedures.ProcedureSpec:
    governance = (
        procedures.PracticeGovernance(
            "synthetic owner", version, "SIMULATED rationale", "2026-05-01"
        )
        if governed
        else None
    )
    return procedures.ProcedureSpec(
        title,
        ("local case",),
        "SIMULATED local situation",
        ("candidate", title),
        "pass",
        ("restore prior rule",),
        (source_id,),
        governance=governance,
    )


def evidence(b: SimpleNamespace, content: str) -> int:
    result = b.store.add(Drawer(wing=WING, room="sources", content=content))
    assert result.id is not None
    return result.id


def transition(
    b: SimpleNamespace,
    procedure_id: int,
    state: str,
    prior: object | None,
    *,
    extra: tuple[int, ...] = (),
    policy: object | None = None,
) -> object:
    return b.book.transition_lifecycle(
        procedure_id,
        to_state=state,
        evidence_ids=(b.source_ids[0], *extra),
        rationale=f"SIMULATED {state} reason",
        expected_prior_id=None if prior is None else prior.drawer_id,
        validation_policy=policy,
    )


def policy(receipt: procedures.EvaluationReceipt) -> object:
    construct = getattr(procedures, "PracticeValidationPolicy", None)
    assert callable(construct), "R20_PUBLIC_API_MISSING: PracticeValidationPolicy"
    return construct(
        assigned_tier="P2",
        minimum_cases=2,
        minimum_score=1.0,
        evidence_ids=(
            receipt.drawer_id,
            *(case.candidate_observation_id for case in receipt.cases),
        ),
        origin="simulated",
    )


def active(b: SimpleNamespace, title: str, source_id: int) -> SimpleNamespace:
    candidate = b.book.propose(wing=WING, spec=spec(b, title, source_id))
    proposed = transition(b, candidate.drawer_id, "proposed", None)
    experimental = transition(b, candidate.drawer_id, "experimental", proposed)
    evaluation = b.book.evaluate(candidate.drawer_id, evaluator_id=EVALUATOR)
    assert evaluation.passed and evaluation.candidate_score == 1.0
    validated = transition(
        b,
        evaluation.current_id,
        "validated",
        experimental,
        extra=(evaluation.drawer_id, *(case.candidate_observation_id for case in evaluation.cases)),
        policy=policy(evaluation),
    )
    promoted = b.book.promote(evaluation.current_id, evaluation_id=evaluation.drawer_id)
    assert b.requests[-1].procedure_id == evaluation.current_id
    activated = transition(b, promoted.drawer_id, "active", validated)
    return SimpleNamespace(
        candidate=candidate,
        proposed=proposed,
        experimental=experimental,
        evaluation=evaluation,
        validated=validated,
        promoted=promoted,
        activated=activated,
    )


def durable(store: DrawerStore) -> tuple[object, ...]:
    queries = (
        "SELECT id,wing,room,content,metadata,supersedes_id,provenance FROM drawers ORDER BY id",
        "SELECT drawer_id,root_id,parent_id,payload FROM procedure_records ORDER BY drawer_id",
        "SELECT drawer_id,payload FROM procedure_evaluations ORDER BY drawer_id",
    )
    return tuple(tuple(tuple(row) for row in store._conn.execute(query)) for query in queries)


def scan(b: SimpleNamespace, *context: str) -> dict[int, object]:
    rows = b.book.scan_practices(wing=WING, context=context)
    assert isinstance(rows, tuple)
    result = {row.procedure_id: row for row in rows}
    assert len(result) == len(rows), "scan duplicated a rule"
    return result


def generated(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    assert text.count(BEGIN) == text.count(END) == 1
    return text.split(BEGIN, 1)[1].split(END, 1)[0]


def test_01_six_states_real_evaluation_operator_and_restart(tmp_path: Path) -> None:
    b = fixture(tmp_path)
    try:
        value = active(b, "Rule alpha", b.source_ids[0])
        assert [r.state for r in b.book.lifecycle_history(value.promoted.drawer_id)] == [
            "proposed",
            "experimental",
            "validated",
            "active",
        ]
        assert value.experimental.effective_tier == "P3" and value.experimental.mode == "INFORM"
        assert value.validated.validation_policy.assigned_tier == "P2"
        assert value.activated.effective_tier == "P2" and value.activated.mode == "ACTIVE"
        assert value.activated.epoch_id == value.candidate.drawer_id
        row = scan(b, "studio")[value.promoted.drawer_id]
        assert (row.state, row.effective_tier, row.mode) == ("active", "P2", "ACTIVE")
        deprecated = transition(b, value.promoted.drawer_id, "deprecated", value.activated)
        assert scan(b, "studio")[value.promoted.drawer_id].mode == "INFORM"
        retired = transition(b, value.promoted.drawer_id, "retired", deprecated)
        assert value.promoted.drawer_id not in scan(b, "studio")
        assert value.promoted.drawer_id not in {p.drawer_id for p in b.book.list(wing=WING)}
        assert value.promoted.drawer_id in {
            p.drawer_id for p in b.book.list(wing=WING, active_only=False)
        }
        assert retired.record_sha256 and retired.recorded_at
        before = durable(b.store)
        with pytest.raises(procedures.ProcedureError):
            transition(b, value.promoted.drawer_id, "active", retired)
        assert durable(b.store) == before
        b.store.close()
        reopened = DrawerStore(b.path, HashEmbeddingProvider(dimension=16))
        try:
            reread = procedures.ProcedureBook(reopened, {})
            assert reread.get_lifecycle(value.promoted.drawer_id).drawer_id == retired.drawer_id
            assert [r.drawer_id for r in reread.lifecycle_history(value.promoted.drawer_id)] == [
                value.proposed.drawer_id,
                value.experimental.drawer_id,
                value.validated.drawer_id,
                value.activated.drawer_id,
                deprecated.drawer_id,
                retired.drawer_id,
            ]
        finally:
            reopened.close()
    finally:
        b.store.close()


def test_13_new_candidate_epoch_does_not_display_old_active_authority(tmp_path: Path) -> None:
    b = fixture(tmp_path)
    try:
        original = active(b, "Epoch reset guidance", b.source_ids[0])
        revised = b.book.revise(
            original.promoted.drawer_id,
            spec=spec(b, "Epoch reset guidance", b.source_ids[0], version="2"),
        )
        snapshot = codeglass.build_practice_register(b.store, wing=WING, as_of="2026-04-02")
        row = next(item for item in snapshot.rows if item.current_id == revised.drawer_id)
        assert row.status == "awaiting_lifecycle_reset"
        assert row.lifecycle[-1].state == "active", "old phase history was discarded"
        assert (row.assigned_tier, row.effective_tier, row.mode) == (None, None, "UNAPPLIED")
        result = project_to_obsidian(
            b.store, vault=b.vault, wing=WING, practice_register=True, as_of="2026-04-02"
        )
        assert result.practice_register_status == "published"
        assert result.practice_register_note is not None
        authority_lines = [
            line
            for line in generated(result.practice_register_note).splitlines()
            if "Epoch reset guidance" in line and "| awaiting_lifecycle_reset |" in line
        ]
        assert authority_lines
        assert all("| UNAPPLIED |" in line for line in authority_lines)
        assert all("| P2 |" not in line and "| ACTIVE |" not in line for line in authority_lines)
    finally:
        b.store.close()


def test_14_lifecycle_only_source_visibility_revokes_its_owned_receipt(tmp_path: Path) -> None:
    from cairntir.provenance import Sensitivity

    b = fixture(tmp_path)
    try:
        extra = evidence(b, "LIFECYCLE_ONLY_SOURCE_SENTINEL")
        candidate = b.book.propose(wing=WING, spec=spec(b, "Visibility guidance", b.source_ids[0]))
        transition(b, candidate.drawer_id, "proposed", None, extra=(extra,))
        initial = project_to_obsidian(
            b.store, vault=b.vault, wing=WING, practice_register=True, as_of="2026-04-01"
        )
        assert initial.practice_register_status == "published"
        assert initial.practice_register_note is not None
        receipt = b.vault / "cairntir-sync" / "receipts" / f"drawer-{extra}.md"
        assert receipt.is_file() and f"cairntir://drawer/{extra}" in generated(receipt)
        human = b"\nMyNotes: preserve this exact local sentence.\n"
        initial.practice_register_note.write_bytes(
            initial.practice_register_note.read_bytes() + human
        )
        provenance = b.store.get_provenance(extra)
        assert provenance is not None
        b.store._conn.execute(
            "UPDATE drawers SET provenance=? WHERE id=?",
            (replace(provenance, sensitivity=Sensitivity.SECRET).to_json(), extra),
        )
        result = project_to_obsidian(
            b.store, vault=b.vault, wing=WING, practice_register=True, as_of="2026-04-02"
        )
        assert result.practice_register_status == "unavailable"
        assert initial.practice_register_note.read_bytes().endswith(human)
        assert "LIFECYCLE_ONLY_SOURCE_SENTINEL" not in generated(receipt)
        assert "unavailable" in generated(receipt).lower()
    finally:
        b.store.close()


def test_15_unrelated_malformed_portable_record_does_not_block_healthy_wing(tmp_path: Path) -> None:
    b = fixture(tmp_path)
    try:
        original = active(b, "Independent wing guidance", b.source_ids[0])
        foreign = b.store.add(Drawer(wing="unrelated-wing", room="misc", content="unrelated"))
        assert foreign.id is not None
        b.store._conn.execute(
            "UPDATE portable_records SET record=? WHERE drawer_id=?", ("{", foreign.id)
        )
        assert original.promoted.drawer_id in {item.drawer_id for item in b.book.list(wing=WING)}
        assert original.promoted.drawer_id in scan(b, "studio")
    finally:
        b.store.close()


def test_02_same_spec_revise_resets_epoch_and_incomplete_governance_cannot_activate(
    tmp_path: Path,
) -> None:
    b = fixture(tmp_path)
    try:
        original_spec = spec(b, "Unfinished lesson", b.source_ids[0], governed=False)
        candidate = b.book.propose(wing=WING, spec=original_spec)
        proposed = transition(b, candidate.drawer_id, "proposed", None)
        experimental = transition(b, candidate.drawer_id, "experimental", proposed)
        assert scan(b, "local")[candidate.drawer_id].mode == "INFORM"
        revised = b.book.revise(candidate.drawer_id, spec=original_spec)
        assert revised.revision_sha256 == candidate.revision_sha256
        assert revised.drawer_id != candidate.drawer_id
        assert revised.drawer_id not in scan(b, "local")
        before = durable(b.store)
        with pytest.raises(procedures.ProcedureError):
            transition(b, revised.drawer_id, "active", experimental)
        assert durable(b.store) == before
        fresh = evidence(b, "SIMULATED fresh evidence after identical-spec revise")
        reset = transition(b, revised.drawer_id, "proposed", experimental, extra=(fresh,))
        assert reset.epoch_id == revised.drawer_id and reset.assigned_tier is None
        experiment2 = transition(b, revised.drawer_id, "experimental", reset)
        evaluation = b.book.evaluate(revised.drawer_id, evaluator_id=EVALUATOR)
        validated = transition(
            b,
            evaluation.current_id,
            "validated",
            experiment2,
            extra=(evaluation.drawer_id, *(c.candidate_observation_id for c in evaluation.cases)),
            policy=policy(evaluation),
        )
        promoted = b.book.promote(evaluation.current_id, evaluation_id=evaluation.drawer_id)
        before = durable(b.store)
        with pytest.raises(procedures.ProcedureError):
            transition(b, promoted.drawer_id, "active", validated)
        assert durable(b.store) == before
        governed = replace(
            original_spec,
            governance=procedures.PracticeGovernance(
                "synthetic owner", "1", "SIMULATED rationale", "2026-05-01"
            ),
        )
        candidate3 = b.book.revise(promoted.drawer_id, spec=governed)
        assert candidate3.drawer_id not in scan(b, "local")
        assert [r.drawer_id for r in b.book.lifecycle_history(candidate3.drawer_id)][
            -1
        ] == validated.drawer_id
    finally:
        b.store.close()


def test_03_policy_threshold_sources_and_unapproved_promotion_fail_closed(tmp_path: Path) -> None:
    b = fixture(tmp_path, approval=False)
    try:
        candidate = b.book.propose(wing=WING, spec=spec(b, "Rule", b.source_ids[0]))
        first = transition(b, candidate.drawer_id, "proposed", None)
        second = transition(b, candidate.drawer_id, "experimental", first)
        evaluation = b.book.evaluate(candidate.drawer_id, evaluator_id=EVALUATOR)
        with pytest.raises(procedures.ProcedureError):
            b.book.promote(evaluation.current_id, evaluation_id=evaluation.drawer_id)
        bad = replace(policy(evaluation), minimum_cases=3)
        before = durable(b.store)
        with pytest.raises(procedures.ProcedureError):
            transition(
                b,
                evaluation.current_id,
                "validated",
                second,
                extra=(evaluation.drawer_id,),
                policy=bad,
            )
        assert durable(b.store) == before
        cross = b.store.add(Drawer(wing="other", room="sources", content="cross-wing"))
        assert cross.id is not None
        before = durable(b.store)
        with pytest.raises((procedures.ProcedureError, AccessDenied)):
            transition(
                b,
                evaluation.current_id,
                "validated",
                second,
                extra=(cross.id,),
                policy=policy(evaluation),
            )
        assert durable(b.store) == before
    finally:
        b.store.close()


def test_04_context_mask_restoration_and_archived_original(tmp_path: Path) -> None:
    b = fixture(tmp_path)
    try:
        old = active(b, "Old best practice", b.source_ids[0])
        new = active(b, "Context alternative", b.source_ids[1])
        context_evidence = evidence(b, "SIMULATED context: studio build")
        relation = b.book.record_contextual_supersession(
            older_id=old.promoted.drawer_id,
            replacement_id=new.promoted.drawer_id,
            context=("studio", "build"),
            evidence_ids=(b.source_ids[0], b.source_ids[1], context_evidence),
            rationale="SIMULATED replacement only during studio builds",
        )
        assert relation.status == "active" and relation.context == ("studio", "build")
        inside = scan(b, "studio", "build")
        outside = scan(b, "mobile", "build")
        assert old.promoted.drawer_id not in inside
        assert new.promoted.drawer_id in inside
        assert {old.promoted.drawer_id, new.promoted.drawer_id} <= set(outside)
        assert b.book.get_supersession(relation.drawer_id).record_sha256 == relation.record_sha256
        archived = b.book.history(old.promoted.drawer_id)[0]
        assert archived.spec.title == "Old best practice"
        fresh = evidence(b, "SIMULATED new evidence after replacement")
        restored = b.book.restore_contextual_supersession(
            relation.drawer_id,
            archived_evidence_id=b.source_ids[0],
            new_evidence_id=fresh,
            rationale="SIMULATED recheck supports old practice",
        )
        assert restored.status == "restored"
        assert {old.promoted.drawer_id, new.promoted.drawer_id} <= set(scan(b, "studio", "build"))
        assert [r.drawer_id for r in b.book.supersession_history(old.promoted.drawer_id)] == [
            relation.drawer_id,
            restored.drawer_id,
        ]
    finally:
        b.store.close()


def test_05_bad_context_cycle_stale_and_cross_wing_append_nothing(tmp_path: Path) -> None:
    b = fixture(tmp_path)
    try:
        old = active(b, "Old", b.source_ids[0])
        new = active(b, "New", b.source_ids[1])
        context_id = evidence(b, "SIMULATED studio context")
        before = durable(b.store)
        for context in ((), ("STUDIO",), ("studio", "studio")):
            with pytest.raises((procedures.ProcedureError, ValueError)):
                b.book.record_contextual_supersession(
                    older_id=old.promoted.drawer_id,
                    replacement_id=new.promoted.drawer_id,
                    context=context,
                    evidence_ids=(b.source_ids[0], b.source_ids[1], context_id),
                    rationale="SIMULATED invalid context",
                )
        assert durable(b.store) == before
        relation = b.book.record_contextual_supersession(
            older_id=old.promoted.drawer_id,
            replacement_id=new.promoted.drawer_id,
            context=("studio",),
            evidence_ids=(b.source_ids[0], b.source_ids[1], context_id),
            rationale="SIMULATED studio rule",
        )
        before = durable(b.store)
        with pytest.raises(procedures.ProcedureError):
            b.book.record_contextual_supersession(
                older_id=old.promoted.drawer_id,
                replacement_id=new.promoted.drawer_id,
                context=("studio",),
                evidence_ids=(b.source_ids[0], b.source_ids[1], context_id),
                rationale="SIMULATED contradictory repeat",
            )
        with pytest.raises(procedures.ProcedureError):
            b.book.restore_contextual_supersession(
                relation.drawer_id,
                archived_evidence_id=b.source_ids[0],
                new_evidence_id=context_id,
                rationale="old evidence cannot restore",
            )
        assert durable(b.store) == before
        b.book.rollback(new.promoted.drawer_id, reason="SIMULATED withdrawal")
        with pytest.raises(procedures.ProcedureError):
            scan(b, "studio")
    finally:
        b.store.close()


def test_06_active_consumers_archive_and_incomplete_scope(tmp_path: Path) -> None:
    b = fixture(tmp_path)
    try:
        opted = active(b, "Opted", b.source_ids[0])
        legacy_candidate = b.book.propose(wing=WING, spec=spec(b, "Legacy", b.source_ids[1]))
        legacy_eval = b.book.evaluate(legacy_candidate.drawer_id, evaluator_id=EVALUATOR)
        legacy = b.book.promote(legacy_eval.current_id, evaluation_id=legacy_eval.drawer_id)
        deprecated = transition(b, opted.promoted.drawer_id, "deprecated", opted.activated)
        retired = transition(b, opted.promoted.drawer_id, "retired", deprecated)
        assert legacy.drawer_id in {p.drawer_id for p in b.book.list(wing=WING)}
        assert opted.promoted.drawer_id not in {p.drawer_id for p in b.book.list(wing=WING)}
        active_discoveries = learning.list_discoveries(
            b.store, wing=WING, active_only=True, limit=None
        )
        assert legacy.drawer_id in {d.drawer_id for d in active_discoveries}
        assert opted.promoted.drawer_id not in {d.drawer_id for d in active_discoveries}
        archived = learning.list_discoveries(b.store, wing=WING, active_only=False, limit=None)
        assert opted.promoted.drawer_id in {d.drawer_id for d in archived}
        token = issue_grant(
            b.store, scopes=[{"wing": WING, "rooms": ["discoveries"]}], capabilities=["read"]
        )
        scoped = bind_grant(b.store, token)
        before = durable(b.store)
        with pytest.raises(AccessDenied):
            procedures.ProcedureBook(scoped, {}).list(wing=WING)
        with pytest.raises(AccessDenied):
            learning.list_discoveries(scoped, wing=WING, active_only=True, limit=None)
        assert durable(b.store) == before
        b.store._conn.execute(
            "UPDATE drawers SET content=? WHERE id=?",
            ("TAMPERED: missing original lifecycle content", retired.drawer_id),
        )
        with pytest.raises((procedures.ProcedureError, AccessDenied)):
            b.book.list(wing=WING)
        with pytest.raises((procedures.ProcedureError, AccessDenied)):
            learning.list_discoveries(b.store, wing=WING, active_only=True, limit=None)
    finally:
        b.store.close()


def test_07_register_obsidian_human_bytes_and_conflict_freshness(tmp_path: Path) -> None:
    b = fixture(tmp_path)
    try:
        old = active(b, "Old guidance", b.source_ids[0])
        new = active(b, "New guidance", b.source_ids[1])
        conflict_source = evidence(b, "SIMULATED apparent rule conflict")
        conflict = b.book.record_conflict(
            wing=WING,
            first=procedures.PracticeConflictRule(
                old.promoted.drawer_id, "P1", ("studio",), b.source_ids[0]
            ),
            second=procedures.PracticeConflictRule(
                new.promoted.drawer_id, "P2", ("studio",), b.source_ids[1]
            ),
            situation=("studio",),
            conflict_evidence_id=conflict_source,
            origin="simulated",
        )
        initial = codeglass.build_practice_register(b.store, wing=WING, as_of="2026-04-01")
        assert next(r for r in initial.conflicts if r.conflict_id == conflict.drawer_id).current
        first = project_to_obsidian(
            b.store, vault=b.vault, wing=WING, practice_register=True, as_of="2026-04-01"
        )
        assert first.practice_register_note is not None
        human = "\nMy handwritten choice remains mine: [brackets] & Unicode ✓\n"
        first.practice_register_note.write_bytes(
            first.practice_register_note.read_bytes() + human.encode()
        )
        deprecated = transition(b, old.promoted.drawer_id, "deprecated", old.activated)
        transition(b, old.promoted.drawer_id, "retired", deprecated)
        later = codeglass.build_practice_register(b.store, wing=WING, as_of="2026-04-02")
        found = next(r for r in later.conflicts if r.conflict_id == conflict.drawer_id)
        assert not found.current and found.winner_id is None
        assert b.book.get_conflict(conflict.drawer_id).first.procedure_id == old.promoted.drawer_id
        projected = project_to_obsidian(
            b.store, vault=b.vault, wing=WING, practice_register=True, as_of="2026-04-02"
        )
        assert projected.practice_register_note == first.practice_register_note
        assert projected.practice_register_note.read_bytes().endswith(human.encode())
        body = generated(projected.practice_register_note)
        assert "retired" in body and "Old guidance" in body
        assert "New guidance" in body and "cairntir-sync/" in body
        for note in projected.practice_history_notes:
            assert note.is_file() and note.resolve().is_relative_to(b.vault.resolve())
    finally:
        b.store.close()


def test_08_mutated_scan_or_register_cannot_hide_retirement_or_context(tmp_path: Path) -> None:
    b = fixture(tmp_path)
    try:
        old = active(b, "Context old", b.source_ids[0])
        new = active(b, "Context new", b.source_ids[1])
        context = evidence(b, "SIMULATED exact context")
        b.book.record_contextual_supersession(
            older_id=old.promoted.drawer_id,
            replacement_id=new.promoted.drawer_id,
            context=("studio",),
            evidence_ids=(b.source_ids[0], b.source_ids[1], context),
            rationale="SIMULATED context replacement",
        )
        real_inside = scan(b, "studio")
        real_outside = scan(b, "mobile")

        def assert_visible(inside: dict[int, object], outside: dict[int, object]) -> None:
            assert old.promoted.drawer_id not in inside, "old rule leaked in matching context"
            assert new.promoted.drawer_id in inside, "replacement missing"
            assert {old.promoted.drawer_id, new.promoted.drawer_id} <= set(outside), (
                "old rule hidden globally"
            )

        assert_visible(real_inside, real_outside)
        with pytest.raises(AssertionError, match="leaked"):
            assert_visible(
                {**real_inside, old.promoted.drawer_id: real_outside[old.promoted.drawer_id]},
                real_outside,
            )
        with pytest.raises(AssertionError, match="globally"):
            assert_visible(
                real_inside, {new.promoted.drawer_id: real_outside[new.promoted.drawer_id]}
            )
        retired = transition(b, new.promoted.drawer_id, "deprecated", new.activated)
        transition(b, new.promoted.drawer_id, "retired", retired)
        assert new.promoted.drawer_id not in scan(b, "mobile")
        assert old.promoted.drawer_id in scan(b, "mobile")
    finally:
        b.store.close()


def test_09_missing_latest_retirement_drawer_never_restores_older_active_leaf(
    tmp_path: Path,
) -> None:
    b = fixture(tmp_path)
    try:
        value = active(b, "Must remain retired", b.source_ids[0])
        deprecated = transition(b, value.promoted.drawer_id, "deprecated", value.activated)
        retired = transition(b, value.promoted.drawer_id, "retired", deprecated)
        assert value.promoted.drawer_id not in {p.drawer_id for p in b.book.list(wing=WING)}
        b.store.close()
        with sqlite3.connect(b.path) as conn:
            assert (
                conn.execute(
                    "SELECT 1 FROM portable_records WHERE drawer_id=?", (retired.drawer_id,)
                ).fetchone()
                is not None
            )
            conn.execute("DELETE FROM drawers WHERE id=?", (retired.drawer_id,))
            assert (
                conn.execute(
                    "SELECT 1 FROM portable_records WHERE drawer_id=?", (retired.drawer_id,)
                ).fetchone()
                is not None
            )
        reopened = DrawerStore(b.path, HashEmbeddingProvider(dimension=16))
        try:
            book = procedures.ProcedureBook(reopened, {})
            before = reopened._conn.total_changes
            with pytest.raises((procedures.ProcedureError, AccessDenied)):
                book.list(wing=WING)
            with pytest.raises((procedures.ProcedureError, AccessDenied)):
                learning.list_discoveries(reopened, wing=WING, active_only=True, limit=None)
            with pytest.raises((procedures.ProcedureError, AccessDenied, ProjectionError)):
                codeglass.build_practice_register(reopened, wing=WING, as_of="2026-04-01")
            assert reopened._conn.total_changes == before
        finally:
            reopened.close()
    finally:
        b.store.close()


def test_10_missing_retired_tail_refuses_explicit_context_scan(tmp_path: Path) -> None:
    b = fixture(tmp_path)
    try:
        value = active(b, "Tail integrity", b.source_ids[0])
        deprecated = transition(b, value.promoted.drawer_id, "deprecated", value.activated)
        retired = transition(b, value.promoted.drawer_id, "retired", deprecated)
        b.store.close()
        with sqlite3.connect(b.path) as conn:
            assert (
                conn.execute(
                    "SELECT 1 FROM portable_records WHERE drawer_id=?", (retired.drawer_id,)
                ).fetchone()
                is not None
            )
            conn.execute("DELETE FROM drawers WHERE id=?", (retired.drawer_id,))
        reopened = DrawerStore(b.path, HashEmbeddingProvider(dimension=16))
        try:
            book = procedures.ProcedureBook(reopened, {})
            before = reopened._conn.total_changes
            with pytest.raises((procedures.ProcedureError, AccessDenied)):
                book.scan_practices(wing=WING, context=("studio",))
            assert reopened._conn.total_changes == before
        finally:
            reopened.close()
    finally:
        b.store.close()


def test_11_contextual_supersession_stales_only_matching_r19_comparison(tmp_path: Path) -> None:
    b = fixture(tmp_path)
    try:
        old = active(b, "Context old", b.source_ids[0])
        new = active(b, "Context new", b.source_ids[1])
        conflict_source = evidence(b, "SIMULATED studio conflict")
        conflict = b.book.record_conflict(
            wing=WING,
            first=procedures.PracticeConflictRule(
                old.promoted.drawer_id, "P1", ("studio",), b.source_ids[0]
            ),
            second=procedures.PracticeConflictRule(
                new.promoted.drawer_id, "P2", ("studio",), b.source_ids[1]
            ),
            situation=("studio",),
            conflict_evidence_id=conflict_source,
            origin="simulated",
        )
        context_source = evidence(b, "SIMULATED studio context")
        relation = b.book.record_contextual_supersession(
            older_id=old.promoted.drawer_id,
            replacement_id=new.promoted.drawer_id,
            context=("studio",),
            evidence_ids=(b.source_ids[0], b.source_ids[1], context_source),
            rationale="SIMULATED studio-only alternative",
        )
        snapshot = codeglass.build_practice_register(b.store, wing=WING, as_of="2026-04-01")
        row = next(item for item in snapshot.conflicts if item.conflict_id == conflict.drawer_id)
        assert row.status.startswith("stale") and not row.current and row.winner_id is None
        assert b.book.get_conflict(conflict.drawer_id).record_sha256 == conflict.record_sha256
        assert old.promoted.drawer_id in scan(b, "mobile")
        assert old.promoted.drawer_id not in scan(b, "studio")
        before = b.store._conn.total_changes
        with pytest.raises(procedures.ProcedureError):
            b.book.record_contextual_supersession(
                older_id=new.promoted.drawer_id,
                replacement_id=old.promoted.drawer_id,
                context=("studio",),
                evidence_ids=(b.source_ids[0], b.source_ids[1], context_source),
                rationale="SIMULATED reverse cycle",
            )
        assert b.store._conn.total_changes == before
        fresh = evidence(b, "SIMULATED later evidence supporting old context")
        b.book.restore_contextual_supersession(
            relation.drawer_id,
            archived_evidence_id=b.source_ids[0],
            new_evidence_id=fresh,
            rationale="SIMULATED reconsideration",
        )
        restored = codeglass.build_practice_register(b.store, wing=WING, as_of="2026-04-02")
        after = next(item for item in restored.conflicts if item.conflict_id == conflict.drawer_id)
        assert after.current and after.winner_id == conflict.winner_id
    finally:
        b.store.close()


def test_12_hidden_supersession_source_redacts_generated_notes_preserving_human_bytes(
    tmp_path: Path,
) -> None:
    from cairntir.provenance import Sensitivity, WriteProvenance

    b = fixture(tmp_path)
    try:
        old = active(b, "Human old guidance", b.source_ids[0])
        new = active(b, "Human new guidance", b.source_ids[1])
        published = project_to_obsidian(
            b.store, vault=b.vault, wing=WING, practice_register=True, as_of="2026-04-01"
        )
        assert published.practice_register_status == "published"
        assert published.practice_register_note is not None
        note = published.practice_register_note
        human = "\nPRIVATE HUMAN NOTE: keep my context verbatim ✓\n".encode()
        note.write_bytes(note.read_bytes() + human)
        provenance = WriteProvenance.create(
            host="r20-fixture",
            capture_path="synthetic-secret",
            sensitivity=Sensitivity.SECRET,
        )
        hidden = b.store.add(
            Drawer(wing=WING, room="sources", content="R20_SECRET_CONTEXT_SENTINEL"),
            provenance=provenance,
        )
        assert hidden.id is not None
        b.book.record_contextual_supersession(
            older_id=old.promoted.drawer_id,
            replacement_id=new.promoted.drawer_id,
            context=("studio",),
            evidence_ids=(b.source_ids[0], b.source_ids[1], hidden.id),
            rationale="SIMULATED secret-context replacement",
        )
        before = durable(b.store)
        result = project_to_obsidian(
            b.store, vault=b.vault, wing=WING, practice_register=True, as_of="2026-04-02"
        )
        assert result.practice_register_status == "unavailable"
        block = generated(note)
        assert "unavailable" in block.lower()
        assert "Human old guidance" not in block
        assert "Human new guidance" not in block
        assert "R20_SECRET_CONTEXT_SENTINEL" not in block
        assert str(hidden.id) not in block
        assert note.read_bytes().endswith(human)
        for history_note in published.practice_history_notes:
            assert "R20_SECRET_CONTEXT_SENTINEL" not in generated(history_note)
        assert durable(b.store) == before
    finally:
        b.store.close()
