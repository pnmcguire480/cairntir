"""Malformed label must use the typed refusal boundary before any write."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from cairntir.errors import MemoryStoreError
from cairntir.iteration_artifacts import IterationArtifactBook, IterationArtifactError
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer, Layer

STL = Path(__file__).resolve().parent / "fixtures/bracket.stl"


@pytest.mark.parametrize("route", ["public", "structured_store"])
def test_surrogate_label_refuses_without_attachment_tables(tmp_path: Path, route: str) -> None:
    db = tmp_path / "memory.db"
    with DrawerStore(db, HashEmbeddingProvider(dimension=32)) as store:
        parent = store.add(
            Drawer(
                wing="c49-print-fixture",
                room="iterations",
                content="Another remembered bracket iteration",
                layer=Layer.ON_DEMAND,
                metadata={"source": "blender", "kind": "print_outcome"},
            )
        )
        assert parent.id is not None
        label = "\ud800.stl"
        if route == "public":
            with pytest.raises(IterationArtifactError) as caught:
                IterationArtifactBook(store).attach(parent.id, STL, kind="stl", label=label)
            assert caught.value.code == "UNSAFE_SOURCE"
        else:
            with pytest.raises(MemoryStoreError):
                store._iteration_artifact_attach(parent.id, "stl", label, STL.read_bytes())
    with sqlite3.connect(db) as connection:
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "iteration_artifact_refs" not in tables
    assert "iteration_artifact_blobs" not in tables
