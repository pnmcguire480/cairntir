"""Independent R12 behavioral acceptance on real managed Python execution."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import unittest
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

import cairntir.paladin_python as paladin_module
from cairntir.codeglass import retention_report
from cairntir.memory.taxonomy import Drawer
from cairntir.obsidian import project_to_obsidian
from cairntir.paladin_python import PaladinPythonError, PaladinPythonRun
from cairntir.provenance import Sensitivity

REPO = Path(__file__).resolve().parents[3]
PACKET = Path(__file__).resolve().parent

if Path(paladin_module.__file__).resolve() != (REPO / "src/cairntir/paladin_python.py").resolve():
    raise RuntimeError("R12 product import did not resolve to the selected repository")

for relative, expected in (
    (
        "tests/acceptance/paladin_python_unit/fixtures.py",
        "f8f03f6651ceb9b9864f2bfb385fe4d56b7a912b508b948c7f02daf2bdfb95fa",
    ),
    (
        "tests/acceptance/paladin_python_unit/controlled_stage.py",
        "5fa32da4fffb954265600d70fdf11436f4381b0a77389c3eb9a9f6f4ebfd1d1a",
    ),
):
    if hashlib.sha256((REPO / relative).read_bytes()).hexdigest() != expected:
        raise RuntimeError(f"R12 borrowed fixture changed: {relative}")

from paladin_python_unit import fixtures  # noqa: E402


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def prepared():
    cases = []

    def make():
        case = unittest.TestCase()
        cases.append(case)
        fixture = fixtures.PreparedFixture(case, modes=("flow", "flow", "flow"))
        for index, snapshot in enumerate(fixture.snapshots):
            shutil.copyfile(
                PACKET / "fixture/run_stage.py", snapshot / "acceptance/controlled_stage.py"
            )
            shutil.copyfile(
                PACKET / ("fixture/flow-bug.py" if index == 0 else "fixture/flow-repair.py"),
                snapshot / "src/flow.py",
            )
        child = next(
            row for row in fixture.plan["inputs"] if row["path"] == "acceptance/controlled_stage.py"
        )
        child["sha256"] = _sha((PACKET / "fixture/run_stage.py").read_bytes())
        fixture.implementation_paths.append("src/flow.py")
        fixture.plan["implementation_paths"] = list(fixture.implementation_paths)
        stage = next(row for row in fixture.plan["stages"] if row["stage_id"] == "integration")
        stage["required_test_ids"] = [
            ["r12_flow.FlowChecks", name]
            for name in ("test_positive", "test_negative", "test_label", "test_missing")
        ]
        stage["artifacts"].append(
            {"path": "integration/trace.json", "format": "file", "required_members": []}
        )
        return fixture

    yield make
    for case in reversed(cases):
        case.doCleanups()


def _two(fixture):
    first = PaladinPythonRun(fixture.runtime, contract=fixture.contract(0))
    old = first.execute("integration", fixture.action("integration", 0))
    second = PaladinPythonRun(fixture.runtime, contract=fixture.contract(1))
    new = second.execute("integration", fixture.action("integration", 1))
    return first, second, old, new


def _flow(run, adapter):
    import cairntir.paladin_python as api

    assert hasattr(api, "HumanFlowRun"), "R12 connected narration API is absent"
    return api.HumanFlowRun(run, adapter=adapter)


def _selectors(fixture):
    return {
        "source_spans": tuple(
            {
                "attempt_id": fixture.attempt_ids[index],
                "path": "src/flow.py",
                "start_line": 1,
                "end_line": 9,
            }
            for index in (0, 1)
        ),
        "artifact_paths": tuple(
            {
                "attempt_id": fixture.attempt_ids[index],
                "stage_id": "integration",
                "path": "integration/trace.json",
            }
            for index in (0, 1)
        ),
    }


def _stage(checks, index):
    attempt = next(row for row in checks["attempts"] if row["index"] == index)
    return next(row for row in attempt["stages"] if row["stage_id"] == "integration")


def _case(stage, name):
    return next(row for row in stage["cases"] if row["name"] == name)


class FixtureAdapter:
    identity = {  # noqa: RUF012
        "kind": "fixture",
        "model_id": "frozen-flow",
        "prompt_version": "r12-fixture-v1",
    }

    def __init__(self, *, mode="valid", foreign_id=None):
        self.mode = mode
        self.foreign_id = foreign_id
        self.calls = 0

    def generate(self, bundle, *, reader_level, max_output_chars):
        self.calls += 1
        anchors = bundle["anchors"]

        def anchor(kind, index, name=None):
            rows = [
                row
                for row in anchors
                if row["kind"] == kind
                and row["attempt_id"] == bundle["checks"]["attempts"][index]["attempt_id"]
                and (name is None or row.get("name") == name)
            ]
            assert len(rows) == 1, (kind, index, name, rows)
            return rows[0]

        source = anchor("source_span", 1)
        trace = anchor("artifact", 1)
        old_fail = anchor("case", 0, "test_negative")
        old_error = anchor("case", 0, "test_label")
        new_pass = anchor("case", 1, "test_negative")
        missing = anchor("case", 1, "test_missing")
        assert (
            old_fail["outcome"],
            old_error["outcome"],
            new_pass["outcome"],
            missing["outcome"],
        ) == ("failure", "error", "passed", "MISSING")
        claims = [
            {
                "id": "trace",
                "epistemic": "observed",
                "kind": "artifact",
                "subject_ref": trace["id"],
                "support_refs": [trace["id"]],
                "text": "The second attempt recorded input -2 and output 4.",
            },
            {
                "id": "source",
                "epistemic": "observed",
                "kind": "source",
                "subject_ref": source["id"],
                "support_refs": [source["id"]],
                "text": "normalize uses abs and compute doubles its result.",
            },
            {
                "id": "old-fail",
                "epistemic": "observed",
                "kind": "case",
                "subject_ref": old_fail["id"],
                "support_refs": [old_fail["id"]],
                "outcome": "failure",
                "text": "The earlier negative check failed.",
            },
            {
                "id": "old-error",
                "epistemic": "observed",
                "kind": "case",
                "subject_ref": old_error["id"],
                "support_refs": [old_error["id"]],
                "outcome": "error",
                "text": "The earlier label check errored.",
            },
            {
                "id": "new-pass",
                "epistemic": "observed",
                "kind": "case",
                "subject_ref": new_pass["id"],
                "support_refs": [new_pass["id"]],
                "outcome": "passed",
                "text": "The repaired negative check passed.",
            },
            {
                "id": "missing",
                "epistemic": "observed",
                "kind": "case",
                "subject_ref": missing["id"],
                "support_refs": [missing["id"]],
                "outcome": "MISSING",
                "text": "A required check is still missing.",
            },
            {
                "id": "reason",
                "epistemic": "inferred",
                "kind": "interpretation",
                "subject_ref": source["id"],
                "support_refs": [source["id"], trace["id"]],
                "text": "The absolute-value step likely aims to handle negative input.",
            },
        ]
        response = {
            "sections": {
                "what": "Input -2 produced output 4 in the repaired attempt [claim:trace].",
                "how": (
                    "Beginner: abs turns -2 into 2; compute doubles it [claim:source]."
                    if reader_level == "beginner"
                    else "Intermediate: normalize applies abs before compute multiplies [claim:source]."  # noqa: E501
                ),
                "where": "The flow is in src/flow.py [claim:source].",
                "when": (
                    "The old check failed [claim:old-fail] and errored [claim:old-error]; "
                    "the repaired check passed [claim:new-pass], but one required check "
                    "remains missing [claim:missing]."
                ),
                "why": "Inferred purpose, not a recorded decision [claim:reason].",
            },
            "glossary": "normalize: turn a signed input into a nonnegative value [claim:source].",
            "danger_zones": "A passing repaired case does not cover the missing required check [claim:missing].",  # noqa: E501
            "claims": claims,
        }
        if self.mode == "exception":
            raise RuntimeError("configured adapter unavailable")
        if self.mode == "case-lie":
            claims[2]["outcome"] = "passed"
        if self.mode == "false-decision":
            claims[6]["epistemic"] = "observed"
            claims[6]["kind"] = "decision"
        if self.mode == "unrelated-source":
            claims[1]["support_refs"] = [anchor("source_span", 0)["id"]]
        if self.mode == "scope-instruction":
            response["tool_calls"] = [{"name": "publish", "wing": "other-wing"}]
        if self.mode == "foreign-ref":
            claims[1]["support_refs"] = [f"drawer:{self.foreign_id}"]
        if self.mode == "false-impact":
            claims[6]["epistemic"] = "observed"
            claims[6]["outcome"] = "prevented_errors"
        if self.mode == "unanchored-glossary":
            response["glossary"] = "normalize changes signed values."
        if self.mode == "unanchored-danger":
            response["danger_zones"] = "A passing case does not cover all risks."
        if self.mode == "omit-when":
            response["sections"]["when"] = "unknown"
        return response


def test_connected_real_flow_and_read_only_draft(prepared):
    fixture = prepared()
    _, second, old, new = _two(fixture)  # noqa: RUF059
    checks = second.check_report()
    assert old["managed_result"]["exit_code"] == 1
    assert _case(_stage(checks, 0), "test_negative")["outcome"] == "failure"
    assert _case(_stage(checks, 0), "test_label")["outcome"] == "error"
    assert _case(_stage(checks, 1), "test_negative")["outcome"] == "passed"
    assert _case(_stage(checks, 1), "test_missing")["outcome"] == "MISSING"
    assert checks["attempts"][0]["source_inputs"] != checks["attempts"][1]["source_inputs"]
    assert json.loads((fixture.outputs[0] / "integration/trace.json").read_text())["compute"] == -4
    assert json.loads((fixture.outputs[1] / "integration/trace.json").read_text())["compute"] == 4
    before = fixture.state()
    effects = (fixture.effects(0), fixture.effects(1))
    adapter = FixtureAdapter()
    draft = _flow(second, adapter).draft(reader_level="beginner", **_selectors(fixture))
    assert draft["schema"] == "cairntir.humanflow-draft.v1" and draft["status"] == "DRAFT"
    assert draft["bundle"]["checks"] == checks
    assert all(row["sha256"] for row in draft["bundle"]["source_spans"])
    assert "abs" in draft["sections"]["how"] and "-2" in draft["sections"]["what"]
    assert adapter.calls == 1 and fixture.state() == before
    assert (fixture.effects(0), fixture.effects(1)) == effects


@pytest.mark.parametrize(
    "bad",
    [
        "case-lie",
        "false-decision",
        "unrelated-source",
        "scope-instruction",
        "false-impact",
        "unanchored-glossary",
        "unanchored-danger",
        "exception",
    ],
)
def test_malformed_model_output_fails_before_publication(prepared, bad):
    fixture = prepared()
    _, second, _, _ = _two(fixture)
    adapter = FixtureAdapter(mode=bad)
    before = fixture.state()
    with pytest.raises(PaladinPythonError):
        _flow(second, adapter).draft(reader_level="beginner", **_selectors(fixture))
    assert adapter.calls == 1 and fixture.state() == before
    assert fixture.effects(0) == fixture.effects(1) == b"integration\n"


@pytest.mark.parametrize("tamper", ["source", "artifact", "missing_artifact"])
def test_preflight_rejects_unbound_paths_before_model_and_stale_bytes_before_publish(
    prepared, tamper
):
    fixture = prepared()
    _, second, _, _ = _two(fixture)
    adapter = FixtureAdapter()
    narrator = _flow(second, adapter)
    selectors = _selectors(fixture)
    for path in ("../outside.py", "src/subject.json/../flow.py", "C:/outside.py"):
        bad = dict(selectors)
        bad["source_spans"] = (
            {"attempt_id": fixture.attempt_ids[1], "path": path, "start_line": 1, "end_line": 1},
        )
        with pytest.raises(PaladinPythonError):
            narrator.draft(reader_level="beginner", **bad)
    assert adapter.calls == 0
    draft = narrator.draft(reader_level="beginner", **selectors)
    before = fixture.state()
    if tamper == "source":
        (fixture.snapshots[1] / "src/flow.py").write_text("tampered", encoding="utf-8")
    elif tamper == "artifact":
        (fixture.outputs[1] / "integration/trace.json").write_text("tampered", encoding="utf-8")
    else:
        (fixture.outputs[1] / "integration/trace.json").unlink()
    with pytest.raises(PaladinPythonError):
        narrator.publish(draft)
    assert fixture.state() == before and adapter.calls == 1


def test_forged_or_modified_draft_is_not_attributed_to_model(prepared):
    fixture = prepared()
    _, second, _, _ = _two(fixture)
    adapter = FixtureAdapter()
    narrator = _flow(second, adapter)
    draft = narrator.draft(reader_level="beginner", **_selectors(fixture))
    clone = copy.deepcopy(draft)
    clone["adapter"]["model_id"] = "forged-model"
    clone["response_sha256"] = _sha(json.dumps(clone, sort_keys=True).encode())
    before = fixture.state()
    with pytest.raises(PaladinPythonError):
        narrator.publish(clone)
    assert fixture.state() == before
    same_bytes_copy = copy.deepcopy(draft)
    with pytest.raises(PaladinPythonError):
        narrator.publish(same_bytes_copy)
    assert adapter.calls == 1 and fixture.state() == before


def test_explicit_publication_retry_projection_and_redaction(prepared):
    fixture = prepared()
    _, second, old, _ = _two(fixture)
    adapter = FixtureAdapter()
    narrator = _flow(second, adapter)
    draft = narrator.draft(reader_level="intermediate", **_selectors(fixture))
    effects = (fixture.effects(0), fixture.effects(1))
    first = narrator.publish(draft)
    again = narrator.publish(draft)
    assert first["status"] == again["status"] == "PUBLISHED"
    assert first["walkthrough_id"] == again["walkthrough_id"] and again["replayed"]
    assert adapter.calls == 1 and (fixture.effects(0), fixture.effects(1)) == effects
    walkthrough = fixture.store.get(first["walkthrough_id"])
    assert walkthrough.metadata["humanflow_schema"] == "cairntir.humanflow-walkthrough.v1"
    assert old["evidence"][-1]["drawer_id"] in walkthrough.metadata["evidence_drawer_ids"]
    for value in (
        "test_negative",
        "failure",
        "test_label",
        "error",
        "MISSING",
        "Errors prevented: UNKNOWN",
        "Inferred purpose",
    ):
        assert value in walkthrough.content
    vault = fixture.root / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    projected = project_to_obsidian(fixture.store, vault=vault, wing="paladin")
    note = next(
        path for path in projected.codeglass_notes if path.name.startswith(f"{walkthrough.id}-")
    )
    original = note.read_bytes()
    human = b"Human note: keep exactly these bytes.\r\n"
    note.write_bytes(original + human)
    project_to_obsidian(fixture.store, vault=vault, wing="paladin")
    assert note.read_bytes().endswith(human)
    old_source = old["evidence"][-1]["drawer_id"]
    provenance = fixture.store.get_provenance(old_source)
    with fixture.store.transaction():
        fixture.store._conn.execute(
            "UPDATE drawers SET provenance = ? WHERE id = ?",
            (replace(provenance, sensitivity=Sensitivity.SECRET).to_json(), old_source),
        )
    project_to_obsidian(fixture.store, vault=vault, wing="paladin")
    redacted = note.read_bytes()
    generated = redacted.split(b"<!-- cairntir:generated:begin -->", 1)[1].split(
        b"<!-- cairntir:generated:end -->", 1
    )[0]
    assert b"unavailable" in generated.lower()
    assert b"test_negative" not in generated and b"input -2" not in generated
    assert redacted.endswith(human)
    assert (fixture.effects(0), fixture.effects(1)) == effects


def test_reader_level_changes_prose_not_checks_and_no_fabricated_learning(prepared):
    fixture = prepared()
    _, second, _, _ = _two(fixture)
    first = FixtureAdapter()
    beginner = _flow(second, first).draft(reader_level="beginner", **_selectors(fixture))
    second_adapter = FixtureAdapter()
    intermediate = _flow(second, second_adapter).draft(
        reader_level="intermediate", **_selectors(fixture)
    )
    assert beginner["sections"]["how"] != intermediate["sections"]["how"]
    assert beginner["bundle"]["checks"] == intermediate["bundle"]["checks"]
    narrator = _flow(second, FixtureAdapter())
    draft = narrator.draft(reader_level="beginner", **_selectors(fixture))
    published = narrator.publish(draft)
    report = retention_report(fixture.store, walkthrough_id=published["walkthrough_id"])
    assert report.immediate_score is None and report.delayed_score is None
    assert report.retention_delta is None
    assert fixture.effects(0) == fixture.effects(1) == b"integration\n"


@pytest.mark.parametrize("visibility", ["secret", "expired"])
def test_hidden_or_expired_evidence_refuses_before_adapter(prepared, visibility):
    fixture = prepared()
    _, second, _, new = _two(fixture)
    source_id = new["evidence"][-1]["drawer_id"]
    provenance = fixture.store.get_provenance(source_id)
    changed = (
        replace(provenance, sensitivity=Sensitivity.SECRET)
        if visibility == "secret"
        else replace(provenance, valid_until=datetime(2000, 1, 1, tzinfo=UTC))
    )
    with fixture.store.transaction():
        fixture.store._conn.execute(
            "UPDATE drawers SET provenance = ? WHERE id = ?",
            (changed.to_json(), source_id),
        )
    before = fixture.state()
    adapter = FixtureAdapter()
    with pytest.raises(PaladinPythonError):
        _flow(second, adapter).draft(reader_level="beginner", **_selectors(fixture))
    assert adapter.calls == 0 and fixture.state() == before


def test_foreign_drawer_and_omitted_model_section_do_not_hide_canonical_checks(prepared):
    fixture = prepared()
    _, second, _, _ = _two(fixture)
    foreign = fixture.store.add(Drawer(wing="other-wing", room="claims", content="unrelated"))
    bad = FixtureAdapter(mode="foreign-ref", foreign_id=foreign.id)
    with pytest.raises(PaladinPythonError):
        _flow(second, bad).draft(reader_level="beginner", **_selectors(fixture))
    sparse = FixtureAdapter(mode="omit-when")
    narrator = _flow(second, sparse)
    draft = narrator.draft(reader_level="beginner", **_selectors(fixture))
    published = narrator.publish(draft)
    content = fixture.store.get(published["walkthrough_id"]).content
    for token in (
        "failure",
        "error",
        "MISSING",
        "test_negative",
        "test_label",
        "Required minimum",
        "Errors prevented: UNKNOWN",
    ):
        assert token in content
    assert fixture.effects(0) == fixture.effects(1) == b"integration\n"


def test_transient_publication_failure_retry_and_hidden_first_projection(prepared, monkeypatch):
    fixture = prepared()
    _, second, old, _ = _two(fixture)
    adapter = FixtureAdapter()
    narrator = _flow(second, adapter)
    draft = narrator.draft(reader_level="beginner", **_selectors(fixture))
    original_add = fixture.store.add
    failures = 0

    def fail_once(drawer):
        nonlocal failures
        if drawer.metadata.get("kind") == "codeglass.walkthrough" and failures == 0:
            failures += 1
            raise OSError("simulated publication interruption")
        return original_add(drawer)

    monkeypatch.setattr(fixture.store, "add", fail_once)
    pending = narrator.publish(draft)
    assert pending["status"] == "PENDING" and pending["walkthrough_id"] is None
    monkeypatch.setattr(fixture.store, "add", original_add)
    published = narrator.publish(draft)
    assert published["status"] == "PUBLISHED" and failures == 1
    assert narrator.publish(draft)["walkthrough_id"] == published["walkthrough_id"]
    assert adapter.calls == 1
    source_id = old["evidence"][-1]["drawer_id"]
    provenance = fixture.store.get_provenance(source_id)
    with fixture.store.transaction():
        fixture.store._conn.execute(
            "UPDATE drawers SET provenance = ? WHERE id = ?",
            (replace(provenance, sensitivity=Sensitivity.SECRET).to_json(), source_id),
        )
    vault = fixture.root / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    projected = project_to_obsidian(fixture.store, vault=vault, wing="paladin")
    note = next(
        path
        for path in projected.codeglass_notes
        if path.name.startswith(f"{published['walkthrough_id']}-")
    )
    body = note.read_text(encoding="utf-8")
    generated = body.split("<!-- cairntir:generated:begin -->", 1)[1].split(
        "<!-- cairntir:generated:end -->", 1
    )[0]
    assert "unavailable" in generated.lower()
    assert "test_negative" not in generated and "Input -2" not in generated
    assert fixture.effects(0) == fixture.effects(1) == b"integration\n"


def test_local_adapter_does_not_accept_cloud_or_implicit_model():
    import cairntir.paladin_python as api

    assert hasattr(api, "OllamaNarrationAdapter")
    for endpoint, model in (("https://cloud.example", "qwen"), ("http://127.0.0.1:11434", "")):
        with pytest.raises((PaladinPythonError, ValueError)):
            api.OllamaNarrationAdapter(endpoint=endpoint, model=model)
