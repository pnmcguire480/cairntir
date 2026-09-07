from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


@pytest.fixture()
def judge():
    path = Path(__file__).resolve().parents[2] / "scripts" / "verify_history.py"
    spec = importlib.util.spec_from_file_location("verification_history_gate", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.behavior_proved


@pytest.mark.parametrize("witness", [None, "EXPECTED BEHAVIOR"])
@pytest.mark.parametrize(
    ("code", "cases"),
    [
        (0, ""),
        (0, "<testcase/><testcase/>"),
        (0, '<testcase><skipped message="optional"/></testcase>'),
        (1, "<testcase><error>AssertionError EXPECTED BEHAVIOR</error></testcase>"),
        (1, "<testcase><failure>ModuleNotFoundError EXPECTED BEHAVIOR</failure></testcase>"),
        (1, "<testcase><failure>AssertionError unrelated behavior</failure></testcase>"),
        (2, "<testcase><failure>AssertionError EXPECTED BEHAVIOR</failure></testcase>"),
    ],
)
def test_harness_errors_skips_and_unrelated_failures_are_not_behavioral_evidence(
    judge, tmp_path, witness, code, cases
):
    report = tmp_path / "pytest.xml"
    report.write_text(f"<testsuites><testsuite>{cases}</testsuite></testsuites>", encoding="utf-8")
    assert not judge(report, code, witness)


def test_only_passing_control_and_specific_assertion_are_accepted(judge, tmp_path):
    report = tmp_path / "pytest.xml"
    assert not judge(report, 0, None)
    report.write_text(
        "<testsuites><testsuite><testcase/></testsuite></testsuites>", encoding="utf-8"
    )
    assert judge(report, 0, None)
    assert not judge(report, 1, "EXPECTED BEHAVIOR")
    report.write_text(
        "<testsuites><testsuite><testcase><failure>AssertionError: EXPECTED BEHAVIOR"
        "</failure></testcase></testsuite></testsuites>",
        encoding="utf-8",
    )
    assert judge(report, 1, "EXPECTED BEHAVIOR")
    assert not judge(report, 0, None)
