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
    for manifest in ("REVIEW-FREEZE.json", "HUB-LAYOUT-FREEZE.json"):
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

    class HubControl(base.Controls):
        def test_hub_selected_missing_model_with_invalid_tokenizer(self):
            snapshot = self.cache / "models--synthetic--review" / "snapshots" / ("a" * 40)
            snapshot.parent.mkdir(parents=True)
            self.model.rename(snapshot)
            self.model = snapshot
            reference = snapshot.parent.parent / "refs" / "main"
            reference.parent.mkdir()
            reference.write_text(snapshot.name)
            def cached(repo_id, filename, cache_dir=None, **kwargs):
                repository = Path(cache_dir) / "models--synthetic--review"
                selected = repository / "snapshots" / (repository / "refs" / "main").read_text() / filename
                return str(selected) if selected.is_file() else None
            with patch.object(sys.modules["huggingface_hub"], "try_to_load_from_cache", cached):
                self.assertEqual(self.provider().embed(["valid Hub control"]), [[1.0, 0.0]])
                self.assertEqual(self.calls[-1]["specific_model_path"], str(snapshot.resolve()))
                self.assertIs(self.calls[-1]["local_files_only"], True)
                self.calls.clear()
                (snapshot / "model.onnx").unlink()
                (snapshot / "tokenizer.json").unlink()
                (snapshot / "tokenizer.json").mkdir()
                self.refuse_without_acquisition()

    started = time.monotonic()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([
        HubControl("test_hub_selected_missing_model_with_invalid_tokenizer")]))
    report = {"cases": result.testsRun, "elapsed_seconds": time.monotonic() - started,
              "runtime_sha256": runtime, "observations": base.OBSERVATIONS,
              "failures": [{"name": str(t), "traceback": text} for t, text in result.failures],
              "errors": [{"name": str(t), "traceback": text} for t, text in result.errors]}
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if result.wasSuccessful() else 1

if __name__ == "__main__":
    raise SystemExit(main())
