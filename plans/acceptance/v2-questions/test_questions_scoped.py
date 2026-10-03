"""Public pre-adapter acceptance for scoped durable question lifecycles."""

import hashlib
import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from cairntir.access import bind_grant, issue_grant, revoke_grant
from cairntir.errors import CairntirError
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.questions import list_questions, open_question, resolve_question


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ScopedQuestionAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.owner = DrawerStore(Path(self.temp.name) / "questions.db", HashEmbeddingProvider(32))
        self.addCleanup(self.owner.close)
        self.open_evidence = self.owner.add(
            Drawer(wing="questions", room="open-evidence", content="Opening measurement")
        )
        self.resolve_evidence = self.owner.add(
            Drawer(wing="questions", room="resolve-evidence", content="Resolution measurement")
        )
        self.request = {
            "schema": "cairntir.question-open.v1",
            "request_id": str(uuid4()),
            "wing": "questions",
            "room": "work",
            "content": "Private lifecycle question",
            "owner": "Declared owner",
            "evidence": [self.ref(self.open_evidence)],
        }
        self.opened = open_question(self.owner, self.request, wing="questions")
        self.resolve_request = self.resolution(self.opened)
        self.resolved = resolve_question(self.owner, self.resolve_request, wing="questions")
        self.required = {
            self.open_evidence.id,
            self.resolve_evidence.id,
            self.opened["question_drawer_id"],
            self.resolved["resolution_drawer_id"],
        }

    def ref(self, drawer):
        return {
            "drawer_id": drawer.id,
            "source_identity": self.owner.portable_identity(drawer.id),
            "content_sha256": sha(drawer.content),
        }

    def resolution(self, opened):
        return {
            "schema": "cairntir.question-resolve.v1",
            "request_id": str(uuid4()),
            "wing": "questions",
            "question_id": opened["question_id"],
            "question_drawer_id": opened["question_drawer_id"],
            "question_sha256": opened["question_sha256"],
            "content": "Explicit supported resolution",
            "evidence": [self.ref(self.resolve_evidence)],
        }

    def reader(self, ids=None, expires_at=None):
        token = issue_grant(
            self.owner,
            scopes=[
                {"wing": "questions", "drawer_ids": sorted(self.required if ids is None else ids)}
            ],
            capabilities=["read"],
            expires_at=expires_at,
        )
        return token, bind_grant(self.owner, token)

    def state(self):
        return {
            table: [
                tuple(row)
                for row in self.owner._conn.execute(f"SELECT * FROM {table} ORDER BY rowid")
            ]
            for table in ("drawers", "workflow_runs")
        }

    def test_authorized_reader_sees_owner_committed_lifecycle_without_mutation(self):
        _, reader = self.reader()
        expected = list_questions(self.owner, wing="questions", include_resolved=True)
        before = self.state()
        actual = list_questions(reader, wing="questions", include_resolved=True)
        self.assertEqual(actual, expected)
        self.assertEqual(actual["questions"][0]["status"], "resolved")
        self.assertEqual(list_questions(reader, wing="questions")["questions"], [])
        self.assertEqual(self.state(), before)

    def test_each_hidden_required_record_withholds_complete_lifecycle(self):
        for hidden in sorted(self.required):
            with self.subTest(hidden=hidden):
                _, reader = self.reader(self.required - {hidden})
                for historical in (False, True):
                    report = list_questions(reader, wing="questions", include_resolved=historical)
                    self.assertEqual(report["questions"], [])
                    encoded = json.dumps(report)
                    self.assertNotIn(self.opened["question_id"], encoded)
                    self.assertNotIn(self.request["content"], encoded)
                    self.assertNotIn(self.resolve_request["content"], encoded)

    def test_read_only_grant_cannot_open_or_resolve(self):
        _, reader = self.reader()
        before = self.state()
        with self.assertRaises(CairntirError):
            open_question(reader, {**self.request, "request_id": str(uuid4())}, wing="questions")
        with self.assertRaises(CairntirError):
            resolve_question(
                reader, {**self.resolve_request, "request_id": str(uuid4())}, wing="questions"
            )
        self.assertEqual(self.state(), before)

    def test_revoked_and_expired_reader_fail_on_next_list(self):
        token, revoked = self.reader()
        list_questions(revoked, wing="questions", include_resolved=True)
        revoke_grant(self.owner, token)
        with self.assertRaises(CairntirError):
            list_questions(revoked, wing="questions", include_resolved=True)
        now = datetime.now(UTC)
        _, expiring = self.reader(expires_at=now + timedelta(minutes=1))
        with patch("cairntir.access.datetime", wraps=datetime) as clock:
            clock.now.return_value = now + timedelta(minutes=2)
            with self.assertRaises(CairntirError):
                list_questions(expiring, wing="questions", include_resolved=True)

    def test_legacy_adopted_resolution_is_withheld_when_its_resolution_is_hidden(self):
        legacy = self.owner.add(
            Drawer(
                wing="questions",
                room="work",
                content="Legacy current leaf",
                metadata={"open_question": True},
            )
        )
        opened = {
            "question_id": self.owner.portable_identity(legacy.id),
            "question_drawer_id": legacy.id,
            "question_sha256": sha(legacy.content),
        }
        resolution = resolve_question(self.owner, self.resolution(opened), wing="questions")
        _, full = self.reader(
            {legacy.id, self.resolve_evidence.id, resolution["resolution_drawer_id"]}
        )
        entries = list_questions(full, wing="questions", include_resolved=True)["questions"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["status"], "resolved")
        _, hidden = self.reader({legacy.id, self.resolve_evidence.id})
        self.assertEqual(
            list_questions(hidden, wing="questions", include_resolved=True)["questions"], []
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
