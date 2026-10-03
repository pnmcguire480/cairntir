"""Portable runner for the unchanged, frozen eight E22 review controls."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    source = args.source_root.resolve()
    original = json.loads((here / "REVIEW-FREEZE.json").read_text(encoding="utf-8-sig"))
    adapter = json.loads((here / "PORTABLE-FREEZE.json").read_text(encoding="utf-8-sig"))
    for name, expected in {**original["files_sha256"], **adapter["files_sha256"]}.items():
        if sha(here / name) != expected:
            raise SystemExit("frozen review artifact differs: " + name)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(source / "src"))
    # Preload the requested package before the preserved historical module adds
    # its original absolute path. Verify actual imports belong to this checkout.
    from cairntir.memory import artifacts, embeddings, store
    runtime = {}
    for module in (artifacts, embeddings, store):
        actual = Path(module.__file__).resolve()
        expected = source / "src/cairntir/memory" / actual.name
        if actual != expected.resolve():
            raise SystemExit("wrong runtime import: " + str(actual))
        runtime[actual.name] = sha(actual)
    spec = importlib.util.spec_from_file_location("frozen_review_controls", here / "adversarial_controls.py")
    controls = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(controls)
    controls.SOURCE = source
    started = time.monotonic()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(controls.Controls))
    observations = controls.OBSERVATIONS.copy()
    with patch.object(artifacts.PinnedArtifacts, "verify", lambda self: None):
        wrong = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([
            controls.Controls("test_08_pinned_mutation_refused_before_constructor")]))
    detected = len(wrong.failures) == 1 and not wrong.errors
    report = {"elapsed_seconds": time.monotonic() - started, "cases": result.testsRun,
              "source_root": str(source), "runtime_sha256": runtime,
              "failures": [{"name": str(t), "traceback": text} for t, text in result.failures],
              "errors": [{"name": str(t), "traceback": text} for t, text in result.errors],
              "observations": observations,
              "wrong_control": {"disable_preload_verification_detected": detected,
                  "failures": [{"name": str(t), "traceback": text} for t, text in wrong.failures]}}
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if result.wasSuccessful() and detected else 1


if __name__ == "__main__":
    raise SystemExit(main())
