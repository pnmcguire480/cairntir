"""Run the independently frozen public E22 cases in normal unfiltered pytest."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[2]
PACKET = SOURCE / "plans" / "acceptance" / "embedding-artifacts-1.14"


def _module(name, filename):
    spec = importlib.util.spec_from_file_location(name, PACKET / filename)
    assert spec is not None and spec.loader is not None
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def _load_frozen_cases():
    freeze = json.loads((PACKET / "FIXTURE-V3-FREEZE.json").read_text(encoding="utf-8"))
    for filename, expected in freeze["files_sha256"].items():
        actual = hashlib.sha256((PACKET / filename).read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(f"independent E22 acceptance custody changed: {filename}")
    base = _module("cairntir_e22_frozen_original", "test_embedding_artifacts.py")
    relative = _module("cairntir_e22_frozen_relative", "test_relative_cache_supplement_v2.py")
    original = sys.modules.get("test_embedding_artifacts")
    sys.modules["test_embedding_artifacts"] = base
    try:
        supplement = _module("cairntir_e22_frozen_supplement", "test_embedding_supplement_v3.py")
    finally:
        if original is None:
            sys.modules.pop("test_embedding_artifacts", None)
        else:
            sys.modules["test_embedding_artifacts"] = original
    base.SOURCE_ROOT = SOURCE
    relative.base.SOURCE_ROOT = SOURCE
    modules = {"original": base, "relative": relative, "supplement": supplement}
    cases = [
        ("original", name)
        for name in unittest.defaultTestLoader.getTestCaseNames(base.ArtifactAcceptance)
    ]
    cases.extend(
        ("relative", name)
        for name in (
            "test_relative_cache_remains_absolute_and_pinned_across_cwd_change",
            "test_changed_environment_does_not_create_unrelated_cache_after_pin",
        )
    )
    cases.extend(("supplement", name) for name in supplement.SUPPLEMENT_NAMES)
    assert len(cases) == 35
    return modules, cases


MODULES, CASES = _load_frozen_cases()


@pytest.mark.parametrize("group,name", CASES, ids=[f"{group}:{name}" for group, name in CASES])
def test_embedding_artifact_acceptance(group, name):
    sys.dont_write_bytecode = True
    classes = {
        "original": MODULES["original"].ArtifactAcceptance,
        "relative": MODULES["relative"].RelativeCacheAcceptance,
        "supplement": MODULES["supplement"].SupplementaryAcceptance,
    }
    case = classes[group](name)
    result = unittest.TestResult()
    case.run(result)
    assert result.testsRun == 1
    failures = [traceback for _, traceback in result.failures + result.errors]
    if failures:
        pytest.fail("\n".join(failures), pytrace=False)
    if result.skipped:
        pytest.skip("; ".join(reason for _, reason in result.skipped))
