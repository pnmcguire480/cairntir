"""Public synthetic supplementary E22 controls; freeze before implementation."""
from __future__ import annotations

import importlib.metadata
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import test_embedding_artifacts as base


class SupplementaryAcceptance(base.ArtifactAcceptance):
    def setUp(self):
        super().setUp()
        self.trace = []
        self.synthetic_user_home = self.root / "synthetic user home"
        self.synthetic_user_home.mkdir()
        isolation = patch.dict(os.environ, {
            "USERPROFILE": str(self.synthetic_user_home),
            "HOME": str(self.synthetic_user_home),
            "CAIRNTIR_VAULT": "",
        })
        isolation.start()
        self.addCleanup(isolation.stop)
        initial_cwd = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, initial_cwd)
        self.addCleanup(self.save_trace)

    def save_trace(self):
        if self.trace:
            target = base.PACKET / "runs" / (self.id().split(".")[-1] + "-cli.json")
            target.write_text(json.dumps(self.trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def cli(self, *arguments):
        from cairntir.cli import app
        from typer.testing import CliRunner
        result = CliRunner().invoke(app, list(arguments))
        self.trace.append({
            "arguments": list(arguments), "exit_code": result.exit_code,
            "output": result.output,
            "exception_type": type(result.exception).__name__ if result.exception else None,
        })
        return result

    def assert_state(self, result, state):
        lines = [line.split(":", 1)[1].strip() for line in result.output.splitlines() if line.startswith("state:")]
        self.assertEqual(lines, [state], result.output)

    def test_26_actual_cli_legacy_doctor_raw_reindex_recall_workflow(self):
        database, drawer = self.legacy()
        before = self.logical(database)
        doctor = self.cli("doctor")
        self.assertEqual(doctor.exit_code, 1, doctor.output)
        self.assert_state(doctor, "unverified")
        self.assertEqual(self.logical(database), before)
        self.assertEqual(self.calls, [])
        raw = self.cli("get", str(drawer.id))
        self.assertEqual(raw.exit_code, 0, raw.output)
        raw_record = json.loads(raw.output)
        self.assertEqual(raw_record["id"], drawer.id)
        self.assertEqual(raw_record["content"], drawer.content)
        self.assertEqual(self.logical(database), before)
        denied = self.cli("recall", "query", "--wing", "cairntir")
        self.assertNotEqual(denied.exit_code, 0)
        self.assertEqual(self.logical(database), before)
        self.assertEqual(self.calls, [])
        backup = self.root / "workflow backup.db"
        rebuilt = self.cli("reindex", "--yes", "--backup", str(backup))
        self.assertEqual(rebuilt.exit_code, 0, rebuilt.output)
        self.assertEqual(self.logical(backup), before)
        after = self.logical(database)
        self.assertEqual(after["drawers"], before["drawers"])
        self.assertEqual(dict(after["metadata"])["embedding_space_id"], self.Provider().embedding_space_id)
        self.assertNotEqual(dict(after["metadata"])["embedding_generation"], dict(before["metadata"])["embedding_generation"])
        calls_before = len(self.calls)
        doctor = self.cli("doctor")
        self.assertEqual(doctor.exit_code, 0, doctor.output)
        self.assert_state(doctor, "verified")
        self.assertEqual(len(self.calls), calls_before, "doctor must not construct an inference model")
        recalled = self.cli("recall", "query", "--wing", "cairntir")
        self.assertEqual(recalled.exit_code, 0, recalled.output)
        self.assertIn(str(drawer.id), recalled.output)
        self.assertIn("Original", recalled.output)
        self.assertEqual(self.logical(database), after)
        for call in self.calls:
            self.assertIs(call.get("local_files_only"), True)
            self.assertEqual(Path(call["specific_model_path"]).resolve(), self.snapshot().resolve())

    def test_27_actual_cli_raw_legacy_with_absent_cache(self):
        database, drawer = self.legacy()
        before = self.logical(database)
        missing = self.root / "absent CLI cache"
        os.environ["FASTEMBED_CACHE_PATH"] = str(missing)
        doctor = self.cli("doctor")
        self.assertEqual(doctor.exit_code, 1, doctor.output)
        self.assertIn("unverified", doctor.output.lower())
        raw = self.cli("get", str(drawer.id))
        self.assertEqual(raw.exit_code, 0, raw.output)
        self.assertEqual(json.loads(raw.output)["content"], drawer.content)
        self.assertEqual(self.logical(database), before)
        self.assertEqual(self.calls, [])
        self.assertFalse(missing.exists())

    def test_28_cli_partial_batch_failure_preserves_all_source_and_backup(self):
        self.home.mkdir(exist_ok=True)
        database = self.home / "cairntir.db"
        with self.Store(database, self.Hash(dimension=base.DIM)) as store:
            for content in ("first synthetic drawer", "second FAIL-HERE drawer", "third synthetic drawer"):
                store.add(self.Drawer(wing="cairntir", room="synthetic", content=content))
            store.checkpoint()
        import sqlite3
        with sqlite3.connect(database) as conn:
            conn.execute("UPDATE store_metadata SET value=? WHERE key='embedding_space_id'", (base.OLD_ID,))
        before = self.logical(database)
        backup = self.root / "partial batch backup.db"
        self.fail_inference_text = "FAIL-HERE"
        result = self.cli("reindex", "--yes", "--backup", str(backup))
        self.assertNotEqual(result.exit_code, 0, result.output)
        self.assertGreaterEqual(self.inference_faults, 1)
        self.assertTrue(backup.exists())
        self.assertEqual(self.logical(backup), before)
        self.assertEqual(self.logical(database), before)

    def test_29_each_runtime_version_is_required_and_nonempty(self):
        version = importlib.metadata.version
        for package in ("fastembed", "onnxruntime", "tokenizers", "numpy"):
            for failure in ("missing", "empty"):
                with self.subTest(package=package, failure=failure):
                    def evidence(name):
                        if name == package:
                            if failure == "missing":
                                raise importlib.metadata.PackageNotFoundError(name)
                            return ""
                        return version(name)
                    before = base.tree_bytes(self.root)
                    with patch("importlib.metadata.version", side_effect=evidence):
                        with self.assertRaises(self.EmbeddingError) as raised:
                            self.manifest(self.Provider())
                    self.assertTrue(str(raised.exception).strip())
                    self.assertEqual(base.tree_bytes(self.root), before)
                    self.assertEqual(self.calls, [])

    def test_30_runtime_version_changes_identity_without_mutating_pinned_identity(self):
        provider = self.Provider()
        original = provider.embedding_space_id
        expected = self.manifest(provider)
        version = importlib.metadata.version
        with patch("importlib.metadata.version", side_effect=lambda name: "synthetic-version-change" if name == "tokenizers" else version(name)):
            fresh = self.Provider()
            self.assertNotEqual(fresh.embedding_space_id, original)
            self.assertEqual(self.manifest(fresh)["runtime"]["tokenizers"], "synthetic-version-change")
            self.assertEqual(provider.embedding_space_id, original)
            self.assertEqual(self.manifest(provider), expected)
        self.assertEqual(self.calls, [])

    def test_31_pinned_missing_asset_never_reacquires(self):
        for readonly in (False, True):
            with self.subTest(readonly=readonly):
                self.write_snapshot(base.REV_A)
                provider = self.Provider()
                identity = provider.embedding_space_id
                self.allow_acquire = True
                (self.snapshot() / "tokenizer.json").unlink()
                before = base.tree_bytes(self.root)
                with self.assertRaises(self.EmbeddingError):
                    provider.embed_query_readonly("query") if readonly else provider.embed(["query"])
                self.assertEqual(provider.embedding_space_id, identity)
                self.assertEqual(self.calls, [])
                self.assertEqual(base.tree_bytes(self.root), before)

    def test_33_invalid_dimension_and_unknown_asset_scheme_fail_typed(self):
        for dimension in (0, -1, "512", None, True):
            with self.subTest(dimension=dimension):
                self.description["dim"] = dimension
                with self.assertRaises(self.EmbeddingError):
                    self.manifest(self.Provider())
        self.description["dim"] = base.DIM
        for asset in ("https://example.invalid/model.bin", "file:///outside.bin", {"uri": "unknown://tensor"}):
            with self.subTest(asset=asset):
                self.description["additional_files"] = [asset]
                with self.assertRaises(self.EmbeddingError):
                    self.manifest(self.Provider())
        self.assertEqual(self.calls, [])

    def replace_with_symlink(self, asset, target):
        probe = self.root / "symlink privilege probe"
        try:
            probe.symlink_to(target)
        except OSError as error:
            self.skipTest(f"symlink creation unavailable; containment evidence incomplete: {error}")
        probe.unlink()
        asset.unlink()
        asset.symlink_to(target)

    def test_35_hub_symlink_to_other_repository_blob_is_rejected(self):
        outside = self.cache / "models--synthetic--other-repository" / "blobs" / "unrelated"
        outside.parent.mkdir(parents=True)
        outside.write_bytes(base.PAYLOADS["onnx/model.onnx"])
        self.replace_with_symlink(self.snapshot() / "onnx/model.onnx", outside)
        before = base.tree_bytes(self.root)
        with self.assertRaises(self.EmbeddingError):
            self.manifest(self.Provider())
        self.assertEqual(self.calls, [])
        self.assertEqual(base.tree_bytes(self.root), before)

SUPPLEMENT_NAMES = [name for name in unittest.defaultTestLoader.getTestCaseNames(SupplementaryAcceptance) if int(name.split("_", 2)[1]) >= 26]
