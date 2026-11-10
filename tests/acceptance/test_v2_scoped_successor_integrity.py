import pytest

from cairntir.access import AccessDenied, bind_grant, issue_grant
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer


def test_scoped_writer_sees_hidden_successor_existence_without_its_contents(tmp_path):
    with DrawerStore(tmp_path / "memory.db", HashEmbeddingProvider(32)) as store:
        original = store.add(
            Drawer(wing="decision", room="shared", content="Use Postgres for the datastore")
        )
        hidden = store.add(
            Drawer(
                wing="decision",
                room="private",
                content="Reversed: use SQLite instead",
                supersedes_id=original.id,
            )
        )
        token = issue_grant(
            store,
            scopes=[{"wing": "decision", "rooms": ["shared"]}],
            capabilities=["read", "write"],
        )
        scoped = bind_grant(store, token)
        assert [drawer.id for drawer in scoped.list_by(wing="decision", limit=None)] == [
            original.id
        ]
        assert scoped.has_direct_successor(original.id) is True
        assert scoped.context_suppressed_ids([original.id]) == {original.id}
        with pytest.raises(AccessDenied):
            scoped.has_direct_successor(hidden.id)
        with pytest.raises(AccessDenied):
            scoped.context_suppressed_ids([hidden.id])
        with pytest.raises(AccessDenied):
            scoped.get(hidden.id)
        assert store.get(hidden.id).content == "Reversed: use SQLite instead"
