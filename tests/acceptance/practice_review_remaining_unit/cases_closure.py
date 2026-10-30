"""Additive recursive portable-closure boundary under a broad wing grant."""

from dataclasses import replace

from cairntir.access import AccessDenied

from .cases_completeness import WING, CompletenessBoundary


class RecursiveClosure(CompletenessBoundary):
    def test_foreign_ancestor_cannot_hide_newer_transition_under_broad_requested_wing(self):
        self.pair()
        foreign = self.add("foreign ancestor", wing="foreign-private")
        source = self.add("same-wing source with foreign ancestor", supersedes_id=foreign)
        newer = self.book.revise(
            self.target.drawer_id,
            spec=replace(
                self.spec,
                evidence_ids=self.spec.evidence_ids + (source,),  # noqa: RUF005 - Preserve original tuple oracle.
                governance=replace(self.spec.governance, version="2"),
            ),
        )
        self.assertEqual(self.book.history(newer.drawer_id)[-1], newer)
        with self.scoped([{"wing": WING}]) as book:
            with self.assertRaises(AccessDenied):
                book._store.get(source)
            with self.assertRaises(AccessDenied):
                self.assessment(book)
            with self.assertRaises(AccessDenied):
                self.queue(book)
