"""Independent R18 adversarial probes, synthetic stores, no production access."""

from __future__ import annotations

import json
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cairntir import procedures as api
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.reason.model import Experiment, Outcome

WING = "r18-redteam-synthetic"


class Runner:
    def run(self, hypothesis):
        value = json.loads(hypothesis.claim)
        observed = hypothesis.predicted_outcome if value["steps"] == ["qualified"] else "miss"
        return Outcome(
            Experiment(hypothesis, "synthetic local control"),
            observed,
            observed == hypothesis.predicted_outcome,
        )


class Harness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="r18-redteam-")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "synthetic.db"
        self.store = DrawerStore(self.path, HashEmbeddingProvider(dimension=32))
        self.addCleanup(lambda: self.store.close())
        self.network = patch.object(socket.socket, "connect", side_effect=AssertionError("offline"))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.source = self.add("immutable usage source")
        development = self.add("development example")
        cases = tuple(
            api.HoldoutCase(str(n), self.add("holdout " + str(n)), "pass") for n in (1, 2)
        )
        self.registry = {
            "local": api.RegisteredEvaluation(
                api.EvaluationManifest("local", ("baseline",), cases), Runner()
            )
        }
        self.approvals = []

        def approve(request):
            self.approvals.append(request)
            return True

        self.book = api.ProcedureBook(self.store, self.registry, approve)
        self.spec = api.ProcedureSpec(
            "Synthetic practice",
            ("input",),
            "synthetic only",
            ("qualified",),
            "pass",
            ("reuse source",),
            (development,),
            governance=api.PracticeGovernance("attributed owner", "1", "synthetic", "2024-02-29"),
        )
        self.candidate = self.book.propose(wing=WING, spec=self.spec)
        self.evaluation = self.book.evaluate(self.candidate.drawer_id, evaluator_id="local")
        self.target = self.book.promote(
            self.evaluation.current_id, evaluation_id=self.evaluation.drawer_id
        )

    def add(self, content, wing=WING, room="cases", **kwargs):
        return self.store.add(Drawer(wing=wing, room=room, content=content, **kwargs)).id

    def obs(self, event="event", **kwargs):
        values = dict(  # noqa: C408 - Preserve original fixture construction.
            event_id=event,
            observed_on="2024-02-29",
            origin="observed",
            triggered=True,
            false_positive=False,
            overridden=False,
            baseline_impact=3,
            practice_impact=5,
            impact_unit="minutes",
            evidence_ids=(self.source,),
        )
        values.update(kwargs)
        return api.PracticeObservation(**values)

    def record(self, event="event", **kwargs):
        return self.book.record_observation(
            self.target.drawer_id, observation=self.obs(event, **kwargs)
        )

    def policy(self, **kwargs):
        values = dict(minimum_observations=1, minimum_trigger_rate=1)  # noqa: C408 - Preserve original fixture construction.
        values.update(kwargs)
        return api.PracticeReviewPolicy(**values)

    def assess(self, **kwargs):
        values = dict(  # noqa: C408 - Preserve original fixture construction.
            period_start="2024-02-01",
            period_end="2024-04-01",
            as_of="2024-03-01",
            policy=self.policy(),
        )
        values.update(kwargs)
        return self.book.assess_review(self.target.drawer_id, **values)

    def complete(self, assessment, **kwargs):
        values = dict(  # noqa: C408 - Preserve original fixture construction.
            assessment=assessment,
            reviewer="  reviewer  ",
            decision="retain",
            rationale="  preserved rationale\n",
            next_review_due="2024-04-02",
        )
        values.update(kwargs)
        return self.book.complete_review(self.target.drawer_id, **values)

    def counts(self):
        return tuple(
            self.store._conn.execute("SELECT count(*) FROM " + table).fetchone()[0]  # noqa: S608 - Three fixed fixture table names.
            for table in ("drawers", "procedure_records", "procedure_evaluations")
        )

    def ledger(self, key):
        return self.store._conn.execute(
            "SELECT payload FROM procedure_evaluations WHERE drawer_id=?", (key,)
        ).fetchone()[0]

    def setledger(self, key, value):
        self.store._conn.execute(
            "UPDATE procedure_evaluations SET payload=? WHERE drawer_id=?", (value, key)
        )
        self.store._conn.commit()

    def reject_atomic(self, action, error=None):
        before = self.counts()
        with self.assertRaises(error or api.ProcedureError):
            action()
        self.assertEqual(before, self.counts())
