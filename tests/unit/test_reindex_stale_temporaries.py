"""A crashed reindex must not leave its rebuild copy behind forever."""

from __future__ import annotations

from pathlib import Path

import pytest

from cairntir.errors import MemoryStoreError
from cairntir.mcp.server import _tool_specs
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore, reindex_database
from cairntir.memory.taxonomy import Drawer

ORPHAN = f".cairntir.db.reindex-{'a' * 32}.tmp"


def _seeded(tmp_path: Path) -> Path:
    database = tmp_path / "cairntir.db"
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        store.add(Drawer(wing="wing", room="room", content="kept"), model="test")
    return database


def _rebuild(database: Path) -> None:
    reindex_database(database, HashEmbeddingProvider(dimension=32))


def test_next_reindex_removes_orphans_and_keeps_every_drawer(tmp_path: Path) -> None:
    database = _seeded(tmp_path)
    for name in (ORPHAN, f"{ORPHAN}-wal", f"{ORPHAN}-shm"):
        (tmp_path / name).write_bytes(b"left by a crash")

    _rebuild(database)

    assert [p.name for p in tmp_path.iterdir() if ".reindex-" in p.name] == []
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        assert store.search("kept", wing="wing", room="room", limit=1)[0][0].content == "kept"


@pytest.mark.parametrize(
    "name",
    [
        ".cairntir.db.reindex-notes.tmp",
        f".cairntir.db.reindex-{'a' * 32}.tmp.bak",
        f".other.db.reindex-{'a' * 32}.tmp",
        f"cairntir.db.reindex-{'a' * 32}.tmp",
    ],
)
def test_lookalike_files_are_never_deleted(tmp_path: Path, name: str) -> None:
    database = _seeded(tmp_path)
    lookalike = tmp_path / name
    lookalike.write_bytes(b"not ours")

    _rebuild(database)

    assert lookalike.read_bytes() == b"not ours"


def test_undeletable_orphan_is_reported_and_source_is_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _seeded(tmp_path)
    (tmp_path / ORPHAN).write_bytes(b"held by a running reindex")
    before = database.read_bytes()
    unlink = Path.unlink

    def denied(path: Path, *args: object, **kwargs: object) -> None:
        if path.name == ORPHAN:
            raise OSError("in use")
        unlink(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "unlink", denied)
    with pytest.raises(MemoryStoreError, match="another reindex may be running"):
        _rebuild(database)
    assert database.read_bytes() == before


def test_correct_tool_states_the_key_formats_it_enforces() -> None:
    tool = next(spec for spec in _tool_specs() if spec.name == "cairntir_correct")
    properties = tool.inputSchema["properties"]
    assert "UUID" in properties["idempotency_key"]["description"]
    assert "portable_identity" in properties["source_identity"]["description"]
