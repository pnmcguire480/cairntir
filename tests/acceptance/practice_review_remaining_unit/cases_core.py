"""Independent R18 adversarial probes, synthetic stores, no production access."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import unittest
from unittest.mock import patch

from practice_review_edges_unit.fixtures_v2 import Harness

from cairntir import procedures as api
from cairntir.access import AccessDenied, bind_grant, issue_grant
from cairntir.errors import MemoryStoreError
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore

WING = "r18-redteam-synthetic"


class BaselineControls(Harness):
    def test_legacy_bytes_and_exact_approval(self):
        legacy = dataclasses.replace(self.spec, governance=None)
        first = self.book.propose(wing=WING, spec=legacy)
        payload = dataclasses.asdict(legacy)
        del payload["governance"]
        canonical = lambda v: json.dumps(  # noqa: E731 - Preserve original identity oracle.
            v, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        )
        self.assertEqual(
            first.revision_sha256,
            hashlib.sha256(canonical({"wing": WING, "spec": payload}).encode()).hexdigest(),
        )
        self.assertEqual(
            self.store.get(first.drawer_id).content,
            "Discovery: Synthetic practice\nState: candidate\n\n" + canonical(payload),
        )
        self.assertEqual(len(self.approvals), 1)
        denied = api.ProcedureBook(self.store, self.registry)
        self.reject_atomic(
            lambda: denied.promote(
                self.evaluation.current_id, evaluation_id=self.evaluation.drawer_id
            )
        )
        self.reject_atomic(
            lambda: self.book.promote(first.drawer_id, evaluation_id=self.evaluation.drawer_id)
        )

    def test_copied_procedure_is_not_authority(self):
        original = self.store.get(self.target.drawer_id)
        fake = self.add(original.content, room="discoveries", metadata=original.metadata)
        self.reject_atomic(lambda: self.book.rollback(fake, reason="forged metadata"))


class R18Probes(Harness):
    def test_api_present(self):
        for name in (
            "PracticeObservation",
            "PracticeReviewPolicy",
            "PracticeObservationReceipt",
            "PracticeMetrics",
            "PracticeReviewAssessment",
            "PracticeReviewReceipt",
        ):
            self.assertTrue(hasattr(api, name), name)

    def test_observation_primitives_and_atomic_validation(self):
        bad = {
            "event_id": ["", " blank ", "x" * 257, "bad\ud800", 1],
            "observed_on": ["20240229", "2024-W09-4", "2024-02-30", "9999-01-01", True],
            "origin": ["field", "OBSERVED", None],
            "triggered": [1, "true"],
            "false_positive": [1, "false"],
            "overridden": [1],
            "baseline_impact": [True, float("nan"), float("inf"), 10**1000],
            "practice_impact": [float("-inf"), "5"],
            "impact_unit": ["", " minutes", "x" * 65, "bad\ud800"],
            "evidence_ids": [
                (),
                (True,),
                (0,),
                (2**63,),
                (self.source, self.source),
                tuple(range(1, 66)),
            ],
        }
        for field, values in bad.items():
            for value in values:
                with self.subTest(field=field, value=str(value)[:80]):
                    self.reject_atomic(
                        lambda: self.book.record_observation(
                            self.target.drawer_id,
                            observation=self.obs(**{field: value}),  # noqa: B023 - Called synchronously.
                        )
                    )
        for fields in (
            {"triggered": False},
            {"triggered": None},
            {"baseline_impact": None},
            {"baseline_impact": None, "practice_impact": None},
            {"impact_unit": None},
        ):
            with self.subTest(fields=fields):
                self.reject_atomic(
                    lambda: self.book.record_observation(
                        self.target.drawer_id,
                        observation=self.obs(**fields),  # noqa: B023 - Called synchronously.
                    )
                )

    def test_policy_and_calendar_validation(self):
        bad = (
            {"minimum_observations": True},
            {"minimum_observations": 0},
            {"minimum_observations": 2**63},
            {"minimum_trigger_rate": None},
            {"minimum_trigger_rate": True},
            {"minimum_trigger_rate": -0.1},
            {"maximum_override_rate": float("nan")},
            {"minimum_mean_impact": 1},
            {"impact_unit": "minutes"},
            {"minimum_mean_impact": 10**1000, "impact_unit": "minutes"},
        )
        for fields in bad:
            with self.subTest(fields=str(fields)[:80]):
                self.reject_atomic(lambda: self.assess(policy=self.policy(**fields)))  # noqa: B023 - Called synchronously.
        for fields in (
            {"period_start": "20240201"},
            {"as_of": "2024-02-01"},
            {"period_end": "2024-02-01"},
            {"as_of": "2024-02-30"},
            {"period_end": True},
        ):
            with self.subTest(fields=fields):
                self.reject_atomic(lambda: self.assess(**fields))  # noqa: B023 - Called synchronously.

    def test_detached_frozen_values_and_source_binding(self):
        ids = [self.source]
        observation = self.obs(evidence_ids=ids)
        ids.append(99999)
        receipt = self.book.record_observation(self.target.drawer_id, observation=observation)
        self.assertEqual(receipt.observation.evidence_ids, (self.source,))
        self.assertEqual(len(receipt.evidence_sha256), 1)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            receipt.observation.origin = "simulated"
        self.store._conn.execute(
            "UPDATE drawers SET content='changed source' WHERE id=?", (self.source,)
        )
        self.store._conn.commit()
        self.reject_atomic(lambda: self.book.get_observation(receipt.drawer_id))
        self.reject_atomic(lambda: self.assess())

    def test_foreign_missing_and_denied_evidence(self):
        foreign = self.add("foreign", wing="other")
        for key in (foreign, 2**62):
            self.reject_atomic(lambda: self.record(evidence_ids=(key,)))  # noqa: B023 - Called synchronously.
        token = issue_grant(
            self.store,
            scopes=[{"wing": WING, "rooms": ["discoveries", "practice-reviews"]}],
            capabilities=["read", "write"],
        )
        scoped = api.ProcedureBook(bind_grant(self.store, token), self.registry)
        self.reject_atomic(
            lambda: scoped.record_observation(self.target.drawer_id, observation=self.obs()),
            AccessDenied,
        )

    def test_partial_visibility_cannot_produce_complete_metrics(self):
        receipt = self.record()
        token = issue_grant(
            self.store,
            scopes=[{"wing": WING, "rooms": ["discoveries", "cases"]}],
            capabilities=["read", "write"],
        )
        scoped = api.ProcedureBook(bind_grant(self.store, token), self.registry)
        with self.assertRaises(AccessDenied):
            scoped.get_observation(receipt.drawer_id)
        with self.assertRaises(AccessDenied):
            scoped.assess_review(
                self.target.drawer_id,
                period_start="2024-02-01",
                period_end="2024-04-01",
                as_of="2024-03-01",
                policy=self.policy(),
            )

    def test_exact_replay_corrections_stale_branch(self):
        one = self.record()
        before = self.counts()
        self.assertEqual(one, self.record())
        self.assertEqual(before, self.counts())
        self.reject_atomic(lambda: self.record(practice_impact=9))
        two = self.book.record_observation(
            self.target.drawer_id,
            observation=self.obs(practice_impact=9),
            supersedes_id=one.drawer_id,
        )
        self.assertEqual(
            self.book.record_observation(
                self.target.drawer_id,
                observation=self.obs(practice_impact=9),
                supersedes_id=one.drawer_id,
            ),
            two,
        )
        self.reject_atomic(
            lambda: self.book.record_observation(
                self.target.drawer_id,
                observation=self.obs(practice_impact=8),
                supersedes_id=one.drawer_id,
            )
        )
        self.reject_atomic(
            lambda: self.book.record_observation(
                self.target.drawer_id,
                observation=self.obs("wrong-event"),
                supersedes_id=two.drawer_id,
            )
        )
        self.assertEqual(self.assess().observation_ids, (two.drawer_id,))
        self.assertEqual(self.book.observation_history(self.target.drawer_id), [one, two])

    def test_registration_failures_rollback_and_retry(self):
        before = self.counts()
        with patch.object(  # noqa: SIM117 - Preserve original context ordering.
            self.store,
            "_register_procedure_evaluation",
            side_effect=OSError("injected write failure"),
        ):
            with self.assertRaises(OSError):
                self.record()
        self.assertEqual(before, self.counts())
        receipt = self.record()
        self.assertEqual(self.book.get_observation(receipt.drawer_id), receipt)
        assessment = self.assess()
        before = self.counts()
        with patch.object(  # noqa: SIM117 - Preserve original context ordering.
            self.store,
            "_register_procedure_evaluation",
            side_effect=OSError("injected write failure"),
        ):
            with self.assertRaises(OSError):
                self.complete(assessment)
        self.assertEqual(before, self.counts())
        review = self.complete(assessment)
        self.assertEqual(self.book.get_review(review.drawer_id), review)

    def test_unknown_nullable_denominators_and_halfopen(self):
        self.record(
            "eligible",
            triggered=True,
            false_positive=None,
            overridden=None,
            baseline_impact=None,
            practice_impact=None,
            impact_unit=None,
        )
        self.record("unknown-trigger", triggered=None, false_positive=None, overridden=None)
        self.record("excluded", observed_on="2024-03-01")
        observed, simulated, unknown = self.assess().metrics
        self.assertEqual(
            (observed.observation_count, observed.trigger_known, observed.trigger_unknown),
            (2, 1, 1),
        )
        self.assertEqual((observed.false_positive_unknown, observed.override_unknown), (2, 2))
        self.assertEqual((observed.impact_known, observed.impact_unknown), (1, 1))
        self.assertEqual(
            (
                observed.trigger_rate,
                observed.false_positive_rate,
                observed.override_rate,
                observed.mean_impact,
            ),
            (None,) * 4,
        )
        self.assertEqual(simulated.observation_count, 0)
        self.assertEqual(unknown.observation_count, 0)

    def test_no_trigger_denominator_and_known_impact(self):
        self.record(triggered=False, false_positive=None, overridden=None)
        metrics = self.assess().metrics[0]
        self.assertEqual(metrics.trigger_rate, 0)
        self.assertEqual((metrics.false_positive_rate, metrics.override_rate), (None, None))
        self.assertEqual(metrics.mean_impact, 2)
        self.assertEqual((metrics.false_positive_known, metrics.false_positive_unknown), (0, 0))

    def test_simulated_unknown_cannot_poison_actual_thresholds(self):
        self.record("actual")
        for origin in ("simulated", "unknown"):
            self.record(
                origin,
                origin=origin,
                triggered=False,
                false_positive=None,
                overridden=None,
                baseline_impact=10,
                practice_impact=0,
            )
        assessment = self.assess(policy=self.policy(minimum_mean_impact=0, impact_unit="minutes"))
        self.assertEqual(assessment.reasons, ("due",))
        self.assertEqual(
            [x.origin for x in assessment.metrics], ["observed", "simulated", "unknown"]
        )
        self.assertEqual([x.mean_impact for x in assessment.metrics], [2, -10, -10])
        self.assertEqual([x.trigger_rate for x in assessment.metrics], [1, 0, 0])

    def test_strict_threshold_equality_and_metric_sample(self):
        self.record(false_positive=True, overridden=True)
        assessment = self.assess(
            policy=self.policy(
                maximum_false_positive_rate=1,
                maximum_override_rate=1,
                minimum_mean_impact=2,
                impact_unit="minutes",
            )
        )
        self.assertEqual(assessment.reasons, ("due",))
        assessment = self.assess(
            policy=self.policy(
                maximum_false_positive_rate=0.9,
                maximum_override_rate=0.9,
                minimum_mean_impact=2.1,
                impact_unit="minutes",
            )
        )
        self.assertEqual(
            assessment.reasons, ("due", "false-positive-rate", "override-rate", "impact")
        )
        self.assertEqual(
            self.assess(
                policy=self.policy(minimum_observations=2, maximum_override_rate=0)
            ).reasons,
            ("due",),
        )

    def test_mixed_units_and_nonfinite_arithmetic_typed(self):
        first = self.record("first")
        second = self.record("second", impact_unit="hours")
        self.reject_atomic(lambda: self.assess())
        self.book.record_observation(
            self.target.drawer_id, observation=self.obs("second"), supersedes_id=second.drawer_id
        )
        self.book.record_observation(
            self.target.drawer_id,
            observation=self.obs("first", baseline_impact=-1e308, practice_impact=1e308),
            supersedes_id=first.drawer_id,
        )
        self.reject_atomic(lambda: self.assess())

    def test_copied_metadata_not_authenticated_or_counted(self):
        genuine = self.record()
        original = self.store.get(genuine.drawer_id)
        fake = self.add(original.content, room="practice-reviews", metadata=original.metadata)
        self.reject_atomic(lambda: self.book.get_observation(fake))
        self.assertEqual(self.assess().observation_ids, (genuine.drawer_id,))
        assessment = self.assess()
        review = self.complete(assessment)
        drawer = self.store.get(review.drawer_id)
        copied = self.add(drawer.content, room="practice-reviews", metadata=drawer.metadata)
        self.reject_atomic(lambda: self.book.get_review(copied))
        self.assertEqual(self.book.review_history(self.target.drawer_id), [review])

    def test_new_ledger_malformed_raw_and_shape_errors_typed(self):
        observation = self.record()
        original = self.ledger(observation.drawer_id)
        for raw in ("{", "null", "[]", '"text"', "{}", '{"kind":"forged"}'):
            with self.subTest(raw=raw):
                self.setledger(observation.drawer_id, raw)
                for call in (
                    lambda: self.book.get_observation(observation.drawer_id),
                    lambda: self.assess(),
                ):
                    with self.assertRaises(
                        MemoryStoreError if raw in ("null", "[]", '"text"') else api.ProcedureError
                    ):
                        call()
        self.setledger(observation.drawer_id, original)
        review = self.complete(self.assess())
        original = self.ledger(review.drawer_id)
        for raw in ("{", "null", "[]", "{}"):
            with self.subTest(review_raw=raw):
                self.setledger(review.drawer_id, raw)
                with self.assertRaises(
                    MemoryStoreError if raw in ("null", "[]") else api.ProcedureError
                ):
                    self.book.get_review(review.drawer_id)
                with self.assertRaises(
                    MemoryStoreError if raw in ("null", "[]") else api.ProcedureError
                ):
                    self.assess()
        self.setledger(review.drawer_id, original)

    def test_receipt_hash_and_ledger_payload_mutation(self):
        receipt = self.record()
        original = self.ledger(receipt.drawer_id)
        payload = json.loads(original)

        def mutate(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key == "record_sha256":
                        value[key] = "0" * 64
                        return True
                    if mutate(item):
                        return True
            return False

        self.assertTrue(mutate(payload), "ledger did not retain expected record hash")
        self.setledger(receipt.drawer_id, json.dumps(payload))
        self.reject_atomic(lambda: self.book.get_observation(receipt.drawer_id))
        self.reject_atomic(lambda: self.assess())

    def test_forged_assessment_stale_source_and_lifecycle(self):
        self.record()
        assessment = self.assess()
        mutations = (
            {"assessment_sha256": "0" * 64},
            {"observation_ids": ()},
            {"reasons": ()},
            {"effective_review_due": "2024-01-01"},
            {"last_review_id": True},
            {
                "metrics": (dataclasses.replace(assessment.metrics[0], observation_count=True),)  # noqa: RUF005 - Preserve original tuple oracle.
                + assessment.metrics[1:]
            },
        )
        for fields in mutations:
            with self.subTest(fields=fields):
                self.reject_atomic(lambda: self.complete(dataclasses.replace(assessment, **fields)))  # noqa: B023 - Called synchronously.
        self.record("new event")
        self.reject_atomic(lambda: self.complete(assessment))
        fresh = self.assess()
        revised = self.book.revise(
            self.target.drawer_id,
            spec=dataclasses.replace(
                self.spec, governance=dataclasses.replace(self.spec.governance, version="2")
            ),
        )
        self.reject_atomic(lambda: self.complete(fresh))
        self.assertEqual(revised.state, "candidate")

    def test_completion_exact_replay_acknowledgement_new_evidence(self):
        first = self.record(triggered=False, false_positive=None, overridden=None)
        policy = self.policy(minimum_trigger_rate=0.5)
        assessment = self.assess(policy=policy)
        review = self.complete(assessment)
        before = self.counts()
        self.assertEqual(self.complete(assessment), review)
        self.assertEqual(before, self.counts())
        self.reject_atomic(lambda: self.complete(assessment, decision="revise"))
        fresh = self.assess(policy=policy)
        self.assertEqual(fresh.effective_review_due, "2024-04-02")
        self.assertEqual(fresh.last_review_id, review.drawer_id)
        self.assertEqual(fresh.reasons, ())
        self.assertEqual(fresh.metrics[0].trigger_rate, 0)
        self.book.record_observation(
            self.target.drawer_id,
            observation=self.obs(
                practice_impact=6, triggered=False, false_positive=None, overridden=None
            ),
            supersedes_id=first.drawer_id,
        )
        self.assertEqual(self.assess(policy=policy).reasons, ("trigger-rate",))

    def test_completion_validation_and_decisions_preserve_lifecycle(self):
        self.record()
        assessment = self.assess()
        for field, values in {
            "reviewer": ["", "bad\ud800", "x" * 257, True],
            "rationale": [" ", "x" * 8193],
            "decision": ["promote", "withdraw", "RETAIN"],
            "next_review_due": ["2024-03-01", "20240302", "2024-02-30"],
        }.items():
            for value in values:
                with self.subTest(field=field, value=str(value)[:50]):
                    self.reject_atomic(lambda: self.complete(assessment, **{field: value}))  # noqa: B023 - Called synchronously.
        history = self.book.history(self.target.drawer_id)
        bytes_before = list(
            self.store._conn.execute(
                "SELECT drawer_id,payload FROM procedure_records ORDER BY drawer_id"
            )
        )
        approvals = len(self.approvals)
        for n, decision in enumerate(("retain", "revise", "defer")):
            if n:
                self.record(str(n))
            review = self.complete(self.assess(), decision=decision)
            self.assertEqual(review.reviewed_on, "2024-03-01")
            self.assertEqual(review.reviewer, "  reviewer  ")
            self.assertEqual(review.rationale, "  preserved rationale\n")
        self.assertEqual(self.book.history(self.target.drawer_id), history)
        self.assertEqual(
            list(
                self.store._conn.execute(
                    "SELECT drawer_id,payload FROM procedure_records ORDER BY drawer_id"
                )
            ),
            bytes_before,
        )
        self.assertEqual(len(self.approvals), approvals)

    def test_tagged_records_never_promote_and_nonactive_queue(self):
        observation = self.record()
        review = self.complete(self.assess())
        for receipt in (observation, review):
            self.reject_atomic(lambda: self.book.get_evaluation(receipt.drawer_id))  # noqa: B023 - Called synchronously.
            self.reject_atomic(
                lambda: self.book.promote(self.target.drawer_id, evaluation_id=receipt.drawer_id)  # noqa: B023 - Called synchronously.
            )
        candidate = self.book.propose(wing=WING, spec=self.spec)
        self.reject_atomic(
            lambda: self.book.record_observation(candidate.drawer_id, observation=self.obs())
        )
        self.book.record_observation(
            candidate.drawer_id, observation=self.obs("sim", origin="simulated")
        )
        expired = self.book.rollback(self.target.drawer_id, reason="synthetic withdrawal")
        self.reject_atomic(
            lambda: self.book.record_observation(
                expired.drawer_id, observation=self.obs("withdrawn", origin="unknown")
            )
        )
        due = self.book.due_reviews(
            wing=WING,
            period_start="2024-02-01",
            period_end="2024-04-01",
            as_of="2024-03-01",
            policy=self.policy(),
        )
        self.assertEqual(due, [])

    def test_family_history_late_historical_observation_and_reopen(self):
        one = self.record()
        review = self.complete(self.assess())
        revised = self.book.revise(
            self.target.drawer_id,
            spec=dataclasses.replace(
                self.spec, governance=dataclasses.replace(self.spec.governance, version="2")
            ),
        )
        self.book.record_observation(self.target.drawer_id, observation=self.obs("late"))
        historical = self.book.observation_history(revised.drawer_id)
        self.assertEqual(len(historical), 2)
        self.assertEqual(historical[0], one)
        self.assertEqual(self.book.review_history(revised.drawer_id), [review])
        new = self.book.record_observation(
            revised.drawer_id, observation=self.obs("new version", origin="simulated")
        )
        self.assertEqual(
            self.book.assess_review(
                revised.drawer_id,
                period_start="2024-02-01",
                period_end="2024-04-01",
                as_of="2024-03-01",
                policy=self.policy(),
            ).observation_ids,
            (new.drawer_id,),
        )
        all_history = self.book.observation_history(revised.drawer_id)
        self.store.close()
        self.store = DrawerStore(self.path, HashEmbeddingProvider(dimension=32))
        self.book = api.ProcedureBook(self.store, self.registry)
        self.assertEqual(self.book.observation_history(revised.drawer_id), all_history)
        self.assertEqual(self.book.review_history(revised.drawer_id), [review])


if __name__ == "__main__":
    unittest.main(verbosity=2)
