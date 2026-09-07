from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tomllib
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


@pytest.mark.parametrize(("covered", "expected_exit"), [(2299, 1), (2300, 0)])
def test_coverage_gate_enforces_the_threshold_without_rounding_up(tmp_path, covered, expected_exit):
    root = Path(__file__).resolve().parents[2]
    configuration = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    options = configuration["tool"]["pytest"]["ini_options"]["addopts"]
    options = [value.replace("--cov=cairntir", "--cov=subject") for value in options]
    (tmp_path / "pytest.ini").write_text("[pytest]\naddopts = " + " ".join(options) + "\n")
    (tmp_path / ".coveragerc").write_text("[run]\nbranch = true\n")
    exercised = covered - 2
    unused = 2500 - covered
    (tmp_path / "subject.py").write_text(
        "def exercised():\n"
        + "    value = 1\n" * (exercised - 1)
        + "    return value\n"
        + "def unused():\n"
        + "    value = 2\n" * (unused - 1)
        + "    return value\n"
    )
    (tmp_path / "test_subject.py").write_text(
        "import subject\ndef test_subject():\n    assert subject.exercised() == 1\n"
    )
    environment = os.environ | {"COVERAGE_FILE": str(tmp_path / ".coverage")}
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-c", "pytest.ini", "--cov-config=.coveragerc", "-q"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert "1 passed" in result.stdout, result.stdout + result.stderr
    assert result.returncode == expected_exit, "GATE: coverage below 92 percent was accepted"
