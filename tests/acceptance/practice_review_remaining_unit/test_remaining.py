"""Run only the remaining original 53 R18 cases with their registered cleanups."""

import unittest

import pytest

from . import (
    cases_additional,
    cases_closure,
    cases_closure_additional,
    cases_completeness,
    cases_core,
    cases_sequences,
)


def _original_cases():
    cases = []
    for case_type in (
        cases_core.BaselineControls,
        cases_core.R18Probes,
        cases_additional.ApprovalIsolation,
        cases_additional.InterleavedAndAdditionalR18,
        cases_sequences.ReceiptSequences,
        cases_completeness.CompletenessBoundary,
        cases_closure_additional.ClosureAdditional,
    ):
        cases.extend(unittest.defaultTestLoader.loadTestsFromTestCase(case_type))
    cases.append(
        cases_closure.RecursiveClosure(
            "test_foreign_ancestor_cannot_hide_newer_transition_under_broad_requested_wing"
        )
    )
    if len(cases) != 53 or len({case.id() for case in cases}) != 53:
        raise AssertionError("Original remaining53 inventory changed")
    return cases


_CASES = _original_cases()


@pytest.mark.parametrize("case", _CASES, ids=[case.id() for case in _CASES])
def test_original_remaining_case(case: unittest.TestCase) -> None:
    try:
        case.debug()
    finally:
        if not case.doCleanups():
            raise RuntimeError("Original R18 registered cleanup failed")
