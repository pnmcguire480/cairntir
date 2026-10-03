"""Public post-review regression for expiry isolation, frozen before repair."""

import hashlib
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from cairntir.access import bind_grant, issue_grant
from cairntir.handoff import compose
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.provenance import WriteProvenance
from cairntir.questions import list_questions, open_question, resolve_question


class QuestionExpiryAcceptance(unittest.TestCase):
    def test_expired_opening_evidence_withholds_only_its_question(self):
        self.check_expiry(False)

    def test_expired_resolution_evidence_never_reopens_or_blocks_other_questions(self):
        self.check_expiry(True)

    def check_expiry(self, resolved):
        with tempfile.TemporaryDirectory() as directory:
            store = DrawerStore(Path(directory) / "questions.db", HashEmbeddingProvider(32))
            try:
                now = datetime.now(UTC)
                evidence = store.add(
                    Drawer(wing="questions", room="work", content="Expiring measurement"),
                    provenance=WriteProvenance.create(
                        host="acceptance",
                        capture_path="fixture",
                        valid_until=now + timedelta(hours=1),
                    ),
                )
                ref = {
                    "drawer_id": evidence.id,
                    "source_identity": store.portable_identity(evidence.id),
                    "content_sha256": hashlib.sha256(evidence.content.encode()).hexdigest(),
                }
                request = {
                    "schema": "cairntir.question-open.v1",
                    "request_id": str(uuid4()),
                    "wing": "questions",
                    "room": "work",
                    "content": "Affected question",
                    "owner": None,
                    "evidence": [] if resolved else [ref],
                }
                affected = open_question(store, request, wing="questions")
                if resolved:
                    resolve_question(
                        store,
                        {
                            "schema": "cairntir.question-resolve.v1",
                            "request_id": str(uuid4()),
                            "wing": "questions",
                            "question_id": affected["question_id"],
                            "question_drawer_id": affected["question_drawer_id"],
                            "question_sha256": affected["question_sha256"],
                            "content": "Declared resolved",
                            "evidence": [ref],
                        },
                        wing="questions",
                    )
                unaffected = open_question(
                    store,
                    {
                        **request,
                        "request_id": str(uuid4()),
                        "content": "Unaffected question",
                        "evidence": [],
                    },
                    wing="questions",
                )
                token = issue_grant(store, scopes=[{"wing": "questions"}], capabilities=["read"])
                reader = bind_grant(store, token)
                before = [
                    tuple(row) for row in store._conn.execute("SELECT * FROM drawers ORDER BY id")
                ]
                with patch("cairntir.questions.datetime", wraps=datetime) as clock:
                    clock.now.return_value = now + timedelta(hours=2)
                    for scope in (store, reader):
                        for historical in (False, True):
                            report = list_questions(
                                scope, wing="questions", include_resolved=historical
                            )
                            self.assertEqual(
                                [entry["question_id"] for entry in report["questions"]],
                                [unaffected["question_id"]],
                            )
                        handoff = compose(scope, wing="questions", budget_chars=16000)
                        section = next(
                            item for item in handoff.sections if item.key == "open_questions"
                        )
                        self.assertEqual(
                            [drawer.id for drawer in section.included],
                            [unaffected["question_drawer_id"]],
                        )
                self.assertEqual(
                    [
                        tuple(row)
                        for row in store._conn.execute("SELECT * FROM drawers ORDER BY id")
                    ],
                    before,
                )
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
