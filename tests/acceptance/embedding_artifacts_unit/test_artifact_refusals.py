"""Invalid local evidence is refused without acquisition. No real models or network."""

from __future__ import annotations

import importlib.metadata
import os
import socket
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from cairntir.errors import EmbeddingError
from cairntir.memory import embeddings

MODEL = "synthetic/review-model"
FILES = {
    "model.onnx": b"onnxAAAA",
    "config.json": b"{}",
    "tokenizer.json": b"{}",
    "tokenizer_config.json": b"{}",
    "special_tokens_map.json": b"{}",
}


class ControlsFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="synthetic-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.cache = self.root / "cache"
        self.model = self.cache / "review-model"
        self.calls = []
        self.allow_acquire = False
        self.populate()
        fixture = self

        class FakeTextEmbedding:
            @classmethod
            def list_supported_models(cls):
                return [
                    {
                        "model": MODEL,
                        "dim": 2,
                        "model_file": "model.onnx",
                        "additional_files": [],
                        "sources": {"hf": "synthetic/review"},
                    }
                ]

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

        for p in [
            patch.dict(sys.modules, {"fastembed": fake, "huggingface_hub": hub}),
            patch.dict(
                os.environ,
                {
                    "FASTEMBED_CACHE_PATH": str(self.cache),
                    "CAIRNTIR_HOME": str(self.root / "home"),
                    "HF_HUB_OFFLINE": "1",
                    "HOME": str(self.root / "user"),
                    "USERPROFILE": str(self.root / "user"),
                },
            ),
            patch.object(embeddings, "_embed_trace", lambda *args: None),
            patch.object(importlib.metadata, "version", lambda name: "1.2.3"),
            patch.object(socket.socket, "connect", blocked),
            patch.object(socket.socket, "connect_ex", blocked),
            patch.object(socket, "create_connection", blocked),
        ]:
            p.start()
            self.addCleanup(p.stop)

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


class Controls(ControlsFixture):
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
        with patch.object(
            importlib.metadata,
            "version",
            side_effect=importlib.metadata.PackageNotFoundError("tokenizers"),
        ):
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


class CachePermissionControl(ControlsFixture):
    def test_offline_cache_stat_permission_error_is_typed(self):
        original_stat = Path.stat

        def denied(path, *args, **kwargs):
            if path == self.cache:
                raise PermissionError("synthetic cache stat denial")
            return original_stat(path, *args, **kwargs)

        with patch.object(Path, "stat", denied), self.assertRaises(EmbeddingError):
            self.provider().artifact_manifest()
        self.assertEqual(self.calls, [])


class HubControl(ControlsFixture):
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
            selected = (
                repository / "snapshots" / (repository / "refs" / "main").read_text() / filename
            )
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

    def prepare_hub(self):
        snapshot = self.cache / "models--synthetic--review" / "snapshots" / ("a" * 40)
        snapshot.parent.mkdir(parents=True)
        self.model.rename(snapshot)
        self.model = snapshot
        reference = snapshot.parent.parent / "refs" / "main"
        reference.parent.mkdir()
        reference.write_text(snapshot.name)
        return snapshot, reference

    def test_hub_genuine_missing_model_acquires_then_pins(self):
        snapshot, _reference = self.prepare_hub()
        (snapshot / "model.onnx").unlink()

        def cached(repo_id, filename, cache_dir=None, **kwargs):
            selected = snapshot / filename
            return str(selected) if selected.is_file() else None

        self.allow_acquire = True
        with patch.object(sys.modules["huggingface_hub"], "try_to_load_from_cache", cached):
            self.assertEqual(self.provider().embed(["genuinely absent"]), [[1.0, 0.0]])
        self.assertEqual(len(self.calls), 2)
        self.assertNotIn("specific_model_path", self.calls[0])
        self.assertEqual(self.calls[1]["specific_model_path"], str(snapshot.resolve()))
        self.assertIs(self.calls[1]["local_files_only"], True)

    def test_hub_malformed_selected_refs_refuse_without_acquisition(self):
        snapshot, reference = self.prepare_hub()
        (snapshot / "model.onnx").unlink()
        for value in ("", "..", "../other", "/outside", "C:/outside", "a/b"):
            with self.subTest(reference=value):
                reference.write_text(value)
                self.calls.clear()
                # Hub cannot resolve a cached model. The provider must not
                # convert invalid ref evidence into acquisition authority.
                with patch.object(
                    sys.modules["huggingface_hub"], "try_to_load_from_cache", lambda *a, **k: None
                ):
                    self.refuse_without_acquisition()
