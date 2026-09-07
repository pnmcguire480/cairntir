from __future__ import annotations

import sqlite3
from datetime import datetime

import pytest
from test_recovery_outcomes import TEXT, contents

from cairntir.access import AccessDenied, bind_grant, issue_grant, revoke_grant
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Layer


@pytest.mark.parametrize(
    "scopes",
    [
        [{"wing": ""}],
        [{"wing": "recovery", "unknown": True}],
        [{"wing": "recovery", "rooms": "evidence"}],
        [{"wing": "recovery", "rooms": [None]}],
        [{"wing": "recovery", "drawer_ids": [True]}],
        [{"wing": "recovery", "drawer_ids": [0]}],
    ],
)
def test_invalid_grant_never_creates_authority_or_changes_evidence(seeded, scopes):
    database, _, _ = seeded
    before = contents(database)
    with (
        DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store,
        pytest.raises(AccessDenied),
    ):
        issue_grant(store, scopes=scopes, capabilities=["read"], principal="verification")
    assert contents(database) == before


@pytest.mark.parametrize("capabilities", [["admin"], "read"])
def test_unknown_or_ambiguous_capabilities_cannot_create_a_grant(seeded, capabilities):
    database, _, _ = seeded
    before = contents(database)
    with (
        DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store,
        pytest.raises(AccessDenied, match="capabilities"),
    ):
        issue_grant(
            store,
            scopes=[{"wing": "recovery"}],
            capabilities=capabilities,
            principal="verification",
        )
    assert contents(database) == before


def test_timezone_ambiguous_expiry_cannot_create_an_unbounded_grant(seeded):
    database, _, _ = seeded
    before = contents(database)
    with (
        DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store,
        pytest.raises(AccessDenied, match="timezone"),
    ):
        issue_grant(
            store,
            scopes=[{"wing": "recovery"}],
            capabilities=["read"],
            principal="verification",
            expires_at=datetime(2030, 1, 1),
        )
    assert contents(database) == before


def test_bound_grant_allows_metadata_updates_only_inside_its_scope(seeded):
    database, _, _ = seeded
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        token = issue_grant(
            store,
            scopes=[{"wing": "recovery", "drawer_ids": [1]}],
            capabilities=["read", "write"],
            principal="verification",
        )
        scoped = bind_grant(store, token)
        scoped.update_layer(1, Layer.DEEP)
        assert scoped.get(1).layer is Layer.DEEP
        assert scoped.add_anchors(1, [{"path": "src/example.py"}]) == [{"path": "src/example.py"}]
        before = contents(database)
        assert scoped.repair_anchors(1) == [{"path": "src/example.py"}]
        assert contents(database) == before
        assert scoped.reinforce(1, amount=2) == 3
        assert scoped.weaken(1, amount=1) == 2
        assert scoped.get(1).content == TEXT
        for operation in (
            lambda: scoped.update_layer(2, Layer.DEEP),
            lambda: scoped.add_anchors(2, [{"path": "src/example.py"}]),
            lambda: scoped.repair_anchors(2),
            lambda: scoped.reinforce(2),
            lambda: scoped.weaken(2),
        ):
            before = contents(database)
            with pytest.raises(AccessDenied):
                operation()
            assert contents(database) == before


def test_binding_cannot_widen_existing_grant_or_expose_its_owner(seeded):
    database, _, _ = seeded
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        token = issue_grant(
            store, scopes=[{"wing": "recovery"}], capabilities=["read"], principal="verification"
        )
        scoped = bind_grant(store, token)
        before = contents(database)
        for operation in (
            lambda: bind_grant(scoped, token),
            lambda: issue_grant(
                scoped, scopes=[{"wing": "recovery"}], capabilities=["write"], principal="other"
            ),
            lambda: revoke_grant(scoped, token),
            lambda: scoped._conn,
            lambda: scoped.checkpoint(),
        ):
            with pytest.raises(AccessDenied):
                operation()
            assert contents(database) == before


@pytest.mark.parametrize("token", [None, "", "   ", 1, "unknown"])
def test_invalid_token_cannot_expose_any_existing_memory(seeded, token):
    database, _, _ = seeded
    before = contents(database)
    with (
        DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store,
        pytest.raises(AccessDenied),
    ):
        bind_grant(store, token)
    assert contents(database) == before


def test_lost_grant_read_access_denies_existing_bound_session_then_recovers(seeded):
    database, _, _ = seeded
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        token = issue_grant(
            store, scopes=[{"wing": "recovery"}], capabilities=["read"], principal="verification"
        )
        scoped = bind_grant(store, token)
        before = contents(database)
        store._conn.set_authorizer(
            lambda action, table, *_: (
                sqlite3.SQLITE_DENY
                if action == sqlite3.SQLITE_READ and table == "access_grants"
                else sqlite3.SQLITE_OK
            )
        )
        try:
            with pytest.raises(AccessDenied):
                scoped.list_by()
        finally:
            store._conn.set_authorizer(None)
        assert contents(database) == before
        assert [item.id for item in scoped.list_by(wing="recovery", room="evidence")] == [1]
