"""Independent composed-reference controls using real SQLite and synthetic policy."""

from __future__ import annotations

import json
import socket
import sqlite3
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest

from cairntir import procedures
from cairntir.access import bind_grant, issue_grant
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.reason.model import Experiment, Outcome

WING = "r20-composed-reference-proof"
EVALUATOR = "synthetic-integer-transform/v1"
STATES = ("proposed", "experimental", "validated", "active", "deprecated", "retired")


@pytest.fixture(autouse=True)
def isolation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("HOME", "USERPROFILE", "CAIRNTIR_HOME", "HF_HOME", "XDG_CACHE_HOME"):
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
        pytest.fail("composed-reference fixture attempted network access")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


class IntegerRunner:
    def run(self, hypothesis: object) -> Outcome:
        request = json.loads(hypothesis.claim)
        values = json.loads(request["input"])["values"]
        for step in request["steps"]:
            if step == "identity":
                continue
            if step == "unique":
                values = list(dict.fromkeys(values))
            elif step == "sort-numerically":
                values = sorted(values)
            else:
                raise ValueError(f"unregistered synthetic step: {step}")
        observed = json.dumps(values)
        return Outcome(
            experiment=Experiment(
                hypothesis=hypothesis,
                description="SYNTHETIC integer transform, not field or operator evidence",
            ),
            observed=observed,
            success=observed == hypothesis.predicted_outcome,
            delta="" if observed == hypothesis.predicted_outcome else "different integer order",
        )


def snapshot(connection: sqlite3.Connection) -> tuple[object, ...]:
    schema = tuple(
        tuple(row)
        for row in connection.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"
        )
    )
    tables = []
    for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND (sql IS NULL OR upper(sql) NOT LIKE 'CREATE VIRTUAL TABLE%') ORDER BY name"
    ):
        name = row[0]
        quoted = '"' + name.replace('"', '""') + '"'
        rows = tuple(
            sorted(
                (tuple(item) for item in connection.execute(f"SELECT * FROM {quoted}")),  # noqa: S608 - schema names are double-quote escaped
                key=repr,
            )
        )
        tables.append((name, rows))
    return schema, tuple(tables)


class Scenario:
    def __init__(self, root: Path, scoped: bool) -> None:
        self.path = root / "practice.db"
        self.store = DrawerStore(self.path, HashEmbeddingProvider(dimension=16))
        self.sources = tuple(self.add(f"SYNTHETIC supporting source {i}") for i in range(512))
        cases = tuple(
            procedures.HoldoutCase(
                f"synthetic-holdout-{i}",
                self.add(json.dumps({"origin": "simulated", "values": values})),
                json.dumps(expected),
            )
            for i, values, expected in (
                (1, [2, 1, 2], [1, 2]),
                (2, [10, 2, 10], [2, 10]),
            )
        )
        self.registration = procedures.RegisteredEvaluation(
            procedures.EvaluationManifest(EVALUATOR, ("identity",), cases),
            IntegerRunner(),
        )
        self.approvals = []
        self.token = (
            issue_grant(
                self.store,
                scopes=[{"wing": WING}],
                capabilities=["read", "write", "approve"],
                principal="synthetic acceptance operator",
            )
            if scoped
            else None
        )
        self.bind()

    def approve(self, request: object) -> bool:
        self.approvals.append(asdict(request))
        return True

    def bind(self) -> None:
        target = bind_grant(self.store, self.token) if self.token is not None else self.store
        self.book = procedures.ProcedureBook(
            target,
            {EVALUATOR: self.registration},
            operator_approval=self.approve,
        )

    def add(self, content: str) -> int:
        drawer = self.store.add(Drawer(wing=WING, room="sources", content=content))
        assert drawer.id is not None
        return drawer.id

    def candidate(self, title: str, source: int) -> object:
        return self.book.propose(
            wing=WING,
            spec=procedures.ProcedureSpec(
                title,
                ("SYNTHETIC local integer list",),
                "SYNTHETIC acceptance scope only",
                ("unique", "sort-numerically"),
                "distinct integers in numeric order",
                ("reuse original list",),
                (source,),
                governance=procedures.PracticeGovernance(
                    "synthetic acceptance operator", "1", "SYNTHETIC rationale", "2027-01-01"
                ),
            ),
        )

    def reopen(self, expected: tuple[object, ...]) -> None:
        assert not self.store.transaction_active
        self.store.close()
        with sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True) as connection:
            assert snapshot(connection) == expected, "closed SQLite state changed"
        self.store = DrawerStore(self.path, HashEmbeddingProvider(dimension=16))
        self.bind()
        assert snapshot(self.store._conn) == expected, "opening the store changed durable evidence"

    def close(self) -> None:
        self.store.close()


@pytest.fixture(params=[False, True], ids=["owner", "scoped"])
def scenario(tmp_path: Path, request: pytest.FixtureRequest):
    result = Scenario(tmp_path, request.param)
    try:
        yield result
    finally:
        result.close()


def validation_policy(receipt: object) -> object:
    return procedures.PracticeValidationPolicy(
        "P2",
        2,
        1.0,
        (receipt.drawer_id, *(item.candidate_observation_id for item in receipt.cases)),
        "simulated",
    )


def step(
    s: Scenario,
    target: int,
    state: str,
    prior: object | None,
    policy: object | None = None,
) -> object:
    return s.book.transition_lifecycle(
        target,
        to_state=state,
        evidence_ids=(s.sources[0],),
        rationale=f"SYNTHETIC prepare {state}",
        expected_prior_id=None if prior is None else prior.drawer_id,
        validation_policy=policy,
    )


def prepare(
    s: Scenario,
    state: str,
    title: str = "Synthetic rule",
    source: int | None = None,
) -> object:
    candidate = s.candidate(title, s.sources[0] if source is None else source)
    target = candidate.drawer_id
    prior = None
    policy = None
    for current in STATES:
        if current == "validated":
            evaluation = s.book.evaluate(target, evaluator_id=EVALUATOR)
            assert evaluation.passed and evaluation.candidate_score == 1.0
            target = evaluation.current_id
            policy = validation_policy(evaluation)
        if current == "active":
            promoted = s.book.promote(target, evaluation_id=evaluation.drawer_id)
            target = promoted.drawer_id
            assert s.approvals[-1]["procedure_id"] == promoted.supersedes_id
        if current == state:
            mandatory = tuple(
                dict.fromkeys(
                    (
                        *(policy.evidence_ids if policy else ()),
                        target,
                        *((prior.drawer_id,) if prior else ()),
                    )
                )
            )
            return SimpleNamespace(
                target=target,
                prior=prior,
                policy=policy,
                supplied_policy=policy if state == "validated" else None,
                mandatory=mandatory,
            )
        prior = step(s, target, current, prior, policy if current == "validated" else None)
    raise AssertionError("unknown lifecycle state")


def active(s: Scenario, title: str, source: int) -> object:
    prepared = prepare(s, "active", title, source)
    receipt = step(s, prepared.target, "active", prepared.prior)
    assert receipt.mode == "ACTIVE" and receipt.effective_tier == "P2"
    return SimpleNamespace(procedure_id=prepared.target, lifecycle_id=receipt.drawer_id)


def sources_for(
    s: Scenario,
    mandatory: tuple[int, ...],
    total: int,
    overlap: bool = False,
) -> tuple[int, ...]:
    distinct = tuple(dict.fromkeys(mandatory))
    assert not set(distinct).intersection(s.sources)
    values = s.sources[: total - len(distinct)]
    return (*values, *distinct) if overlap else values


def expected_union(references: tuple[int, ...], mandatory: tuple[int, ...]) -> tuple[int, ...]:
    return tuple(dict.fromkeys((*references, *mandatory)))


def checked_lifecycle(
    s: Scenario,
    state: str,
    prepared: object,
    references: tuple[int, ...],
) -> object:
    return s.book.transition_lifecycle(
        prepared.target,
        to_state=state,
        evidence_ids=references,
        rationale=f"SYNTHETIC composed boundary {state}",
        expected_prior_id=None if prepared.prior is None else prepared.prior.drawer_id,
        validation_policy=prepared.supplied_policy,
    )


def pair(s: Scenario) -> object:
    older = active(s, "Synthetic archived rule", s.sources[0])
    newer = active(s, "Synthetic contextual replacement", s.sources[1])
    mandatory = (older.procedure_id, newer.procedure_id, older.lifecycle_id, newer.lifecycle_id)
    return SimpleNamespace(older=older, newer=newer, mandatory=mandatory)


def supersede(s: Scenario, participants: object, references: tuple[int, ...]) -> object:
    return s.book.record_contextual_supersession(
        older_id=participants.older.procedure_id,
        replacement_id=participants.newer.procedure_id,
        context=("studio", "build"),
        evidence_ids=references,
        rationale="SYNTHETIC contextual evidence boundary",
    )


def read_pair(
    s: Scenario,
    participants: object,
    relation: object,
    restored: object | None = None,
) -> None:
    assert s.book.get_supersession(relation.drawer_id) == relation
    inside = {
        item.procedure_id for item in s.book.scan_practices(wing=WING, context=("studio", "build"))
    }
    outside = {item.procedure_id for item in s.book.scan_practices(wing=WING, context=("mobile",))}
    both = {participants.older.procedure_id, participants.newer.procedure_id}
    assert both <= outside
    assert participants.newer.procedure_id in inside
    if restored is None:
        assert participants.older.procedure_id not in inside
        assert s.book.supersession_history(participants.older.procedure_id) == (relation,)
    else:
        assert both <= inside
        assert s.book.get_supersession(restored.drawer_id) == restored
        assert s.book.supersession_history(participants.older.procedure_id) == (relation, restored)


@pytest.mark.parametrize("overlap", [False, True], ids=["automatic-sources", "dedup-sources"])
def test_lifecycle_exact512_readable_for_every_phase(scenario: Scenario, overlap: bool) -> None:
    s = scenario
    for state in STATES:
        prepared = prepare(s, state, f"Synthetic {state} overlap={overlap}")
        references = sources_for(s, prepared.mandatory, 512, overlap)
        expected = expected_union(references, prepared.mandatory)
        assert len(references) <= 512 and len(expected) == 512
        receipt = checked_lifecycle(s, state, prepared, references)
        assert receipt.state == state and receipt.evidence_ids == expected
        assert len(receipt.evidence_ids) == len(set(receipt.evidence_ids)) == 512
        if prepared.policy is not None:
            assert set(prepared.policy.evidence_ids) <= set(receipt.evidence_ids)
        if prepared.prior is not None:
            assert prepared.prior.drawer_id in receipt.evidence_ids
        before_read = snapshot(s.store._conn)
        assert s.book.get_lifecycle(prepared.target) == receipt
        s.reopen(before_read)
        assert s.book.get_lifecycle(prepared.target) == receipt
        assert s.book.lifecycle_history(prepared.target)[-1] == receipt
        assert snapshot(s.store._conn) == before_read


@pytest.mark.parametrize("state", STATES)
def test_lifecycle_composed513_refuses_without_durable_mutation(
    scenario: Scenario, state: str
) -> None:
    s = scenario
    prepared = prepare(s, state)
    references = sources_for(s, prepared.mandatory, 513)
    assert len(references) <= 512
    assert len(expected_union(references, prepared.mandatory)) == 513
    old_history = s.book.lifecycle_history(prepared.target)
    before = snapshot(s.store._conn)
    with pytest.raises(procedures.ProcedureError):
        checked_lifecycle(s, state, prepared, references)
    assert not s.store.transaction_active
    assert snapshot(s.store._conn) == before, "refusal committed drawer/registry changes"
    assert s.book.lifecycle_history(prepared.target) == old_history
    s.reopen(before)
    assert s.book.lifecycle_history(prepared.target) == old_history
    assert snapshot(s.store._conn) == before


@pytest.mark.parametrize("overlap", [False, True], ids=["automatic-sources", "dedup-sources"])
def test_contextual_exact512_readable_and_scoped_to_context(
    scenario: Scenario, overlap: bool
) -> None:
    s = scenario
    participants = pair(s)
    references = sources_for(s, participants.mandatory, 512, overlap)
    expected = expected_union(references, participants.mandatory)
    assert len(references) <= 512 and len(expected) == 512
    relation = supersede(s, participants, references)
    assert relation.evidence_ids == expected and len(set(relation.evidence_ids)) == 512
    before_read = snapshot(s.store._conn)
    read_pair(s, participants, relation)
    s.reopen(before_read)
    read_pair(s, participants, relation)
    assert snapshot(s.store._conn) == before_read


def test_contextual_composed513_refuses_without_durable_mutation(scenario: Scenario) -> None:
    s = scenario
    participants = pair(s)
    references = sources_for(s, participants.mandatory, 513)
    assert len(references) <= 512
    assert len(expected_union(references, participants.mandatory)) == 513
    before = snapshot(s.store._conn)
    with pytest.raises(procedures.ProcedureError):
        supersede(s, participants, references)
    assert not s.store.transaction_active
    assert snapshot(s.store._conn) == before, "refusal committed drawer/registry changes"
    assert s.book.supersession_history(participants.older.procedure_id) == ()
    s.reopen(before)
    assert s.book.supersession_history(participants.older.procedure_id) == ()
    assert snapshot(s.store._conn) == before


def test_restoration_exact512_deduplicates_archived_evidence_and_reopens(
    scenario: Scenario,
) -> None:
    s = scenario
    participants = pair(s)
    relation = supersede(s, participants, sources_for(s, participants.mandatory, 510))
    assert len(relation.evidence_ids) == 510 and s.sources[0] in relation.evidence_ids
    fresh = s.add("SYNTHETIC actual fresh support after contextual directive")
    expected = tuple(
        dict.fromkeys((*relation.evidence_ids, relation.drawer_id, s.sources[0], fresh))
    )
    assert len(expected) == 512
    restored = s.book.restore_contextual_supersession(
        relation.drawer_id,
        archived_evidence_id=s.sources[0],
        new_evidence_id=fresh,
        rationale="SYNTHETIC archived and fresh evidence restore the rule",
    )
    assert restored.evidence_ids == expected and len(set(restored.evidence_ids)) == 512
    before_read = snapshot(s.store._conn)
    read_pair(s, participants, relation, restored)
    s.reopen(before_read)
    read_pair(s, participants, relation, restored)
    assert snapshot(s.store._conn) == before_read


@pytest.mark.parametrize("original_count", [511, 512], ids=["composed513", "composed514"])
def test_restoration_overflow_refuses_without_durable_mutation(
    scenario: Scenario, original_count: int
) -> None:
    s = scenario
    participants = pair(s)
    relation = supersede(s, participants, sources_for(s, participants.mandatory, original_count))
    fresh = s.add("SYNTHETIC actual fresh support for refused restoration")
    expected = tuple(
        dict.fromkeys((*relation.evidence_ids, relation.drawer_id, s.sources[0], fresh))
    )
    assert len(expected) == original_count + 2
    before = snapshot(s.store._conn)
    with pytest.raises(procedures.ProcedureError):
        s.book.restore_contextual_supersession(
            relation.drawer_id,
            archived_evidence_id=s.sources[0],
            new_evidence_id=fresh,
            rationale="SYNTHETIC oversized restoration must leave original directive intact",
        )
    assert not s.store.transaction_active
    assert snapshot(s.store._conn) == before, "refusal committed drawer/registry changes"
    read_pair(s, participants, relation)
    s.reopen(before)
    read_pair(s, participants, relation)
    assert snapshot(s.store._conn) == before


def test_ordinary_small_workflow_keeps_reversible_history(scenario: Scenario) -> None:
    s = scenario
    participants = pair(s)
    relation = supersede(s, participants, s.sources[:3])
    assert len(relation.evidence_ids) == 7
    fresh = s.add("SYNTHETIC independent later support for ordinary restoration")
    restored = s.book.restore_contextual_supersession(
        relation.drawer_id,
        archived_evidence_id=s.sources[0],
        new_evidence_id=fresh,
        rationale="SYNTHETIC ordinary reversible workflow",
    )
    assert len(restored.evidence_ids) == 9
    before_read = snapshot(s.store._conn)
    read_pair(s, participants, relation, restored)
    s.reopen(before_read)
    read_pair(s, participants, relation, restored)
    assert snapshot(s.store._conn) == before_read
