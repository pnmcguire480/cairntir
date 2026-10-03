"""Public independent preimplementation acceptance; temporary stores only."""

import hashlib
import importlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from cairntir.errors import CairntirError, MemoryStoreError
from cairntir.handoff import compose
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer, Layer
from cairntir.provenance import Sensitivity, TrustLevel, Visibility, WriteProvenance


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class CorrectionAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bridge = importlib.import_module("cairntir.obsidian_bridge")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / "memory.db"
        self.store = self.open_store(self.db)

    def open_store(self, db):
        store = DrawerStore(db, HashEmbeddingProvider(dimension=16))
        self.addCleanup(store.close)
        return store

    def source(self, **overrides):
        values = dict(
            wing="cairntir",
            room="notes",
            content="Original evidence.\r\n",
            metadata={"note": "preserve me"},
        )
        values.update(overrides)
        return self.store.add(Drawer(**values))

    def request(self, drawer, content="  Corrected café 🧭.\r\n\r\n"):
        return {
            "schema": "cairntir.obsidian-correction.v1",
            "request_id": str(uuid4()),
            "wing": drawer.wing,
            "source_drawer_id": drawer.id,
            "source_identity": self.store.portable_identity(drawer.id),
            "source_sha256": sha(drawer.content),
            "content": content,
        }

    def apply(self, request, wing="cairntir"):
        return self.bridge.apply_correction(self.store, request, wing=wing)

    def count(self):
        return len(self.store.list_by(limit=None, include_expired=True))

    def assert_rejected(self, request, wing="cairntir"):
        before = self.count()
        with self.assertRaises(self.bridge.CorrectionError):
            self.apply(request, wing)
        self.assertEqual(self.count(), before)

    def test_append_preserves_original_and_exact_correction(self):
        source = self.source()
        provenance = self.store.get_provenance(source.id)
        identity = self.store.portable_identity(source.id)
        request = self.request(source)
        receipt = self.apply(request)
        self.assertEqual(receipt["schema"], "cairntir.obsidian-correction-receipt.v1")
        self.assertEqual(receipt["status"], "committed")
        self.assertEqual(receipt["request_id"], request["request_id"])
        self.assertEqual(receipt["source_drawer_id"], source.id)
        self.assertEqual(receipt["source_identity"], identity)
        self.assertEqual(receipt["content_sha256"], sha(request["content"]))
        self.assertIs(receipt["replayed"], False)
        saved = self.store.get(receipt["correction_drawer_id"])
        self.assertEqual(saved.content, request["content"])
        self.assertEqual(
            (saved.wing, saved.room, saved.layer), (source.wing, source.room, source.layer)
        )
        self.assertEqual(saved.supersedes_id, source.id)
        self.assertEqual(self.store.get(source.id), source)
        self.assertEqual(self.store.get_provenance(source.id), provenance)
        self.assertEqual(self.store.portable_identity(source.id), identity)
        self.assertEqual(self.count(), 2)

    def test_reopened_retry_returns_same_commit_before_stale_check(self):
        source = self.source()
        request = self.request(source)
        first = self.apply(request)
        self.store.close()
        self.store = self.open_store(self.db)
        second = self.apply(dict(request))
        self.assertIs(second["replayed"], True)
        self.assertEqual(
            {k: v for k, v in second.items() if k != "replayed"},
            {k: v for k, v in first.items() if k != "replayed"},
        )
        self.assertEqual(self.count(), 2)

    def test_request_id_cannot_be_reused_for_changed_payload(self):
        source = self.source()
        request = self.request(source)
        self.apply(request)
        self.assert_rejected({**request, "content": "Different correction"})

    def test_new_request_against_historical_source_is_stale(self):
        source = self.source()
        self.apply(self.request(source))
        self.assert_rejected(self.request(source, "A stale conflicting edit"))

    def test_current_correction_can_be_corrected_without_forking(self):
        source = self.source()
        first = self.apply(self.request(source))
        correction = self.store.get(first["correction_drawer_id"])
        second = self.apply(self.request(correction, "Second correction"))
        final = self.store.get(second["correction_drawer_id"])
        self.assertEqual(final.supersedes_id, correction.id)
        self.assertEqual(final.content, "Second correction")
        self.assertEqual(self.count(), 3)

    def test_source_hash_wing_and_missing_id_are_checked(self):
        source = self.source()
        for change in (
            {"source_sha256": "0" * 64},
            {"source_drawer_id": 987654},
            {"wing": "another-wing"},
        ):
            with self.subTest(change=change):
                self.assert_rejected({**self.request(source), **change})
        self.assert_rejected(self.request(source), wing="another-wing")

    def test_equal_local_id_and_hash_in_another_store_is_not_same_source(self):
        source = self.source()
        request = self.request(source)
        other = self.open_store(self.root / "other.db")
        duplicate = other.add(source.model_copy(update={"id": None}))
        self.assertEqual(duplicate.id, source.id)
        self.assertEqual(sha(duplicate.content), request["source_sha256"])
        self.assertNotEqual(other.portable_identity(duplicate.id), request["source_identity"])
        with self.assertRaises(self.bridge.CorrectionError):
            self.bridge.apply_correction(other, request, wing="cairntir")
        self.assertEqual(len(other.list_by(limit=None)), 1)

    def test_untrusted_correction_inherits_privacy_and_layer(self):
        source = self.store.add(
            Drawer(wing="cairntir", room="private", content="Sensitive evidence", layer=Layer.DEEP),
            provenance=WriteProvenance.create(
                host="fixture",
                capture_path="fixture",
                trust=TrustLevel.SYSTEM,
                sensitivity=Sensitivity.SENSITIVE,
                visibility=Visibility.PROJECT,
            ),
        )
        receipt = self.apply(self.request(source))
        provenance = self.store.get_provenance(receipt["correction_drawer_id"])
        self.assertEqual(provenance.trust, TrustLevel.UNTRUSTED)
        self.assertEqual(provenance.sensitivity, Sensitivity.SENSITIVE)
        self.assertEqual(provenance.visibility, Visibility.PROJECT)
        self.assertEqual(self.store.get(receipt["correction_drawer_id"]).layer, Layer.DEEP)

    def test_secret_and_structured_protocol_sources_refused(self):
        secret = self.store.add(
            Drawer(wing="cairntir", room="private", content="Secret fixture"),
            provenance=WriteProvenance.create(
                host="fixture", capture_path="fixture", sensitivity=Sensitivity.SECRET
            ),
        )
        self.assert_rejected(self.request(secret))
        for metadata in (
            {"task_checkpoint": {"task_id": str(uuid4()), "revision": 1}},
            {"kind": "codeglass.walkthrough"},
            {"kind": "discovery"},
        ):
            with self.subTest(metadata=metadata):
                self.assert_rejected(self.request(self.source(metadata=metadata)))

    def test_malformed_requests_never_append(self):
        source = self.source()
        changes = (
            {"schema": "wrong"},
            {"request_id": ""},
            {"request_id": "not-a-uuid"},
            {"source_drawer_id": True},
            {"source_drawer_id": 0},
            {"source_identity": "not-a-uuid"},
            {"source_sha256": "short"},
            {"content": " \r\n"},
            {"content": 42},
        )
        for change in changes:
            with self.subTest(change=change):
                self.assert_rejected({**self.request(source), **change})

    def test_failure_after_append_rolls_back_and_retry_can_commit(self):
        source = self.source()
        request = self.request(source)
        real_add = self.store.add

        def append_then_fail(*args, **kwargs):
            real_add(*args, **kwargs)
            raise MemoryStoreError("synthetic interrupted commit")

        with (
            patch.object(self.store, "add", side_effect=append_then_fail),
            self.assertRaises(CairntirError),
        ):
            self.apply(request)
        self.assertEqual(self.count(), 1)
        receipt = self.apply(request)
        self.assertIs(receipt["replayed"], False)
        self.assertEqual(self.count(), 2)

    def test_resumed_handoff_contains_committed_on_demand_correction(self):
        source = self.source()
        request = self.request(source)
        receipt = self.apply(request)
        self.store.close()
        self.store = self.open_store(self.db)
        drawers = {
            d.id: d for d in compose(self.store, wing="cairntir", budget_chars=20000).all_drawers()
        }
        self.assertIn(receipt["correction_drawer_id"], drawers)
        self.assertEqual(drawers[receipt["correction_drawer_id"]].content, request["content"])


if __name__ == "__main__":
    unittest.main()
