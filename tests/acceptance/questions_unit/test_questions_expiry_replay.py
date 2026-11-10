"""Public temporal replay regression, frozen before expiry replay repair."""

import hashlib
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from cairntir.access import bind_grant, issue_grant, revoke_grant
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.provenance import WriteProvenance
from cairntir.questions import QuestionError, open_question, resolve_question


class QuestionExpiryReplayAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "questions.db"
        self.store = DrawerStore(self.database, HashEmbeddingProvider(32))
        self.addCleanup(lambda: self.store.close())
        self.now = datetime.now(UTC)
        self.provenance = WriteProvenance.create(
            host="acceptance", capture_path="fixture", valid_until=self.now + timedelta(hours=1)
        )

    def reference(self, drawer):
        return {
            "drawer_id": drawer.id,
            "source_identity": self.store.portable_identity(drawer.id),
            "content_sha256": hashlib.sha256(drawer.content.encode()).hexdigest(),
        }

    def opening(self, refs):
        return {
            "schema": "cairntir.question-open.v1",
            "request_id": str(uuid4()),
            "wing": "questions",
            "room": "work",
            "content": "Question exact text",
            "owner": None,
            "evidence": refs,
        }

    def resolution(self, opened, refs):
        return {
            "schema": "cairntir.question-resolve.v1",
            "request_id": str(uuid4()),
            "wing": "questions",
            "question_id": opened["question_id"],
            "question_drawer_id": opened["question_drawer_id"],
            "question_sha256": opened["question_sha256"],
            "content": "Declared supported answer",
            "evidence": refs,
        }

    def rows(self):
        return [tuple(row) for row in self.store._conn.execute("SELECT * FROM drawers ORDER BY id")]

    def restart(self):
        self.store.close()
        self.store = DrawerStore(self.database, HashEmbeddingProvider(32))

    def test_expired_evidence_replays_both_acknowledgements_after_restart_but_no_new_writes(self):
        evidence = self.store.add(
            Drawer(wing="questions", room="work", content="Expiring support"),
            provenance=self.provenance,
        )
        request = self.opening([self.reference(evidence)])
        opened = open_question(self.store, request, wing="questions")
        resolution = self.resolution(opened, request["evidence"])
        resolved = resolve_question(self.store, resolution, wing="questions")
        self.restart()
        before = self.rows()
        with patch("cairntir.questions.datetime", wraps=datetime) as clock:
            clock.now.return_value = self.now + timedelta(hours=2)
            self.assertEqual(
                open_question(self.store, request, wing="questions"), {**opened, "replayed": True}
            )
            self.assertEqual(
                resolve_question(self.store, resolution, wing="questions"),
                {**resolved, "replayed": True},
            )
            for changed in (
                {**request, "request_id": str(uuid4())},
                {**request, "content": "Changed payload"},
            ):
                with self.assertRaises(QuestionError):
                    open_question(self.store, changed, wing="questions")
            for changed in (
                {**resolution, "request_id": str(uuid4())},
                {**resolution, "content": "Changed answer"},
            ):
                with self.assertRaises(QuestionError):
                    resolve_question(self.store, changed, wing="questions")
        self.assertEqual(self.rows(), before)

    def test_expired_legacy_question_replays_its_committed_resolution(self):
        question = self.store.add(
            Drawer(
                wing="questions",
                room="work",
                content="Legacy question",
                metadata={"open_question": True},
            ),
            provenance=self.provenance,
        )
        evidence = self.store.add(
            Drawer(wing="questions", room="work", content="Permanent support")
        )
        reference = self.reference(question)
        opened = {
            "question_id": reference["source_identity"],
            "question_drawer_id": question.id,
            "question_sha256": reference["content_sha256"],
        }
        request = self.resolution(opened, [self.reference(evidence)])
        resolved = resolve_question(self.store, request, wing="questions")
        self.restart()
        before = self.rows()
        with patch("cairntir.questions.datetime", wraps=datetime) as clock:
            clock.now.return_value = self.now + timedelta(hours=2)
            self.assertEqual(
                resolve_question(self.store, request, wing="questions"),
                {**resolved, "replayed": True},
            )
            with self.assertRaises(QuestionError):
                resolve_question(
                    self.store, {**request, "request_id": str(uuid4())}, wing="questions"
                )
        self.assertEqual(self.rows(), before)

    def test_revoked_grant_cannot_replay_committed_opening(self):
        token = issue_grant(
            self.store, scopes=[{"wing": "questions"}], capabilities=["read", "write"]
        )
        reader = bind_grant(self.store, token)
        request = self.opening([])
        open_question(reader, request, wing="questions")
        revoke_grant(self.store, token)
        with self.assertRaises(QuestionError):
            open_question(reader, request, wing="questions")


if __name__ == "__main__":
    unittest.main(verbosity=2)
