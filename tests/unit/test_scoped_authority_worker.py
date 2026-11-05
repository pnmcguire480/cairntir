from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from cairntir.access import AccessDenied, bind_grant, issue_grant, revoke_grant, validate_startup
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer


@pytest.fixture
def authority(tmp_path: Path) -> Iterator[tuple[DrawerStore, Path, Drawer, Drawer, str]]:
    path = tmp_path / "authority.db"
    with DrawerStore(path, HashEmbeddingProvider(32)) as owner:
        public = owner.add(Drawer(wing="worker", room="public", content="public evidence"))
        private = owner.add(Drawer(wing="worker", room="private", content="private evidence"))
        token = issue_grant(owner, scopes=[{"wing": "worker"}], capabilities=["read"])
        yield owner, path, public, private, token


def _children() -> set[int]:
    return {child.pid for child in multiprocessing.active_children()}


def _files(root: Path) -> dict[str, tuple[int, bytes]]:
    return {
        path.name: (path.stat().st_mtime_ns, path.read_bytes())
        for path in root.iterdir()
        if path.is_file()
    }


def test_snapshot_worker_is_reused_but_live_scope_and_revocation_are_not_cached(authority) -> None:
    owner, path, public, private, token = authority
    with (
        DrawerStore(path, HashEmbeddingProvider(32), read_only=True) as snapshot,
        closing(bind_grant(snapshot, token)) as scoped,
    ):
        reader = scoped._grant_reader
        assert reader is not None
        pid = reader._process.pid
        assert pid is not None and pid != os.getpid()
        for _ in range(3):
            assert scoped.get(public.id).content == public.content
            assert scoped.get(private.id).content == private.content
            assert scoped._grant_reader is reader and reader._process.pid == pid
        with owner.transaction():
            owner._conn.execute(
                "UPDATE access_grants SET scopes=? WHERE token_hash=?",
                (
                    json.dumps([{"wing": "worker", "rooms": ["public"]}]),
                    hashlib.sha256(token.encode()).hexdigest(),
                ),
            )
        assert scoped.get(public.id).content == public.content
        with pytest.raises(AccessDenied):
            scoped.get(private.id)
        assert scoped._grant_reader is reader and reader._process.pid == pid
        revoke_grant(owner, token)
        with pytest.raises(AccessDenied):
            scoped.get(public.id)


def test_owner_scope_observes_revocation_without_starting_worker(authority) -> None:
    owner, _, public, _, token = authority
    scoped = bind_grant(owner, token)
    assert scoped.get(public.id).content == public.content
    assert scoped._grant_reader is None
    revoke_grant(owner, token)
    changes = owner._conn.total_changes
    with pytest.raises(AccessDenied):
        scoped.get(public.id)
    assert owner._conn.total_changes == changes
    assert scoped._grant_reader is None


def test_snapshot_reads_and_revoked_bind_leave_cold_original_bytes_and_sidecars_untouched(
    tmp_path: Path,
) -> None:
    path = tmp_path / "cold.db"
    with DrawerStore(path, HashEmbeddingProvider(32)) as owner:
        saved = owner.add(Drawer(wing="worker", room="public", content="original evidence"))
        token = issue_grant(owner, scopes=[{"wing": "worker"}], capabilities=["read"])
    before = _files(tmp_path)
    assert set(before) == {"cold.db"}
    with (
        DrawerStore(path, HashEmbeddingProvider(32), read_only=True) as snapshot,
        closing(bind_grant(snapshot, token)) as scoped,
    ):
        assert scoped.get(saved.id).content == saved.content
        assert [drawer.id for drawer in scoped.list_by(limit=None)] == [saved.id]
        assert _files(tmp_path) == before
    assert _files(tmp_path) == before
    with DrawerStore(path, HashEmbeddingProvider(32)) as owner:
        revoke_grant(owner, token)
    before = _files(tmp_path)
    children = _children()
    with (
        DrawerStore(path, HashEmbeddingProvider(32), read_only=True) as snapshot,
        pytest.raises(AccessDenied),
    ):
        bind_grant(snapshot, token)
    assert _children() == children
    assert _files(tmp_path) == before


def test_scope_close_closes_worker_and_pipe(authority) -> None:
    _, path, public, _, token = authority
    with DrawerStore(path, HashEmbeddingProvider(32), read_only=True) as snapshot:
        scoped = bind_grant(snapshot, token)
        try:
            assert scoped.get(public.id).content == public.content
            reader = scoped._grant_reader
            process, connection = reader._process, reader._connection
            pid = process.pid
        finally:
            scoped.close()
        assert reader._closed and connection.closed
        assert pid not in _children()


def test_dead_authority_helper_fails_closed_without_restart(authority) -> None:
    _, path, public, _, token = authority
    with (
        DrawerStore(path, HashEmbeddingProvider(32), read_only=True) as snapshot,
        closing(bind_grant(snapshot, token)) as scoped,
    ):
        reader = scoped._grant_reader
        process = reader._process
        process.terminate()
        process.join(timeout=5)
        assert not process.is_alive()
        for _ in range(2):
            with pytest.raises(AccessDenied):
                scoped.get(public.id)
            assert scoped._grant_reader is reader
        assert reader._closed and reader._connection.closed


def test_snapshot_workers_keep_tokens_isolated(authority) -> None:
    owner, path, public, private, _ = authority
    public_token = issue_grant(
        owner, scopes=[{"wing": "worker", "rooms": ["public"]}], capabilities=["read"]
    )
    private_token = issue_grant(
        owner, scopes=[{"wing": "worker", "rooms": ["private"]}], capabilities=["read"]
    )
    with (
        DrawerStore(path, HashEmbeddingProvider(32), read_only=True) as first,
        DrawerStore(path, HashEmbeddingProvider(32), read_only=True) as second,
        closing(bind_grant(first, public_token)) as public_scope,
        closing(bind_grant(second, private_token)) as private_scope,
    ):
        assert public_scope._grant_reader._process.pid != private_scope._grant_reader._process.pid
        assert public_scope.get(public.id).content == public.content
        assert private_scope.get(private.id).content == private.content
        with pytest.raises(AccessDenied):
            public_scope.get(private.id)
        with pytest.raises(AccessDenied):
            private_scope.get(public.id)
        revoke_grant(owner, public_token)
        with pytest.raises(AccessDenied):
            public_scope.get(public.id)
        assert private_scope.get(private.id).content == private.content


def test_invalid_startup_token_does_not_leave_authority_worker(authority) -> None:
    _, path, _, _, token = authority
    children = _children()
    with pytest.raises(AccessDenied):
        validate_startup(path, token + "invalid")
    assert _children() == children
