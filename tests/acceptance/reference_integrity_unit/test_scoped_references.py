"""Small independent controls for scoped creation's complete reference checks."""

from __future__ import annotations

import json
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from cairntir.access import AccessDenied, ScopedStore, bind_grant, issue_grant, revoke_grant
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer

from .fixture_core import snapshot

WING = "r20-scoped-reference-proof"
PRINCIPAL = "synthetic scoped reference fixture"


@pytest.fixture(autouse=True)
def isolation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("HOME", "USERPROFILE", "CAIRNTIR_HOME", "HF_HOME", "XDG_CACHE_HOME"):
        path = tmp_path / name.lower()
        path.mkdir()
        monkeypatch.setenv(name, str(path))
    for name in (
        "CAIRNTIR_DISABLE_AUTOREGISTER",
        "CAIRNTIR_DISABLE_UPDATE_CHECK",
        "HF_HUB_OFFLINE",
    ):
        monkeypatch.setenv(name, "1")

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("scoped reference fixture attempted network access")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


@pytest.fixture
def scenario(tmp_path: Path):
    path = tmp_path / "references.db"
    owner = DrawerStore(path, HashEmbeddingProvider(dimension=16))
    sources = []
    for number in range(4):
        saved = owner.add(
            Drawer(wing=WING, room="sources", content=f"SYNTHETIC reference source {number}")
        )
        assert saved.id is not None
        sources.append(saved.id)
    token = issue_grant(
        owner,
        scopes=[{"wing": WING}],
        capabilities=["read", "write"],
        principal=PRINCIPAL,
    )
    result = SimpleNamespace(
        owner=owner,
        path=path,
        sources=sources,
        token=token,
        target=bind_grant(owner, token),
    )
    try:
        yield result
    finally:
        result.owner.close()


def output(*, content: str = "SYNTHETIC derived output", metadata: object = None, parent=None):
    return Drawer(
        wing=WING,
        room="outputs",
        content=content,
        metadata={} if metadata is None else metadata,
        supersedes_id=parent,
    )


def reopen(s: SimpleNamespace, expected: object) -> None:
    assert not s.owner.transaction_active
    assert snapshot(s.owner._conn) == expected
    s.owner.close()
    s.owner = DrawerStore(s.path, HashEmbeddingProvider(dimension=16))
    assert snapshot(s.owner._conn) == expected


def refused(s: SimpleNamespace, drawer: Drawer) -> str:
    before = snapshot(s.owner._conn)
    with pytest.raises(AccessDenied) as caught:
        s.target.add(drawer)
    reopen(s, before)
    return str(caught.value)


@pytest.mark.parametrize("kind", ["nested", "textual", "all-kinds", "duplicate-paths"])
def test_recognized_references_preserve_all_relationships(
    scenario: SimpleNamespace, kind: str
) -> None:
    s = scenario
    a, b, c, d = s.sources
    if kind == "nested":
        drawer = output(
            metadata={"nested": {"items": [{"evidence_ids": [a, b]}], "parent_drawer_id": c}}
        )
        expected, count = {a, b, c}, 3
    elif kind == "textual":
        drawer = output(content=f"SYNTHETIC cairntir://drawer/{a} and CAIRNTIR://DRAWER/{b}")
        expected, count = {a, b}, 2
    elif kind == "all-kinds":
        drawer = output(
            parent=a,
            metadata={
                "evidence_drawer_ids": [b],
                "counterexample_drawer_ids": [c],
                "walkthrough_id": d,
                "derived_from": a,
                "evidence_ids": [b],
                "parent_drawer_id": c,
            },
        )
        expected, count = {a, b, c, d}, 7
    else:
        drawer = output(
            content=f"SYNTHETIC cairntir://drawer/{a} cairntir://drawer/{a}",
            metadata={"evidence_ids": [a, a], "nested": {"derived_from": a, "parent_drawer_id": a}},
        )
        expected, count = {a}, 5
    saved = s.target.add(drawer)
    assert saved.id is not None
    relations = s.owner.portable_relations(saved.id)
    assert {item["target_drawer_id"] for item in relations} == expected
    assert len(relations) == count
    rows = {item.id: item for item in s.owner.list_by(wing=WING, room="outputs", limit=None)}
    assert rows[saved.id].content == drawer.content
    assert rows[saved.id].metadata == drawer.metadata
    before = snapshot(s.owner._conn)
    reopen(s, before)
    assert s.owner.portable_relations(saved.id) == relations
    assert snapshot(s.owner._conn) == before


@pytest.mark.parametrize("kind", ["missing", "hidden-indirect"])
def test_unavailable_reference_closure_refuses_without_failed_write(
    scenario: SimpleNamespace, kind: str
) -> None:
    s = scenario
    if kind == "missing":
        reference = 999999
    else:
        hidden = s.owner.add(
            Drawer(wing="other-wing", room="private", content="SYNTHETIC hidden source detail")
        )
        assert hidden.id is not None
        derived = s.owner.add(
            Drawer(
                wing=WING,
                room="sources",
                content="SYNTHETIC derived visible-scope source",
                metadata={"evidence_ids": [hidden.id]},
            )
        )
        assert derived.id is not None
        reference = derived.id
    message = refused(s, output(metadata={"nested": {"evidence_ids": [reference]}}))
    assert "SYNTHETIC hidden source detail" not in message


def test_expired_grant_refuses_before_creation(scenario: SimpleNamespace) -> None:
    s = scenario
    with s.owner.transaction():
        changed = s.owner._conn.execute(
            "UPDATE access_grants SET expires_at=? WHERE principal=?",
            ((datetime.now(UTC) - timedelta(days=1)).isoformat(), PRINCIPAL),
        )
        assert changed.rowcount == 1
    refused(s, output())


def test_write_only_empty_positive_reference_set_still_creates(scenario: SimpleNamespace) -> None:
    s = scenario
    token = issue_grant(
        s.owner,
        scopes=[{"wing": WING}],
        capabilities=["write"],
        principal="synthetic write-only creation",
    )
    write_only = bind_grant(s.owner, token)
    drawer = output(
        content="SYNTHETIC nonpositive cairntir://drawer/0",
        metadata={"evidence_ids": [0, -1, False, 1.0], "nested": {"derived_from": None}},
    )
    saved = write_only.add(drawer)
    assert saved.id is not None and s.owner.portable_relations(saved.id) == []
    before = snapshot(s.owner._conn)
    reopen(s, before)


def test_write_only_nonempty_reference_set_is_denied(scenario: SimpleNamespace) -> None:
    s = scenario
    token = issue_grant(
        s.owner,
        scopes=[{"wing": WING}],
        capabilities=["write"],
        principal="synthetic write-only referenced creation",
    )
    s.target = bind_grant(s.owner, token)
    refused(s, output(metadata={"evidence_ids": [s.sources[0]]}))


@pytest.mark.parametrize("mutation", ["revoke", "narrow", "remove-read"])
def test_grant_change_after_genuine_row_delivery_prevents_creation(
    scenario: SimpleNamespace, mutation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = scenario
    native = ScopedStore._rows
    after_change = []

    def deliver(target: ScopedStore, *, capability: str = "read") -> object:
        result = native(target, capability=capability)
        if not after_change and s.sources[0] in result:
            assert not s.owner.transaction_active
            if mutation == "revoke":
                revoke_grant(s.owner, s.token)
            else:
                column = "scopes" if mutation == "narrow" else "capabilities"
                value = (
                    [{"wing": WING, "rooms": ["sources", "outputs"]}]
                    if mutation == "narrow"
                    else ["write"]
                )
                with s.owner.transaction():
                    changed = s.owner._conn.execute(
                        f"UPDATE access_grants SET {column}=? WHERE principal=?",  # noqa: S608 - column is one of two fixed literals
                        (json.dumps(value), PRINCIPAL),
                    )
                    assert changed.rowcount == 1
            after_change.append(snapshot(s.owner._conn))
        return result

    monkeypatch.setattr(ScopedStore, "_rows", deliver)
    with pytest.raises(AccessDenied):
        s.target.add(output(metadata={"evidence_ids": [s.sources[0]]}))
    assert len(after_change) == 1, "control did not mutate authority after genuine row delivery"
    reopen(s, after_change[0])
