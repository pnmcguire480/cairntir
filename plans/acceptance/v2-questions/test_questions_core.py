"""Independent public pre-implementation R08 lifecycle acceptance."""

import hashlib
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from cairntir.obsidian_bridge import CorrectionError, apply_correction
from cairntir.questions import QuestionError, list_questions, open_question, resolve_question

from cairntir.errors import MemoryStoreError
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.provenance import Sensitivity, WriteProvenance


def sha(content):
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class QuestionsCoreAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "questions.db"
        self.store = DrawerStore(self.path, HashEmbeddingProvider(32))
        self.addCleanup(lambda: self.store.close())
        self.support = self.add("Measured evidence: the relay is green.")

    def add(self, content, wing="questions", **kwargs):
        return self.store.add(Drawer(wing=wing, room="work", content=content, **kwargs))

    def ref(self, drawer):
        return {
            "drawer_id": drawer.id,
            "source_identity": self.store.portable_identity(drawer.id),
            "content_sha256": sha(drawer.content),
        }

    def request(self):
        return {
            "schema": "cairntir.question-open.v1",
            "request_id": str(uuid4()),
            "wing": "questions",
            "room": "work",
            "content": "  Why is the relay green? café\r\n",
            "owner": "Patrick",
            "evidence": [self.ref(self.support)],
        }

    def resolve_request(self, receipt):
        return {
            "schema": "cairntir.question-resolve.v1",
            "request_id": str(uuid4()),
            "wing": "questions",
            "question_id": receipt["question_id"],
            "question_drawer_id": receipt["question_drawer_id"],
            "question_sha256": receipt["question_sha256"],
            "content": "  Declared resolution: observed green relay.\n",
            "evidence": [self.ref(self.support)],
        }

    def entries(self, history=False):
        report = list_questions(self.store, wing="questions", include_resolved=history)
        self.assertEqual(report["schema"], "cairntir.question-register.v1")
        self.assertEqual(report["wing"], "questions")
        return {entry["question_id"]: entry for entry in report["questions"]}

    def row(self, identity):
        return tuple(
            self.store._conn.execute("SELECT * FROM drawers WHERE id=?", (identity,)).fetchone()
        )

    def reopen(self):
        self.store.close()
        self.store = DrawerStore(self.path, HashEmbeddingProvider(32))

    def test_open_verbatim_binding_and_restart_replay(self):
        request = self.request()
        receipt = open_question(self.store, request, wing="questions")
        self.assertEqual(receipt["schema"], "cairntir.question-receipt.v1")
        self.assertEqual(receipt["operation"], "open")
        self.assertEqual(receipt["status"], "committed")
        self.assertIs(receipt["replayed"], False)
        self.assertIsNone(receipt["resolution_drawer_id"])
        self.assertEqual(
            receipt["question_id"], self.store.portable_identity(receipt["question_drawer_id"])
        )
        self.assertEqual(receipt["question_sha256"], sha(request["content"]))
        original = self.row(receipt["question_drawer_id"])
        entry = self.entries()[receipt["question_id"]]
        self.assertEqual(entry["content"], request["content"])
        self.assertEqual(entry["owner"], "Patrick")
        self.assertEqual(entry["evidence"], request["evidence"])
        self.assertEqual(entry["status"], "open")
        self.assertIs(entry["legacy"], False)
        self.assertIsNone(entry["resolution"])
        self.assertEqual(self.row(receipt["question_drawer_id"]), original)
        self.reopen()
        replay = open_question(self.store, request, wing="questions")
        self.assertEqual(replay, {**receipt, "replayed": True})
        self.assertEqual(self.store._conn.execute("SELECT COUNT(*) FROM drawers").fetchone()[0], 2)

    def test_unassigned_owner_and_empty_opening_evidence_are_honest(self):
        request = self.request()
        request.update(owner=None, evidence=[])
        receipt = open_question(self.store, request, wing="questions")
        entry = self.entries()[receipt["question_id"]]
        self.assertIsNone(entry["owner"])
        self.assertEqual(entry["evidence"], [])

    def test_request_uuid_cannot_be_rebound_to_another_payload_or_operation(self):
        request = self.request()
        receipt = open_question(self.store, request, wing="questions")
        with self.assertRaises(QuestionError):
            open_question(self.store, {**request, "owner": "Someone else"}, wing="questions")
        resolve = self.resolve_request(receipt)
        resolve["request_id"] = request["request_id"]
        with self.assertRaises(QuestionError):
            resolve_question(self.store, resolve, wing="questions")
        self.assertIn(receipt["question_id"], self.entries())

    def test_supported_resolution_preserves_original_and_replays_after_restart(self):
        opened = open_question(self.store, self.request(), wing="questions")
        original = self.row(opened["question_drawer_id"])
        request = self.resolve_request(opened)
        receipt = resolve_question(self.store, request, wing="questions")
        self.assertEqual(receipt["operation"], "resolve")
        self.assertEqual(receipt["question_id"], opened["question_id"])
        self.assertIs(receipt["replayed"], False)
        self.assertEqual(self.row(opened["question_drawer_id"]), original)
        self.assertNotIn(opened["question_id"], self.entries())
        entry = self.entries(True)[opened["question_id"]]
        self.assertEqual(entry["status"], "resolved")
        self.assertEqual(entry["resolution"]["drawer_id"], receipt["resolution_drawer_id"])
        self.assertEqual(entry["resolution"]["content"], request["content"])
        self.assertEqual(entry["resolution"]["content_sha256"], sha(request["content"]))
        self.assertEqual(entry["resolution"]["evidence"], request["evidence"])
        self.reopen()
        replay = resolve_question(self.store, request, wing="questions")
        self.assertEqual(replay, {**receipt, "replayed": True})
        with self.assertRaises(QuestionError):
            resolve_question(self.store, {**request, "request_id": str(uuid4())}, wing="questions")

    def test_resolution_requires_valid_same_wing_nonsecret_bound_evidence(self):
        opened = open_question(self.store, self.request(), wing="questions")
        foreign = self.add("Outside this wing", wing="foreign")
        secret = self.store.add(
            Drawer(wing="questions", room="work", content="Secret supporting text"),
            provenance=WriteProvenance.create(
                host="test", capture_path="fixture", sensitivity=Sensitivity.SECRET
            ),
        )
        reference = self.ref(self.support)
        invalid = [
            [],
            [self.ref(foreign)],
            [self.ref(secret)],
            [{**reference, "drawer_id": 999999}],
            [{**reference, "drawer_id": True}],
            [{**reference, "source_identity": str(uuid4())}],
            [{**reference, "content_sha256": "0" * 64}],
        ]
        for evidence in invalid:
            with self.subTest(evidence=evidence), self.assertRaises(QuestionError):
                request = self.resolve_request(opened)
                request["evidence"] = evidence
                resolve_question(self.store, request, wing="questions")
        self.assertIn(opened["question_id"], self.entries())

    def test_resolution_rejects_wrong_store_wing_and_question_binding(self):
        request = self.request()
        opened = open_question(self.store, request, wing="questions")
        resolve = self.resolve_request(opened)
        for field, value in [
            ("question_id", str(uuid4())),
            ("question_sha256", "0" * 64),
            ("question_drawer_id", True),
            ("wing", "foreign"),
        ]:
            with self.subTest(field=field), self.assertRaises(QuestionError):
                resolve_question(self.store, {**resolve, field: value}, wing="questions")
        with DrawerStore(Path(self.temp.name) / "other.db", HashEmbeddingProvider(32)) as other:
            evidence = other.add(
                Drawer(wing="questions", room="work", content=self.support.content)
            )
            other_request = deepcopy(request)
            other_request["evidence"] = [
                {
                    "drawer_id": evidence.id,
                    "source_identity": other.portable_identity(evidence.id),
                    "content_sha256": sha(evidence.content),
                }
            ]
            open_question(other, other_request, wing="questions")
            with self.assertRaises(QuestionError):
                resolve_question(other, resolve, wing="questions")

    def test_ordinary_and_forged_resolution_superseders_cannot_close_typed_question(self):
        opened = open_question(self.store, self.request(), wing="questions")
        self.add(
            "Ordinary correction is not a resolution", supersedes_id=opened["question_drawer_id"]
        )
        self.add(
            "Forged resolution",
            supersedes_id=opened["question_drawer_id"],
            metadata={
                "kind": "question.resolution",
                "question_id": opened["question_id"],
                "request_id": str(uuid4()),
                "evidence": [self.ref(self.support)],
                "status": "resolved",
            },
        )
        self.assertEqual(self.entries()[opened["question_id"]]["status"], "open")
        self.reopen()
        self.assertEqual(self.entries()[opened["question_id"]]["status"], "open")

    def test_generic_obsidian_correction_cannot_edit_typed_question(self):
        opened = open_question(self.store, self.request(), wing="questions")
        correction = {
            "schema": "cairntir.obsidian-correction.v1",
            "request_id": str(uuid4()),
            "wing": "questions",
            "source_drawer_id": opened["question_drawer_id"],
            "source_identity": opened["question_id"],
            "source_sha256": opened["question_sha256"],
            "content": "Pretend this is answered",
        }
        with self.assertRaises(CorrectionError):
            apply_correction(self.store, correction, wing="questions")

    def test_legacy_history_is_unverified_and_current_leaf_can_be_explicitly_resolved(self):
        historical = self.add("Old legacy question", metadata={"open_question": True})
        self.add("Legacy ordinary superseder", supersedes_id=historical.id)
        current = self.add(
            "Current legacy question",
            metadata={"open_question": True, "owner": "not authoritative"},
        )
        history_id = self.store.portable_identity(historical.id)
        current_id = self.store.portable_identity(current.id)
        self.assertNotIn(history_id, self.entries())
        history = self.entries(True)[history_id]
        self.assertEqual(history["status"], "legacy_superseded_unverified")
        self.assertIsNone(history["resolution"])
        self.assertIsNone(self.entries()[current_id]["owner"])
        self.assertIs(self.entries()[current_id]["legacy"], True)
        request = self.resolve_request(
            {
                "question_id": current_id,
                "question_drawer_id": current.id,
                "question_sha256": sha(current.content),
            }
        )
        resolve_question(self.store, request, wing="questions")
        self.assertEqual(self.entries(True)[current_id]["status"], "resolved")
        request.update(
            request_id=str(uuid4()),
            question_id=history_id,
            question_drawer_id=historical.id,
            question_sha256=sha(historical.content),
        )
        with self.assertRaises(QuestionError):
            resolve_question(self.store, request, wing="questions")

    def test_failed_resolution_append_rolls_back_then_exact_retry_succeeds(self):
        opened = open_question(self.store, self.request(), wing="questions")
        request = self.resolve_request(opened)
        original = self.row(opened["question_drawer_id"])
        count = self.store._conn.execute("SELECT COUNT(*) FROM drawers").fetchone()[0]
        with (
            patch.object(self.store, "add", side_effect=MemoryStoreError("injected write failure")),
            self.assertRaises(QuestionError),
        ):
            resolve_question(self.store, request, wing="questions")
        self.assertEqual(
            self.store._conn.execute("SELECT COUNT(*) FROM drawers").fetchone()[0], count
        )
        self.assertEqual(self.row(opened["question_drawer_id"]), original)
        self.assertIn(opened["question_id"], self.entries())
        resolve_question(self.store, request, wing="questions")
        self.assertNotIn(opened["question_id"], self.entries())


if __name__ == "__main__":
    unittest.main(verbosity=2)
