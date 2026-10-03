"""Run additive independent R18 completeness assertions without changing originals."""

from __future__ import annotations

import hashlib
import sys
import types
import unittest
import zipfile
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parents[2] / "plans/acceptance/evidence-practice-review-r18"
_PINNED = (
    (
        "redteam-controls.zip",
        "probes_v2.py",
        "5d6d9ea5592c121a0b51834e7726def2ce315f155bbf08a2634fc4b8f35d94ae",
    ),
    (
        "redteam-round2-controls.zip",
        "completeness_probes.py",
        "b36bf721679fbe4ebab8b25eec95abc851419b2617bd7aabab9caec23aee034a",
    ),
    (
        "redteam-round2-controls.zip",
        "closure_probes.py",
        "174a595e73bc77f8ac9492f97fec530e3707f32d65e3aa81ad02bc719e8aaf55",
    ),
    (
        "redteam-round2-controls.zip",
        "closure_additional.py",
        "79bda09fd54d738db65d8c4c0c8846fc7013737d7b4b8dcc3bccc5b7fccae679",
    ),
    (
        "redteam-round2-controls.zip",
        "grant_recheck_probes.py",
        "93e33479a84efba360df638759854621c400300817ab2ca03c136e54105c685f",
    ),
)


def _frozen_cases() -> list[unittest.TestCase]:
    modules: dict[str, types.ModuleType] = {}
    prior: dict[str, Any] = {}
    cases: list[unittest.TestCase] = []
    missing = object()
    try:
        for packet_name, filename, digest in _PINNED:
            packet = _ROOT / packet_name
            with zipfile.ZipFile(packet) as archive:
                if len(archive.namelist()) != len(set(archive.namelist())):
                    raise AssertionError("duplicate archive member")
                raw = archive.read(filename)
            if hashlib.sha256(raw).hexdigest() != digest:
                raise AssertionError(f"frozen probe changed: {filename}")
            name = filename.removesuffix(".py")
            module = types.ModuleType(name)
            module.__file__ = f"{packet}!{filename}"
            prior[name] = sys.modules.get(name, missing)
            sys.modules[name] = module
            exec(compile(raw, module.__file__, "exec"), module.__dict__)  # noqa: S102
            modules[name] = module
        for module_name, class_name in (
            ("completeness_probes", "CompletenessBoundary"),
            ("closure_additional", "ClosureAdditional"),
            ("grant_recheck_probes", "GrantRecheck"),
        ):
            case_type = getattr(modules[module_name], class_name)
            cases.extend(unittest.defaultTestLoader.loadTestsFromTestCase(case_type))
        closure_type = modules["closure_probes"].RecursiveClosure
        cases.append(
            closure_type(
                "test_foreign_ancestor_cannot_hide_newer_transition_under_broad_requested_wing"
            )
        )
    finally:
        for name, previous in prior.items():
            if previous is missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
    if len(cases) != 25:
        raise AssertionError("complete additive25 inventory changed")
    return cases


_CASES = _frozen_cases()


@pytest.mark.parametrize("case", _CASES, ids=[case.id() for case in _CASES])
def test_frozen_round2_redteam_case(case: unittest.TestCase) -> None:
    """Preserve every original assertion, typed failure and registered cleanup."""
    case.debug()
