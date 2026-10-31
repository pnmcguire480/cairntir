"""Selector-sensitive registered-discovery authorization boundary."""

from __future__ import annotations

from pathlib import Path

import pytest

from cairntir.access import AccessDenied, bind_grant, issue_grant
from cairntir.learning import list_discoveries, record_discovery
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.procedures import ProcedureBook, ProcedureSpec


def test_id_only_selector_uses_matched_registered_rows_before_dependency_closure(
    tmp_path: Path,
) -> None:
    wing = "juniper"
    with DrawerStore(tmp_path / "cairntir.db", HashEmbeddingProvider(dimension=32)) as owner:
        private_evidence = owner.add(
            Drawer(wing=wing, room="sources", content="procedure source hidden from ID grants")
        )
        assert private_evidence.id is not None
        registered = ProcedureBook(owner, {}).propose(
            wing=wing,
            spec=ProcedureSpec(
                "Registered candidate",
                ("local case",),
                "Local situation",
                ("check registered source",),
                "registered source checked",
                ("return to prior method",),
                (private_evidence.id,),
            ),
        )
        ordinary_evidence = owner.add(
            Drawer(wing=wing, room="discoveries", content="ordinary cited observation")
        )
        assert ordinary_evidence.id is not None
        ordinary = record_discovery(
            owner,
            wing=wing,
            title="Ordinary visible lesson",
            summary="Keep the cited observation.",
            novelty="user",
            evidence_ids=(ordinary_evidence.id,),
            state="candidate",
        )
        selected_ordinary = issue_grant(
            owner,
            scopes=[{"wing": wing, "drawer_ids": [ordinary_evidence.id, ordinary.drawer_id]}],
            capabilities=["read"],
        )
        selected_registered = issue_grant(
            owner,
            scopes=[{"wing": wing, "drawer_ids": [registered.drawer_id]}],
            capabilities=["read"],
        )
        before = owner._conn.total_changes
        ordinary_view = bind_grant(owner, selected_ordinary)
        assert [
            item.drawer_id for item in list_discoveries(ordinary_view, wing=wing, active_only=True)
        ] == [ordinary.drawer_id]
        registered_view = bind_grant(owner, selected_registered)
        with pytest.raises(AccessDenied):
            list_discoveries(registered_view, wing=wing, active_only=True)
        assert owner._conn.total_changes == before
