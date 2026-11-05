"""Additive P1 visibility controls using real ScopedStore and inert grant loading."""

from contextlib import contextmanager
from dataclasses import replace
from unittest.mock import patch

from practice_review_edges_unit.fixtures_v2 import WING, Harness, api

from cairntir.access import AccessDenied, ScopedStore


class CompletenessBoundary(Harness):
    @contextmanager
    def scoped(self, scopes, capabilities=("read", "write")):
        store = ScopedStore(self.store, "inert-round2-no-persisted-grant")
        book = api.ProcedureBook(store, self.registry)
        with patch.object(
            store, "_grant", return_value={"scopes": scopes, "capabilities": list(capabilities)}
        ):
            yield book

    def ids(self, *hidden):
        return [
            row[0]
            for row in self.store._conn.execute("SELECT id FROM drawers")
            if row[0] not in hidden
        ]

    def assessment(self, book):
        return book.assess_review(
            self.target.drawer_id,
            period_start="2024-02-01",
            period_end="2024-04-01",
            as_of="2024-03-01",
            policy=self.policy(minimum_trigger_rate=0.75),
        )

    def queue(self, book):
        return book.due_reviews(
            wing=WING,
            period_start="2024-02-01",
            period_end="2024-04-01",
            as_of="2024-03-01",
            policy=self.policy(minimum_trigger_rate=0.75),
        )

    def pair(self):
        bad = self.record("bad", triggered=False, false_positive=None, overridden=None)
        good = self.record("good")
        return bad, good

    def test_whole_wing_read_assessment_history_and_queue_match_owner(self):
        self.pair()
        owner = self.assessment(self.book)
        with self.scoped([{"wing": WING}]) as book:
            self.assertEqual(self.assessment(book), owner)
            self.assertEqual(
                book.observation_history(self.target.drawer_id),
                self.book.observation_history(self.target.drawer_id),
            )
            self.assertEqual(book.review_history(self.target.drawer_id), [])
            self.assertEqual(self.queue(book), self.queue(self.book))

    def test_hidden_observation_cannot_convert_half_to_complete_rate(self):
        bad, _ = self.pair()
        owner = self.assessment(self.book)
        self.assertEqual(owner.metrics[0].trigger_rate, 0.5)
        self.assertIn("trigger-rate", owner.reasons)
        with self.scoped([{"wing": WING, "drawer_ids": self.ids(bad.drawer_id)}]) as book:  # noqa: SIM117 - Preserve original context ordering.
            with self.assertRaises(AccessDenied):
                self.assessment(book)

    def test_hidden_correction_cannot_resurrect_previous_snapshot(self):
        bad, _ = self.pair()
        correction = self.book.record_observation(
            self.target.drawer_id, observation=self.obs("bad"), supersedes_id=bad.drawer_id
        )
        self.assertEqual(self.assessment(self.book).metrics[0].trigger_rate, 1)
        with self.scoped([{"wing": WING, "drawer_ids": self.ids(correction.drawer_id)}]) as book:  # noqa: SIM117 - Preserve original context ordering.
            with self.assertRaises(AccessDenied):
                self.assessment(book)

    def test_hidden_review_cannot_restore_old_deadline(self):
        self.pair()
        review = self.complete(self.assessment(self.book), next_review_due="2024-06-01")
        self.assertEqual(self.assessment(self.book).effective_review_due, "2024-06-01")
        with self.scoped([{"wing": WING, "drawer_ids": self.ids(review.drawer_id)}]) as book:  # noqa: SIM117 - Preserve original context ordering.
            with self.assertRaises(AccessDenied):
                self.assessment(book)

    def test_even_all_current_known_ids_do_not_prove_complete_history(self):
        self.pair()
        with self.scoped([{"wing": WING, "drawer_ids": self.ids()}]) as book:
            for call in (
                lambda: self.assessment(book),
                lambda: book.observation_history(self.target.drawer_id),
                lambda: book.review_history(self.target.drawer_id),
                lambda: self.queue(book),
            ):
                with self.subTest(call=call):  # noqa: SIM117 - Preserve original context ordering.
                    with self.assertRaises(AccessDenied):
                        call()

    def test_mixed_finite_scopes_cannot_union_into_unrestricted_history(self):
        self.pair()
        ids = self.ids()
        scopes = [{"wing": WING, "drawer_ids": ids[::2]}, {"wing": WING, "drawer_ids": ids[1::2]}]
        with self.scoped(scopes) as book:
            with self.assertRaises(AccessDenied):
                self.assessment(book)
            with self.assertRaises(AccessDenied):
                self.queue(book)

    def test_room_unions_covering_current_rooms_still_do_not_prove_closure(self):
        self.pair()
        rooms = [row[0] for row in self.store._conn.execute("SELECT DISTINCT room FROM drawers")]
        for scopes in (
            [{"wing": WING, "rooms": rooms}],
            [{"wing": WING, "rooms": [room]} for room in rooms],
        ):
            with self.subTest(scopes=scopes):  # noqa: SIM117 - Preserve original context ordering.
                with self.scoped(scopes) as book:
                    with self.assertRaises(AccessDenied):
                        self.assessment(book)

    def test_unrelated_broad_wing_does_not_make_requested_wing_complete(self):
        self.pair()
        with self.scoped([{"wing": "unrelated"}, {"wing": WING, "drawer_ids": self.ids()}]) as book:  # noqa: SIM117 - Preserve original context ordering.
            with self.assertRaises(AccessDenied):
                self.assessment(book)

    def test_valid_whole_wing_scope_survives_additional_restricted_scopes(self):
        self.pair()
        with self.scoped(
            [{"wing": WING, "drawer_ids": [self.target.drawer_id]}, {"wing": WING}]
        ) as book:
            self.assertEqual(self.assessment(book), self.assessment(self.book))

    def test_scope_requires_read_capability(self):
        self.pair()
        with self.scoped([{"wing": WING}], capabilities=("write",)) as book:  # noqa: SIM117 - Preserve original context ordering.
            with self.assertRaises(AccessDenied):
                self.assessment(book)

    def test_hidden_procedure_transition_cannot_treat_old_promoted_as_current(self):
        self.pair()
        revised = self.book.revise(
            self.target.drawer_id,
            spec=replace(self.spec, governance=replace(self.spec.governance, version="2")),
        )
        with self.scoped([{"wing": WING, "drawer_ids": self.ids(revised.drawer_id)}]) as book:
            with self.assertRaises(AccessDenied):
                self.assessment(book)
            with self.assertRaises(AccessDenied):
                self.queue(book)

    def test_queue_cannot_succeed_with_empty_partial_visibility(self):
        self.pair()
        with self.scoped([{"wing": WING, "drawer_ids": [self.source]}]) as book:  # noqa: SIM117 - Preserve original context ordering.
            with self.assertRaises(AccessDenied):
                self.queue(book)

    def test_direct_authenticated_get_remains_per_reference_scoped(self):
        first = self.record()
        review = self.complete(self.assessment(self.book), next_review_due="2024-06-01")
        with self.scoped([{"wing": WING, "drawer_ids": self.ids()}]) as book:
            self.assertEqual(book.get_observation(first.drawer_id), first)
            self.assertEqual(book.get_review(review.drawer_id), review)

    def test_partial_history_write_cannot_create_duplicate_event(self):
        first = self.record()
        before = self.counts()
        with self.scoped([{"wing": WING, "drawer_ids": self.ids(first.drawer_id)}]) as book:  # noqa: SIM117 - Preserve original context ordering.
            with self.assertRaises(AccessDenied):
                book.record_observation(self.target.drawer_id, observation=self.obs())
        self.assertEqual(before, self.counts())

    def test_room_limited_source_portable_dependency_closure_fails_closed(self):
        parent = self.add("hidden source parent", room="hidden-lineage")
        child = self.add("visible source child", room="cases", supersedes_id=parent)
        self.record(evidence_ids=(child,))
        scopes = [
            {
                "wing": WING,
                "rooms": ["cases", "discoveries", "practice-reviews", "procedure-evaluations"],
            }
        ]
        with self.scoped(scopes) as book:  # noqa: SIM117 - Preserve original context ordering.
            with self.assertRaises(AccessDenied):
                self.assessment(book)

    def test_outer_transaction_receipts_are_provisional_and_rollback_retries_cleanly(self):
        before = self.counts()
        with self.assertRaisesRegex(RuntimeError, "abort outer"):  # noqa: SIM117 - Preserve original context ordering.
            with self.store.transaction():
                provisional = self.record()
                self.assertEqual(self.book.get_observation(provisional.drawer_id), provisional)
                raise RuntimeError("abort outer")
        self.assertEqual(self.counts(), before)
        durable = self.record()
        assessment = self.assessment(self.book)
        before = self.counts()
        with self.assertRaisesRegex(RuntimeError, "abort outer"):  # noqa: SIM117 - Preserve original context ordering.
            with self.store.transaction():
                provisional_review = self.complete(assessment)
                self.assertEqual(
                    self.book.get_review(provisional_review.drawer_id), provisional_review
                )
                raise RuntimeError("abort outer")
        self.assertEqual(self.counts(), before)
        durable_review = self.complete(assessment)
        self.assertEqual(self.book.get_observation(durable.drawer_id), durable)
        self.assertEqual(self.book.get_review(durable_review.drawer_id), durable_review)
