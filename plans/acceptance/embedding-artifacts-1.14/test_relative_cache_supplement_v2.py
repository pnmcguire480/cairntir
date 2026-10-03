from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import sys
import unittest

PACKET = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("e22_frozen_fixture", PACKET / "test_embedding_artifacts.py")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


class RelativeCacheAcceptance(base.ArtifactAcceptance):
    def test_relative_cache_remains_absolute_and_pinned_across_cwd_change(self):
        original_cwd = Path.cwd()
        self.addCleanup(os.chdir, original_cwd)
        destination = self.root / "later cwd"
        destination.mkdir()
        for readonly in (False, True):
            with self.subTest(readonly=readonly):
                os.chdir(self.root)
                os.environ["FASTEMBED_CACHE_PATH"] = str(self.cache.relative_to(self.root))
                provider = self.Provider()
                identity = provider.embedding_space_id
                os.chdir(destination)
                before = base.tree_bytes(self.root)
                before_cache = base.tree_bytes(self.cache)
                if readonly:
                    provider.embed_query_readonly("query")
                else:
                    provider.embed(["query"])
                self.assertEqual(self.calls[-1]["cache_dir"], str(self.cache.resolve()))
                self.assertEqual(Path(self.calls[-1]["specific_model_path"]).resolve(), self.snapshot().resolve())
                self.assertEqual(provider.embedding_space_id, identity)
                self.assertEqual(base.tree_bytes(self.cache), before_cache)
                if readonly:
                    self.assertEqual(base.tree_bytes(self.root), before)
                self.assertFalse((destination / self.cache.name).exists())

    def test_changed_environment_does_not_create_unrelated_cache_after_pin(self):
        provider = self.Provider()
        identity = provider.embedding_space_id
        unrelated = self.root / "unrelated cache"
        os.environ["FASTEMBED_CACHE_PATH"] = str(unrelated)
        provider.embed(["query"])
        self.assertEqual(self.calls[-1]["cache_dir"], str(self.cache.resolve()))
        self.assertEqual(provider.embedding_space_id, identity)
        self.assertFalse(unrelated.exists())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    args = parser.parse_args()
    base.SOURCE_ROOT = args.source_root.resolve()
    sys.path.insert(0, str(base.SOURCE_ROOT / "src"))
    sys.dont_write_bytecode = True
    names = [
        "test_relative_cache_remains_absolute_and_pinned_across_cwd_change",
        "test_changed_environment_does_not_create_unrelated_cache_after_pin",
    ]
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(RelativeCacheAcceptance(name) for name in names))
    raise SystemExit(0 if result.wasSuccessful() else 1)
