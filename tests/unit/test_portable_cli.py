from pathlib import Path

import pytest
from typer.testing import CliRunner

import cairntir.cli as cli
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer


def test_v2_cli_roundtrip_maps_original_relationships(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, target, bundle = (tmp_path / name for name in ("source.db", "target.db", "bundle.json"))
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(cli, "ensure_registered", lambda: None)
    monkeypatch.setattr(cli, "maybe_check_in_background", lambda: None)
    monkeypatch.setattr(cli, "pending_update_banner", lambda: None)
    monkeypatch.setattr(
        cli, "production_embedding_provider", lambda: HashEmbeddingProvider(dimension=16)
    )
    with DrawerStore(source, HashEmbeddingProvider(dimension=16)) as store:
        first = store.add(Drawer(wing="archive", room="evidence", content="Original."))
        store.add(
            Drawer(wing="archive", room="evidence", content="Correction.", supersedes_id=first.id)
        )
        identity = store.portable_identity(first.id)
    monkeypatch.setattr(cli, "db_path", lambda **kwargs: source)
    exported = CliRunner().invoke(cli.app, ["export", str(bundle), "--format", "2"])
    assert exported.exit_code == 0, exported.output
    monkeypatch.setattr(cli, "db_path", lambda **kwargs: target)
    for _ in range(2):
        imported = CliRunner().invoke(cli.app, ["import", str(bundle), "--format", "2"])
        assert imported.exit_code == 0, imported.output
    with DrawerStore(target, HashEmbeddingProvider(dimension=16)) as store:
        drawers = store.list_by(limit=None)
        assert len(drawers) == 2
        original = next(item for item in drawers if item.content == "Original.")
        correction = next(item for item in drawers if item.content == "Correction.")
        assert correction.supersedes_id == original.id
        assert store.portable_identity(original.id) == identity
