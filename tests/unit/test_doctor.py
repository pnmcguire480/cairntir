"""Tests for `cairntir doctor --gate` — the gate that runs where the data lives.

The seams plan's law: a check that runs where its subject does not exist is
worse than no check, because it advertises protection it cannot provide. The
CI store-health step skips on hosted runners (no store there), so the gate
lives here — in the CLI, where a real bank exists. That makes *these* the
load-bearing tests: the gate must genuinely fail on a damaged store and skip
loudly when there is nothing to gate. A gate that can only pass is the defect
it exists to prevent, wearing a disguise.

Nothing here touches the real store. Every test points CAIRNTIR_HOME at a
temporary directory, and the embedding provider is swapped for the cheap
hash provider so no real model loads.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cairntir.cli import app
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer

runner = CliRunner()

_LEAKED_CONTENT = '<parameter name="content">a leaked envelope</content>'


@pytest.fixture(autouse=True)
def _isolate_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Never let a developer's real store or vault leak into a test."""
    monkeypatch.delenv("CAIRNTIR_VAULT", raising=False)
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "cairntir.cli.production_embedding_provider",
        lambda: HashEmbeddingProvider(dimension=32),
    )


def _make_store(tmp_path: Path, *, drawers: int = 1) -> Path:
    """Create a healthy store in the temporary CAIRNTIR_HOME and return its path."""
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    db = home / "cairntir.db"
    with DrawerStore(db, HashEmbeddingProvider(dimension=32)) as store:
        for index in range(drawers):
            store.add(
                Drawer(
                    wing="cairntir",
                    room="journey",
                    content=f"ordinary drawer {index}",
                    metadata={"k": "v"},
                )
            )
    return db


def _make_vault(tmp_path: Path, notes: dict[str, str]) -> Path:
    """Build a minimal Obsidian vault with mapped walkthrough notes."""
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    for relative, text in notes.items():
        target = vault / "walkthroughs" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return vault


def test_gate_fails_on_a_damaged_store(tmp_path: Path) -> None:
    """The one test the whole gate exists to make possible."""
    db = _make_store(tmp_path)

    # Stage the damage behind the write guard the only way such rows can
    # still arise — rewriting a stored row directly, like the pre-guard
    # history did.
    conn = sqlite3.connect(db)
    conn.execute(
        "UPDATE drawers SET content = ?, metadata = '' WHERE id = 1",
        (_LEAKED_CONTENT,),
    )
    conn.commit()
    conn.close()

    result = runner.invoke(app, ["doctor", "--gate"])
    assert result.exit_code == 1, result.output
    assert "tool-call envelope serialized into content" in result.output
    assert "gate: FAIL" in result.output


def test_gate_passes_on_a_healthy_store(tmp_path: Path) -> None:
    _make_store(tmp_path)
    result = runner.invoke(app, ["doctor", "--gate"])
    assert result.exit_code == 0, result.output
    assert "store is whole." in result.output
    assert "gate: ok" in result.output
    # No vault configured: the skip must be loud, not silent.
    assert "vault gate: SKIP" in result.output


def test_gate_skips_loudly_when_there_is_no_store(tmp_path: Path) -> None:
    (tmp_path / "home").mkdir(exist_ok=True)
    result = runner.invoke(app, ["doctor", "--gate"])
    assert result.exit_code == 0, result.output
    assert "SKIP: no store at" in result.output


def test_gate_fails_on_vault_drift(tmp_path: Path) -> None:
    _make_store(tmp_path)
    vault = _make_vault(
        tmp_path,
        {"Triangulate/2026-03-30-pipeline-audit.md": "The audit found three gaps."},
    )
    result = runner.invoke(app, ["doctor", "--gate", "--vault", str(vault)])
    assert result.exit_code == 1, result.output
    assert "DRIFT" in result.output


def test_gate_passes_when_every_walkthrough_has_a_drawer(tmp_path: Path) -> None:
    """The drift gate must be able to pass too — after the import, not before."""
    from cairntir.vault import apply_sync, plan_sync, resolve_vault

    db = _make_store(tmp_path)
    vault = _make_vault(
        tmp_path,
        {"Triangulate/2026-03-30-pipeline-audit.md": "The audit found three gaps."},
    )

    with DrawerStore(db, HashEmbeddingProvider(dimension=32)) as store:
        plan = plan_sync(store, resolve_vault(vault))
        apply_sync(store, plan, model="test")

    result = runner.invoke(app, ["doctor", "--gate", "--vault", str(vault)])
    assert result.exit_code == 0, result.output
    assert "every vault walkthrough has a drawer." in result.output
