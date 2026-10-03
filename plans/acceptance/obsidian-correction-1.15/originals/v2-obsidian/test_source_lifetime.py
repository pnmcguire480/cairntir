"""Public supplemental lifetime checks; authored after core implementation."""

import hashlib
import importlib
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.provenance import WriteProvenance


class SourceLifetimeAcceptance(unittest.TestCase):
    def setUp(self):
        self.bridge = importlib.import_module("cairntir.obsidian_bridge")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = DrawerStore(
            Path(self.tmp.name) / "memory.db", HashEmbeddingProvider(dimension=16)
        )
        self.addCleanup(self.store.close)

    def source(self, start, end):
        return self.store.add(
            Drawer(wing="cairntir", room="notes", content="Time-limited original"),
            provenance=WriteProvenance.create(
                host="fixture", capture_path="fixture", valid_from=start, valid_until=end
            ),
        )

    def request(self, source):
        return {
            "schema": "cairntir.obsidian-correction.v1",
            "request_id": str(uuid4()),
            "wing": source.wing,
            "source_drawer_id": source.id,
            "source_identity": self.store.portable_identity(source.id),
            "source_sha256": hashlib.sha256(source.content.encode()).hexdigest(),
            "content": "Time-limited correction",
        }

    def test_expired_and_not_yet_valid_sources_cannot_be_corrected(self):
        now = datetime.now(UTC)
        for start, end in (
            (now - timedelta(days=2), now - timedelta(days=1)),
            (now + timedelta(days=1), now + timedelta(days=2)),
        ):
            with self.subTest(start=start, end=end):
                source = self.source(start, end)
                count = len(self.store.list_by(limit=None, include_expired=True))
                with self.assertRaises(self.bridge.CorrectionError):
                    self.bridge.apply_correction(self.store, self.request(source), wing="cairntir")
                self.assertEqual(len(self.store.list_by(limit=None, include_expired=True)), count)

    def test_successor_inherits_exact_validity_window(self):
        now = datetime.now(UTC)
        start, end = now - timedelta(days=1), now + timedelta(days=1)
        source = self.source(start, end)
        receipt = self.bridge.apply_correction(self.store, self.request(source), wing="cairntir")
        provenance = self.store.get_provenance(receipt["correction_drawer_id"])
        self.assertEqual((provenance.valid_from, provenance.valid_until), (start, end))

    def test_acknowledged_retry_remains_available_after_validity_expiry(self):
        now = datetime.now(UTC)
        source = self.source(now - timedelta(days=1), now + timedelta(days=1))
        request = self.request(source)
        first = self.bridge.apply_correction(self.store, request, wing="cairntir")

        class Later(datetime):
            @classmethod
            def now(cls, tz=None):
                return now + timedelta(days=2)

        with patch.object(self.bridge, "datetime", Later):
            replay = self.bridge.apply_correction(self.store, request, wing="cairntir")
        self.assertIs(replay["replayed"], True)
        self.assertEqual(replay["correction_drawer_id"], first["correction_drawer_id"])
        self.assertEqual(len(self.store.list_by(limit=None, include_expired=True)), 2)


if __name__ == "__main__":
    unittest.main()
