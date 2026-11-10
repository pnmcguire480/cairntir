"""Independent real-SQLite equivalence and SQL budget for scoped closure."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from cairntir.access import AccessDenied, bind_grant, issue_grant, revoke_grant
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer

from .fixture_core import snapshot

WING = "r20-scoped-closure-proof"


@pytest.fixture
def scenario(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    for name in (
        "CAIRNTIR_DISABLE_AUTOREGISTER",
        "CAIRNTIR_DISABLE_UPDATE_CHECK",
        "HF_HUB_OFFLINE",
    ):
        monkeypatch.setenv(name, "1")
    owner = DrawerStore(tmp_path / "closure.db", HashEmbeddingProvider(dimension=16))
    token = issue_grant(owner, scopes=[{"wing": WING}], capabilities=["read", "write"])
    value = SimpleNamespace(owner=owner, token=token, target=bind_grant(owner, token))
    try:
        yield value
    finally:
        owner.close()


def add(s, content, *, refs=(), wing=WING, metadata=None, parent=None):
    row = s.owner.add(
        Drawer(
            wing=wing,
            room="sources",
            content=content,
            metadata={"evidence_ids": list(refs)} if metadata is None else metadata,
            supersedes_id=parent,
        )
    )
    assert row.id is not None
    return row.id


def visible(s):
    return {row.id for row in s.target.list_by(wing=WING, limit=None, include_expired=True)}


def source(s, key):
    return s.owner.portable_source(key)


def replace_source(s, key, value):
    with s.owner.transaction():
        changed = s.owner._conn.execute(
            "UPDATE portable_records SET record=? WHERE drawer_id=?",
            (json.dumps(value, ensure_ascii=True) if value is not None else None, key),
        )
        assert changed.rowcount == 1


def test_direct_transitive_hidden_dependencies_preserve_healthy_rows(scenario):
    s = scenario
    healthy = add(s, "SYNTHETIC healthy")
    hidden = add(s, "SYNTHETIC hidden", wing="foreign-wing")
    direct = add(s, "SYNTHETIC direct", refs=(hidden,))
    add(s, "SYNTHETIC transitive", refs=(direct,))
    ordinary = add(s, "SYNTHETIC ordinary", refs=(healthy,))
    before = snapshot(s.owner._conn)
    assert visible(s) == {healthy, ordinary}
    assert snapshot(s.owner._conn) == before


def test_all_seven_reference_kinds_still_resolve(scenario):
    s = scenario
    a = add(s, "SYNTHETIC a")
    b = add(s, "SYNTHETIC b")
    child = add(
        s,
        "SYNTHETIC typed references",
        parent=a,
        metadata={
            "evidence_drawer_ids": [a],
            "counterexample_drawer_ids": [b],
            "walkthrough_id": a,
            "derived_from": b,
            "evidence_ids": [a],
            "parent_drawer_id": b,
        },
    )
    assert visible(s) == {a, b, child}
    assert len(s.owner.portable_relations(child)) == 7


def test_canonical_string_targets_use_zero_individual_identity_queries(scenario):
    s = scenario
    a = add(s, "SYNTHETIC query source a")
    b = add(s, "SYNTHETIC query source b")
    child = add(s, "SYNTHETIC repeated references", refs=(a, b, a, b))
    statements = []
    s.owner._conn.set_trace_callback(statements.append)
    try:
        assert visible(s) == {a, b, child}
    finally:
        s.owner._conn.set_trace_callback(None)
    lookups = [
        text
        for text in statements
        if re.search(
            r"(?is)^\s*SELECT\s+drawer_id\s+FROM\s+portable_records\s+WHERE\s+identity\s*=", text
        )
    ]
    assert lookups == [], f"per-target identity queries remain: {lookups}"
    assert statements, "SQL trace did not observe a genuine public closure read"


@pytest.mark.parametrize("kind", ["missing-original", "unknown-target"])
def test_missing_identity_or_original_withholds_transitive_ancestors(scenario, kind):
    s = scenario
    healthy = add(s, "SYNTHETIC healthy unrelated")
    target = add(s, "SYNTHETIC target")
    direct = add(s, "SYNTHETIC direct", refs=(target,))
    parent = add(s, "SYNTHETIC parent", refs=(direct,))
    if kind == "missing-original":
        with s.owner.transaction():
            s.owner._conn.execute("DELETE FROM portable_records WHERE drawer_id=?", (target,))
        expected = {healthy}
    else:
        record = source(s, direct)
        record["references"][0]["target_identity"] = str(uuid4())
        replace_source(s, direct, record)
        expected = {healthy, target}
    before = snapshot(s.owner._conn)
    assert visible(s) == expected and parent not in visible(s)
    assert snapshot(s.owner._conn) == before


@pytest.mark.parametrize("kind", ["invalid-json", "null-original"])
def test_corrupt_source_still_withholds_row_and_dependent(scenario, kind):
    s = scenario
    healthy = add(s, "SYNTHETIC healthy")
    corrupt = add(s, "SYNTHETIC corrupt original")
    add(s, "SYNTHETIC dependent", refs=(corrupt,))
    with s.owner.transaction():
        s.owner._conn.execute(
            "UPDATE portable_records SET record=? WHERE drawer_id=?",
            ("{broken" if kind == "invalid-json" else None, corrupt),
        )
    before = snapshot(s.owner._conn)
    assert visible(s) == {healthy}
    assert snapshot(s.owner._conn) == before


def test_visible_cycle_and_later_narrowed_grant_keep_fixed_point_semantics(scenario):
    s = scenario
    a = add(s, "SYNTHETIC cyclic a")
    b = add(s, "SYNTHETIC cyclic b", refs=(a,))
    record = source(s, a)
    record["references"] = [
        {
            "kind": "evidence",
            "path": "/metadata/evidence_ids/0",
            "source_target_id": b,
            "target_identity": s.owner.portable_identity(b),
        }
    ]
    replace_source(s, a, record)
    assert visible(s) == {a, b}
    with s.owner.transaction():
        s.owner._conn.execute(
            "UPDATE access_grants SET scopes=?",
            (json.dumps([{"wing": WING, "drawer_ids": [a]}]),),
        )
    before = snapshot(s.owner._conn)
    assert visible(s) == set()
    assert snapshot(s.owner._conn) == before


@pytest.mark.parametrize("target", [[], {}, None, True, 1.0])
def test_nonstring_target_keeps_existing_sqlite_binding_refusal(scenario, target):
    s = scenario
    healthy = add(s, "SYNTHETIC healthy")
    malformed = add(s, "SYNTHETIC malformed target", refs=(healthy,))
    record = source(s, malformed)
    record["references"][0]["target_identity"] = target
    replace_source(s, malformed, record)
    before = snapshot(s.owner._conn)
    assert visible(s) == {healthy}
    assert snapshot(s.owner._conn) == before


@pytest.mark.parametrize("kind", ["null-references", "missing-target-key"])
def test_malformed_reference_shape_keeps_existing_fail_closed_exception(scenario, kind):
    s = scenario
    a = add(s, "SYNTHETIC source")
    child = add(s, "SYNTHETIC malformed shape", refs=(a,))
    record = source(s, child)
    if kind == "null-references":
        record["references"] = None
        error = TypeError
    else:
        del record["references"][0]["target_identity"]
        error = KeyError
    replace_source(s, child, record)
    before = snapshot(s.owner._conn)
    with pytest.raises(error):
        visible(s)
    assert snapshot(s.owner._conn) == before


def test_surrogate_identity_keeps_existing_unicode_error(scenario):
    s = scenario
    a = add(s, "SYNTHETIC source")
    child = add(s, "SYNTHETIC surrogate target", refs=(a,))
    record = source(s, child)
    record["references"][0]["target_identity"] = "\ud800"
    replace_source(s, child, record)
    before = snapshot(s.owner._conn)
    with pytest.raises(UnicodeEncodeError):
        visible(s)
    assert snapshot(s.owner._conn) == before


def test_identity_map_is_fresh_after_actual_database_change(scenario):
    s = scenario
    a = add(s, "SYNTHETIC source")
    child = add(s, "SYNTHETIC dependent", refs=(a,))
    original = s.owner.portable_identity(a)
    assert visible(s) == {a, child}
    with s.owner.transaction():
        s.owner._conn.execute(
            "UPDATE portable_records SET identity=? WHERE drawer_id=?", (str(uuid4()), a)
        )
    assert visible(s) == {a}
    with s.owner.transaction():
        s.owner._conn.execute(
            "UPDATE portable_records SET identity=? WHERE drawer_id=?", (original, a)
        )
    assert visible(s) == {a, child}


def test_grant_is_fresh_on_the_next_public_call(scenario):
    s = scenario
    a = add(s, "SYNTHETIC source")
    assert visible(s) == {a}
    revoke_grant(s.owner, s.token)
    before = snapshot(s.owner._conn)
    with pytest.raises(AccessDenied):
        visible(s)
    assert snapshot(s.owner._conn) == before


def test_identity_map_sql_failure_is_fail_closed(scenario):
    s = scenario
    a = add(s, "SYNTHETIC source")
    add(s, "SYNTHETIC dependent", refs=(a,))
    before = snapshot(s.owner._conn)

    def authorize(action, table, column, _database, _trigger):
        if action == sqlite3.SQLITE_READ and table == "portable_records" and column == "identity":
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    s.owner._conn.set_authorizer(authorize)
    try:
        with pytest.raises(AccessDenied):
            visible(s)
    finally:
        s.owner._conn.set_authorizer(None)
    assert snapshot(s.owner._conn) == before
