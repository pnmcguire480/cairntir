"""Independent supporting probes for reviewed automatic-backup failure boundaries."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cairntir import backups
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer


@pytest.fixture()
def configured(tmp_cairntir_home: Path) -> tuple[Path, Path]:
    database = tmp_cairntir_home / "cairntir.db"
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        store.add(Drawer(wing="backup-failure", room="evidence", content="Original evidence."))
    existing = set(tmp_cairntir_home.iterdir())
    backups.configure(database, tmp_cairntir_home / "copies")
    configurations = [
        path for path in set(tmp_cairntir_home.iterdir()) - existing if path.suffix == ".json"
    ]
    assert len(configurations) == 1
    return database, configurations[0]


@pytest.mark.parametrize("damage", ["invalid-utf8", "nonstring-owner"])
def test_damaged_configuration_warns_without_blocking_startup_or_committed_write(
    configured: tuple[Path, Path], damage: str
) -> None:
    database, configuration = configured
    if damage == "invalid-utf8":
        configuration.write_bytes(b"\xff")
    else:
        state = json.loads(configuration.read_text(encoding="utf-8"))
        state["owner"] = 17
        configuration.write_text(json.dumps(state), encoding="utf-8")
    damaged = configuration.read_bytes()
    with pytest.raises(backups.BackupError):
        backups.run(database)
    with pytest.warns(backups.BackupWarning, match=".+"):
        owner = DrawerStore(database, HashEmbeddingProvider(dimension=32), automatic_backups=True)
    try:
        with pytest.warns(backups.BackupWarning, match=".+"):
            saved = owner.add(
                Drawer(
                    wing="backup-failure",
                    room="evidence",
                    content="Committed despite damaged backup configuration.",
                )
            )
        assert not owner._conn.in_transaction
    finally:
        owner.close()
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as reopened:
        assert saved.id is not None
        retrieved = reopened.get(saved.id)
        assert retrieved is not None and retrieved.content == saved.content
    assert configuration.read_bytes() == damaged


def test_status_omits_deleted_snapshot_without_rewriting_interrupted_manifest(
    configured: tuple[Path, Path],
) -> None:
    database, configuration = configured
    first = backups.run(database)["snapshot"]
    removed = backups.run(database)["snapshot"]
    before = configuration.read_bytes()
    Path(removed["path"]).unlink()
    assert Path(removed["path"]).with_name("receipt.json").is_file()
    files = set(database.parent.rglob("*"))

    result = backups.status(database)

    assert result["snapshots"] == [first]
    assert Path(first["path"]).is_file()
    assert result["last_success_at"] == removed["created_at"]
    assert not result["in_progress"]
    assert configuration.read_bytes() == before
    assert set(database.parent.rglob("*")) == files
