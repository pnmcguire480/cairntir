"""Run every independent frozen R18 red-team assertion in normal pytest CI."""

from __future__ import annotations

import hashlib
import sys
import types
import unittest
import zipfile
from pathlib import Path
from typing import Any

import pytest

_ARCHIVE = (
    Path(__file__).resolve().parents[2]
    / "plans/acceptance/evidence-practice-review-r18/redteam-controls.zip"
)
_PINNED = {
    "probes.py": "44bd3db1f5969caaf745c38cd25308e6a900d9ec2ab5c46e833212bfb4c21992",
    "probes_v2.py": "5d6d9ea5592c121a0b51834e7726def2ce315f155bbf08a2634fc4b8f35d94ae",
    "additional_probes_v2.py": "78814df5f735be933663c5c4ed73a40ae3f85c9b7fc222333b77b67bc9ad111e",
    "visibility_probes_v2.py": "7d205c6dc95ed06fa2d5e357524e0f1c19741acd7f1c4bc2a5ac92acd586c3f9",
    "edge_probes.py": "18e57d167a4c4b68e5501691be2eda59b28bd42e94e87d5909cae47382fc75a1",
    "sequence_probes.py": "65107bbea59a1cd364149d639f67a198770b5e2be408ff4830daa2d8ee055d75",
}


def _frozen_cases() -> list[unittest.TestCase]:
    modules: dict[str, types.ModuleType] = {}
    prior: dict[str, Any] = {}
    cases: list[unittest.TestCase] = []
    missing = object()
    with zipfile.ZipFile(_ARCHIVE) as archive:
        if len(archive.namelist()) != len(set(archive.namelist())):
            raise AssertionError("duplicate zip members")
        try:
            for filename, digest in _PINNED.items():
                raw = archive.read(filename)
                if hashlib.sha256(raw).hexdigest() != digest:
                    raise AssertionError(f"frozen probe changed: {filename}")
                name = filename.removesuffix(".py")
                module = types.ModuleType(name)
                module.__file__ = f"{_ARCHIVE}!{filename}"
                prior[name] = sys.modules.get(name, missing)
                sys.modules[name] = module
                exec(compile(raw, module.__file__, "exec"), module.__dict__)  # noqa: S102
                modules[name] = module
            inventory = (
                ("probes_v2", "BaselineControls"),
                ("probes_v2", "R18Probes"),
                ("additional_probes_v2", "ApprovalIsolation"),
                ("additional_probes_v2", "InterleavedAndAdditionalR18"),
                ("visibility_probes_v2", "DependencyVisibility"),
                ("edge_probes", "SourceReviewEdges"),
                ("sequence_probes", "ReceiptSequences"),
            )
            for name, class_name in inventory:
                case_type = getattr(modules[name], class_name)
                cases.extend(unittest.defaultTestLoader.loadTestsFromTestCase(case_type))
        finally:
            for name, previous in prior.items():
                if previous is missing:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = previous
    if len(cases) != 36:
        raise AssertionError("complete independent inventory changed")
    return cases


_CASES = _frozen_cases()


@pytest.mark.parametrize("case", _CASES, ids=[case.id() for case in _CASES])
def test_frozen_redteam_case(case: unittest.TestCase) -> None:
    """TestCase.debug retains exact assertions, errors and registered cleanups."""
    case.debug()
