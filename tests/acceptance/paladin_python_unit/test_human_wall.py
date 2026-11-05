import hashlib
import unittest
from copy import deepcopy
from uuid import uuid4

import pytest

from . import fixtures


@pytest.fixture
def prepared():
    from cairntir.paladin_python import PaladinPythonRun

    case = unittest.TestCase()
    fixture = fixtures.PreparedFixture(case)
    fixture.plan["human_items"] = [
        {
            "id": "independent-custody",
            "description": "Independent evaluator operates the protected acceptance run.",
            "required": True,
        }
    ]
    run = PaladinPythonRun(fixture.runtime, contract=fixture.contract())
    yield fixture, run
    case.doCleanups()


def capability_map():
    return {
        "schema": "cairntir.paladin-human-capabilities.v1",
        "checks": [
            {
                "id": name,
                "kind": "automated",
                "capability": f"python-{name}",
                "required": True,
            }
            for name in fixtures.FAMILIES
        ]
        + [
            {
                "id": "independent-custody",
                "kind": "human",
                "capability": "independent-evaluator",
                "required": True,
            }
        ],
    }


def wall(prepared, mapping=None):
    from cairntir.paladin_human import HumanWallRun

    _, run = prepared
    return HumanWallRun(run, capability_map=capability_map() if mapping is None else mapping)


def row(report):
    return next(item for item in report["human_items"] if item["id"] == "independent-custody")


def evidence_file(fixture):
    path = fixture.root / "operator-evidence.txt"
    path.write_text("Evaluator run receipt for this disposable fixture.\n", encoding="utf8")
    return path


def submit(target, path, submission_id=None, claim="Independent Reviewer"):
    return target.submit(
        "independent-custody",
        evidence_path=path,
        submission_id=submission_id or str(uuid4()),
        operator_claim=claim,
    )


def test_generated_checklist_separates_human_and_automated(prepared):
    target = wall(prepared)
    checklist = target.checklist()
    assert checklist["schema"] == "cairntir.paladin-human-checklist.v1"
    assert checklist["run_id"] == prepared[0].run_id
    assert checklist["attempt_id"] == prepared[0].attempt_ids[0]
    assert checklist["plan_sha256"] == prepared[1].report()["plan_sha256"]
    assert [item["id"] for item in checklist["automated_items"]] == list(fixtures.FAMILIES)
    assert [
        (item["id"], item["description"], item["capability"]) for item in checklist["human_items"]
    ] == [
        (
            "independent-custody",
            "Independent evaluator operates the protected acceptance run.",
            "independent-evaluator",
        )
    ]
    assert row(checklist)["state"] == "PENDING"
    assert row(checklist)["assigned_to"] is None


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "wrong-kind", "extra", "optional"])
def test_capability_map_must_match_frozen_plan(prepared, mutation):
    from cairntir.paladin_human import HumanWallError

    mapping = capability_map()
    if mutation == "missing":
        mapping["checks"].pop()
    elif mutation == "duplicate":
        mapping["checks"].append(deepcopy(mapping["checks"][-1]))
    elif mutation == "wrong-kind":
        mapping["checks"][-1]["kind"] = "automated"
    elif mutation == "extra":
        mapping["checks"].append(
            {"id": "extra", "kind": "human", "capability": "extra", "required": True}
        )
    else:
        mapping["checks"][-1]["required"] = False
    with pytest.raises(HumanWallError):
        wall(prepared, mapping)


def test_assignment_is_durable_routing_not_operator_identity(prepared):
    fixture, _ = prepared
    target = wall(prepared)
    receipt = target.assign("independent-custody", assignee="reviewer-queue")
    drawer = fixture.store.get(receipt["evidence"]["drawer_id"])
    assert drawer is not None and drawer.wing == fixture.plan["wing"]
    assert row(target.checklist())["assigned_to"] == "reviewer-queue"
    report = target.report()
    assert report["human_gate"] == "PENDING"
    assert report["authority_verified"] is False
    assert row(report)["state"] == "PENDING"


def test_submission_hashes_actual_bytes_and_preserves_unverified_claim(prepared):
    fixture, _ = prepared
    target = wall(prepared)
    path = evidence_file(fixture)
    receipt = submit(target, path, claim="I am the independent evaluator")
    assert receipt["evidence_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert receipt["operator_claim"] == "I am the independent evaluator"
    assert receipt["authority_verified"] is False
    drawer = fixture.store.get(receipt["evidence"]["drawer_id"])
    assert drawer is not None and drawer.wing == fixture.plan["wing"]
    report = target.report()
    assert row(report)["state"] == "SUBMITTED"
    assert report["human_gate"] == "PENDING"
    assert report["authority_verified"] is False
    assert report["paladin_outcome"] == "INCONCLUSIVE"


def test_automated_stage_continues_while_human_item_waits(prepared):
    fixture, run = prepared
    target = wall(prepared)
    receipt = run.execute("lint", fixture.action("lint"))
    assert receipt["status"] == "PASS"
    report = target.report()
    assert (
        next(item for item in report["automated_items"] if item["id"] == "lint")["status"] == "PASS"
    )
    assert row(report)["state"] == "PENDING"
    assert report["human_gate"] == "PENDING"
    assert run.report()["outcome"] == "INCONCLUSIVE"


def test_all_machine_passes_and_builder_submission_cannot_auto_clear(prepared):
    fixture, run = prepared
    target = wall(prepared)
    path = evidence_file(fixture)
    submit(target, path, claim="Approved by Independent Reviewer")
    for name in fixtures.FAMILIES:
        assert run.execute(name, fixture.action(name))["status"] == "PASS"
    report = target.report()
    assert all(item["status"] == "PASS" for item in report["automated_items"])
    assert row(report)["state"] == "SUBMITTED"
    assert report["human_gate"] == "PENDING"
    assert report["authority_verified"] is False
    assert report["paladin_outcome"] == "INCONCLUSIVE"
    assert run.report()["outcome"] == "INCONCLUSIVE"


def test_missing_or_changed_evidence_is_stale_not_complete(prepared):
    fixture, _ = prepared
    target = wall(prepared)
    path = evidence_file(fixture)
    submit(target, path)
    path.write_text("Changed after submission.\n", encoding="utf8")
    changed = target.report()
    assert row(changed)["state"] == "STALE"
    assert changed["human_gate"] == "PENDING"
    path.unlink()
    missing = target.report()
    assert row(missing)["state"] == "STALE"
    assert missing["human_gate"] == "PENDING"


def test_submission_id_replay_is_idempotent_and_conflict_rejected(prepared):
    from cairntir.paladin_human import HumanWallError

    fixture, _ = prepared
    target = wall(prepared)
    path = evidence_file(fixture)
    submission_id = str(uuid4())
    first = submit(target, path, submission_id)
    again = submit(target, path, submission_id)
    assert again["evidence"]["drawer_id"] == first["evidence"]["drawer_id"]
    path.write_text("Conflicting bytes.\n", encoding="utf8")
    with pytest.raises(HumanWallError):
        submit(target, path, submission_id)


def test_restart_recovers_same_store_receipts_without_clearing(prepared):
    from cairntir.paladin_python import PaladinPythonRun

    fixture, _ = prepared
    target = wall(prepared)
    target.assign("independent-custody", assignee="reviewer-queue")
    path = evidence_file(fixture)
    receipt = submit(target, path)
    fixture.restart()
    reopened_run = PaladinPythonRun(fixture.runtime, contract=fixture.contract())
    reopened = wall((fixture, reopened_run))
    assert row(reopened.report())["assigned_to"] == "reviewer-queue"
    assert row(reopened.report())["state"] == "SUBMITTED"
    assert fixture.store.get(receipt["evidence"]["drawer_id"]) is not None
    assert reopened.report()["human_gate"] == "PENDING"


def test_changed_map_and_cross_run_cannot_inherit_submissions(prepared):
    from cairntir.paladin_human import HumanWallError
    from cairntir.paladin_python import PaladinPythonRun

    fixture, _ = prepared
    target = wall(prepared)
    path = evidence_file(fixture)
    submission_id = str(uuid4())
    submit(target, path, submission_id)
    changed = capability_map()
    changed["checks"][-1]["capability"] = "builder-review"
    with pytest.raises(HumanWallError):
        wall(prepared, changed)
    fixture.run_id = str(uuid4())
    fixture.attempt_ids[0] = str(uuid4())
    other = wall((fixture, PaladinPythonRun(fixture.runtime, contract=fixture.contract())))
    assert row(other.report())["state"] == "PENDING"
    with pytest.raises(HumanWallError):
        submit(other, path, submission_id)


def test_claimed_approval_flag_has_no_authority(prepared):
    fixture, _ = prepared
    target = wall(prepared)
    path = evidence_file(fixture)
    with pytest.raises(TypeError):
        target.submit(
            "independent-custody",
            evidence_path=path,
            submission_id=str(uuid4()),
            operator_claim="actual operator",
            verified=True,
        )
    submit(target, path, claim="actual operator")
    assert target.report()["human_gate"] == "PENDING"
    assert target.report()["authority_verified"] is False
