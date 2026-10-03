"""Frozen, inert cross-feature controls for corrections and attributed procedures."""

from __future__ import annotations

import hashlib
import json
import socket
import subprocess
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from cairntir import obsidian_bridge as bridge
from cairntir import procedures as api
from cairntir.access import AccessDenied, bind_grant, issue_grant
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.reason.model import Experiment, Outcome

_ROOT = Path(__file__).resolve().parents[2]
_PACKET = _ROOT / "plans" / "acceptance" / "combined-foundation-1.15"
_FREEZE = json.loads((_PACKET / "FREEZE.json").read_text(encoding="utf-8"))
for _relative, _expected in _FREEZE["files_sha256"].items():
    if hashlib.sha256((_ROOT / _relative).read_bytes()).hexdigest() != _expected:
        raise pytest.UsageError(f"independent combined acceptance custody changed: {_relative}")

WING = "combined-fixture"
EVALUATOR = "inert-list/v1"


class _Runner:
    def __init__(self):
        self.calls = []

    def run(self, hypothesis):
        self.calls.append(hypothesis)
        payload = json.loads(hypothesis.claim)
        values = json.loads(payload["input"])
        if payload["steps"] == ["unique-sort"]:
            values = sorted(set(values))
        elif payload["steps"] != ["identity"]:
            raise ValueError("unknown inert fixture steps")
        observed = json.dumps(values)
        return Outcome(
            experiment=Experiment(hypothesis=hypothesis, description="Execute inert list fixture"),
            observed=observed,
            success=observed == hypothesis.predicted_outcome,
            delta="" if observed == hypothesis.predicted_outcome else "Ordering differs",
        )


@pytest.fixture
def combined(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    for name in ("CAIRNTIR_HOME", "XDG_CACHE_HOME", "HF_HOME", "TORCH_HOME", "TEMP", "TMP"):
        isolated = tmp_path / "isolation" / name.lower()
        isolated.mkdir(parents=True)
        monkeypatch.setenv(name, str(isolated))
    monkeypatch.delenv("CAIRNTIR_GRANT_FILE", raising=False)
    monkeypatch.setenv("CAIRNTIR_DISABLE_AUTOREGISTER", "1")
    monkeypatch.setenv("CAIRNTIR_DISABLE_UPDATE_CHECK", "1")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")

    def deny(*_args, **_kwargs):
        pytest.fail("Combined fixture attempted a network connection or external process")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(subprocess, "Popen", deny)
    database = tmp_path / "combined.db"
    store = DrawerStore(database, HashEmbeddingProvider(dimension=16))
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    development = store.add(Drawer(wing=WING, room="cases", content="[9, 8, 9]\r\n"))
    cases = tuple(
        api.HoldoutCase(
            case_id=name,
            evidence_id=store.add(Drawer(wing=WING, room="cases", content=value)).id,
            expected_outcome=expected,
        )
        for name, value, expected in (
            ("holdout-a", "[2, 1, 2]", "[1, 2]"),
            ("holdout-b", "[10, 2, 10]", "[2, 10]"),
        )
    )
    governance = api.PracticeGovernance(
        owner="  Administrator label grants no authority  ",
        version="1",
        rationale="Reason café\r\nverbatim  ",
        review_due="2024-02-29",
    )
    spec = api.ProcedureSpec(
        title="Governed integer ordering",
        prerequisites=("Integer list",),
        applicability="Inert ordering fixture",
        steps=("unique-sort",),
        expected_outcome="Unique increasing integers",
        rollback=("Reuse original evidence",),
        evidence_ids=(development.id,),
        governance=governance,
    )
    runner = _Runner()
    registration = api.RegisteredEvaluation(
        manifest=api.EvaluationManifest(
            evaluator_id=EVALUATOR, baseline_steps=("identity",), cases=cases, threshold=0.5
        ),
        runner=runner,
    )
    registry = {EVALUATOR: registration}
    bundle = SimpleNamespace(
        store=store,
        database=database,
        vault=vault,
        development=development,
        spec=spec,
        registry=registry,
        runner=runner,
        book=api.ProcedureBook(store, registry),
    )
    try:
        yield bundle
    finally:
        store.close()


def _rows(store, table):
    quoted = table.replace('"', '""')
    # The names come from the disposable fixture schema, with quotes escaped.
    rows = store._conn.execute(f'SELECT * FROM "{quoted}"').fetchall()  # noqa: S608
    return tuple(sorted((tuple(row) for row in rows), key=repr))


def _snapshot(store):
    tables = store._conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {name: _rows(store, name) for (name,) in tables}


def _assert_row_only_touched(before, after, columns):
    telemetry = {"last_accessed_at", "access_count"}
    assert {k: v for k, v in zip(columns, before, strict=True) if k not in telemetry} == {
        k: v for k, v in zip(columns, after, strict=True) if k not in telemetry
    }
    count = columns.index("access_count")
    stamp = columns.index("last_accessed_at")
    assert after[count] >= before[count]
    if after[count] == before[count]:
        assert after[stamp] == before[stamp]
    else:
        assert after[stamp] >= before[stamp]


def _assert_only_read_telemetry_changed(store, before, after):
    assert before.keys() == after.keys()
    assert {k: v for k, v in before.items() if k != "drawers"} == {
        k: v for k, v in after.items() if k != "drawers"
    }
    columns = [row[1] for row in store._conn.execute("PRAGMA table_info(drawers)")]
    original = {row[0]: row for row in before["drawers"]}
    current = {row[0]: row for row in after["drawers"]}
    assert original.keys() == current.keys()
    for drawer_id, row in original.items():
        _assert_row_only_touched(row, current[drawer_id], columns)


def _request(store, drawer, content="  Correction café 雪\r\n\r\nlast space \r\n"):
    return {
        "schema": "cairntir.obsidian-correction.v1",
        "request_id": str(uuid4()),
        "wing": drawer.wing,
        "source_drawer_id": drawer.id,
        "source_identity": store.portable_identity(drawer.id),
        "source_sha256": hashlib.sha256(drawer.content.encode("utf-8")).hexdigest(),
        "content": content,
    }


def _submit(bundle, request):
    outbox = bundle.vault / "cairntir-sync" / "outbox"
    outbox.mkdir(parents=True, exist_ok=True)
    path = outbox / (request["request_id"] + ".json")
    path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
    return path


def _manifest(bundle):
    return json.loads(
        (bundle.vault / "cairntir-sync" / "workspace.json").read_text(encoding="utf-8")
    )


def _corroborated(bundle):
    candidate = bundle.book.propose(wing=WING, spec=bundle.spec)
    receipt = bundle.book.evaluate(candidate.drawer_id, evaluator_id=EVALUATOR)
    assert receipt.passed is True
    return receipt


def test_governed_lifecycle_and_reopened_correction_preserve_shared_history(combined):
    b = combined
    first = b.book.propose(wing=WING, spec=b.spec)
    original_row = b.store._conn.execute(
        "SELECT * FROM drawers WHERE id=?", (first.drawer_id,)
    ).fetchone()
    second_spec = replace(b.spec, governance=replace(b.spec.governance, version="2"))
    second = b.book.revise(first.drawer_id, spec=second_spec)
    evaluated = b.book.evaluate(second.drawer_id, evaluator_id=EVALUATOR)
    assert evaluated.passed is True and len(b.runner.calls) == 4
    approvals = []
    approving = api.ProcedureBook(
        b.store, b.registry, operator_approval=lambda request: approvals.append(request) or True
    )
    promoted = approving.promote(evaluated.current_id, evaluation_id=evaluated.drawer_id)
    assert len(approvals) == 1
    withdrawn = approving.rollback(promoted.drawer_id, reason="Explicit fixture withdrawal")
    history = approving.history(withdrawn.drawer_id)
    assert [p.state for p in history] == [
        "candidate",
        "candidate",
        "corroborated",
        "promoted",
        "expired",
    ]
    assert [p.spec.governance.version for p in history] == ["1", "2", "2", "2", "2"]
    registry_before = _rows(b.store, "procedure_records")
    evaluations_before = _rows(b.store, "procedure_evaluations")
    assert (
        bridge.sync_workspace(b.store, vault=b.vault, wing=WING)["projection"]["status"]
        == "complete"
    )
    entries = {x["drawer_id"]: x for x in _manifest(b)["drawers"]}
    for record in history:
        assert entries[record.drawer_id]["editable"] is False
        assert entries[record.drawer_id]["content"] == b.store.get(record.drawer_id).content
    note = b.vault / entries[b.development.id]["note"]
    annotation = "\r\nHuman café note\nretain exact bytes.\r\n".encode()
    note.write_bytes(note.read_bytes() + annotation)
    request = _request(b.store, b.development)
    proposal = _submit(b, request)
    proposal_bytes = proposal.read_bytes()
    report = bridge.sync_workspace(b.store, vault=b.vault, wing=WING)
    receipt = next(x["receipt"] for x in report["results"] if x["status"] == "committed")
    assert receipt["replayed"] is False
    assert note.read_bytes().endswith(annotation)
    assert b.store.get(receipt["correction_drawer_id"]).content == request["content"]
    assert b.store.get(b.development.id) == b.development
    retained_row = b.store._conn.execute(
        "SELECT * FROM drawers WHERE id=?", (first.drawer_id,)
    ).fetchone()
    _assert_row_only_touched(original_row, retained_row, list(original_row.keys()))
    assert _rows(b.store, "procedure_records") == registry_before
    assert _rows(b.store, "procedure_evaluations") == evaluations_before
    assert approving.history(withdrawn.drawer_id) == history
    b.store.close()
    with DrawerStore(b.database, HashEmbeddingProvider(dimension=16)) as reopened:
        before = _snapshot(reopened)
        replay = bridge.sync_workspace(reopened, vault=b.vault, wing=WING)
        repeated = next(x["receipt"] for x in replay["results"] if x["status"] == "committed")
        assert repeated["replayed"] is True
        assert {k: v for k, v in repeated.items() if k != "replayed"} == {
            k: v for k, v in receipt.items() if k != "replayed"
        }
        assert _snapshot(reopened) == before
        assert api.ProcedureBook(reopened, b.registry).history(withdrawn.drawer_id) == history
    assert proposal.read_bytes() == proposal_bytes and note.read_bytes().endswith(annotation)


@pytest.mark.parametrize("kind", ["governed", "evaluation", "prediction"])
def test_generic_correction_refuses_structured_governed_workflows(combined, kind):
    b = combined
    evaluated = _corroborated(b)
    drawer_id = {
        "governed": evaluated.current_id,
        "evaluation": evaluated.drawer_id,
        "prediction": evaluated.cases[0].baseline_prediction_id,
    }[kind]
    source = b.store.get(drawer_id)
    before = _snapshot(b.store)
    with pytest.raises(bridge.CorrectionError, match="dedicated lifecycle"):
        bridge.apply_correction(b.store, _request(b.store, source), wing=WING)
    assert _snapshot(b.store) == before
    assert (
        bridge.sync_workspace(b.store, vault=b.vault, wing=WING)["projection"]["status"]
        == "complete"
    )
    entries = {x["drawer_id"]: x for x in _manifest(b)["drawers"]}
    assert entries[drawer_id]["editable"] is False


def test_owner_attribution_does_not_replace_approval_or_scoped_authority(combined):
    b = combined
    evaluated = _corroborated(b)
    before = _snapshot(b.store)
    with pytest.raises(api.ProcedureError, match="local operator approval"):
        b.book.promote(evaluated.current_id, evaluation_id=evaluated.drawer_id)
    _assert_only_read_telemetry_changed(b.store, before, _snapshot(b.store))
    token = issue_grant(b.store, scopes=[{"wing": WING}], capabilities=["read", "write"])
    scoped = bind_grant(b.store, token)
    callbacks = []
    scoped_book = api.ProcedureBook(
        scoped, b.registry, operator_approval=lambda request: callbacks.append(request) or True
    )
    before = _snapshot(b.store)
    with pytest.raises(AccessDenied):
        scoped_book.promote(evaluated.current_id, evaluation_id=evaluated.drawer_id)
    assert callbacks == [] and _snapshot(b.store) == before
    approving = api.ProcedureBook(
        b.store, b.registry, operator_approval=lambda request: callbacks.append(request) or True
    )
    promoted = approving.promote(evaluated.current_id, evaluation_id=evaluated.drawer_id)
    assert len(callbacks) == 1 and promoted.spec.governance == b.spec.governance


def test_scoped_workspace_keeps_governed_records_readonly_and_plain_correction_usable(combined):
    b = combined
    governed = b.book.propose(wing=WING, spec=b.spec)
    foreign = b.store.add(Drawer(wing="foreign", room="cases", content="FOREIGN-FIXTURE-SENTINEL"))
    token = issue_grant(b.store, scopes=[{"wing": WING}], capabilities=["read", "write"])
    scoped = bind_grant(b.store, token)
    assert api.ProcedureBook(scoped, b.registry).list(wing=WING, active_only=False) == [governed]
    assert (
        bridge.sync_workspace(scoped, vault=b.vault, wing=WING)["projection"]["status"]
        == "complete"
    )
    entries = {x["drawer_id"]: x for x in _manifest(b)["drawers"]}
    assert entries[governed.drawer_id]["editable"] is False
    assert entries[b.development.id]["editable"] is True
    assert foreign.id not in entries and "FOREIGN-FIXTURE-SENTINEL" not in json.dumps(_manifest(b))
    registry = _rows(b.store, "procedure_records")
    request = _request(b.store, b.development)
    receipt = bridge.apply_correction(scoped, request, wing=WING)
    assert receipt["status"] == "committed" and receipt["replayed"] is False
    assert b.store.get(receipt["correction_drawer_id"]).content == request["content"]
    assert _rows(b.store, "procedure_records") == registry
    assert api.ProcedureBook(scoped, b.registry).history(governed.drawer_id) == [governed]
