"""Additional frozen proof of adapter closure denial and authorized graph success."""

from dataclasses import replace

from practice_review_edges_unit.fixtures_v2 import WING, Harness

from cairntir.access import AccessDenied

from .cases_completeness import CompletenessBoundary


class ClosureAdditional(Harness):
    def scoped(self, scopes):
        return CompletenessBoundary.scoped(self, scopes)

    def pair(self):
        return CompletenessBoundary.pair(self)

    def queue(self, book):
        return CompletenessBoundary.queue(self, book)

    def assessment(self, book, target=None):
        return book.assess_review(
            target or self.target.drawer_id,
            period_start="2024-02-01",
            period_end="2024-04-01",
            as_of="2024-03-01",
            policy=self.policy(minimum_trigger_rate=0.75),
        )

    def hidden_transition(self):
        self.pair()
        foreign = self.add("foreign ancestor", wing="foreign-private")
        source = self.add("same wing descendant", supersedes_id=foreign)
        newer = self.book.revise(
            self.target.drawer_id,
            spec=replace(
                self.spec,
                evidence_ids=self.spec.evidence_ids + (source,),  # noqa: RUF005 - Preserve original tuple oracle.
                governance=replace(self.spec.governance, version="2"),
            ),
        )
        return foreign, source, newer

    def test_queue_denies_recursive_hidden_current_transition(self):
        self.hidden_transition()
        with self.scoped([{"wing": WING}]) as book:
            with self.assertRaises(AccessDenied) as caught:
                self.queue(book)
            self.assertEqual(str(caught.exception), "access denied")

    def test_full_foreign_dependency_authority_preserves_positive_complete_graph(self):
        _, _, newer = self.hidden_transition()
        with self.scoped([{"wing": WING}, {"wing": "foreign-private"}]) as book:
            self.assertEqual(
                self.assessment(book, newer.drawer_id), self.assessment(self.book, newer.drawer_id)
            )
            self.assertEqual(self.queue(book), self.queue(self.book))
            self.assertEqual(
                book.observation_history(newer.drawer_id),
                self.book.observation_history(newer.drawer_id),
            )
            self.assertEqual(
                book.review_history(newer.drawer_id), self.book.review_history(newer.drawer_id)
            )

    def test_history_requires_complete_wing_even_when_hidden_drawer_is_unrelated(self):
        one = self.record()
        foreign = self.add("foreign ancestor", wing="foreign-private")
        self.add("unrelated hidden own-wing descendant", supersedes_id=foreign)
        with self.scoped([{"wing": WING}]) as book:
            self.assertEqual(book.get_observation(one.drawer_id), one)
            for call in (
                lambda: book.observation_history(self.target.drawer_id),
                lambda: book.review_history(self.target.drawer_id),
                lambda: self.assessment(book),
            ):
                with self.subTest(call=call):
                    with self.assertRaises(AccessDenied) as caught:
                        call()
                    self.assertEqual(str(caught.exception), "access denied")

    def test_hidden_observation_source_recursive_closure_remains_denied(self):
        foreign = self.add("foreign source ancestor", wing="foreign-private")
        source = self.add("source descendant", supersedes_id=foreign)
        self.record(evidence_ids=(source,))
        with self.scoped([{"wing": WING}]) as book:
            with self.assertRaises(AccessDenied):
                book.observation_history(self.target.drawer_id)
            with self.assertRaises(AccessDenied):
                self.assessment(book)

    def test_read_only_broad_grant_proof_does_not_require_write(self):
        self.pair()
        with CompletenessBoundary.scoped(self, [{"wing": WING}], capabilities=("read",)) as book:
            before = self.counts()
            self.assertEqual(self.assessment(book), self.assessment(self.book))
            self.assertEqual(self.queue(book), self.queue(self.book))
            self.assertEqual(self.counts(), before)
