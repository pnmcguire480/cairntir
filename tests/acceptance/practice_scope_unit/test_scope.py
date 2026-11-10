"""Original R18 completeness and transaction-composition regressions."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import replace

import pytest

from cairntir.access import AccessDenied, ScopedStore
from cairntir.errors import MemoryStoreError
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer

from . import fixtures as _base

bundle = _base.bundle
isolation = _base.isolation


def _snapshot(b):
    return tuple(
        tuple(tuple(row) for row in b.store._conn.execute(f"SELECT * FROM {table} ORDER BY rowid"))  # noqa: S608 - fixed fixture table names
        for table in ("drawers", "procedure_records", "procedure_evaluations")
    )


def _grant_book(b, monkeypatch, scopes, capabilities=("read", "write")):
    scoped = ScopedStore(b.store, "inert-no-persisted-grant")
    monkeypatch.setattr(
        scoped, "_grant", lambda: {"scopes": scopes, "capabilities": list(capabilities)}
    )
    return _base.api.ProcedureBook(scoped, {})


def _call(book, b, operation):
    if operation == "assess":
        return book.assess_review(
            b.promoted.drawer_id,
            period_start="2026-01-01",
            period_end="2026-04-01",
            as_of="2026-04-01",
            policy=_base.policy(),
        )
    if operation == "queue":
        return book.due_reviews(
            wing=_base.WING,
            period_start="2026-01-01",
            period_end="2026-04-01",
            as_of="2026-04-01",
            policy=_base.policy(),
        )
    if operation == "observations":
        return book.observation_history(b.promoted.drawer_id)
    return book.review_history(b.promoted.drawer_id)


def _deny_without_disclosure(action):
    with pytest.raises(AccessDenied) as denied:
        action()
    assert str(denied.value) == "access denied"


@pytest.mark.parametrize("hidden_kind", ["observation", "correction", "review"])
@pytest.mark.parametrize("operation", ["assess", "queue", "observations", "reviews"])
def test_hidden_record_never_becomes_complete_subset_metrics_or_deadline(
    bundle, monkeypatch, hidden_kind, operation
):
    b = bundle
    bad = b.book.record_observation(
        b.promoted.drawer_id,
        observation=_base.obs(
            b, "HIDDEN-SENSITIVE-EVENT", triggered=False, false_positive=None, overridden=None
        ),
    )
    b.book.record_observation(b.promoted.drawer_id, observation=_base.obs(b, "visible-good"))
    owner = _base.assess(b)
    assert owner.metrics[0].trigger_rate == 0.5
    hidden = bad.drawer_id
    if hidden_kind == "correction":
        fixed = b.book.record_observation(
            b.promoted.drawer_id,
            observation=_base.obs(b, "HIDDEN-SENSITIVE-EVENT"),
            supersedes_id=bad.drawer_id,
        )
        hidden = fixed.drawer_id
        assert _base.assess(b).metrics[0].trigger_rate == 1
    elif hidden_kind == "review":
        review = _base.complete(b, owner)
        hidden = review.drawer_id
        assert _base.assess(b).effective_review_due == "2026-07-01"
    ids = [row[0] for row in b.store._conn.execute("SELECT id FROM drawers") if row[0] != hidden]
    scoped = _grant_book(b, monkeypatch, [{"wing": _base.WING, "drawer_ids": ids}])
    before = _snapshot(b)
    _deny_without_disclosure(lambda: _call(scoped, b, operation))
    assert _snapshot(b) == before


@pytest.mark.parametrize("operation", ["assess", "queue", "observations", "reviews"])
def test_currently_all_ids_is_unprovable_completeness_and_denies(bundle, monkeypatch, operation):
    b = bundle
    b.book.record_observation(b.promoted.drawer_id, observation=_base.obs(b))
    ids = [row[0] for row in b.store._conn.execute("SELECT id FROM drawers")]
    scoped = _grant_book(b, monkeypatch, [{"wing": _base.WING, "drawer_ids": ids}])
    before = _snapshot(b)
    _deny_without_disclosure(lambda: _call(scoped, b, operation))
    assert _snapshot(b) == before


@pytest.mark.parametrize("transition", ["withdrawal", "revision"])
@pytest.mark.parametrize("operation", ["assess", "queue"])
def test_hidden_lifecycle_cannot_restore_old_active_revision(
    bundle, monkeypatch, transition, operation
):
    b = bundle
    ids = [row[0] for row in b.store._conn.execute("SELECT id FROM drawers")]
    if transition == "withdrawal":
        b.book.rollback(b.promoted.drawer_id, reason="HIDDEN-SENSITIVE-WITHDRAWAL")
    else:
        b.book.revise(
            b.promoted.drawer_id,
            spec=replace(b.spec, governance=replace(b.spec.governance, version="2")),
        )
    scoped = _grant_book(b, monkeypatch, [{"wing": _base.WING, "drawer_ids": ids}])
    before = _snapshot(b)
    _deny_without_disclosure(lambda: _call(scoped, b, operation))
    assert _snapshot(b) == before


def test_full_unrestricted_wing_read_matches_owner_without_grant_creation(bundle, monkeypatch):
    b = bundle
    receipt = b.book.record_observation(b.promoted.drawer_id, observation=_base.obs(b))
    review = _base.complete(b)
    scoped = _grant_book(b, monkeypatch, [{"wing": _base.WING}])
    for operation in ("assess", "queue", "observations", "reviews"):
        assert _call(scoped, b, operation) == _call(b.book, b, operation)
    assert scoped.get_observation(receipt.drawer_id) == receipt
    assert scoped.get_review(review.drawer_id) == review
    grant_tables = [
        row[0]
        for row in b.store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%grant%'"
        )
    ]
    assert all(
        b.store._conn.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0] == 0  # noqa: S608 - inert SQLite schema names
        for table in grant_tables
    )


@pytest.mark.parametrize("operation", ["assess", "queue", "observations"])
def test_broad_wing_authorization_still_authenticates_hidden_source_dependency(
    bundle, monkeypatch, operation
):
    b = bundle
    external = b.store.add(
        Drawer(wing="hidden-wing", room="cases", content="HIDDEN-SENSITIVE-DEPENDENCY")
    )
    source = b.store.add(
        Drawer(
            wing=_base.WING,
            room="cases",
            content="visible source with inaccessible dependency",
            metadata={"evidence_drawer_ids": [external.id]},
        )
    )
    b.book.record_observation(
        b.promoted.drawer_id, observation=_base.obs(b, evidence_ids=(source.id,))
    )
    scoped = _grant_book(b, monkeypatch, [{"wing": _base.WING}])
    before = _snapshot(b)
    _deny_without_disclosure(lambda: _call(scoped, b, operation))
    assert _snapshot(b) == before


@pytest.mark.parametrize("action", ["record", "complete"])
def test_unprovable_scope_write_denial_is_atomic(bundle, monkeypatch, action):
    b = bundle
    assessment = _base.assess(b)
    ids = [row[0] for row in b.store._conn.execute("SELECT id FROM drawers")]
    scoped = _grant_book(b, monkeypatch, [{"wing": _base.WING, "drawer_ids": ids}])
    before = _snapshot(b)

    def call():
        if action == "record":
            return scoped.record_observation(b.promoted.drawer_id, observation=_base.obs(b))
        return scoped.complete_review(
            b.promoted.drawer_id,
            assessment=assessment,
            reviewer="reviewer",
            decision="retain",
            rationale="visible rationale",
            next_review_due="2026-07-01",
        )

    _deny_without_disclosure(call)
    assert _snapshot(b) == before


class _CallerRollbackError(Exception):
    pass


@pytest.mark.parametrize("action", ["record", "complete"])
@pytest.mark.parametrize("commit", [False, True])
def test_outer_transaction_receipt_is_provisional_until_caller_commit(bundle, action, commit):
    b = bundle
    assessment = _base.assess(b)
    before = _snapshot(b)
    try:
        with b.store.transaction():
            provisional = (
                b.book.record_observation(b.promoted.drawer_id, observation=_base.obs(b))
                if action == "record"
                else _base.complete(b, assessment)
            )
            with closing(sqlite3.connect(b.path)) as observer:
                assert observer.execute(
                    "SELECT count(*) FROM procedure_evaluations WHERE drawer_id=?",
                    (provisional.drawer_id,),
                ).fetchone() == (0,)
            if not commit:
                raise _CallerRollbackError()  # noqa: TRY301 - explicit caller rollback control
    except _CallerRollbackError:
        pass
    if not commit:
        assert _snapshot(b) == before
    with DrawerStore(b.path, HashEmbeddingProvider(dimension=16)) as reopened:
        book = _base.api.ProcedureBook(reopened, {})
        if commit:
            actual = (
                book.get_observation(provisional.drawer_id)
                if action == "record"
                else book.get_review(provisional.drawer_id)
            )
            assert actual == provisional
        else:
            with pytest.raises(_base.api.ProcedureError):
                (book.get_observation if action == "record" else book.get_review)(
                    provisional.drawer_id
                )


@pytest.mark.parametrize("action", ["record", "complete"])
def test_owned_commit_failure_returns_no_receipt_rolls_back_and_retries(bundle, action):
    b = bundle
    assessment = _base.assess(b)
    before = _snapshot(b)
    denied = []

    def authorizer(code, first, second, database, origin):
        if code == sqlite3.SQLITE_TRANSACTION and first == "COMMIT" and not denied:
            denied.append(True)
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    b.store._conn.set_authorizer(authorizer)
    try:
        with pytest.raises(MemoryStoreError):
            b.book.record_observation(
                b.promoted.drawer_id, observation=_base.obs(b)
            ) if action == "record" else _base.complete(b, assessment)
    finally:
        b.store._conn.set_authorizer(None)
    assert denied and _snapshot(b) == before
    receipt = (
        b.book.record_observation(b.promoted.drawer_id, observation=_base.obs(b))
        if action == "record"
        else _base.complete(b, assessment)
    )
    assert receipt.drawer_id > 0
