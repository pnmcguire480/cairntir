from __future__ import annotations

from pathlib import Path

import pytest

from cairntir.codeglass import record_walkthrough
from cairntir.errors import ProjectionError
from cairntir.learning import record_discovery
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.obsidian import project_to_obsidian


def _vault(tmp_path: Path) -> Path:
    vault = tmp_path / "Anthropicer"
    (vault / ".obsidian").mkdir(parents=True)
    return vault


def test_projection_writes_learning_codeglass_and_preserves_user_notes(
    tmp_path: Path,
) -> None:
    vault = _vault(tmp_path)
    with DrawerStore(
        tmp_path / "projection.db",
        HashEmbeddingProvider(dimension=16),
    ) as store:
        evidence = store.add(
            Drawer(
                wing="cairntir",
                room="evidence",
                content="Sensitive raw evidence remains only in SQLite.",
            )
        )
        assert evidence.id is not None
        walkthrough = record_walkthrough(
            store,
            wing="cairntir",
            target="Reason loop",
            reader_level="novice",
            sections={
                name: f"{name} explanation [source:src/reason/loop.py:1]"
                for name in ("what", "how", "where", "when", "why")
            },
            evidence_ids=(evidence.id,),
            glossary="Loop: a repeatable sequence.",
            danger_zones="Runner failures must surface.",
        )
        record_discovery(
            store,
            wing="cairntir",
            title="A learning signal",
            summary="The cited walkthrough improved understanding.",
            novelty="user",
            evidence_ids=(evidence.id,),
            state="candidate",
        )

        result = project_to_obsidian(store, vault=vault, wing="cairntir")
        assert result.learning_log.exists()
        assert len(result.codeglass_notes) == 1
        assert walkthrough.content in result.codeglass_notes[0].read_text(encoding="utf-8")

        receipt = vault / "cairntir-sync" / "receipts" / f"drawer-{evidence.id}.md"
        receipt_text = receipt.read_text(encoding="utf-8")
        assert "Sensitive raw evidence" not in receipt_text
        assert "content sha256" in receipt_text

        codeglass_note = result.codeglass_notes[0]
        codeglass_note.write_text(
            codeglass_note.read_text(encoding="utf-8") + "\nPatrick note: this clicked.\n",
            encoding="utf-8",
        )
        project_to_obsidian(store, vault=vault, wing="cairntir")
        assert "Patrick note: this clicked." in codeglass_note.read_text(encoding="utf-8")


def test_projection_refuses_to_overwrite_unmarked_user_note(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    target = vault / "cairntir-sync" / "learning-log.md"
    target.parent.mkdir(parents=True)
    target.write_text("Patrick owns this file.", encoding="utf-8")
    with (
        DrawerStore(
            tmp_path / "projection.db",
            HashEmbeddingProvider(dimension=16),
        ) as store,
        pytest.raises(ProjectionError, match="user-owned"),
    ):
        project_to_obsidian(store, vault=vault)


def test_shared_evidence_and_prefix_ids_do_not_corrupt_receipt_links(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    with DrawerStore(tmp_path / "memory.db", HashEmbeddingProvider(dimension=16)) as store:
        for index in range(10):
            store.add(Drawer(wing="cairntir", room="evidence", content=f"Fact {index}"))
        for title in ("First discovery", "Second discovery"):
            record_discovery(
                store,
                wing="cairntir",
                title=title,
                summary="Shared evidence.",
                novelty="user",
                evidence_ids=(1, 10),
                state="candidate",
            )
        result = project_to_obsidian(store, vault=vault)
    text = result.learning_log.read_text(encoding="utf-8")
    expected = (
        "- evidence: [[cairntir-sync/receipts/drawer-1|#1]], "
        "[[cairntir-sync/receipts/drawer-10|#10]]"
    )
    assert text.count(expected) == 2
