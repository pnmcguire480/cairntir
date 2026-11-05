"""Freeze authorization changes during proof/collection, using actual scoped reads."""

import copy
from unittest.mock import patch

from cairntir.access import AccessDenied, ScopedStore

from .fixtures_v2 import WING, Harness, api


class GrantRecheck(Harness):
    def view(self):
        scoped = ScopedStore(self.store, "inert-grant-recheck-no-persisted-grant")
        state = {"grant": {"scopes": [{"wing": WING}], "capabilities": ["read", "write"]}}
        return scoped, api.ProcedureBook(scoped, self.registry), state

    def assessment_args(self):
        return dict(  # noqa: C408 - Preserve original fixture construction.
            period_start="2024-02-01",
            period_end="2024-04-01",
            as_of="2024-03-01",
            policy=self.policy(),
        )

    def test_guard_rechecks_grant_after_recursive_visible_rows(self):
        self.record()
        scoped, _, state = self.view()
        original = scoped._rows

        def rows(*args, **kwargs):
            result = original(*args, **kwargs)
            state["grant"] = {
                "scopes": [{"wing": WING, "drawer_ids": [self.source]}],
                "capabilities": ["read"],
            }
            return result

        with patch.object(scoped, "_grant", side_effect=lambda: copy.deepcopy(state["grant"])):  # noqa: SIM117 - Preserve original patch nesting.
            with patch.object(scoped, "_rows", side_effect=rows):
                with self.assertRaises(AccessDenied):
                    scoped._authorize_complete_wing(WING)

    def test_queue_rechecks_when_scope_narrows_to_empty_after_initial_proof(self):
        self.record()
        scoped, book, state = self.view()
        original = scoped._procedure_records

        def records(*args, **kwargs):
            state["grant"] = {
                "scopes": [{"wing": WING, "drawer_ids": [self.source]}],
                "capabilities": ["read"],
            }
            return original(*args, **kwargs)

        with patch.object(scoped, "_grant", side_effect=lambda: copy.deepcopy(state["grant"])):  # noqa: SIM117 - Preserve original patch nesting.
            with patch.object(scoped, "_procedure_records", side_effect=records):
                with self.assertRaises(AccessDenied):
                    book.due_reviews(wing=WING, **self.assessment_args())

    def test_history_rechecks_scope_after_initial_proof_before_empty_collection(self):
        receipt = self.record()
        scoped, book, state = self.view()
        original = scoped.list_by
        ids = [
            row[0]
            for row in self.store._conn.execute("SELECT id FROM drawers")
            if row[0] != receipt.drawer_id
        ]

        def listing(*args, **kwargs):
            state["grant"] = {
                "scopes": [{"wing": WING, "drawer_ids": ids}],
                "capabilities": ["read"],
            }
            return original(*args, **kwargs)

        with patch.object(scoped, "_grant", side_effect=lambda: copy.deepcopy(state["grant"])):  # noqa: SIM117 - Preserve original patch nesting.
            with patch.object(scoped, "list_by", side_effect=listing):
                with self.assertRaises(AccessDenied):
                    book.observation_history(self.target.drawer_id)
