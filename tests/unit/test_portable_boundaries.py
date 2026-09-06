"""Independent boundary proof: imported source metadata has no lifecycle authority."""

from pathlib import Path

from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.portable import export_bundle, import_bundle


def test_nested_supersedes_metadata_cannot_create_a_top_level_supersession(tmp_path: Path) -> None:
    with (
        DrawerStore(tmp_path / "source.db", HashEmbeddingProvider(16)) as source,
        DrawerStore(tmp_path / "target.db", HashEmbeddingProvider(16)) as target,
    ):
        first = source.add(Drawer(wing="portable", room="archive", content="First original."))
        second = source.add(Drawer(wing="portable", room="archive", content="Second original."))
        original = source.add(
            Drawer(
                wing="portable",
                room="archive",
                content="A record with no top-level supersession.",
                metadata={
                    "supersedes_id": first.id,
                    "payload": {"supersedes_id": second.id},
                },
            )
        )
        assert original.supersedes_id is None
        path = tmp_path / "bundle.json"
        export_bundle(source, path)
        result = import_bundle(target, path)
        local_id = result["identity_map"][source.portable_identity(original.id)]
        imported = target.get(local_id)
        assert imported is not None
        assert imported.content == original.content
        assert target.portable_source(local_id)["drawer"]["metadata"] == original.metadata
        assert imported.supersedes_id is None, (
            "Nested source metadata created a new local lifecycle edge; only the original "
            "top-level /supersedes_id reference may activate Drawer.supersedes_id."
        )
