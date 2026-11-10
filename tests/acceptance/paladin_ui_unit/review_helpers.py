from copy import deepcopy
from uuid import uuid4

from .fixture import absolute_file
from .oracle import canonical, digest, read_json

EMPTY_HEAD = {"generation": 0, "revision_sha256": None}


def review_artifact(fixture, bundle, expected, decision):
    manifest = bundle["manifest"]
    assert digest(canonical(manifest)) == bundle["manifest_sha256"]
    images = []
    for row in manifest["images"]:
        for role in ("current", "previous", "diff"):
            if row[role] is not None:
                images.append({"role": role, "viewport_id": row["viewport_id"], **row[role]})
    review_id = str(uuid4())
    value = {
        "schema": "cairntir.paladin-ui-independent-review.v1",
        "review_id": review_id,
        "candidate_id": manifest["candidate_id"],
        "candidate_manifest_sha256": bundle["manifest_sha256"],
        "expected_revision": deepcopy(expected),
        "scope": deepcopy(manifest["scope"]),
        "decision": decision,
        "reviewed_images": images,
        "reviewer": "independent unit fixture",
        "method": "SYNTHETIC_UNIT_EVIDENCE: exact binding test, no real image review claim.",
        "reason": "Test exact authenticated baseline transition only.",
    }
    directory = fixture.root / "independent-reviews"
    directory.mkdir(exist_ok=True)
    path = directory / (review_id + ".json")
    path.write_bytes(canonical(value))
    reference = absolute_file(path)

    def approved(request):
        assert request["review_evidence"] == reference
        actual = read_json(path, 131072)
        assert absolute_file(path) == reference
        assert actual == value
        assert request["candidate"] == manifest
        assert request["candidate_manifest_sha256"] == bundle["manifest_sha256"]
        assert request["expected_revision"] == expected
        return decision == "APPROVE"

    return value, reference, approved


def approved_reference(review):
    outcome = review["review"]
    assert outcome["decision"] == "APPROVED"
    return {
        "head": deepcopy(outcome["after"]),
        "manifest": deepcopy(outcome["approval_manifest"]),
        "approval_id": outcome["review_id"],
        "approval": deepcopy(review["evidence"]),
    }
