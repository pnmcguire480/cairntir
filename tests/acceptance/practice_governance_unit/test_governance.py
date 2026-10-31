"""Independent tiny-SQLite bounded R17 controls, authored before candidate edits."""

import copy
import hashlib
import json
import unittest
from contextlib import contextmanager
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from unittest.mock import patch

from cairntir import procedures
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.reason import model

API = procedures
STORE = DrawerStore
DRAWER = Drawer
EMBEDDER = HashEmbeddingProvider
MODEL = model
ROOT = None
COUNTER = 0
WING = "r17-independent-fresh"
NAMES = (
    "title",
    "prerequisites",
    "applicability",
    "steps",
    "expected_outcome",
    "rollback",
    "evidence_ids",
    "counterexample_ids",
    "development_case_ids",
)


def canonical(value):
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )


def wire(spec):
    result = {
        name: list(getattr(spec, name))
        if isinstance(getattr(spec, name), tuple)
        else getattr(spec, name)
        for name in NAMES
    }
    gov = getattr(spec, "governance", None)
    if gov is not None:
        result["governance"] = {
            name: getattr(gov, name) for name in ("owner", "version", "rationale", "review_due")
        }
    return result


def fingerprint(spec):
    return hashlib.sha256(canonical({"wing": WING, "spec": wire(spec)}).encode("utf-8")).hexdigest()


def metadata(version="release-A", **changes):
    value = dict(  # noqa: C408 - Preserve the original fixture constructor.
        owner="  A responsible maintainer 🪨  ",
        version=version,
        rationale="  Keep the measured result.\nDo not rewrite evidence.  ",
        review_due="2024-02-29",
    )
    value.update(changes)
    return API.PracticeGovernance(**value)


class InertRunner:
    def __init__(self):
        self.calls = []

    def run(self, hypothesis):
        self.calls.append(hypothesis)
        claim = json.loads(hypothesis.claim)
        values = json.loads(claim["input"])
        for step in claim["steps"]:
            if step == "unique":
                values = list(dict.fromkeys(values))
            elif step != "identity":
                raise AssertionError("Fixture supports only inert bounded operations")
        observed = json.dumps(values)
        return MODEL.Outcome(
            experiment=MODEL.Experiment(
                hypothesis=hypothesis, description="Synthetic finite list operation"
            ),
            observed=observed,
            success=observed == hypothesis.predicted_outcome,
            delta="",
        )


class FreshR17(unittest.TestCase):
    def setUp(self):
        global COUNTER
        COUNTER += 1
        self.path = Path(ROOT) / ("synthetic-%03d.db" % COUNTER)  # noqa: UP031 - Preserve original fixture path formatting.
        self.store = self.open()
        dev = self.add("[8, 8, 2]")
        self.spec = API.ProcedureSpec(
            title="Fresh synthetic method",
            prerequisites=("Finite list",),
            applicability="Independent bounded inspection",
            steps=("unique",),
            expected_outcome="Keep first instances",
            rollback=("Preserve original evidence",),
            evidence_ids=(dev,),
            development_case_ids=("dev",),
        )
        cases = tuple(
            API.HoldoutCase(name, self.add(source), expected)
            for name, source, expected in (
                ("A", "[4, 4, 1]", "[4, 1]"),
                ("B", "[9, 3, 9]", "[9, 3]"),
            )
        )
        self.runner = InertRunner()
        self.manifest = API.EvaluationManifest(
            evaluator_id="frozen-inert", baseline_steps=("identity",), cases=cases
        )
        self.registry = {
            self.manifest.evaluator_id: API.RegisteredEvaluation(self.manifest, self.runner)
        }
        self.book = API.ProcedureBook(self.store, self.registry)

    def open(self):
        return STORE(
            self.path, EMBEDDER(dimension=32), backup_migrations=False, automatic_backups=False
        )

    def add(self, content):
        result = self.store.add(DRAWER(wing=WING, room="synthetic-evidence", content=content))
        self.assertIsNotNone(result.id)
        return result.id

    def tearDown(self):
        self.store.close()

    def governed(self, version="release-A", **changes):
        return replace(self.spec, governance=metadata(version, **changes))

    def propose(self, version="release-A", **changes):
        return self.book.propose(wing=WING, spec=self.governed(version, **changes))

    def counts(self):
        return tuple(
            self.store._conn.execute("SELECT COUNT(*) FROM " + name).fetchone()[0]  # noqa: S608 - Three fixed fixture table names.
            for name in ("drawers", "procedure_records", "procedure_evaluations")
        )

    def no_write(self, action):
        before = self.counts()
        with self.assertRaises(API.ProcedureError):
            action()
        self.assertEqual(self.counts(), before)

    def payload(self, identifier):
        return json.loads(
            self.store._conn.execute(
                "SELECT payload FROM procedure_records WHERE drawer_id=?", (identifier,)
            ).fetchone()[0]
        )

    def save_payload(self, identifier, payload):
        self.store._conn.execute(
            "UPDATE procedure_records SET payload=? WHERE drawer_id=?",
            (canonical(payload), identifier),
        )

    def test_01_legacy_wire_content_hash_exact(self):
        p = self.book.propose(wing=WING, spec=self.spec)
        self.assertEqual(p.revision_sha256, fingerprint(self.spec))
        self.assertEqual(self.payload(p.drawer_id)["spec"], wire(self.spec))
        self.assertEqual(
            self.store.get(p.drawer_id).content,
            "Discovery: Fresh synthetic method\nState: candidate\n\n" + canonical(wire(self.spec)),
        )
        self.assertNotIn("governance", self.payload(p.drawer_id)["spec"])

    def test_02_legacy_reopen_history_remains_identical(self):
        p = self.book.propose(wing=WING, spec=self.spec)
        original = self.store.get(p.drawer_id).content
        self.store.close()
        self.store = self.open()
        self.book = API.ProcedureBook(self.store, {})
        self.assertEqual(self.book.history(p.drawer_id), [p])
        self.assertEqual(self.store.get(p.drawer_id).content, original)

    def test_03_governance_frozen_verbatim_without_execution(self):
        gov = metadata()
        with self.assertRaises(FrozenInstanceError):
            gov.owner = "overwritten"
        p = self.propose()
        self.assertEqual(p.spec.governance, gov)
        self.assertEqual(self.runner.calls, [])
        self.assertEqual(self.payload(p.drawer_id)["spec"], wire(p.spec))
        self.assertEqual(
            self.store.get(p.drawer_id).content,
            "Discovery: Fresh synthetic method\nState: candidate\n\n" + canonical(wire(p.spec)),
        )

    def test_04_each_field_changes_hash(self):
        first = self.propose()
        for field, value in (
            ("owner", "Different owner"),
            ("version", "release-B"),
            ("rationale", "Different rationale"),
            ("review_due", "1980-01-01"),
        ):
            with self.subTest(field=field):
                p = self.propose(**{field: value})
                self.assertNotEqual(p.revision_sha256, first.revision_sha256)
                self.assertEqual(p.revision_sha256, fingerprint(p.spec))

    def test_05_invalid_complete_primitive_strings_atomic(self):
        class HostileText(str):
            def strip(self):
                raise AssertionError("Caller callback must not run")

        for field in ("owner", "version", "rationale", "review_due"):
            for value in (None, True, 17, "", " \n", HostileText("2026-12-12")):
                with self.subTest(field=field, value=repr(value)):
                    self.no_write(lambda: self.propose(**{field: value}))  # noqa: B023 - Called synchronously.

    def test_06_version_outer_whitespace_atomic(self):
        for version in (" A", "A ", "\nA", "A\t", "\u2003A"):
            with self.subTest(version=repr(version)):
                self.no_write(lambda: self.propose(version=version))  # noqa: B023 - Called synchronously.

    def test_07_dates_exact_real_past_allowed(self):
        for date in ("0001-01-01", "1980-01-01", "2024-02-29", "9999-12-31"):
            self.assertEqual(self.propose(review_due=date).spec.governance.review_due, date)
        for date in (
            "2025-02-29",
            "2026-13-01",
            "2026-04-31",
            "2026-1-01",
            "20261003",
            "2026-10-03T00:00:00",
            "2026-10-03 ",
            "２０２６-１０-０３",  # noqa: RUF001 - Intentional invalid fullwidth date.
        ):
            with self.subTest(date=date):
                self.no_write(lambda: self.propose(review_due=date))  # noqa: B023 - Called synchronously.

    def test_08_unicode_encoding_failures_typed_atomic(self):
        for field in ("owner", "version", "rationale", "review_due"):
            with self.subTest(field=field):
                self.no_write(lambda: self.propose(**{field: "bad\ud800text"}))  # noqa: B023 - Called synchronously.
        first = self.propose()
        for field in ("owner", "version", "rationale"):
            with self.subTest(revise_field=field):
                values = dict(version="release-B")  # noqa: C408 - Preserve original oracle construction.
                values[field] = "bad\udfff"
                self.no_write(
                    lambda: self.book.revise(first.drawer_id, spec=self.governed(**values))  # noqa: B023 - Called synchronously.
                )

    def test_09_exact_type_and_mutated_frozen_revalidated(self):
        for value in ({"owner": "x"}, object()):
            self.no_write(
                lambda: self.book.propose(wing=WING, spec=replace(self.spec, governance=value))  # noqa: B023 - Called synchronously.
            )
        gov = metadata()
        object.__setattr__(gov, "version", " invalid ")
        self.no_write(lambda: self.book.propose(wing=WING, spec=replace(self.spec, governance=gov)))

    def test_10_revision_durable_immutable_history_list(self):
        first = self.propose()
        original = self.store.get(first.drawer_id).content
        second = self.book.revise(
            first.drawer_id,
            spec=self.governed(
                "release-B",
                owner="Second owner",
                rationale="Second reason",
                review_due="2027-01-02",
            ),
        )
        self.store.close()
        self.store = self.open()
        self.book = API.ProcedureBook(self.store, {})
        self.assertEqual(self.book.history(second.drawer_id), [first, second])
        self.assertEqual(self.book.list(wing=WING, active_only=False), [second])
        self.assertEqual(self.store.get(first.drawer_id).content, original)
        self.assertEqual(second.supersedes_id, first.drawer_id)

    def test_11_governance_strip_atomic(self):
        first = self.propose()
        self.no_write(lambda: self.book.revise(first.drawer_id, spec=self.spec))

    def test_12_reused_version_current_and_historical_atomic(self):
        first = self.propose()
        self.no_write(
            lambda: self.book.revise(first.drawer_id, spec=self.governed(owner="changed"))
        )
        second = self.book.revise(first.drawer_id, spec=self.governed("release-B"))
        self.no_write(
            lambda: self.book.revise(second.drawer_id, spec=self.governed(rationale="Reused label"))
        )
        self.assertEqual(
            [p.spec.governance.version for p in self.book.history(second.drawer_id)],
            ["release-A", "release-B"],
        )

    def test_13_versions_family_local_and_legacy_optin(self):
        first, unrelated = self.propose(), self.propose()
        self.assertNotEqual(first.drawer_id, unrelated.drawer_id)
        legacy = self.book.propose(wing=WING, spec=self.spec)
        original = self.store.get(legacy.drawer_id).content
        governed = self.book.revise(legacy.drawer_id, spec=self.governed())
        self.assertEqual(self.book.history(governed.drawer_id), [legacy, governed])
        self.assertIsNone(legacy.spec.governance)
        self.assertEqual(self.store.get(legacy.drawer_id).content, original)

    def test_14_stale_and_interleaved_revision_atomic(self):
        first = self.propose()
        second = self.book.revise(first.drawer_id, spec=self.governed("release-B"))
        self.no_write(lambda: self.book.revise(first.drawer_id, spec=self.governed("release-C")))
        original = self.store.transaction
        interleaved = []

        @contextmanager
        def transaction():
            if not interleaved:
                interleaved.append(True)
                self.book.revise(second.drawer_id, spec=self.governed("release-C"))
            with original():
                yield

        before = self.counts()
        with (
            patch.object(self.store, "transaction", transaction),
            self.assertRaises(API.ProcedureError),
        ):
            self.book.revise(second.drawer_id, spec=self.governed("release-D"))
        self.assertEqual(self.counts(), (before[0] + 1, before[1] + 1, before[2]))
        self.assertEqual(
            [p.spec.governance.version for p in self.book.history(first.drawer_id)],
            ["release-A", "release-B", "release-C"],
        )

    def test_15_evaluate_promote_withdraw_metadata_history(self):
        approvals = []
        self.book._operator_approval = lambda request: approvals.append(request) or True
        first = self.propose()
        original = self.store.get(first.drawer_id).content
        receipt = self.book.evaluate(first.drawer_id, evaluator_id="frozen-inert")
        self.assertTrue(receipt.passed)
        self.assertEqual(len(self.runner.calls), 4)
        promoted = self.book.promote(receipt.current_id, evaluation_id=receipt.drawer_id)
        self.assertEqual(approvals[0].revision_sha256, first.revision_sha256)
        self.assertEqual(self.book.list(wing=WING), [promoted])
        expired = self.book.rollback(promoted.drawer_id, reason="Synthetic withdrawal")
        history = self.book.history(expired.drawer_id)
        self.assertEqual(
            [p.state for p in history], ["candidate", "corroborated", "promoted", "expired"]
        )
        self.assertTrue(all(p.spec.governance == first.spec.governance for p in history))
        self.assertTrue(all(p.revision_sha256 == first.revision_sha256 for p in history))
        self.assertEqual(self.store.get(first.drawer_id).content, original)

    def test_16_owner_does_not_authorize_promotion(self):
        first = self.propose(owner="local-operator")
        receipt = self.book.evaluate(first.drawer_id, evaluator_id="frozen-inert")
        self.no_write(
            lambda: self.book.promote(receipt.current_id, evaluation_id=receipt.drawer_id)
        )
        self.assertEqual(self.book.list(wing=WING), [])

    def test_17_revision_invalidates_evaluation(self):
        self.book._operator_approval = lambda request: True
        first = self.propose()
        receipt = self.book.evaluate(first.drawer_id, evaluator_id="frozen-inert")
        revised = self.book.revise(receipt.current_id, spec=self.governed("release-B"))
        self.assertIsNone(revised.evaluation_id)
        self.no_write(lambda: self.book.promote(revised.drawer_id, evaluation_id=receipt.drawer_id))

    def test_18_holdout_independence_remains_required(self):
        first = self.propose()
        bad = replace(
            self.manifest,
            cases=(
                API.HoldoutCase("A", self.spec.evidence_ids[0], "[8, 2]"),
                self.manifest.cases[1],
            ),
        )
        self.book = API.ProcedureBook(
            self.store, {"frozen-inert": API.RegisteredEvaluation(bad, self.runner)}
        )
        self.no_write(lambda: self.book.evaluate(first.drawer_id, evaluator_id="frozen-inert"))
        self.assertEqual(self.runner.calls, [])

    def test_19_malformed_stored_metadata_typed_all_exposing_reads(self):
        first = self.propose()
        original = self.payload(first.drawer_id)
        valid = original["spec"]["governance"]
        for value in (
            {},
            "forged",
            {**valid, "extra": "ignore"},
            {**valid, "owner": True},
            {**valid, "review_due": "2025-02-29"},
            {**valid, "rationale": "bad\ud800"},
        ):
            changed = copy.deepcopy(original)
            changed["spec"]["governance"] = value
            # Ensure JSON can represent lone surrogates in synthetic corrupt records.
            self.store._conn.execute(
                "UPDATE procedure_records SET payload=? WHERE drawer_id=?",
                (json.dumps(changed, ensure_ascii=True), first.drawer_id),
            )
            try:
                for name, action in (
                    ("history", lambda: self.book.history(first.drawer_id)),
                    ("list", lambda: self.book.list(wing=WING, active_only=False)),
                ):
                    with (
                        self.subTest(value=repr(value), read=name),
                        self.assertRaises(API.ProcedureError),
                    ):
                        action()
            finally:
                self.save_payload(first.drawer_id, original)

    def test_20_hash_tamper_old_and_current_typed(self):
        first = self.propose()
        second = self.book.revise(first.drawer_id, spec=self.governed("release-B"))
        for p, field in ((first, "owner"), (second, "rationale")):
            original = self.payload(p.drawer_id)
            changed = copy.deepcopy(original)
            changed["spec"]["governance"][field] = "tampered"
            self.save_payload(p.drawer_id, changed)
            try:
                with self.assertRaises(API.ProcedureError):
                    self.book.history(second.drawer_id)
                if p == second:
                    with self.assertRaises(API.ProcedureError):
                        self.book.list(wing=WING, active_only=False)
            finally:
                self.save_payload(p.drawer_id, original)

    def test_21_false_approval_and_reentrancy_remain_atomic(self):
        first = self.propose()
        receipt = self.book.evaluate(first.drawer_id, evaluator_id="frozen-inert")
        self.book._operator_approval = lambda request: "yes"
        self.no_write(
            lambda: self.book.promote(receipt.current_id, evaluation_id=receipt.drawer_id)
        )

        def approval(request):
            self.book.revise(receipt.current_id, spec=self.governed("release-B"))
            return True

        self.book._operator_approval = approval
        before = self.counts()
        with self.assertRaises(API.ProcedureError):
            self.book.promote(receipt.current_id, evaluation_id=receipt.drawer_id)
        self.assertEqual(self.counts(), (before[0] + 1, before[1] + 1, before[2]))
        self.assertEqual(self.book.history(first.drawer_id)[-1].state, "candidate")
