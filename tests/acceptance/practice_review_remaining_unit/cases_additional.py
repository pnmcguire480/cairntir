"""Additive probes: approval isolation, interleaved clients and result forgery."""

import dataclasses
import json
from unittest.mock import patch

from practice_review_edges_unit.fixtures_v2 import WING, Harness, api

from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore


class ApprovalIsolation(Harness):
    def test_fresh_corroborated_requires_exact_true_callback(self):
        proposal = self.book.propose(wing=WING, spec=self.spec)
        evaluated = self.book.evaluate(proposal.drawer_id, evaluator_id="local")
        for callback in (None, lambda request: 1, lambda request: "yes", lambda request: False):
            denied = api.ProcedureBook(self.store, self.registry, callback)
            self.reject_atomic(
                lambda: denied.promote(evaluated.current_id, evaluation_id=evaluated.drawer_id)  # noqa: B023 - Called synchronously.
            )
        self.assertEqual(
            self.book.promote(evaluated.current_id, evaluation_id=evaluated.drawer_id).state,
            "promoted",
        )


class InterleavedAndAdditionalR18(Harness):
    def test_two_client_stale_correction_and_completion(self):
        first = self.record()
        before_assessment = self.assess()
        with DrawerStore(self.path, HashEmbeddingProvider(dimension=32)) as second_store:
            second = api.ProcedureBook(second_store, self.registry)
            newer = second.record_observation(
                self.target.drawer_id,
                observation=self.obs(practice_impact=7),
                supersedes_id=first.drawer_id,
            )
            self.reject_atomic(
                lambda: self.book.record_observation(
                    self.target.drawer_id,
                    observation=self.obs(practice_impact=8),
                    supersedes_id=first.drawer_id,
                )
            )
            self.reject_atomic(lambda: self.complete(before_assessment))
            fresh = self.assess()
            review = second.complete_review(
                self.target.drawer_id,
                assessment=fresh,
                reviewer="other",
                decision="defer",
                rationale="interleaved synthetic",
                next_review_due="2024-04-03",
            )
            self.reject_atomic(lambda: self.complete(fresh))
            self.assertEqual(self.book.get_review(review.drawer_id), review)
            self.assertEqual(self.assess().observation_ids, (newer.drawer_id,))

    def test_source_content_and_source_metadata_tamper(self):
        one = self.record()
        assessment = self.assess()
        self.store._conn.execute("UPDATE drawers SET content='changed' WHERE id=?", (self.source,))
        self.store._conn.commit()
        self.reject_atomic(lambda: self.complete(assessment))
        self.reject_atomic(lambda: self.book.get_observation(one.drawer_id))

    def test_review_ledger_wrong_hash_and_extra_shape(self):
        self.record()
        receipt = self.complete(self.assess())
        raw = self.ledger(receipt.drawer_id)
        payload = json.loads(raw)

        def forge(value):
            if isinstance(value, dict):
                for name, item in value.items():
                    if name == "record_sha256":
                        value[name] = "0" * 64
                        return True
                    if forge(item):
                        return True
            return False

        self.assertTrue(forge(payload))
        self.setledger(receipt.drawer_id, json.dumps(payload))
        self.reject_atomic(lambda: self.book.get_review(receipt.drawer_id))
        self.reject_atomic(lambda: self.assess())
        self.setledger(receipt.drawer_id, raw)
        payload = json.loads(raw)
        payload["unexpected"] = "extra"
        self.setledger(receipt.drawer_id, json.dumps(payload))
        self.reject_atomic(lambda: self.book.get_review(receipt.drawer_id))

    def test_replay_forgery_primitive_boolean_and_same_hash(self):
        self.record()
        assessment = self.assess()
        receipt = self.complete(assessment)
        forged = dataclasses.replace(
            assessment,
            metrics=(  # noqa: RUF005 - Preserve original tuple oracle.
                dataclasses.replace(
                    assessment.metrics[0],
                    observation_count=True,
                    trigger_known=True,
                    triggered_count=True,
                ),
            )
            + assessment.metrics[1:],
        )
        self.assertEqual(forged.assessment_sha256, assessment.assessment_sha256)
        self.reject_atomic(lambda: self.complete(forged))
        self.assertEqual(self.complete(assessment), receipt)

    def test_add_failure_and_clean_retry(self):
        original = self.store.add

        def fail_after_add(*args, **kwargs):
            original(*args, **kwargs)
            raise OSError("injected loss after drawer write")

        before = self.counts()
        with patch.object(self.store, "add", side_effect=fail_after_add):  # noqa: SIM117 - Preserve original context ordering.
            with self.assertRaises(OSError):
                self.record()
        self.assertEqual(before, self.counts())
        one = self.record()
        assessment = self.assess()
        before = self.counts()
        with patch.object(self.store, "add", side_effect=fail_after_add):  # noqa: SIM117 - Preserve original context ordering.
            with self.assertRaises(OSError):
                self.complete(assessment)
        self.assertEqual(before, self.counts())
        self.complete(assessment)
        self.assertEqual(self.book.get_observation(one.drawer_id), one)

    def test_predecessor_and_drawer_boolean_id_forgery(self):
        one = self.record()
        for key in (True, 0, 2**63, "1"):
            self.reject_atomic(lambda: self.book.record_observation(key, observation=self.obs()))  # noqa: B023 - Called synchronously.
            self.reject_atomic(lambda: self.book.get_observation(key))  # noqa: B023 - Called synchronously.
            self.reject_atomic(lambda: self.book.get_review(key))  # noqa: B023 - Called synchronously.
            self.reject_atomic(
                lambda: self.book.record_observation(
                    self.target.drawer_id,
                    observation=self.obs(practice_impact=8),
                    supersedes_id=key,  # noqa: B023 - Called synchronously.
                )
            )
        self.assertEqual(self.book.get_observation(one.drawer_id), one)
