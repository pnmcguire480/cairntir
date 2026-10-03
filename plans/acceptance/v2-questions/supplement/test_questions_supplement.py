"""Independent public R08 input and durable-evidence boundaries."""

import hashlib
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from cairntir.access import bind_grant, issue_grant
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.questions import QuestionError, list_questions, open_question, resolve_question


class QuestionBoundarySupplement(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = DrawerStore(Path(self.temp.name) / "questions.db", HashEmbeddingProvider(32))
        self.addCleanup(self.store.close)
        self.support = self.store.add(
            Drawer(wing="questions", room="work", content="Observed measurement")
        )
        self.ref = {
            "drawer_id": self.support.id,
            "source_identity": self.store.portable_identity(self.support.id),
            "content_sha256": hashlib.sha256(self.support.content.encode()).hexdigest(),
        }

    def request(self):
        return {
            "schema": "cairntir.question-open.v1",
            "request_id": str(uuid4()),
            "wing": "questions",
            "room": "work",
            "content": "Why did the relay change?",
            "owner": None,
            "evidence": [self.ref],
        }

    def resolution(self, opened):
        return {
            "schema": "cairntir.question-resolve.v1",
            "request_id": str(uuid4()),
            "wing": "questions",
            "question_id": opened["question_id"],
            "question_drawer_id": opened["question_drawer_id"],
            "question_sha256": opened["question_sha256"],
            "content": "Declared supported answer",
            "evidence": [self.ref],
        }

    def state(self):
        return (
            [tuple(row) for row in self.store._conn.execute("SELECT * FROM drawers ORDER BY id")],
            [
                tuple(row)
                for row in self.store._conn.execute(
                    "SELECT * FROM workflow_runs ORDER BY idempotency_key"
                )
            ],
        )

    def test_malformed_public_requests_fail_typed_without_writes(self):
        request = self.request()
        malformed = [None, [], {}, {**request, "extra": True}]
        malformed.extend(
            {**request, field: value}
            for field, value in (
                ("schema", "wrong"),
                ("content", ""),
                ("content", "  "),
                ("content", 3),
                ("content", "\ud800"),
                ("request_id", 42),
                ("request_id", "not-a-uuid"),
                ("request_id", request["request_id"].upper()),
                ("owner", ""),
                ("owner", False),
                ("room", "bad room"),
                ("evidence", {}),
                ("evidence", [None]),
                ("evidence", [{"drawer_id": 1}]),
                ("evidence", [{**self.ref, "content_sha256": "X" * 64}]),
                ("evidence", [{**self.ref, "content_sha256": None}]),
                ("evidence", [{**self.ref, "source_identity": False}]),
                ("evidence", [{**self.ref, "drawer_id": 1.5}]),
            )
        )
        before = self.state()
        for payload in malformed:
            with self.subTest(payload=repr(payload)), self.assertRaises(QuestionError):
                open_question(self.store, payload, wing="questions")
            self.assertEqual(self.state(), before)

    def test_register_options_fail_typed(self):
        before = self.state()
        for value in (0, 1, None, "false", []):
            with self.subTest(value=value), self.assertRaises(QuestionError):
                list_questions(self.store, wing="questions", include_resolved=value)
        with self.assertRaises(QuestionError):
            list_questions(self.store, wing="bad wing")
        self.assertEqual(self.state(), before)

    def test_committed_receipt_mismatch_cannot_be_listed_or_replayed(self):
        request = self.request()
        opened = open_question(self.store, request, wing="questions")
        key = "question:" + request["request_id"]
        raw = self.store._conn.execute(
            "SELECT result FROM workflow_runs WHERE idempotency_key=?", (key,)
        ).fetchone()[0]
        for field, value in (("question_sha256", "0" * 64), ("question_id", str(uuid4()))):
            with self.subTest(field=field):
                damaged = json.loads(raw)
                damaged[field] = value
                self.store._conn.execute(
                    "UPDATE workflow_runs SET result=? WHERE idempotency_key=?",
                    (json.dumps(damaged), key),
                )
                self.store._conn.commit()
                before = self.state()
                with self.assertRaises(QuestionError):
                    list_questions(self.store, wing="questions", include_resolved=True)
                with self.assertRaises(QuestionError):
                    open_question(self.store, request, wing="questions")
                self.assertEqual(self.state(), before)
                self.store._conn.execute(
                    "UPDATE workflow_runs SET result=? WHERE idempotency_key=?", (raw, key)
                )
                self.store._conn.commit()
        self.assertEqual(
            list_questions(self.store, wing="questions")["questions"][0]["question_id"],
            opened["question_id"],
        )

    def test_changed_original_content_or_room_is_not_trusted_as_committed(self):
        request = self.request()
        opened = open_question(self.store, request, wing="questions")
        identity = opened["question_drawer_id"]
        for field, changed, original in (
            ("content", "Different original", request["content"]),
            ("room", "other-room", request["room"]),
        ):
            with self.subTest(field=field):
                sql = (
                    "UPDATE drawers SET content=? WHERE id=?"
                    if field == "content"
                    else "UPDATE drawers SET room=? WHERE id=?"
                )
                self.store._conn.execute(sql, (changed, identity))
                self.store._conn.commit()
                with self.assertRaises(QuestionError):
                    list_questions(self.store, wing="questions", include_resolved=True)
                self.store._conn.execute(sql, (original, identity))
                self.store._conn.commit()

    def test_corrupted_resolution_text_or_ancestry_does_not_close_question(self):
        opened = open_question(self.store, self.request(), wing="questions")
        request = self.resolution(opened)
        receipt = resolve_question(self.store, request, wing="questions")
        identity = receipt["resolution_drawer_id"]
        for sql, changed, original in (
            ("UPDATE drawers SET content=? WHERE id=?", "Changed answer", request["content"]),
            (
                "UPDATE drawers SET supersedes_id=? WHERE id=?",
                self.support.id,
                opened["question_drawer_id"],
            ),
        ):
            with self.subTest(sql=sql):
                self.store._conn.execute(sql, (changed, identity))
                self.store._conn.commit()
                with self.assertRaises(QuestionError):
                    list_questions(self.store, wing="questions", include_resolved=True)
                with self.assertRaises(QuestionError):
                    resolve_question(self.store, request, wing="questions")
                self.store._conn.execute(sql, (original, identity))
                self.store._conn.commit()

    def test_secret_required_evidence_withholds_whole_group_and_disallows_replay(self):
        request = self.request()
        opened = open_question(self.store, request, wing="questions")
        resolved = resolve_question(self.store, self.resolution(opened), wing="questions")
        other = open_question(self.store, {**self.request(), "evidence": []}, wing="questions")
        for identity in (
            self.support.id,
            opened["question_drawer_id"],
            resolved["resolution_drawer_id"],
        ):
            with self.subTest(identity=identity):
                original = self.store._conn.execute(
                    "SELECT provenance FROM drawers WHERE id=?", (identity,)
                ).fetchone()[0]
                damaged = json.loads(original)
                damaged["sensitivity"] = "secret"
                self.store._conn.execute(
                    "UPDATE drawers SET provenance=? WHERE id=?", (json.dumps(damaged), identity)
                )
                self.store._conn.commit()
                report = list_questions(self.store, wing="questions", include_resolved=True)
                self.assertEqual(
                    [entry["question_id"] for entry in report["questions"]], [other["question_id"]]
                )
                if identity != resolved["resolution_drawer_id"]:
                    with self.assertRaises(QuestionError):
                        open_question(self.store, request, wing="questions")
                self.store._conn.execute(
                    "UPDATE drawers SET provenance=? WHERE id=?", (original, identity)
                )
                self.store._conn.commit()

    def test_authorized_scoped_writer_can_resolve_and_owner_sees_same_history(self):
        token = issue_grant(
            self.store, scopes=[{"wing": "questions"}], capabilities=["read", "write"]
        )
        writer = bind_grant(self.store, token)
        request = self.request()
        opened = open_question(writer, request, wing="questions")
        resolution = self.resolution(opened)
        resolved = resolve_question(writer, resolution, wing="questions")
        self.assertEqual(
            resolve_question(writer, resolution, wing="questions"), {**resolved, "replayed": True}
        )
        self.assertEqual(
            list_questions(writer, wing="questions", include_resolved=True),
            list_questions(self.store, wing="questions", include_resolved=True),
        )
        self.assertEqual(list_questions(self.store, wing="questions")["questions"], [])

    def test_unpersisted_append_result_cannot_acknowledge_a_commit(self):
        before = self.state()
        with patch.object(
            self.store,
            "add",
            return_value=Drawer(wing="questions", room="work", content="No persisted ID"),
        ):
            with self.assertRaises(QuestionError):
                open_question(self.store, self.request(), wing="questions")
        self.assertEqual(self.state(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
