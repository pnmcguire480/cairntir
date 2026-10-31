from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4

import pytest
import sqlite_vec

from cairntir.access import AccessDenied, bind_grant, issue_grant, revoke_grant
from cairntir.mcp.backend import CairntirBackend
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.obsidian_bridge import CorrectionError


def _state(path: Path) -> str:
    with closing(sqlite3.connect(path)) as conn:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        schema = conn.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"
        ).fetchall()
        tables = []
        for kind, name, _, _ in schema:
            if kind == "table":
                quoted = name.replace('"', '""')
                rows = conn.execute(f'SELECT * FROM "{quoted}"').fetchall()  # noqa: S608
                tables.append((name, sorted(rows, key=repr)))
        return repr((schema, tables, conn.execute("PRAGMA user_version").fetchone()))


def test_correction_replay_requires_live_grant(tmp_cairntir_home: Path) -> None:
    path = tmp_cairntir_home / "cairntir.db"
    with DrawerStore(path, HashEmbeddingProvider(dimension=32)) as owner:
        source = owner.add(
            Drawer(
                wing="correction-access",
                room="database",
                content="Decision: use Postgres. Original canary 85d76a.",
            )
        )
        assert source.id is not None
        original = owner.get(source.id)
        token = issue_grant(owner, scopes=[{"wing": source.wing}], capabilities=["read", "write"])
        with bind_grant(owner, token) as scoped:
            backend = CairntirBackend(scoped)
            request = {
                "wing": source.wing,
                "source_drawer_id": source.id,
                "source_identity": owner.portable_identity(source.id),
                "source_sha256": hashlib.sha256(source.content.encode()).hexdigest(),
                "content": "Decision reversed: use SQLite. Correction canary 3b61fa.",
                "idempotency_key": str(uuid4()),
            }
            receipt = json.loads(backend.correct(**request))
            assert receipt["status"] == "committed"
            assert receipt["replayed"] is False
            assert receipt["source_drawer_id"] == source.id
            assert receipt["source_identity"] == request["source_identity"]
            successor = owner.get(receipt["correction_drawer_id"])
            assert successor is not None
            assert successor.id != source.id
            assert successor.supersedes_id == source.id
            assert successor.content == request["content"]
            assert owner.get(source.id) == original

            committed = _state(path)
            assert json.loads(backend.correct(**request)) == {**receipt, "replayed": True}
            assert _state(path) == committed

            revoke_grant(owner, token)
            revoked = _state(path)
            assert revoked != committed
            with pytest.raises((AccessDenied, CorrectionError)) as denied:
                backend.correct(**request)
            assert source.content not in str(denied.value)
            assert request["content"] not in str(denied.value)
            assert request["source_identity"] not in str(denied.value)
            assert _state(path) == revoked
