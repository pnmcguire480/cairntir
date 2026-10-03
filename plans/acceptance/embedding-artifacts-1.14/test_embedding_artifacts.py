from __future__ import annotations

import argparse
import ast
import copy
from contextlib import closing
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import tomllib
import types
import unittest
from unittest.mock import patch

PACKET = Path(__file__).resolve().parent
MODEL = "jinaai/jina-embeddings-v2-small-en"
REPO = "synthetic/jina-artifacts"
REV_A = "a" * 40
REV_B = "b" * 40
DIM = 512
OLD_ID = f"fastembed/text-embedding-v1/model={MODEL}"
PREFIX = "fastembed/text-embedding-v2/sha256="
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
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def tree_bytes(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    return {str(p.relative_to(root)): digest(p.read_bytes()) for p in root.rglob("*") if p.is_file()}


class ArtifactAcceptance(unittest.TestCase):
    def setUp(self) -> None:
        (PACKET / "runs").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="synthetic-", dir=PACKET / "runs")
        self.root = Path(self.temp.name)
        self.assertTrue(self.root.resolve().is_relative_to((PACKET / "runs").resolve()))
        self.addCleanup(self.temp.cleanup)
        self.home = self.root / "explicit home"
        self.cache = self.root / "cache with spaces"
        self.description = {
            "model": MODEL, "dim": DIM, "sources": {"hf": REPO},
            "model_file": "onnx/model.onnx", "additional_files": [],
        }
        self.calls = []
        self.allow_acquire = False
        self.fail_inference = False
        self.fail_inference_text = None
        self.fail_construct = False
        self.construct_faults = 0
        self.inference_faults = 0
        self.environment = patch.dict(os.environ, {
            "CAIRNTIR_HOME": str(self.home), "FASTEMBED_CACHE_PATH": str(self.cache),
            "HF_HUB_OFFLINE": "1", "CAIRNTIR_DISABLE_AUTOREGISTER": "1",
            "CAIRNTIR_DISABLE_UPDATE_CHECK": "1", "PYTHONDONTWRITEBYTECODE": "1",
        })
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
                        raise AssertionError("unexpected acquisition or unpinned model construction")
                    fixture.write_snapshot(REV_A, cache=Path(cache_dir))
                    self.model_dir = fixture.snapshot(REV_A, Path(cache_dir))
                else:
                    self.model_dir = Path(pinned)

            def embed(self, texts, **kwargs):
                if not self.pinned:
                    raise AssertionError("unpinned acquisition model cannot supply vectors")
                if fixture.fail_inference or (fixture.fail_inference_text and any(fixture.fail_inference_text in text for text in texts)):
                    fixture.inference_faults += 1
                    raise RuntimeError("synthetic inference failure")
                return [[1.0 / (DIM ** 0.5)] * DIM for _ in texts]

        def cached(repo_id, filename, cache_dir=None, revision=None, **kwargs):
            if repo_id != REPO:
                return None
            if not isinstance(filename, str) or filename.startswith(("\\\\", "//")):
                return None
            cache = Path(cache_dir)
            ref = cache / "models--synthetic--jina-artifacts" / "refs" / "main"
            selected = revision if revision and revision != "main" else ref.read_text() if ref.exists() else None
            result = fixture.snapshot(selected, cache) / filename if selected else None
            if result and not result.resolve().is_relative_to(fixture.root.resolve()):
                return None
            return str(result) if result and result.is_file() else None

        def forbidden(*args, **kwargs):
            raise AssertionError("network acquisition API used in synthetic offline acceptance")

        for target in ("socket.create_connection", "socket.socket.connect", "socket.socket.connect_ex"):
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
        from cairntir.memory.embeddings import FastEmbedProvider, HashEmbeddingProvider
        from cairntir.errors import EmbeddingError, EmbeddingSpaceError
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
            file.write_bytes(replacement if replacement is not None and name == "onnx/model.onnx" else data)
        ref = cache / "models--synthetic--jina-artifacts" / "refs" / "main"
        ref.parent.mkdir(parents=True, exist_ok=True)
        ref.write_text(revision)
        return target

    def manifest(self, provider):
        self.assertTrue(callable(getattr(provider, "artifact_manifest", None)), "missing read-only artifact_manifest interface")
        return provider.artifact_manifest()

    def expected(self, model_root=None):
        model_root = model_root or self.snapshot()
        required = set(PAYLOADS) | set(self.description["additional_files"])
        return {
            "schema": "cairntir.embedding-artifacts.v1", "model": MODEL, "dimension": DIM,
            "model_file": self.description["model_file"],
            "files": [{"path": name, "size_bytes": len((model_root / name).read_bytes()),
                "sha256": digest((model_root / name).read_bytes())} for name in sorted(required)],
            "pipeline": "fastembed.TextEmbedding/defaults-v1",
            "runtime": {name: importlib.metadata.version(name) for name in ("fastembed", "onnxruntime", "tokenizers", "numpy")},
        }

    def legacy(self):
        self.home.mkdir(parents=True, exist_ok=True)
        database = self.home / "cairntir.db"
        with self.Store(database, self.Hash(dimension=DIM)) as store:
            drawer = store.add(self.Drawer(wing="cairntir", room="synthetic", content="Original café\r\nExact content."))
            store.checkpoint()
        with closing(sqlite3.connect(database)) as conn, conn:
            conn.execute("UPDATE store_metadata SET value=? WHERE key='embedding_space_id'", (OLD_ID,))
        return database, drawer

    def logical(self, database):
        import sqlite_vec
        conn = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
        try:
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.enable_load_extension(False)
            return {
                "drawers": conn.execute("SELECT id,content,supersedes_id FROM drawers ORDER BY id").fetchall(),
                "metadata": conn.execute("SELECT key,value FROM store_metadata ORDER BY key").fetchall(),
                "vectors": conn.execute("SELECT drawer_id,embedding FROM vec_drawers ORDER BY drawer_id").fetchall(),
            }
        finally:
            conn.close()

    def test_01_canonical_manifest_exact_hashes_and_no_side_effects(self):
        before = tree_bytes(self.root)
        provider = self.Provider()
        manifest = self.manifest(provider)
        self.assertEqual(manifest, self.expected())
        self.assertEqual(provider.embedding_space_id, PREFIX + digest(canonical(manifest)))
        self.assertEqual(self.calls, [])
        self.assertEqual(tree_bytes(self.root), before)

    def test_02_each_required_asset_same_size_change_changes_identity(self):
        original = self.Provider().embedding_space_id
        for name in PAYLOADS:
            with self.subTest(asset=name):
                file = self.snapshot() / name
                data = file.read_bytes()
                changed = (b"X" if data[:1] != b"X" else b"Y") + data[1:]
                file.write_bytes(changed)
                self.assertNotEqual(self.Provider().embedding_space_id, original)
                file.write_bytes(data)
        self.assertEqual(self.calls, [])

    def test_03_relocation_and_unrelated_files_do_not_change_identity(self):
        expected = self.Provider().embedding_space_id
        other = self.root / "another cache"
        shutil.copytree(self.cache, other)
        (self.snapshot(REV_A, other) / "README.md").write_text("irrelevant")
        os.environ["FASTEMBED_CACHE_PATH"] = str(other)
        self.assertEqual(self.Provider().embedding_space_id, expected)

    def test_04_manifest_is_detached_from_internal_identity(self):
        provider = self.Provider()
        manifest = self.manifest(provider)
        identity = provider.embedding_space_id
        manifest["files"][0]["sha256"] = "0" * 64
        manifest["runtime"].clear()
        self.assertEqual(self.manifest(provider), self.expected())
        self.assertEqual(provider.embedding_space_id, identity)

    def test_05_registry_additional_asset_is_required_and_hashed(self):
        self.description["additional_files"] = ["onnx/external.bin"]
        with self.assertRaises(self.EmbeddingError):
            self.manifest(self.Provider())
        extra = self.snapshot() / "onnx/external.bin"
        extra.write_bytes(b"tensor-A")
        first = self.Provider()
        self.assertEqual(self.manifest(first), self.expected())
        identity = first.embedding_space_id
        extra.write_bytes(b"tensor-B")
        self.assertNotEqual(self.Provider().embedding_space_id, identity)

    def test_06_missing_each_required_file_fails_without_model_or_write(self):
        for name in PAYLOADS:
            with self.subTest(asset=name):
                file = self.snapshot() / name
                content = file.read_bytes()
                file.unlink()
                before = tree_bytes(self.root)
                with self.assertRaises(self.EmbeddingError):
                    self.manifest(self.Provider())
                self.assertEqual(tree_bytes(self.root), before)
                self.assertEqual(self.calls, [])
                file.write_bytes(content)

    def test_07_invalid_registry_paths_fail_closed(self):
        outside = self.root / "outside.bin"
        outside.write_bytes(b"outside snapshot")
        (self.snapshot().parent / "escape.bin").write_bytes(b"outside snapshot")
        (self.snapshot() / "model.onnx").write_bytes(b"ambiguous normalized path")
        invalid = ["", "../escape.bin", outside.as_posix(), "C:synthetic-escape.bin", "\\\\?\\" + str(outside), "onnx\\model.onnx", "onnx/../model.onnx", "./onnx/model.onnx"]
        for name in invalid:
            with self.subTest(path=name, field="model_file"):
                self.description["model_file"] = name
                with self.assertRaises(self.EmbeddingError):
                    self.manifest(self.Provider())
            with self.subTest(path=name, field="additional_files"):
                self.description["model_file"] = "onnx/model.onnx"
                self.description["additional_files"] = [name]
                with self.assertRaises(self.EmbeddingError):
                    self.manifest(self.Provider())
                self.description["additional_files"] = []
        self.assertEqual(self.calls, [])

    def test_08_symlink_asset_cannot_escape_model_root(self):
        outside = self.root / "outside.bin"
        outside.write_bytes(b"outside")
        link = self.snapshot() / "onnx/external.bin"
        try:
            link.symlink_to(outside)
        except OSError as error:
            self.skipTest(f"symlink creation unavailable: {error}")
        self.description["additional_files"] = ["onnx/external.bin"]
        with self.assertRaises(self.EmbeddingError):
            self.manifest(self.Provider())

    def test_09_mutating_main_cannot_redirect_pinned_normal_load(self):
        provider = self.Provider()
        expected = provider.embedding_space_id
        self.write_snapshot(REV_B, replacement=b"synthetic-model-bytes-BBBB")
        self.assertNotEqual(self.Provider().embedding_space_id, expected)
        vectors = provider.embed(["synthetic query"])
        self.assertEqual(len(vectors[0]), DIM)
        self.assertEqual(provider.embedding_space_id, expected)
        self.assertTrue(self.calls)
        for call in self.calls:
            self.assertEqual(Path(call["specific_model_path"]).resolve(), self.snapshot().resolve())
            self.assertIs(call.get("local_files_only"), True)
            self.assertEqual(Path(call["cache_dir"]), self.cache)

    def test_10_mutating_main_cannot_redirect_pinned_readonly_load(self):
        provider = self.Provider()
        identity = provider.embedding_space_id
        self.write_snapshot(REV_B, replacement=b"synthetic-model-bytes-BBBB")
        before = tree_bytes(self.root)
        self.assertEqual(len(provider.embed_query_readonly("query")), DIM)
        self.assertEqual(provider.embedding_space_id, identity)
        self.assertEqual(Path(self.calls[-1]["specific_model_path"]).resolve(), self.snapshot().resolve())
        self.assertIs(self.calls[-1].get("local_files_only"), True)
        self.assertEqual(tree_bytes(self.root), before)

    def test_11_changed_pinned_bytes_rejected_before_model_construction(self):
        for readonly in (False, True):
            with self.subTest(readonly=readonly):
                file = self.snapshot() / "onnx/model.onnx"
                file.write_bytes(PAYLOADS["onnx/model.onnx"])
                provider = self.Provider()
                self.manifest(provider)
                original_stat = file.stat()
                file.write_bytes(b"synthetic-model-bytes-BBBB")
                os.utime(file, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
                with self.assertRaises(self.EmbeddingError):
                    provider.embed_query_readonly("query") if readonly else provider.embed(["query"])
                self.assertEqual(self.calls, [])

    def test_12_missing_cache_offline_identity_does_not_create_or_download(self):
        absent = self.root / "does not exist"
        os.environ["FASTEMBED_CACHE_PATH"] = str(absent)
        for operation in (lambda p: self.manifest(p), lambda p: p.embedding_space_id, lambda p: p.embed_query_readonly("query")):
            with self.assertRaises(self.EmbeddingError) as raised:
                operation(self.Provider())
            self.assertTrue(str(raised.exception).strip())
            self.assertFalse(absent.exists())
            self.assertEqual(self.calls, [])

    def test_13_configured_default_cache_is_beneath_explicit_home(self):
        default_cache = self.home / "models"
        self.write_snapshot(REV_A, cache=default_cache)
        os.environ.pop("FASTEMBED_CACHE_PATH")
        provider = self.Provider()
        self.manifest(provider)
        provider.embed_query_readonly("query")
        self.assertEqual(Path(self.calls[-1]["specific_model_path"]).resolve(), self.snapshot(REV_A, default_cache).resolve())
        self.assertEqual(Path(self.calls[-1]["cache_dir"]), default_cache)

    def test_14_explicit_bootstrap_acquires_then_uses_pinned_vectors(self):
        bootstrap_cache = self.root / "fresh bootstrap cache"
        os.environ["FASTEMBED_CACHE_PATH"] = str(bootstrap_cache)
        self.allow_acquire = True
        provider = self.Provider()
        self.assertEqual(provider.dimension, DIM)
        self.assertTrue(any(not c.get("specific_model_path") for c in self.calls), "fixture must observe the permitted acquisition")
        self.assertEqual(Path(self.calls[-1]["specific_model_path"]).resolve(), self.snapshot(REV_A, bootstrap_cache).resolve())
        self.assertIs(self.calls[-1].get("local_files_only"), True)
        self.assertEqual(provider.embedding_space_id, PREFIX + digest(canonical(self.manifest(provider))))

    def test_15_legacy_index_is_unverified_without_retroactive_stamp(self):
        database, drawer = self.legacy()
        before = self.logical(database)
        status = self.inspect(database, self.Provider())
        self.assertEqual(status.state, "unverified")
        self.assertFalse(status.verified)
        self.assertEqual(status.stored_space_id, OLD_ID)
        self.assertEqual(self.logical(database), before)
        self.assertEqual(self.calls, [])
        with self.Store(database, self.Provider()) as store:
            self.assertEqual(store.get(drawer.id).content, drawer.content)
        self.assertEqual(self.logical(database), before)

    def test_16_legacy_semantic_operations_fail_without_mutation(self):
        database, _ = self.legacy()
        before = self.logical(database)
        with self.Store(database, self.Provider()) as store:
            with self.assertRaises(self.SpaceError):
                store.search("query")
            with self.assertRaises(self.SpaceError):
                store.add(self.Drawer(wing="cairntir", room="synthetic", content="must not be saved"))
        self.assertEqual(self.logical(database), before)
        self.assertEqual(self.calls, [])

    def test_17_raw_legacy_retrieval_needs_no_cached_assets(self):
        database, drawer = self.legacy()
        os.environ["FASTEMBED_CACHE_PATH"] = str(self.root / "missing cache")
        before = self.logical(database)
        with self.Store(database, self.Provider()) as store:
            self.assertEqual(store.get(drawer.id).content, drawer.content)
        self.assertEqual(self.logical(database), before)
        self.assertEqual(self.calls, [])

    def test_18_new_index_stamps_artifact_identity_and_detects_change(self):
        self.home.mkdir(exist_ok=True)
        database = self.home / "new.db"
        provider = self.Provider()
        with self.Store(database, provider) as store:
            store.add(self.Drawer(wing="cairntir", room="synthetic", content="pinned source"))
            self.assertEqual(store.embedding_status().stored_space_id, provider.embedding_space_id)
            self.assertTrue(store.embedding_status().verified)
        (self.snapshot() / "onnx/model.onnx").write_bytes(b"synthetic-model-bytes-BBBB")
        status = self.inspect(database, self.Provider())
        self.assertEqual(status.state, "mismatch")

    def test_19_explicit_cli_rebuild_preserves_backup_and_recovers_legacy(self):
        database, drawer = self.legacy()
        before = self.logical(database)
        backup = self.root / "before-rebuild.db"
        from cairntir.cli import app
        from typer.testing import CliRunner
        result = CliRunner().invoke(app, ["reindex", "--yes", "--backup", str(backup)])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertTrue(backup.exists())
        self.assertEqual(self.logical(backup), before)
        after = self.logical(database)
        self.assertEqual(after["drawers"], before["drawers"])
        self.assertNotEqual(dict(after["metadata"])["embedding_generation"], dict(before["metadata"])["embedding_generation"])
        self.assertEqual(dict(after["metadata"])["embedding_space_id"], self.Provider().embedding_space_id)
        self.assertTrue(self.inspect(database, self.Provider()).verified)
        with self.Store(database, self.Provider()) as store:
            self.assertEqual(store.get(drawer.id).content, drawer.content)
            self.assertEqual(store.search("query")[0][0].id, drawer.id)

    def test_20_failed_explicit_rebuild_preserves_original_logical_database(self):
        database, _ = self.legacy()
        before = self.logical(database)
        self.fail_construct = True
        from cairntir.cli import app
        from typer.testing import CliRunner
        result = CliRunner().invoke(app, ["reindex", "--yes", "--backup", str(self.root / "failed-backup.db")])
        self.assertNotEqual(result.exit_code, 0)
        self.assertGreaterEqual(self.construct_faults, 1)
        self.assertEqual(self.logical(database), before)

    def test_21_no_new_project_dependencies(self):
        current = tomllib.loads((SOURCE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        baseline = json.loads((PACKET / "dependency-baseline.json").read_text())
        self.assertEqual(current["project"]["dependencies"], baseline["dependencies"])
        self.assertEqual(current["project"].get("optional-dependencies", {}), baseline["optional-dependencies"])

    def test_22_empty_v1_index_can_adopt_verified_artifact_identity(self):
        self.home.mkdir(exist_ok=True)
        database = self.home / "empty.db"
        with self.Store(database, self.Hash(dimension=DIM)):
            pass
        with closing(sqlite3.connect(database)) as conn, conn:
            conn.execute("UPDATE store_metadata SET value=? WHERE key='embedding_space_id'", (OLD_ID,))
        provider = self.Provider()
        with self.Store(database, provider) as store:
            status = store.embedding_status()
            self.assertTrue(status.verified)
            self.assertEqual(status.drawer_count, 0)
            self.assertEqual(status.vector_count, 0)
            self.assertEqual(status.stored_space_id, provider.embedding_space_id)
        self.assertTrue(self.calls, "empty-index adoption must validate the pinned model")

    def test_23_failed_batch_rebuild_keeps_legacy_source_and_backup(self):
        database, _ = self.legacy()
        before = self.logical(database)
        backup = self.root / "before-failed-batch.db"
        self.fail_inference_text = "Original"
        from cairntir.cli import app
        from typer.testing import CliRunner
        result = CliRunner().invoke(app, ["reindex", "--yes", "--backup", str(backup)])
        self.assertNotEqual(result.exit_code, 0)
        self.assertEqual(self.inference_faults, 1)
        self.assertTrue(backup.exists(), "failure must happen after preflight and backup")
        self.assertEqual(self.logical(backup), before)
        self.assertEqual(self.logical(database), before)

    def test_24_explicit_setup_warmup_can_bootstrap_missing_cache(self):
        bootstrap_cache = self.root / "fresh setup cache"
        os.environ["FASTEMBED_CACHE_PATH"] = str(bootstrap_cache)
        self.allow_acquire = True
        provider = self.Provider()
        vectors = provider.embed(["cairntir setup warmup probe"])
        self.assertEqual(len(vectors[0]), DIM)
        self.assertEqual(Path(self.calls[-1]["specific_model_path"]).resolve(), self.snapshot(REV_A, bootstrap_cache).resolve())
        self.assertIs(self.calls[-1].get("local_files_only"), True)
        self.assertEqual(provider.embedding_space_id, PREFIX + digest(canonical(self.manifest(provider))))

    def test_25_hub_snapshot_blob_symlink_has_same_identity(self):
        expected = self.Provider().embedding_space_id
        artifact = self.snapshot() / "onnx/model.onnx"
        data = artifact.read_bytes()
        blobs = self.cache / "models--synthetic--jina-artifacts" / "blobs"
        blobs.mkdir()
        blob = blobs / digest(data)
        blob.write_bytes(data)
        link_probe = self.snapshot() / "link-probe"
        try:
            link_probe.symlink_to(blob)
        except OSError as error:
            self.skipTest(f"symlink creation unavailable: {error}")
        link_probe.unlink()
        artifact.unlink()
        artifact.symlink_to(blob)
        self.assertEqual(self.Provider().embedding_space_id, expected)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--failfast", action="store_true")
    args = parser.parse_args()
    if args.self_check:
        ast.parse(Path(__file__).read_text(encoding="utf-8"))
        json.loads((PACKET / "dependency-baseline.json").read_text())
        cases = len(unittest.defaultTestLoader.getTestCaseNames(ArtifactAcceptance))
        print(json.dumps({"status": "syntax-and-fixture-metadata-pass", "cases": cases, "product_executed": False}))
        raise SystemExit(0)
    if args.source_root is None:
        parser.error("--source-root is required")
    SOURCE_ROOT = args.source_root.resolve()
    sys.path.insert(0, str(SOURCE_ROOT / "src"))
    sys.dont_write_bytecode = True
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ArtifactAcceptance)
    result = unittest.TextTestRunner(verbosity=2, failfast=args.failfast).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
