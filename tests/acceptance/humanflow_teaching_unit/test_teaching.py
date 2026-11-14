"""R12: a host-narrated teaching artifact meets the original closing criterion.

"The explanation links actual evidence and preserves uncertainty; style cannot
conceal failures or substitute for comprehension checks."

The preserved artifact in ``artifact/`` was written by a host model from a real
two-attempt managed Python run (see ``record.py``). These tests check the
preserved files and then publish the same narration on a fresh real run.
"""

from __future__ import annotations

import copy
import json
import re
import unittest
from collections.abc import Iterator
from typing import Any

import pytest

from cairntir._paladin_contract import canonical_sha
from cairntir.codeglass import retention_report
from cairntir.obsidian import project_to_obsidian
from cairntir.paladin_python import (
    HostNarrationAdapter,
    HumanFlowRun,
    PaladinPythonError,
)

from .teaching import ARTIFACT, prepare_fixture, rebind, run_two, selectors

_CITATION = re.compile(r"cairntir://drawer/(\d+)")


def _load(name: str) -> Any:
    return json.loads((ARTIFACT / name).read_text(encoding="utf-8"))


EXPORTED = _load("bundle.json")
WRITTEN = _load("narration.json")
PUBLICATION = _load("publication.json")
WALKTHROUGH = (ARTIFACT / "walkthrough.md").read_text(encoding="utf-8")
NOTE = (ARTIFACT / "obsidian-note.md").read_text(encoding="utf-8")


def _claim(response: dict[str, Any], claim_id: str) -> dict[str, Any]:
    return next(row for row in response["claims"] if row["id"] == claim_id)


def _walkthroughs(store: Any) -> int:
    row = store._conn.execute(
        "SELECT COUNT(*) FROM drawers WHERE content LIKE '# CodeGlass — HumanFlow %'"
    ).fetchone()
    return int(row[0])


def test_preserved_narration_is_bound_to_its_bundle_and_passes_the_unchanged_validator() -> None:
    bundle = EXPORTED["bundle"]
    assert canonical_sha(bundle) == EXPORTED["bundle_sha256"] == WRITTEN["bundle_sha256"]
    assert PUBLICATION["bundle_sha256"] == EXPORTED["bundle_sha256"]
    assert PUBLICATION["response_sha256"] == canonical_sha(WRITTEN["response"])
    assert PUBLICATION["adapter"] == {
        "kind": "host",
        "model_id": WRITTEN["model_id"],
        "prompt_version": "cairntir-humanflow-host-v1",
    }
    assert PUBLICATION["status"] == "PUBLISHED"
    HumanFlowRun._validate(WRITTEN["response"], bundle, 12000)


def test_preserved_walkthrough_keeps_failures_uncertainty_and_the_real_trace() -> None:
    sections = WALKTHROUGH.split("## HOW", 1)
    ledger, prose = sections[0], sections[1]
    for row in (
        "| r12_flow.FlowChecks / test_negative | failure |",
        "| r12_flow.FlowChecks / test_label | error |",
        "#### integration: FAIL",
        "#### integration: INCONCLUSIVE",
        "Errors prevented: UNKNOWN",
    ):
        assert row in ledger
    assert ledger.count("| r12_flow.FlowChecks / test_missing | MISSING |") == 2
    assert ledger.count(": PENDING") >= 8
    for fact in ("-2 * 2 = -4", "NameError", 'str(4) = "4"', "abs(value)"):
        assert fact in prose
    assert "INCONCLUSIVE rather than passing" in prose
    assert "Inferred, not recorded" in prose
    assert "opaque IDs, not dates" in prose
    why = _claim(WRITTEN["response"], "why")
    assert (why["epistemic"], why["kind"]) == ("inferred", "interpretation")
    assert _claim(WRITTEN["response"], "untested")["epistemic"] == "unknown"
    assert not any(row["kind"] == "decision" for row in WRITTEN["response"]["claims"])
    assert "[claim:" not in WALKTHROUGH
    generated = NOTE.split("<!-- cairntir:generated:begin -->", 1)[1]
    assert "test_negative" in generated and "-2 * 2 = -4" in generated
    assert PUBLICATION["retention"] == {
        "immediate_score": None,
        "delayed_score": None,
        "retention_delta": None,
    }


@pytest.fixture(scope="module")
def fresh() -> Iterator[tuple[Any, Any, dict[str, Any], dict[str, Any]]]:
    case = unittest.TestCase()
    try:
        fixture = prepare_fixture(case)
        run = run_two(fixture)
        reader = HumanFlowRun(
            run, adapter=HostNarrationAdapter({}, model_id="reader", bundle_sha256="0" * 64)
        )
        exported = reader.prepare(**selectors(fixture))
        response = rebind(WRITTEN["response"], EXPORTED["bundle"], exported["bundle"])
        yield fixture, run, exported, response
    finally:
        case.doCleanups()


def test_host_adapter_refuses_narration_written_for_other_evidence(fresh: Any) -> None:
    fixture, run, exported, response = fresh
    assert exported["bundle_sha256"] != EXPORTED["bundle_sha256"]
    before = _walkthroughs(fixture.store)
    stale = HostNarrationAdapter(
        response, model_id=WRITTEN["model_id"], bundle_sha256=EXPORTED["bundle_sha256"]
    )
    with pytest.raises(PaladinPythonError, match="written for different evidence"):
        HumanFlowRun(run, adapter=stale).draft(reader_level="intermediate", **selectors(fixture))
    with pytest.raises(PaladinPythonError):
        HostNarrationAdapter(response, model_id=" ", bundle_sha256=exported["bundle_sha256"])
    assert _walkthroughs(fixture.store) == before


def test_style_cannot_relabel_the_earlier_failure_as_passed(fresh: Any) -> None:
    fixture, run, exported, response = fresh
    before = _walkthroughs(fixture.store)
    for claim_id in ("a1-neg", "a1-label", "a2-missing"):
        lie = copy.deepcopy(response)
        _claim(lie, claim_id)["outcome"] = "passed"
        adapter = HostNarrationAdapter(
            lie, model_id=WRITTEN["model_id"], bundle_sha256=exported["bundle_sha256"]
        )
        with pytest.raises(PaladinPythonError, match="changed an observed check outcome"):
            HumanFlowRun(run, adapter=adapter).draft(
                reader_level="intermediate", **selectors(fixture)
            )
    assert _walkthroughs(fixture.store) == before


def test_fresh_run_publishes_the_narration_with_resolving_evidence_and_no_learning_claim(
    fresh: Any,
) -> None:
    fixture, run, exported, response = fresh
    adapter = HostNarrationAdapter(
        response, model_id=WRITTEN["model_id"], bundle_sha256=exported["bundle_sha256"]
    )
    narrator = HumanFlowRun(run, adapter=adapter)
    draft = narrator.draft(reader_level="intermediate", **selectors(fixture))
    assert draft["adapter"]["kind"] == "host"
    assert draft["sections"] == WRITTEN["response"]["sections"]
    published = narrator.publish(draft)
    assert published["status"] == "PUBLISHED"
    walkthrough = fixture.store.get(published["walkthrough_id"])
    content = walkthrough.content
    cited = {int(key) for key in _CITATION.findall(content)}
    assert cited
    for key in cited:
        drawer = fixture.store.get(key)
        assert drawer is not None and drawer.wing == "paladin"
    anchors = {row["id"]: row for row in exported["bundle"]["anchors"]}
    for claim in response["claims"]:
        assert anchors[claim["subject_ref"]]["kind"] in {
            "source_span",
            "artifact",
            "case",
            "stage_result",
        }

    def prose(text: str) -> str:
        return _CITATION.sub("cairntir://drawer/N", text.split("## HOW", 1)[1])

    assert prose(content) == prose(WALKTHROUGH)
    assert "| r12_flow.FlowChecks / test_negative | failure |" in content
    assert content.count("| r12_flow.FlowChecks / test_missing | MISSING |") == 2
    report = retention_report(fixture.store, walkthrough_id=published["walkthrough_id"])
    assert report.immediate_score is None and report.delayed_score is None
    assert report.retention_delta is None
    vault = fixture.root / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    projected = project_to_obsidian(fixture.store, vault=vault, wing="paladin")
    note = next(
        path for path in projected.codeglass_notes if path.name.startswith(f"{walkthrough.id}-")
    )
    assert "test_negative" in note.read_text(encoding="utf-8")
