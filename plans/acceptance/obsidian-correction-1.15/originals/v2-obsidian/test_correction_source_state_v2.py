"""Public preimplementation source-state supplement; no production stores."""

import hashlib
import importlib
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer


class SourceStateAcceptance(unittest.TestCase):
    def setUp(self):
        self.bridge = importlib.import_module("cairntir.obsidian_bridge")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "memory.db"
        self.store = DrawerStore(self.db, HashEmbeddingProvider(dimension=16))
        self.addCleanup(self.store.close)

    def request(self, drawer):
        return {
            "schema": "cairntir.obsidian-correction.v1",
            "request_id": str(uuid4()),
            "wing": drawer.wing,
            "source_drawer_id": drawer.id,
            "source_identity": self.store.portable_identity(drawer.id),
            "source_sha256": hashlib.sha256(drawer.content.encode()).hexdigest(),
            "content": "A new append-only correction",
        }

    def test_correction_and_retry_never_change_original_sql_row(self):
        source = self.store.add(Drawer(wing="cairntir", room="notes", content="Original"))
        request = self.request(source)
        with closing(sqlite3.connect(self.db)) as connection:
            before = connection.execute("SELECT * FROM drawers WHERE id=?", (source.id,)).fetchone()
        self.bridge.apply_correction(self.store, request, wing="cairntir")
        self.bridge.apply_correction(self.store, request, wing="cairntir")
        with closing(sqlite3.connect(self.db)) as connection:
            after = connection.execute("SELECT * FROM drawers WHERE id=?", (source.id,)).fetchone()
        self.assertEqual(after, before)

    def test_prediction_protocol_fields_require_their_own_workflow(self):
        for field in ("claim", "predicted_outcome", "observed_outcome", "delta"):
            with self.subTest(field=field):
                source = self.store.add(
                    Drawer(
                        wing="cairntir",
                        room="notes",
                        content="Structured original",
                        **{field: "Protocol field"},
                    )
                )
                request = self.request(source)
                count = len(self.store.list_by(limit=None))
                with self.assertRaises(self.bridge.CorrectionError):
                    self.bridge.apply_correction(self.store, request, wing="cairntir")
                self.assertEqual(len(self.store.list_by(limit=None)), count)


if __name__ == "__main__":
    unittest.main()
