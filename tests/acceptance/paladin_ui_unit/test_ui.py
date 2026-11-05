import sys
import time
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest

from cairntir.access import bind_grant, revoke_grant
from cairntir.errors import CairntirError
from cairntir.managed import ManagedRuntime
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.paladin_ui import PaladinUIRun

from .fixture import UIFixture
from .oracle import read_json, verify_semantics
from .review_helpers import EMPTY_HEAD, approved_reference, review_artifact
from .unit_png import verify_identical_metric


@pytest.fixture
def ui(tmp_path, monkeypatch):
    fixture = UIFixture(tmp_path / "ui", monkeypatch)
    try:
        yield fixture
    finally:
        fixture.close()


def execute(fixture, run, callback=None):
    subject = PaladinUIRun(run["runtime"], contract=run["contract"], operator_approval=callback)
    action = fixture.action(run)
    view = subject.execute(run["attempt_id"], action)
    assert set(view) == {"result", "evidence", "replayed"}
    assert view["replayed"] is False
    return subject, action, view


def capture(fixture):
    run = fixture.new_run()
    subject, action, view = execute(fixture, run)
    assert view["result"]["status"] == "UNREVIEWED"
    assert view["result"]["candidate"]["manifest"]["candidate_id"] == run["attempt_id"]
    return run, subject, action, view


def approve(fixture, run, view):
    bundle = view["result"]["candidate"]
    artifact, reference, callback = review_artifact(fixture, bundle, EMPTY_HEAD, "APPROVE")
    subject = PaladinUIRun(run["runtime"], contract=run["contract"], operator_approval=callback)
    reviewed = subject.review_baseline(
        candidate_id=bundle["manifest"]["candidate_id"],
        expected_revision=deepcopy(EMPTY_HEAD),
        review_evidence=reference,
        idempotency_key=artifact["review_id"],
    )
    assert reviewed["review"]["decision"] == "APPROVED"
    assert reviewed["review"]["after"]["generation"] == 1
    fixture.approved = approved_reference(reviewed)
    return reviewed


def compared(fixture):
    original, _, _, view = capture(fixture)
    approve(fixture, original, view)
    run = fixture.new_run(approved=fixture.approved)
    subject, action, result = execute(fixture, run)
    assert result["result"]["status"] == "PASS"
    assert subject.report()["disposition"] == "COMPLETE"
    return run, subject, action, result


def refuses_current(call):
    try:
        result = call()
    except CairntirError:
        return
    assert result["disposition"] != "COMPLETE"
    assert result["qualification"]["status"] != "CURRENT"


def test_contract_rejects_changed_inputs_without_writes(ui):
    run = ui.new_run()
    before = ui.state()
    malformed = deepcopy(run["contract"])
    malformed["approved"] = True
    with pytest.raises(CairntirError):
        PaladinUIRun(run["runtime"], contract=malformed)
    assert ui.state() == before and ui.calls == []
    source = run["snapshot"] / "index.html"
    source.write_bytes(source.read_bytes() + b"\nchanged")
    with pytest.raises(CairntirError):
        PaladinUIRun(run["runtime"], contract=run["contract"])
    assert ui.state() == before and ui.calls == []


def test_unreviewed_candidate_cannot_self_approve(ui):
    run, subject, _, view = capture(ui)
    assert subject.report()["disposition"] == "BLOCKED"
    bundle = view["result"]["candidate"]
    artifact, reference, _ = review_artifact(ui, bundle, EMPTY_HEAD, "APPROVE")
    before = ui.state()
    with pytest.raises(CairntirError):
        subject.review_baseline(
            candidate_id=run["attempt_id"],
            expected_revision=EMPTY_HEAD,
            review_evidence=reference,
            idempotency_key=artifact["review_id"],
        )
    answers = []
    for answer in ("approved", {"approved": True}, None):

        def nonboolean(request, value=answer):
            answers.append(value)
            return value

        untrusted = PaladinUIRun(
            run["runtime"], contract=run["contract"], operator_approval=nonboolean
        )
        with pytest.raises(CairntirError):
            untrusted.review_baseline(
                candidate_id=run["attempt_id"],
                expected_revision=EMPTY_HEAD,
                review_evidence=reference,
                idempotency_key=artifact["review_id"],
            )
    assert answers == ["approved", {"approved": True}, None]
    forged = {**reference, "approved": True, "reviewer": "HumanWall PENDING"}
    with pytest.raises(CairntirError):
        subject.review_baseline(
            candidate_id=run["attempt_id"],
            expected_revision=EMPTY_HEAD,
            review_evidence=forged,
            idempotency_key=str(uuid4()),
        )
    assert ui.state() == before
    assert len(ui.calls) == 1


def test_exact_approval_and_rejection_preserve_active_head(ui):
    capture_run, _, _, initial = capture(ui)
    approve(ui, capture_run, initial)
    original_head = deepcopy(ui.approved["head"])
    clean = ui.new_run(approved=ui.approved, fresh_task=True)
    clean_subject, _, clean_result = execute(ui, clean)
    assert clean["contract"]["task_id"] != capture_run["contract"]["task_id"]
    assert clean_result["result"]["status"] == "PASS"
    clean_before = clean_subject.report()
    bad = ui.new_run(variant="visual-fault", approved=ui.approved)
    bad_subject, _, bad_result = execute(ui, bad)
    assert bad_result["result"]["status"] == "FAIL"
    artifact, reference, callback = review_artifact(
        ui, bad_result["result"]["candidate"], original_head, "REJECT"
    )
    reviewer = PaladinUIRun(bad["runtime"], contract=bad["contract"], operator_approval=callback)
    rejected = reviewer.review_baseline(
        candidate_id=bad["attempt_id"],
        expected_revision=original_head,
        review_evidence=reference,
        idempotency_key=artifact["review_id"],
    )
    assert rejected["review"]["decision"] == "REJECTED"
    assert rejected["review"]["before"] == rejected["review"]["after"] == original_head
    assert rejected["review"]["approval_manifest"] is None
    again = reviewer.review_baseline(
        candidate_id=bad["attempt_id"],
        expected_revision=original_head,
        review_evidence=reference,
        idempotency_key=artifact["review_id"],
    )
    assert again["replayed"] is True and again["evidence"] == rejected["evidence"]
    after = clean_subject.report()
    assert after["qualification"] == clean_before["qualification"]
    assert after["attempts"] == clean_before["attempts"]
    assert after["baseline"]["active"] == clean_before["baseline"]["active"]
    assert any(row["review"]["decision"] == "REJECTED" for row in after["baseline"]["reviews"])
    assert bad_subject.report()["attempts"][0]["result"]["status"] == "FAIL"
    assert len(ui.calls) == 3


def test_review_rechecks_live_authority_and_candidate_cas(ui):
    run, _, _, result = capture(ui)
    bundle = result["result"]["candidate"]
    artifact, reference, original = review_artifact(ui, bundle, EMPTY_HEAD, "APPROVE")
    scoped, token = ui.scoped(("read", "write", "approve"))
    run["runtime"].close(last_sequence=ui.last_sequence)
    runtime = ManagedRuntime(scoped, config=deepcopy(run["config"]))
    runtime.start(str(uuid4()), task_id=ui.task_id)
    ui.runtime, ui.last_sequence = runtime, 0

    def revoke_during_review(request):
        assert original(request) is True
        revoke_grant(ui.store, token)
        return True

    subject = PaladinUIRun(
        runtime, contract=run["contract"], operator_approval=revoke_during_review
    )
    with pytest.raises(CairntirError):
        subject.review_baseline(
            candidate_id=run["attempt_id"],
            expected_revision=EMPTY_HEAD,
            review_evidence=reference,
            idempotency_key=artifact["review_id"],
        )
    owner_runtime = ManagedRuntime(ui.store, config=deepcopy(run["config"]))
    owner_subject = PaladinUIRun(owner_runtime, contract=run["contract"])
    assert owner_subject.report()["baseline"]["active"] is None
    owner_runtime.start(str(uuid4()), task_id=ui.task_id)
    ui.runtime, ui.last_sequence = owner_runtime, 0
    image = Path(bundle["manifest"]["images"][0]["current"]["path"])
    original_bytes = image.read_bytes()

    mutated = False

    def mutate_during_review(request):
        nonlocal mutated
        assert original(request) is True
        mutated = True
        image.write_bytes(original_bytes[:-4])
        return True

    reviewer = PaladinUIRun(
        owner_runtime, contract=run["contract"], operator_approval=mutate_during_review
    )
    with pytest.raises(CairntirError):
        reviewer.review_baseline(
            candidate_id=run["attempt_id"],
            expected_revision=EMPTY_HEAD,
            review_evidence=reference,
            idempotency_key=artifact["review_id"],
        )
    assert mutated is True
    image.write_bytes(original_bytes)
    assert owner_subject.report()["baseline"]["active"] is None
    assert len(ui.calls) == 1


def test_reopened_readonly_report_authenticates_selected_history(ui):
    run, _, action, view = compared(ui)
    scoped, token = ui.scoped()
    before = ui.state()
    reopened = DrawerStore(ui.db, HashEmbeddingProvider(32), read_only=True)
    try:
        read_store = bind_grant(reopened, token)
        runtime = ManagedRuntime(read_store, config=deepcopy(run["config"]))
        subject = PaladinUIRun(runtime, contract=run["contract"])
        assert subject.report()["disposition"] == "COMPLETE"
        replay = subject.execute(run["attempt_id"], action)
        assert replay["replayed"] is True
        assert replay["result"] == view["result"] and replay["evidence"] == view["evidence"]
    finally:
        reopened.close()
    assert ui.state() == before and len(ui.calls) == 2
    partial, _ = ui.scoped(rooms=["requests"])
    subject = PaladinUIRun(
        ManagedRuntime(partial, config=deepcopy(run["config"])), contract=run["contract"]
    )
    with pytest.raises(CairntirError):
        subject.report()
    changed = ui.store._conn.execute(
        "UPDATE workflow_runs SET request_hash=? WHERE idempotency_key LIKE ?",
        ("0" * 64, "%paladin-ui:" + run["contract"]["run_id"] + ":%"),
    )
    assert changed.rowcount > 0
    ui.store._conn.commit()
    with pytest.raises(CairntirError):
        PaladinUIRun(
            ManagedRuntime(scoped, config=deepcopy(run["config"])), contract=run["contract"]
        ).report()


def test_malformed_missing_or_forged_artifacts_never_current_pass(ui):
    run, subject, _, original = compared(ui)
    path = run["output"] / "producer/ui-result.json"
    saved = path.read_bytes()
    for mutation in (b"{", saved.replace(b'"PASS"', b'"FAIL"', 1)):
        path.write_bytes(mutation)
        refuses_current(subject.report)
        path.write_bytes(saved)
    image = run["output"] / "producer/raw/mobile/current.png"
    raw = image.read_bytes()
    image.write_bytes(raw[:-8])
    refuses_current(subject.report)
    image.write_bytes(raw)
    image.rename(image.with_suffix(".missing"))
    refuses_current(subject.report)
    image.with_suffix(".missing").rename(image)
    assert subject.report()["attempts"][0]["result"] == original["result"]


def test_exact_replay_and_lost_reply_do_not_relaunch(ui, monkeypatch):
    run = ui.new_run()
    subject = PaladinUIRun(run["runtime"], contract=run["contract"])
    action = ui.action(run)
    original_dispatch = run["runtime"].dispatch

    class ReplyLost(BaseException):
        pass

    def commit_then_lose(request):
        original_dispatch(request)
        raise ReplyLost()

    monkeypatch.setattr(run["runtime"], "dispatch", commit_then_lose)
    with pytest.raises(ReplyLost):
        subject.execute(run["attempt_id"], action)
    monkeypatch.setattr(run["runtime"], "dispatch", original_dispatch)
    recovered = subject.execute(run["attempt_id"], action)
    assert recovered["result"]["status"] == "UNREVIEWED" and len(ui.calls) == 1
    before = ui.state()
    replay = subject.execute(run["attempt_id"], action)
    assert replay["replayed"] is True and replay["evidence"] == recovered["evidence"]
    assert ui.state() == before and len(ui.calls) == 1
    changed = deepcopy(action)
    changed["action_id"] = str(uuid4())
    with pytest.raises(CairntirError):
        subject.execute(run["attempt_id"], changed)
    assert len(ui.calls) == 1


def test_pending_preparation_does_not_relaunch(ui, monkeypatch):
    run = ui.new_run()
    subject = PaladinUIRun(run["runtime"], contract=run["contract"])
    action = ui.action(run)

    class ControllerStopped(BaseException):
        pass

    monkeypatch.setattr(
        run["runtime"], "dispatch", lambda request: (_ for _ in ()).throw(ControllerStopped())
    )
    with pytest.raises(ControllerStopped):
        subject.execute(run["attempt_id"], action)
    assert ui.calls == []
    before = ui.state()
    report = subject.report()
    assert report["disposition"] == "BLOCKED"
    with pytest.raises(CairntirError):
        subject.execute(run["attempt_id"], action)
    assert ui.calls == [] and ui.state() == before


def test_currentness_keeps_history_and_final_read_authority(ui, monkeypatch):
    run, _, _, view = compared(ui)
    scoped, token = ui.scoped()
    runtime = ManagedRuntime(scoped, config=deepcopy(run["config"]))
    subject = PaladinUIRun(runtime, contract=run["contract"])
    source = run["snapshot"] / "index.html"
    saved = source.read_bytes()
    source.write_bytes(saved + b"\nsource changed")
    refuses_current(subject.report)
    source.write_bytes(saved)
    assert subject.report()["attempts"][0]["result"] == view["result"]
    original_projection = type(scoped)._paladin_ui_records
    revoked = False

    def project_then_revoke(store, **selectors):
        nonlocal revoked
        result = original_projection(store, **selectors)
        if store is scoped and not revoked:
            revoked = True
            revoke_grant(ui.store, token)
        return result

    monkeypatch.setattr(type(scoped), "_paladin_ui_records", project_then_revoke)
    with pytest.raises(CairntirError):
        subject.report()
    assert revoked is True


def test_infrastructure_errors_are_inconclusive(ui):
    for fault in ("nonzero", "truncated", "malformed", "unclosed"):
        run = ui.new_run(fault=fault)
        subject, _, result = execute(ui, run)
        assert result["result"]["status"] == "INCONCLUSIVE"
        assert subject.report()["disposition"] == "BLOCKED"


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="Windows Job Object containment; native UI execution is Windows-only",
)
def test_owned_nonbrowser_cancellation_closes_descendants(tmp_path):
    from cairntir._paladin_ui_worker import OwnedProcess

    heartbeat = tmp_path / "descendant.py"
    heartbeat.write_text(
        "import pathlib,sys,time\np=pathlib.Path(sys.argv[1])\n"
        "while True:\n p.write_text(str(time.monotonic()))\n time.sleep(.02)\n",
        encoding="utf-8",
    )
    parent = tmp_path / "parent.py"
    parent.write_text(
        "import json,pathlib,subprocess,sys,time\n"
        "p=subprocess.Popen([sys.executable,'-I','-B',sys.argv[1],sys.argv[2]])\n"
        "pathlib.Path(sys.argv[3]).write_text(json.dumps({'child':p.pid}))\n"
        "while True: time.sleep(.05)\n",
        encoding="utf-8",
    )
    for branch in ("cancel", "timeout"):
        root = tmp_path / branch
        marker, ready = root / "heartbeat.txt", root / "ready.json"
        root.mkdir()
        job = OwnedProcess(
            [
                str(Path(sys.executable).resolve()),
                "-I",
                "-B",
                str(parent),
                str(heartbeat),
                str(marker),
                str(ready),
            ],
            cwd=str(tmp_path),
            environment=dict(__import__("os").environ),
            output_root=str(root / "job"),
            timeout_seconds=5 if branch == "timeout" else 10,
            output_limit_bytes=65536,
        )
        job.start()
        try:
            deadline = time.monotonic() + 8
            while not (marker.exists() and ready.exists()) and time.monotonic() < deadline:
                assert job.poll() is None, "Owned child ended before readiness"
                time.sleep(0.02)
            assert marker.exists() and read_json(ready)["child"] > 0
            state = job.cancel() if branch == "cancel" else None
            while state is None and time.monotonic() < deadline:
                state = job.poll()
                if state is None:
                    time.sleep(0.02)
            assert state is not None
        finally:
            closed = job.close()
        assert closed == state and job.close() == state
        assert job.closed is True
        assert state["job_active_processes"] == 0
        assert state["direct_process_handle_closed"] is True and state["job_handle_closed"] is True
        assert state["owned_tree_exit_observed"] is True and state["cleanup_uncertain"] is False
        assert state["cancelled"] is (branch == "cancel")
        assert state["timed_out"] is (branch == "timeout")
        heartbeat_after_close = marker.read_bytes()
        time.sleep(0.15)
        assert marker.read_bytes() == heartbeat_after_close, "Owned descendant survived cleanup"
        with pytest.raises(RuntimeError):
            job.start()


def test_independent_oracles_reject_false_passes(ui):
    run, _, _, _ = compared(ui)
    report = read_json(run["output"] / "producer/ui-result.json")
    verify_semantics(report)
    wrong = deepcopy(report)
    wrong["viewports"][0]["checks"][2]["observation"]["name"] = ""
    with pytest.raises(AssertionError):
        verify_semantics(wrong)
    wrong = deepcopy(report)
    for viewport in wrong["viewports"]:
        visual = next(row for row in viewport["checks"] if row["check"]["kind"] == "rgba-diff")
        visual["observation"]["mismatched_pixels"] = 1
    with pytest.raises(AssertionError):
        verify_semantics(wrong)
    visual = next(
        row for row in report["viewports"][0]["checks"] if row["check"]["kind"] == "rgba-diff"
    )["observation"]
    baseline = Path(visual["baseline"]["path"])
    if not baseline.is_absolute():
        baseline = run["output"] / baseline
    current = run["output"] / visual["current"]["path"]
    verify_identical_metric(baseline.read_bytes(), current.read_bytes(), visual)
    consistent_lie = deepcopy(visual)
    consistent_lie["mismatched_pixels"] = consistent_lie["exact_changed_pixels"] = 1
    consistent_lie["diff_ratio"] = 1 / consistent_lie["compared_pixels"]
    with pytest.raises(AssertionError):
        verify_identical_metric(baseline.read_bytes(), current.read_bytes(), consistent_lie)
