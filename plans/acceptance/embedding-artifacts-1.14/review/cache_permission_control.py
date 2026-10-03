"""One layout-specific reproduction of the existing invalid-bootstrap finding."""
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

HERE = Path(__file__).resolve().parent

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    for manifest in ("REVIEW-FREEZE.json", "CACHE-PERMISSION-FREEZE.json"):
        freeze = json.loads((HERE / manifest).read_text(encoding="utf-8-sig"))
        for name, expected in freeze["files_sha256"].items():
            if hashlib.sha256((HERE / name).read_bytes()).hexdigest() != expected:
                raise SystemExit("frozen artifact changed: " + name)
    source = args.source_root.resolve()
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(source / "src"))
    from cairntir.memory import embeddings, artifacts
    runtime = {}
    for module in (embeddings, artifacts):
        path = Path(module.__file__).resolve()
        if path != (source / "src/cairntir/memory" / path.name).resolve():
            raise SystemExit("wrong source import")
        runtime[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    spec = importlib.util.spec_from_file_location("controls", HERE / "adversarial_controls.py")
    base = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(base)

    class CachePermissionControl(base.Controls):
        def test_offline_cache_stat_permission_error_is_typed(self):
            original_stat = Path.stat
            def denied(path, *args, **kwargs):
                if path == self.cache:
                    raise PermissionError("synthetic cache stat denial")
                return original_stat(path, *args, **kwargs)
            with patch.object(Path, "stat", denied):
                with self.assertRaises(base.EmbeddingError):
                    self.provider().artifact_manifest()
            self.assertEqual(self.calls, [])

    started = time.monotonic()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([
        CachePermissionControl("test_offline_cache_stat_permission_error_is_typed")]))
    report = {"cases": result.testsRun, "elapsed_seconds": time.monotonic() - started,
              "runtime_sha256": runtime, "observations": base.OBSERVATIONS,
              "failures": [{"name": str(t), "traceback": text} for t, text in result.failures],
              "errors": [{"name": str(t), "traceback": text} for t, text in result.errors]}
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if result.wasSuccessful() else 1

if __name__ == "__main__":
    raise SystemExit(main())
