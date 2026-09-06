"""Independent cross-capability and authentic-registry disclosure regressions."""

from __future__ import annotations

import importlib.util
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest
import sqlite_vec

from cairntir import procedures
from cairntir.access import AccessDenied, bind_grant, issue_grant
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer


def _state(path: Path) -> str:
    with closing(sqlite3.connect(path)) as connection:
        connection.enable_load_extension(True)
        sqlite_vec.load(connection)
        connection.enable_load_extension(False)
        names = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        tables = []
        for (name,) in names:
            quoted = name.replace('"', '""')
            rows = connection.execute(f'SELECT * FROM "{quoted}"').fetchall()  # noqa: S608
            tables.append((name, sorted(rows, key=repr)))
        return repr(tables)


@pytest.mark.parametrize("method", ["add_anchors", "repair_anchors"])
def test_write_only_anchor_operations_cannot_read_existing_paths(
    tmp_path: Path, method: str
) -> None:
    database = tmp_path / "anchors.db"
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as owner:
        drawer = owner.add(
            Drawer(
                wing="anchor-proof",
                room="evidence",
                content="original evidence",
                metadata={"anchors": [{"path": "private/source-path-canary.py"}]},
            )
        )
        token = issue_grant(owner, scopes=[{"wing": "anchor-proof"}], capabilities=["write"])
        scoped = bind_grant(owner, token)
        before = _state(database)
        with pytest.raises(AccessDenied):
            if method == "add_anchors":
                scoped.add_anchors(drawer.id, [{"path": "newly-authored.py"}])
            else:
                scoped.repair_anchors(drawer.id)
        assert _state(database) == before


def _procedure_fixture(owner: DrawerStore) -> Any:
    # Reuse the already frozen, independently authored real evaluator fixture.
    path = Path(__file__).with_name("test_procedure_acceptance.py")
    specification = importlib.util.spec_from_file_location("frozen_procedure_fixture", path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module._bundle(procedures, owner)


@pytest.mark.parametrize("hidden_reference", ["receipt-current", "procedure-evaluation"])
def test_authentic_registry_payloads_cannot_disclose_hidden_typed_references(
    tmp_path: Path, hidden_reference: str
) -> None:
    database = tmp_path / "procedure-registry.db"
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as owner:
        fixture = _procedure_fixture(owner)
        candidate = fixture.book.propose(wing="procedure-proof", spec=fixture.spec)
        receipt = fixture.book.evaluate(
            candidate.drawer_id, evaluator_id=fixture.manifest.evaluator_id
        )
        all_ids = [drawer.id for drawer in owner.list_by(limit=None)]
        control = bind_grant(
            owner,
            issue_grant(
                owner,
                scopes=[{"wing": "procedure-proof", "drawer_ids": all_ids}],
                capabilities=["read"],
            ),
        )
        control_book = procedures.ProcedureBook(control, evaluations={})
        assert control_book.get_evaluation(receipt.drawer_id) == receipt
        assert control_book.history(receipt.current_id)[-1].evaluation_id == receipt.drawer_id
        hidden_id = (
            receipt.current_id if hidden_reference == "receipt-current" else receipt.drawer_id
        )
        restricted = bind_grant(
            owner,
            issue_grant(
                owner,
                scopes=[
                    {
                        "wing": "procedure-proof",
                        "drawer_ids": [key for key in all_ids if key != hidden_id],
                    }
                ],
                capabilities=["read"],
            ),
        )
        book = procedures.ProcedureBook(restricted, evaluations={})
        before = _state(database)
        with pytest.raises(AccessDenied):
            if hidden_reference == "receipt-current":
                book.get_evaluation(receipt.drawer_id)
            else:
                book.history(receipt.current_id)
        assert _state(database) == before
