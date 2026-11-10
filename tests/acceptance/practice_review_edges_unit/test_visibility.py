"""Frozen visibility boundary probe: denied dependencies versus empty evidence."""

from cairntir.access import AccessDenied, bind_grant, issue_grant

from .fixtures_v1 import WING, Harness, api


class DependencyVisibility(Harness):
    def test_hidden_observation_source_is_not_empty_statistics(self):
        self.record()
        allowed = [
            row[0]
            for row in self.store._conn.execute("SELECT id FROM drawers")
            if row[0] != self.source
        ]
        token = issue_grant(
            self.store,
            scopes=[
                {
                    "wing": WING,
                    "rooms": [
                        "discoveries",
                        "practice-reviews",
                        "cases",
                        "predictions",
                        "observations",
                        "procedure-evaluations",
                    ],
                    "drawer_ids": allowed,
                }
            ],
            capabilities=["read", "write"],
        )
        scoped = api.ProcedureBook(bind_grant(self.store, token), self.registry)
        self.assertEqual(
            scoped.history(self.target.drawer_id)[-1],
            self.target,
            "fixture must expose the governed procedure independently of its usage source",
        )
        with self.assertRaises(AccessDenied):
            scoped.assess_review(
                self.target.drawer_id,
                period_start="2024-02-01",
                period_end="2024-04-01",
                as_of="2024-03-01",
                policy=self.policy(),
            )

    def test_hidden_correction_cannot_restore_superseded_bad_evidence(self):
        first = self.record(triggered=False, false_positive=None, overridden=None)
        newer_source = self.add("correction-only source")
        self.book.record_observation(
            self.target.drawer_id,
            observation=self.obs(evidence_ids=(newer_source,)),
            supersedes_id=first.drawer_id,
        )
        allowed = [
            row[0]
            for row in self.store._conn.execute("SELECT id FROM drawers")
            if row[0] != newer_source
        ]
        token = issue_grant(
            self.store,
            scopes=[{"wing": WING, "drawer_ids": allowed}],
            capabilities=["read", "write"],
        )
        scoped = api.ProcedureBook(bind_grant(self.store, token), self.registry)
        self.assertEqual(scoped.history(self.target.drawer_id)[-1], self.target)
        with self.assertRaises(AccessDenied):
            scoped.assess_review(
                self.target.drawer_id,
                period_start="2024-02-01",
                period_end="2024-04-01",
                as_of="2024-03-01",
                policy=self.policy(),
            )
