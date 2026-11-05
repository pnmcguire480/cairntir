"""A relative model cache stays absolute and pinned after the directory changes."""

from __future__ import annotations

import os
from pathlib import Path

from . import fixture as base


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
                self.assertEqual(
                    Path(self.calls[-1]["specific_model_path"]).resolve(), self.snapshot().resolve()
                )
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
