"""Independent finite E22 review controls. No real models, stores, or network."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
SOURCE = Path(r"C:\Users\pnmcg\AppData\Local\Temp\cairntir-embedding-work-20261003")
sys.dont_write_bytecode = True
sys.path.insert(0, str(SOURCE / "src"))
from cairntir.memory import embeddings
from cairntir.memory import artifacts
from cairntir.errors import EmbeddingError

MODEL = "synthetic/review-model"
FILES = {"model.onnx": b"onnxAAAA", "config.json": b"{}", "tokenizer.json": b"{}",
         "tokenizer_config.json": b"{}", "special_tokens_map.json": b"{}"}
OBSERVATIONS = {}

class Controls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="synthetic-", dir=HERE)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cache = self.root / "cache"
        self.model = self.cache / "review-model"
        self.calls = []
        self.allow_acquire = False
        self.populate()
        fixture = self
        class FakeTextEmbedding:
            @classmethod
            def list_supported_models(cls):
                return [{"model": MODEL, "dim": 2, "model_file": "model.onnx",
                         "additional_files": [], "sources": {"hf": "synthetic/review"}}]
            def __init__(self, **kwargs):
                fixture.calls.append(kwargs)
                self.pinned = kwargs.get("specific_model_path")
                if not self.pinned:
                    if not fixture.allow_acquire:
                        raise RuntimeError("review blocker: unpinned acquisition attempted")
                    fixture.populate()
            def embed(self, texts):
                if not self.pinned:
                    raise AssertionError("acquisition object supplied vectors")
                return [[1.0, 0.0] for text in texts]
        fake = types.ModuleType("fastembed")
        fake.TextEmbedding = FakeTextEmbedding
        hub = types.ModuleType("huggingface_hub")
        hub.try_to_load_from_cache = lambda *args, **kwargs: None
        def blocked(*args, **kwargs):
            raise AssertionError("network forbidden")
        for p in [patch.dict(sys.modules, {"fastembed": fake, "huggingface_hub": hub}),
                  patch.dict(os.environ, {"FASTEMBED_CACHE_PATH": str(self.cache),
                     "CAIRNTIR_HOME": str(self.root / "home"), "HF_HUB_OFFLINE": "1",
                     "HOME": str(self.root / "user"), "USERPROFILE": str(self.root / "user")}),
                  patch.object(embeddings, "_embed_trace", lambda *args: None),
                  patch.object(importlib.metadata, "version", lambda name: "1.2.3"),
                  patch.object(socket.socket, "connect", blocked),
                  patch.object(socket.socket, "connect_ex", blocked),
                  patch.object(socket, "create_connection", blocked)]:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.record)

    def record(self):
        OBSERVATIONS[self._testMethodName] = {"calls": self.calls}

    def populate(self):
        self.model.mkdir(parents=True, exist_ok=True)
        for name, data in FILES.items():
            (self.model / name).write_bytes(data)

    def provider(self):
        return embeddings.FastEmbedProvider(MODEL)

    def refuse_without_acquisition(self):
        with self.assertRaises(EmbeddingError):
            self.provider().embed(["review"])
        self.assertEqual(self.calls, [], "invalid evidence must not enter acquisition")

    def test_01_valid_local_model_uses_pinned_constructor(self):
        self.assertEqual(self.provider().embed(["review"]), [[1.0, 0.0]])
        self.assertEqual(len(self.calls), 1)
        self.assertIs(self.calls[0]["local_files_only"], True)
        self.assertEqual(self.calls[0]["specific_model_path"], str(self.model.resolve()))

    def test_02_nonfile_model_is_not_missing(self):
        (self.model / "model.onnx").unlink()
        (self.model / "model.onnx").mkdir()
        self.refuse_without_acquisition()

    def test_03_missing_model_and_missing_runtime_never_acquire(self):
        (self.model / "model.onnx").unlink()
        with patch.object(importlib.metadata, "version", side_effect=importlib.metadata.PackageNotFoundError("tokenizers")):
            self.refuse_without_acquisition()

    def test_04_missing_config_and_nonfile_tokenizer_never_acquire(self):
        (self.model / "config.json").unlink()
        (self.model / "tokenizer.json").unlink()
        (self.model / "tokenizer.json").mkdir()
        self.refuse_without_acquisition()

    def test_05_genuine_missing_model_bootstraps_then_pins(self):
        (self.model / "model.onnx").unlink()
        self.allow_acquire = True
        self.assertEqual(self.provider().embed(["review"]), [[1.0, 0.0]])
        self.assertEqual(len(self.calls), 2)
        self.assertNotIn("specific_model_path", self.calls[0])
        self.assertIs(self.calls[1]["local_files_only"], True)
        self.assertEqual(self.calls[1]["specific_model_path"], str(self.model.resolve()))

    def test_06_permission_error_is_typed_and_never_acquires(self):
        original = Path.stat
        def stat(path, *args, **kwargs):
            if path == self.model / "model.onnx":
                raise PermissionError("synthetic stat denial")
            return original(path, *args, **kwargs)
        with patch.object(Path, "stat", stat):
            self.refuse_without_acquisition()

    def test_07_path_loop_is_typed_and_never_acquires(self):
        original = Path.resolve
        def resolve(path, *args, **kwargs):
            if path == self.model / "tokenizer.json":
                raise RuntimeError("synthetic symlink loop")
            return original(path, *args, **kwargs)
        with patch.object(Path, "resolve", resolve):
            self.refuse_without_acquisition()

    def test_08_pinned_mutation_refused_before_constructor(self):
        provider = self.provider()
        provider.artifact_manifest()
        (self.model / "model.onnx").write_bytes(b"onnxBBBB")
        with self.assertRaises(EmbeddingError):
            provider.embed(["review"])
        self.assertEqual(self.calls, [])

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

if __name__ == "__main__":
    freeze = json.loads((HERE / "REVIEW-FREEZE.json").read_text(encoding="utf-8-sig"))
    for name, expected in freeze["files_sha256"].items():
        if digest(HERE / name) != expected:
            raise SystemExit("review freeze mismatch: " + name)
    for name, expected in freeze["runtime_sha256"].items():
        if digest(SOURCE / "src/cairntir/memory" / name) != expected:
            raise SystemExit("runtime changed: " + name)
    started = time.monotonic()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Controls)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {"elapsed_seconds": time.monotonic() - started, "cases": result.testsRun,
              "failures": [{"name": str(t), "traceback": text} for t, text in result.failures],
              "errors": [{"name": str(t), "traceback": text} for t, text in result.errors],
              "observations": OBSERVATIONS.copy(), "runtime_sha256": freeze["runtime_sha256"]}
    # Deliberate in-memory wrong control; no runtime file mutation.
    with patch.object(artifacts.PinnedArtifacts, "verify", lambda self: None):
        wrong = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([
            Controls("test_08_pinned_mutation_refused_before_constructor")]))
    report["wrong_control"] = {"disable_preload_verification_detected": len(wrong.failures) == 1 and not wrong.errors,
                               "failures": [{"name": str(t), "traceback": text} for t, text in wrong.failures]}
    (HERE / "review-results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    sys.exit(0 if result.wasSuccessful() and report["wrong_control"]["disable_preload_verification_detected"] else 1)
