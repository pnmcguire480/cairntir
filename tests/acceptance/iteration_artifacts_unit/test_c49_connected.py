"""Independent connected acceptance for remembered print artifacts."""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
from pathlib import Path

import pytest

from cairntir.iteration_artifacts import IterationArtifactBook, IterationArtifactError
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore, backup_database
from cairntir.memory.taxonomy import Drawer, Layer

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
WING = "c49-print-fixture"


def _store(path: Path, *, read_only: bool = False) -> DrawerStore:
    return DrawerStore(path, HashEmbeddingProvider(dimension=32), read_only=read_only)


def _iteration(store: DrawerStore, *, wing: str = WING) -> int:
    drawer = store.add(
        Drawer(
            wing=wing,
            room="iterations",
            content="Bracket print iteration: first layer aligned, preview approved.",
            layer=Layer.ON_DEMAND,
            metadata={"source": "blender", "kind": "print_outcome", "material": "PLA"},
        )
    )
    assert drawer.id is not None
    return drawer.id


def _source(tmp_path: Path, name: str) -> Path:
    return Path(shutil.copyfile(FIXTURES / name, tmp_path / name))


def _parent(db: Path, drawer_id: int) -> tuple[str, str, int]:
    with sqlite3.connect(db) as connection:
        row = connection.execute(
            "SELECT wing, content, access_count FROM drawers WHERE id=?", (drawer_id,)
        ).fetchone()
    assert row is not None
    return str(row[0]), str(row[1]), int(row[2])


def test_two_real_files_survive_source_removal_reopen_and_sqlite_backup(tmp_path: Path) -> None:
    db = tmp_path / "memory.db"
    stl = _source(tmp_path, "bracket.stl")
    gcode = _source(tmp_path, "bracket.gcode")
    originals = {"stl": stl.read_bytes(), "gcode": gcode.read_bytes()}
    with _store(db) as store:
        iteration_id = _iteration(store)
        original_parent = _parent(db, iteration_id)
        book = IterationArtifactBook(store)
        stl_ref = book.attach(iteration_id, stl, kind="stl")
        code_ref = book.attach(iteration_id, gcode, kind="gcode")
        assert stl_ref.artifact_id != code_ref.artifact_id
        assert book.attach(iteration_id, stl, kind="stl") == stl_ref
        assert {ref.artifact_id for ref in book.list_for_iteration(iteration_id)} == {
            stl_ref.artifact_id,
            code_ref.artifact_id,
        }
        assert stl_ref.iteration_identity == store.portable_identity(iteration_id)
        for ref, kind in ((stl_ref, "stl"), (code_ref, "gcode")):
            assert ref.iteration_id == iteration_id and ref.wing == WING and ref.kind == kind
            assert ref.label == (stl if kind == "stl" else gcode).name
            assert ref.byte_count == len(originals[kind])
            assert ref.sha256 == hashlib.sha256(originals[kind]).hexdigest()
            assert str(tmp_path) not in repr(ref)
            assert book.read(iteration_id, ref.artifact_id).data == originals[kind]
    stl.unlink()
    gcode.unlink()
    backup = backup_database(db, tmp_path / "restored.db")
    for path in (db, backup):
        before = path.read_bytes()
        with _store(path, read_only=True) as store:
            book = IterationArtifactBook(store)
            refs = book.list_for_iteration(iteration_id)
            assert {ref.artifact_id for ref in refs} == {
                stl_ref.artifact_id,
                code_ref.artifact_id,
            }
            assert book.read(iteration_id, stl_ref.artifact_id).data == originals["stl"]
            assert book.read(iteration_id, code_ref.artifact_id).data == originals["gcode"]
        assert path.read_bytes() == before
        assert _parent(path, iteration_id) == original_parent


def test_read_only_without_attachment_tables_does_not_create_or_touch(tmp_path: Path) -> None:
    db = tmp_path / "memory.db"
    with _store(db) as store:
        iteration_id = _iteration(store)
    before = db.read_bytes()
    original_parent = _parent(db, iteration_id)
    with _store(db, read_only=True) as store:
        book = IterationArtifactBook(store)
        assert book.list_for_iteration(iteration_id) == []
        with pytest.raises(IterationArtifactError) as caught:
            book.read(iteration_id, 9999)
        assert caught.value.code == "ARTIFACT_NOT_FOUND"
        with pytest.raises(IterationArtifactError) as caught:
            book.attach(iteration_id, FIXTURES / "bracket.stl", kind="stl")
        assert caught.value.code == "STORE_UNAVAILABLE"
    assert db.read_bytes() == before
    assert _parent(db, iteration_id) == original_parent
    with sqlite3.connect(db) as connection:
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "iteration_artifact_refs" not in tables
    assert "iteration_artifact_blobs" not in tables
