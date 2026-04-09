"""Smoke tests for the ``cairntir`` CLI."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from cairntir import __version__
from cairntir.cli import app
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer, Layer

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_root_banner() -> None:
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "cairntir" in result.stdout


def test_status_empty(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))  # type: ignore[attr-defined]
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "not yet initialized" in result.stdout or "empty" in result.stdout


def test_recall_no_store(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))  # type: ignore[attr-defined]
    result = runner.invoke(app, ["recall", "anything"])
    assert result.exit_code == 1
    assert "no store" in result.stderr.lower() or "no store" in result.output.lower()


def test_status_and_recall_with_drawers(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path))  # type: ignore[attr-defined]
    store = DrawerStore(tmp_path / "cairntir.db", HashEmbeddingProvider())
    store.add(
        Drawer(
            wing="demo",
            room="notes",
            content="cairn stones mark the path",
            layer=Layer.ESSENTIAL,
        )
    )
    store.add(
        Drawer(
            wing="demo",
            room="notes",
            content="palantir sees across distance",
            layer=Layer.ON_DEMAND,
        )
    )

    status = runner.invoke(app, ["status"])
    assert status.exit_code == 0
    assert "2 drawers" in status.stdout
    # Regression: each wing must be printed exactly once.
    assert status.stdout.count("  demo  (") == 1

    recall = runner.invoke(app, ["recall", "cairn stones mark the path", "--limit", "5"])
    assert recall.exit_code == 0
    assert "hit" in recall.stdout
