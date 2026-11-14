"""Q04 end to end in a real browser: faults caught, clean passes, review required."""

from copy import deepcopy

import pytest
from tests.acceptance.paladin_ui_unit.oracle import read_json, require_variant
from tests.acceptance.paladin_ui_unit.review_helpers import EMPTY_HEAD, approved_reference

from cairntir.errors import CairntirError
from cairntir.paladin_ui import PaladinUIRun

from .fixture import TOOLS_VARIABLE, RealUIFixture, prepared_root, review_artifact

PREPARED = prepared_root()
pytestmark = pytest.mark.skipif(
    PREPARED is None, reason=TOOLS_VARIABLE + " is not set; see this folder's README"
)
FAULTS = ("name-fault", "keyboard-fault", "overflow-fault", "visual-fault")


@pytest.fixture
def ui(tmp_path, monkeypatch):
    fixture = RealUIFixture(tmp_path / "ui", monkeypatch, PREPARED)
    try:
        yield fixture
    finally:
        fixture.close()


def run_once(fixture, run, callback=None):
    subject = PaladinUIRun(run["runtime"], contract=run["contract"], operator_approval=callback)
    view = subject.execute(run["attempt_id"], fixture.action(run))
    assert view["replayed"] is False
    report = read_json(run["output"] / "producer/ui-result.json", 1048576)
    return subject, view, report


def review(fixture, run, bundle, expected, decision):
    artifact, reference, callback = review_artifact(fixture, bundle, expected, decision)
    subject = PaladinUIRun(run["runtime"], contract=run["contract"], operator_approval=callback)
    return subject.review_baseline(
        candidate_id=bundle["manifest"]["candidate_id"],
        expected_revision=deepcopy(expected),
        review_evidence=reference,
        idempotency_key=artifact["review_id"],
    )


def test_real_browser_detects_faults_and_requires_review(ui):
    # Capture: real screenshots, stored UNREVIEWED; nothing approves itself.
    capture = ui.new_run()
    subject, view, report = run_once(ui, capture)
    assert view["result"]["status"] == "UNREVIEWED"
    assert report["renderer"]["browser"]["version"] == "151.0.7922.34"
    assert subject.report()["disposition"] == "BLOCKED"
    bundle = view["result"]["candidate"]
    with pytest.raises(CairntirError):
        subject.review_baseline(
            candidate_id=capture["attempt_id"],
            expected_revision=EMPTY_HEAD,
            review_evidence=review_artifact(ui, bundle, EMPTY_HEAD, "APPROVE")[1],
            idempotency_key="no-reviewer-callback",
        )
    assert subject.report()["baseline"]["active"] is None

    # Explicit review is the only way a baseline becomes active.
    approved = review(ui, capture, bundle, EMPTY_HEAD, "APPROVE")
    assert approved["review"]["decision"] == "APPROVED"
    ui.approved = approved_reference(approved)
    head = deepcopy(ui.approved["head"])

    # Corrected page: every family passes and the run is COMPLETE.
    clean = ui.new_run(approved=ui.approved, fresh_task=True)
    clean_subject, clean_view, clean_report = run_once(ui, clean)
    require_variant(clean_report, "clean")
    assert clean_view["result"]["status"] == "PASS"
    assert clean_subject.report()["disposition"] == "COMPLETE"

    # Each deliberate fault fails for its own reason, judged by the frozen oracle.
    failed = {}
    for variant in FAULTS:
        run = ui.new_run(variant=variant, approved=ui.approved)
        _, fault_view, fault_report = run_once(ui, run)
        require_variant(fault_report, variant)
        assert fault_view["result"]["status"] == "FAIL", variant
        failed[variant] = (run, fault_view)

    # A changed image is not adopted: rejecting it keeps the approved head.
    active = clean_subject.report()["baseline"]["active"]
    assert active is not None
    run, fault_view = failed["visual-fault"]
    rejected = review(ui, run, fault_view["result"]["candidate"], head, "REJECT")
    assert rejected["review"]["decision"] == "REJECTED"
    assert rejected["review"]["before"] == rejected["review"]["after"] == head
    assert clean_subject.report()["baseline"]["active"] == active
