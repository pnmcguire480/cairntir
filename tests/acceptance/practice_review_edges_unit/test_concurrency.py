"""Frozen source-review follow-ups: acknowledgement history and tiny writer races."""

import threading
from concurrent.futures import ThreadPoolExecutor

from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore

from .fixtures_v2 import Harness, api


class SourceReviewEdges(Harness):
    def test_disjoint_review_windows_do_not_forget_acknowledged_evidence(self):
        bad = self.record("february", triggered=False, false_positive=None, overridden=None)
        february = self.assess(policy=self.policy(minimum_trigger_rate=0.5))
        first = self.complete(february, next_review_due="2024-06-01")
        self.assertEqual(self.assess(policy=self.policy(minimum_trigger_rate=0.5)).reasons, ())
        self.record("march", observed_on="2024-03-02")
        march = self.assess(
            period_start="2024-03-01",
            period_end="2024-04-01",
            as_of="2024-04-01",
            policy=self.policy(minimum_trigger_rate=0.5),
        )
        self.assertNotIn(bad.drawer_id, march.observation_ids)
        second = self.complete(march, next_review_due="2024-06-02")
        revisited = self.assess(
            period_start="2024-02-01",
            period_end="2024-03-01",
            as_of="2024-04-01",
            policy=self.policy(minimum_trigger_rate=0.5),
        )
        self.assertEqual(revisited.last_review_id, second.drawer_id)
        self.assertEqual(revisited.effective_review_due, "2024-06-02")
        self.assertEqual(revisited.observation_ids, (bad.drawer_id,))
        self.assertEqual(revisited.metrics[0].trigger_rate, 0)
        self.assertEqual(
            revisited.reasons, (), "previously acknowledged observed snapshot re-alerted"
        )
        self.assertEqual(self.book.review_history(self.target.drawer_id), [first, second])

    def test_two_tiny_concurrent_corrections_allow_exactly_one_append(self):
        original = self.record()
        barrier = threading.Barrier(2, timeout=5)

        def worker(impact):
            with DrawerStore(self.path, HashEmbeddingProvider(dimension=32)) as store:
                book = api.ProcedureBook(store, self.registry)
                barrier.wait()
                try:
                    return "accepted", book.record_observation(
                        self.target.drawer_id,
                        observation=self.obs(practice_impact=impact),
                        supersedes_id=original.drawer_id,
                    )
                except api.ProcedureError as error:
                    return "rejected", str(error)

        before = self.counts()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, impact) for impact in (7, 8)]
            results = [future.result(timeout=15) for future in futures]
        self.assertEqual(sorted(result[0] for result in results), ["accepted", "rejected"])
        self.assertEqual(self.counts(), (before[0] + 1, before[1], before[2] + 1))
        self.assertEqual(len(self.book.observation_history(self.target.drawer_id)), 2)

    def test_two_tiny_concurrent_completions_allow_exactly_one_append(self):
        self.record()
        assessment = self.assess()
        barrier = threading.Barrier(2, timeout=5)

        def worker(reviewer):
            with DrawerStore(self.path, HashEmbeddingProvider(dimension=32)) as store:
                book = api.ProcedureBook(store, self.registry)
                barrier.wait()
                try:
                    return "accepted", book.complete_review(
                        self.target.drawer_id,
                        assessment=assessment,
                        reviewer=reviewer,
                        decision="retain",
                        rationale="synthetic race",
                        next_review_due="2024-06-01",
                    )
                except api.ProcedureError as error:
                    return "rejected", str(error)

        before = self.counts()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, reviewer) for reviewer in ("one", "two")]
            results = [future.result(timeout=15) for future in futures]
        self.assertEqual(sorted(result[0] for result in results), ["accepted", "rejected"])
        self.assertEqual(self.counts(), (before[0] + 1, before[1], before[2] + 1))
        self.assertEqual(len(self.book.review_history(self.target.drawer_id)), 1)
