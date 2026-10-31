"""Refusal controls for durable iteration attachments."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Literal

import pytest

from cairntir.access import AccessDenied, bind_grant, issue_grant, revoke_grant
from cairntir.errors import MemoryStoreError
from cairntir.iteration_artifacts import IterationArtifactBook, IterationArtifactError
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer, Layer

HERE = Path(__file__).resolve().parent
STL = HERE / "fixtures" / "bracket.stl"
GCODE = HERE / "fixtures" / "bracket.gcode"
WING = "c49-print-fixture"


def _store(path: Path) -> DrawerStore:
    return DrawerStore(path, HashEmbeddingProvider(dimension=32))


def _iteration(store: DrawerStore, *, wing: str = WING) -> int:
    drawer = store.add(
        Drawer(
            wing=wing,
            room="iterations",
            content="A remembered bracket iteration",
            layer=Layer.ON_DEMAND,
            metadata={"source": "blender", "kind": "print_outcome"},
        )
    )
    assert drawer.id is not None
    return drawer.id


def _count(db: Path, table: Literal["iteration_artifact_refs", "iteration_artifact_blobs"]) -> int:
    query = {
        "iteration_artifact_refs": "SELECT count(*) FROM iteration_artifact_refs",
        "iteration_artifact_blobs": "SELECT count(*) FROM iteration_artifact_blobs",
    }[table]
    with sqlite3.connect(db) as connection:
        return int(connection.execute(query).fetchone()[0])


@pytest.mark.parametrize(
    ("damage", "code"),
    [("missing", "ARTIFACT_MISSING"), ("changed", "ARTIFACT_CORRUPT")],
)
def test_missing_or_changed_blob_keeps_reference_and_parent(
    tmp_path: Path, damage: str, code: str
) -> None:
    db = tmp_path / "memory.db"
    with _store(db) as store:
        iteration_id = _iteration(store)
        reference = IterationArtifactBook(store).attach(iteration_id, STL, kind="stl")
    with sqlite3.connect(db) as connection:
        before_parent = connection.execute(
            "SELECT content, metadata FROM drawers WHERE id=?", (iteration_id,)
        ).fetchone()
        if damage == "missing":
            connection.execute(
                "DELETE FROM iteration_artifact_blobs WHERE artifact_id=?",
                (reference.artifact_id,),
            )
        else:
            connection.execute(
                "UPDATE iteration_artifact_blobs SET data=? WHERE artifact_id=?",
                (b"changed print payload", reference.artifact_id),
            )
    before = db.read_bytes()
    with _store(db) as store:
        book = IterationArtifactBook(store)
        assert book.list_for_iteration(iteration_id) == [reference]
        with pytest.raises(IterationArtifactError) as caught:
            book.read(iteration_id, reference.artifact_id)
        assert caught.value.code == code
    assert db.read_bytes() == before
    with sqlite3.connect(db) as connection:
        assert (
            connection.execute(
                "SELECT content, metadata FROM drawers WHERE id=?", (iteration_id,)
            ).fetchone()
            == before_parent
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM iteration_artifact_refs WHERE artifact_id=?",
                (reference.artifact_id,),
            ).fetchone()[0]
            == 1
        )


def test_idempotent_repeat_conflict_and_wrong_parent_refusal(tmp_path: Path) -> None:
    db = tmp_path / "memory.db"
    source = tmp_path / "bracket.stl"
    source.write_bytes(STL.read_bytes())
    with _store(db) as store:
        first_id = _iteration(store)
        second_id = _iteration(store)
        book = IterationArtifactBook(store)
        reference = book.attach(first_id, source, kind="stl", label="bracket.stl")
        assert book.attach(first_id, source, kind="stl", label="bracket.stl") == reference
        source.write_bytes(STL.read_bytes() + b"\nsolid changed\nendsolid changed\n")
        with pytest.raises(IterationArtifactError) as caught:
            book.attach(first_id, source, kind="stl", label="bracket.stl")
        assert caught.value.code == "ATTACHMENT_CONFLICT"
        with pytest.raises(IterationArtifactError) as caught:
            book.read(second_id, reference.artifact_id)
        assert caught.value.code == "ARTIFACT_NOT_FOUND"
        assert book.list_for_iteration(second_id) == []
        assert book.list_for_iteration(first_id) == [reference]
    assert _count(db, "iteration_artifact_refs") == 1
    assert _count(db, "iteration_artifact_blobs") == 1


def test_bounded_input_refuses_before_first_attachment_table(tmp_path: Path) -> None:
    db = tmp_path / "memory.db"
    too_large = tmp_path / "large.stl"
    too_large.write_bytes(STL.read_bytes() * 4)
    with _store(db) as store:
        iteration_id = _iteration(store)
        book = IterationArtifactBook(store, max_bytes=len(STL.read_bytes()))
        for source, kind, label, code in (
            (too_large, "stl", None, "UNSAFE_SOURCE"),
            (STL, "gcode", None, "UNSUPPORTED_ARTIFACT"),
            (GCODE, "gcode", "../outside.gcode", "UNSAFE_SOURCE"),
            (tmp_path / "missing.stl", "stl", None, "UNSAFE_SOURCE"),
        ):
            with pytest.raises(IterationArtifactError) as caught:
                book.attach(iteration_id, source, kind=kind, label=label)
            assert caught.value.code == code
    with sqlite3.connect(db) as connection:
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "iteration_artifact_refs" not in tables
    assert "iteration_artifact_blobs" not in tables


def test_structured_store_attach_refuses_invalid_direct_call(tmp_path: Path) -> None:
    db = tmp_path / "memory.db"
    with _store(db) as store:
        iteration_id = _iteration(store)
        for kind, label, data in (
            ("stl", "blank.stl", b""),
            ("stl", "wrong.gcode", STL.read_bytes()),
        ):
            with pytest.raises(MemoryStoreError):
                store._iteration_artifact_attach(iteration_id, kind, label, data)
    with sqlite3.connect(db) as connection:
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "iteration_artifact_refs" not in tables
    assert "iteration_artifact_blobs" not in tables


def test_scoped_parent_authority_and_live_revocation(tmp_path: Path) -> None:
    db = tmp_path / "memory.db"
    with _store(db) as store:
        allowed_id = _iteration(store)
        withheld_id = _iteration(store)
        token = issue_grant(
            store,
            scopes=[{"wing": WING, "drawer_ids": [allowed_id]}],
            capabilities=["read", "write"],
        )
        scoped = bind_grant(store, token)
        book = IterationArtifactBook(scoped)
        reference = book.attach(allowed_id, STL, kind="stl")
        assert book.read(allowed_id, reference.artifact_id).data == STL.read_bytes()
        with pytest.raises(AccessDenied):
            book.attach(withheld_id, GCODE, kind="gcode")
        with pytest.raises(AccessDenied):
            book.list_for_iteration(withheld_id)
        with pytest.raises(AccessDenied):
            book.read(withheld_id, reference.artifact_id)
        assert _count(db, "iteration_artifact_refs") == 1
        revoke_grant(store, token)
        with pytest.raises(AccessDenied):
            book.read(allowed_id, reference.artifact_id)
        with pytest.raises(AccessDenied):
            book.attach(allowed_id, GCODE, kind="gcode")
    assert _count(db, "iteration_artifact_refs") == 1


def test_second_insert_failure_rolls_back_reference(tmp_path: Path) -> None:
    db = tmp_path / "memory.db"
    with _store(db) as store:
        iteration_id = _iteration(store)
        book = IterationArtifactBook(store)
        first = book.attach(iteration_id, STL, kind="stl")
    with sqlite3.connect(db) as connection:
        connection.execute(
            "CREATE TRIGGER reject_new_artifact_blob BEFORE INSERT ON iteration_artifact_blobs "
            "BEGIN SELECT RAISE(ABORT, 'simulated blob failure'); END"
        )
    with _store(db) as store:
        book = IterationArtifactBook(store)
        with pytest.raises(IterationArtifactError) as caught:
            book.attach(iteration_id, GCODE, kind="gcode")
        assert caught.value.code == "STORE_UNAVAILABLE"
        assert book.list_for_iteration(iteration_id) == [first]
        assert book.read(iteration_id, first.artifact_id).data == STL.read_bytes()
    assert _count(db, "iteration_artifact_refs") == 1
    assert _count(db, "iteration_artifact_blobs") == 1
