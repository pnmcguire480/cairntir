from __future__ import annotations

from pathlib import Path

import pytest
from test_recovery_outcomes import contents

from cairntir import obsidian
from cairntir.errors import ProjectionError
from cairntir.learning import record_discovery
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore


@pytest.mark.parametrize("boundary", ["read", "replace", "cleanup"])
def test_projection_filesystem_failure_preserves_user_notes_and_allows_retry(
    seeded, tmp_path, monkeypatch, boundary
):
    database, _, _ = seeded
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        result = obsidian.project_to_obsidian(store, vault=vault)
        note = result.learning_log
        original = note.read_bytes() + b"\nKeep my own exact notes.\n"
        note.write_bytes(original)
        record_discovery(
            store,
            wing="recovery",
            title="A new finding",
            summary="Updated generated text with evidence #1; unrelated issue #98765.",
            novelty="user",
            evidence_ids=(1,),
            state="candidate",
        )
        before = contents(database)
        read_text = Path.read_text
        unlink = Path.unlink

        def failed_read(path, *args, **kwargs):
            if path == note:
                raise PermissionError("projection read unavailable")
            return read_text(path, *args, **kwargs)

        def failed_replace(source, target):
            raise OSError("projection destination unavailable")

        def failed_cleanup(path, *args, **kwargs):
            if path.name.endswith(".tmp"):
                raise PermissionError("projection cleanup unavailable")
            return unlink(path, *args, **kwargs)

        with monkeypatch.context() as patch:
            if boundary == "read":
                patch.setattr(Path, "read_text", failed_read)
            else:
                patch.setattr(obsidian.os, "replace", failed_replace)
                if boundary == "cleanup":
                    patch.setattr(Path, "unlink", failed_cleanup)
            with pytest.raises(ProjectionError, match="unavailable"):
                obsidian.project_to_obsidian(store, vault=vault)
        assert note.read_bytes() == original
        assert contents(database) == before
        obsidian.project_to_obsidian(store, vault=vault)
        rendered = note.read_text(encoding="utf-8")
        assert rendered.endswith("\nKeep my own exact notes.\n")
        assert "A new finding" in rendered and "issue #98765" in rendered
        assert "drawer-98765" not in rendered


@pytest.mark.parametrize(
    "damaged",
    [
        b"\xff",
        b"<!-- cairntir:generated:end --><!-- cairntir:generated:begin -->",
        b"<!-- cairntir:generated:begin -->only half a marker pair",
        b"<!-- cairntir:generated:begin --><!-- cairntir:generated:begin -->"
        b"<!-- cairntir:generated:end -->",
    ],
)
def test_damaged_projection_is_never_overwritten_as_generated_content(seeded, tmp_path, damaged):
    database, _, _ = seeded
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    note = vault / "cairntir-sync" / "learning-log.md"
    note.parent.mkdir()
    note.write_bytes(damaged)
    before = contents(database)
    with (
        DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store,
        pytest.raises(ProjectionError),
    ):
        obsidian.project_to_obsidian(store, vault=vault)
    assert note.read_bytes() == damaged
    assert contents(database) == before
