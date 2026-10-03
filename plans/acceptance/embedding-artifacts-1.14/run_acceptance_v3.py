"""Serial public synthetic runner, source-selectable and network-blocked by fixtures."""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import sys
import time
import tomllib
import unittest

PACKET = Path(__file__).resolve().parent
sys.path.insert(0, str(PACKET))
sys.dont_write_bytecode = True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    source = args.source_root.resolve()
    report = args.report.resolve()
    if not report.is_relative_to(PACKET):
        parser.error("report must be within the acceptance packet")
    freeze = json.loads((PACKET / "FIXTURE-V3-FREEZE.json").read_text(encoding="utf-8"))
    for name, expected in freeze["files_sha256"].items():
        actual = hashlib.sha256((PACKET / name).read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(f"frozen acceptance file changed: {name}")
    for path in PACKET.glob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    import test_embedding_artifacts as base
    import test_relative_cache_supplement_v2 as relative
    import test_embedding_supplement_v3 as supplement
    base.SOURCE_ROOT = source
    relative.base.SOURCE_ROOT = source
    project = tomllib.loads((source / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    baseline = json.loads((PACKET / "dependency-baseline.json").read_text(encoding="utf-8"))
    assert project["dependencies"] == baseline["dependencies"]
    assert project.get("optional-dependencies", {}) == baseline["optional-dependencies"]
    suite = unittest.TestSuite([
        unittest.defaultTestLoader.loadTestsFromTestCase(base.ArtifactAcceptance),
        unittest.TestSuite(relative.RelativeCacheAcceptance(name) for name in (
            "test_relative_cache_remains_absolute_and_pinned_across_cwd_change",
            "test_changed_environment_does_not_create_unrelated_cache_after_pin",
        )),
        unittest.TestSuite(supplement.SupplementaryAcceptance(name) for name in supplement.SUPPLEMENT_NAMES),
    ])
    metadata = {
        "source_root": str(source), "python": sys.version, "platform": platform.platform(),
        "cases_expected": suite.countTestCases(), "custody": "public synthetic shared workspace",
        "packages": {name: importlib.metadata.version(name) for name in ("fastembed", "onnxruntime", "tokenizers", "numpy")},
        "freeze_sha256": hashlib.sha256((PACKET / "FIXTURE-V3-FREEZE.json").read_bytes()).hexdigest(),
        "requested_author_model": "gpt-6.1-sol", "requested_author_effort": "high",
        "actual_serving_model": "not exposed", "actual_effort": "not exposed", "cost": "unavailable",
    }
    if args.self_check:
        metadata.update(status="self-check-pass", product_executed=False)
        report.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(metadata))
        return 0
    sys.path.insert(0, str(source / "src"))
    began = time.monotonic()
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    metadata.update(
        status="pass" if result.wasSuccessful() else "fail",
        product_executed=True, elapsed_seconds=time.monotonic() - began,
        tests_run=result.testsRun,
        failures=[{"case": test.id(), "traceback": traceback} for test, traceback in result.failures],
        errors=[{"case": test.id(), "traceback": traceback} for test, traceback in result.errors],
        skipped=[{"case": test.id(), "reason": reason} for test, reason in result.skipped],
    )
    report.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
