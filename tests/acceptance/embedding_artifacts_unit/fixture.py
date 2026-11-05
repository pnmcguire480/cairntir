"""Synthetic model, offline loader APIs and base test class for artifact tests."""

from __future__ import annotations

import copy
import hashlib
import importlib.metadata
import json
import os
import sqlite3
import sys
import tempfile
import types
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

MODEL = "jinaai/jina-embeddings-v2-small-en"
REPO = "synthetic/jina-artifacts"
REV_A = "a" * 40
REV_B = "b" * 40
DIM = 512
OLD_ID = f"fastembed/text-embedding-v1/model={MODEL}"
PREFIX = "fastembed/text-embedding-v2/sha256="
CHUNK_PREFIX = "cairntir/chunks/codepoints-v2/window=6000/aggregation=best/"
PAYLOADS = {
    "config.json": b'{"hidden_size":512,"pad_token_id":0}',
    "onnx/model.onnx": b"synthetic-model-bytes-AAAA",
    "special_tokens_map.json": b'{"pad_token":"[PAD]"}',
    "tokenizer.json": b'{"synthetic_tokenizer":"AAAA"}',
    "tokenizer_config.json": b'{"model_max_length":8192,"pad_token":"[PAD]"}',
}


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical(value: dict) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def tree_bytes(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    return {
        str(p.relative_to(root)): digest(p.read_bytes()) for p in root.rglob("*") if p.is_file()
    }


class ArtifactAcceptance(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="synthetic-")
        self.root = Path(self.temp.name).resolve()
        self.addCleanup(self.temp.cleanup)
        self.home = self.root / "explicit home"
        self.cache = self.root / "cache with spaces"
        self.description = {
            "model": MODEL,
            "dim": DIM,
            "sources": {"hf": REPO},
            "model_file": "onnx/model.onnx",
            "additional_files": [],
        }
        self.calls = []
        self.allow_acquire = False
        self.fail_inference = False
        self.fail_inference_text = None
        self.fail_construct = False
        self.construct_faults = 0
        self.inference_faults = 0
        self.environment = patch.dict(
            os.environ,
            {
                "CAIRNTIR_HOME": str(self.home),
                "FASTEMBED_CACHE_PATH": str(self.cache),
                "HF_HUB_OFFLINE": "1",
                "CAIRNTIR_DISABLE_AUTOREGISTER": "1",
                "CAIRNTIR_DISABLE_UPDATE_CHECK": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
            },
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        fixture = self

        class FakeTextEmbedding:
            @classmethod
            def list_supported_models(cls):
                return [copy.deepcopy(fixture.description)]

            @classmethod
            def download_model(cls, model, cache_dir, **kwargs):
                if not fixture.allow_acquire:
                    raise AssertionError("unexpected acquisition")
                fixture.calls.append({"acquisition": "download_model", "cache_dir": cache_dir})
                return fixture.write_snapshot(REV_A, cache=Path(cache_dir))

            def __init__(self, model_name=MODEL, cache_dir=None, **kwargs):
                pinned = kwargs.get("specific_model_path")
                fixture.calls.append({"model_name": model_name, "cache_dir": cache_dir, **kwargs})
                self.pinned = pinned
                if fixture.fail_construct:
                    fixture.construct_faults += 1
                    raise RuntimeError("synthetic constructor failure")
                if not pinned:
                    if not fixture.allow_acquire:
                        raise AssertionError(
                            "unexpected acquisition or unpinned model construction"
                        )
                    fixture.write_snapshot(REV_A, cache=Path(cache_dir))
                    self.model_dir = fixture.snapshot(REV_A, Path(cache_dir))
                else:
                    self.model_dir = Path(pinned)

            def embed(self, texts, **kwargs):
                if not self.pinned:
                    raise AssertionError("unpinned acquisition model cannot supply vectors")
                if fixture.fail_inference or (
                    fixture.fail_inference_text
                    and any(fixture.fail_inference_text in text for text in texts)
                ):
                    fixture.inference_faults += 1
                    raise RuntimeError("synthetic inference failure")
                return [[1.0 / (DIM**0.5)] * DIM for _ in texts]

        def cached(repo_id, filename, cache_dir=None, revision=None, **kwargs):
            if repo_id != REPO:
                return None
            if not isinstance(filename, str) or filename.startswith(("\\\\", "//")):
                return None
            cache = Path(cache_dir)
            ref = cache / "models--synthetic--jina-artifacts" / "refs" / "main"
            selected = (
                revision
                if revision and revision != "main"
                else ref.read_text()
                if ref.exists()
                else None
            )
            result = fixture.snapshot(selected, cache) / filename if selected else None
            if result and not result.resolve().is_relative_to(fixture.root.resolve()):
                return None
            return str(result) if result and result.is_file() else None

        def forbidden(*args, **kwargs):
            raise AssertionError("network acquisition API used in synthetic offline acceptance")

        for target in (
            "socket.create_connection",
            "socket.socket.connect",
            "socket.socket.connect_ex",
        ):
            blocker = patch(target, side_effect=forbidden)
            blocker.start()
            self.addCleanup(blocker.stop)

        fastembed = types.ModuleType("fastembed")
        fastembed.TextEmbedding = FakeTextEmbedding
        fastembed.__version__ = importlib.metadata.version("fastembed")
        hub = types.ModuleType("huggingface_hub")
        hub.try_to_load_from_cache = cached
        hub.snapshot_download = forbidden
        hub.hf_hub_download = forbidden
        self.modules = patch.dict(sys.modules, {"fastembed": fastembed, "huggingface_hub": hub})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        from cairntir.errors import EmbeddingError, EmbeddingSpaceError
        from cairntir.memory.embeddings import FastEmbedProvider, HashEmbeddingProvider
        from cairntir.memory.store import DrawerStore, inspect_embedding_space
        from cairntir.memory.taxonomy import Drawer

        self.Provider = FastEmbedProvider
        self.Hash = HashEmbeddingProvider
        self.EmbeddingError = EmbeddingError
        self.SpaceError = EmbeddingSpaceError
        self.Store = DrawerStore
        self.inspect = inspect_embedding_space
        self.Drawer = Drawer
        self.write_snapshot(REV_A)

    def snapshot(self, revision=REV_A, cache=None):
        return (cache or self.cache) / "models--synthetic--jina-artifacts" / "snapshots" / revision

    def write_snapshot(self, revision, cache=None, replacement=None):
        cache = cache or self.cache
        target = self.snapshot(revision, cache)
        for name, data in PAYLOADS.items():
            file = target / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(
                replacement if replacement is not None and name == "onnx/model.onnx" else data
            )
        ref = cache / "models--synthetic--jina-artifacts" / "refs" / "main"
        ref.parent.mkdir(parents=True, exist_ok=True)
        ref.write_text(revision)
        return target

    def manifest(self, provider):
        self.assertTrue(
            callable(getattr(provider, "artifact_manifest", None)),
            "missing read-only artifact_manifest interface",
        )
        return provider.artifact_manifest()

    def expected(self, model_root=None):
        model_root = model_root or self.snapshot()
        required = set(PAYLOADS) | set(self.description["additional_files"])
        return {
            "schema": "cairntir.embedding-artifacts.v1",
            "model": MODEL,
            "dimension": DIM,
            "model_file": self.description["model_file"],
            "files": [
                {
                    "path": name,
                    "size_bytes": len((model_root / name).read_bytes()),
                    "sha256": digest((model_root / name).read_bytes()),
                }
                for name in sorted(required)
            ],
            "pipeline": "fastembed.TextEmbedding/defaults-v1",
            "runtime": {
                name: importlib.metadata.version(name)
                for name in ("fastembed", "onnxruntime", "tokenizers", "numpy")
            },
        }

    def legacy(self):
        self.home.mkdir(parents=True, exist_ok=True)
        database = self.home / "cairntir.db"
        with self.Store(database, self.Hash(dimension=DIM)) as store:
            drawer = store.add(
                self.Drawer(
                    wing="cairntir", room="synthetic", content="Original café\r\nExact content."
                )
            )
            store.checkpoint()
        with closing(sqlite3.connect(database)) as conn, conn:
            conn.execute(
                "UPDATE store_metadata SET value=? WHERE key='embedding_space_id'", (OLD_ID,)
            )
        return database, drawer

    def logical(self, database):
        import sqlite_vec

        conn = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
        try:
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.enable_load_extension(False)
            return {
                "drawers": conn.execute(
                    "SELECT id,content,supersedes_id FROM drawers ORDER BY id"
                ).fetchall(),
                "metadata": conn.execute(
                    "SELECT key,value FROM store_metadata ORDER BY key"
                ).fetchall(),
                "vectors": conn.execute(
                    "SELECT drawer_id,embedding FROM vec_drawers ORDER BY drawer_id"
                ).fetchall(),
            }
        finally:
            conn.close()
