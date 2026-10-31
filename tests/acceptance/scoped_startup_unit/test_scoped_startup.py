"""Scoped startup discovery filtering over disposable stores."""

from __future__ import annotations

from pathlib import Path

from cairntir.access import bind_grant, issue_grant
from cairntir.learning import list_discoveries, record_discovery
from cairntir.mcp.backend import CairntirBackend
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer, Layer
from cairntir.procedures import ProcedureBook, ProcedureSpec

WING = "juniper"
PUBLIC = "repair the juniper request cache"
HIDDEN = "private-discovery-canary-b81d"


def test_public_only_startup_with_no_visible_discoveries_does_not_probe_hidden_history(
    tmp_path: Path,
) -> None:
    with DrawerStore(tmp_path / "cairntir.db", HashEmbeddingProvider(dimension=32)) as owner:
        owner.add(Drawer(wing=WING, room="public", content=PUBLIC, layer=Layer.ESSENTIAL))
        evidence = owner.add(Drawer(wing=WING, room="discoveries", content=HIDDEN))
        assert evidence.id is not None
        record_discovery(
            owner,
            wing=WING,
            title=HIDDEN,
            summary=HIDDEN,
            novelty="user",
            evidence_ids=(evidence.id,),
            state="candidate",
        )
        token = issue_grant(
            owner,
            scopes=[{"wing": WING, "rooms": ["public"]}],
            capabilities=["read"],
        )
        scoped = bind_grant(owner, token)
        before = owner._conn.total_changes
        assert list_discoveries(scoped, wing=WING, active_only=True, limit=None) == []
        brief = CairntirBackend(scoped).session_start(wing=WING)
        assert PUBLIC in brief
        assert HIDDEN not in brief
        assert owner._conn.total_changes == before


def test_visible_unregistered_active_discovery_remains_in_authorized_brief(
    tmp_path: Path,
) -> None:
    with DrawerStore(tmp_path / "cairntir.db", HashEmbeddingProvider(dimension=32)) as owner:
        evidence = owner.add(
            Drawer(wing=WING, room="discoveries", content="observed repeatable cache repair")
        )
        assert evidence.id is not None
        discovery = record_discovery(
            owner,
            wing=WING,
            title="Request cache repair lesson",
            summary="Check key invalidation before a retry.",
            novelty="user",
            evidence_ids=(evidence.id,),
            state="candidate",
        )
        token = issue_grant(
            owner,
            scopes=[{"wing": WING, "rooms": ["discoveries"]}],
            capabilities=["read"],
        )
        scoped = bind_grant(owner, token)
        before = owner._conn.total_changes
        visible = list_discoveries(scoped, wing=WING, active_only=True, limit=None)
        assert [item.drawer_id for item in visible] == [discovery.drawer_id]
        brief = CairntirBackend(scoped).session_start(wing=WING)
        assert "Request cache repair lesson" in brief
        assert owner._conn.total_changes == before


def test_mixed_wings_do_not_demand_legacy_wing_procedure_history(tmp_path: Path) -> None:
    with DrawerStore(tmp_path / "cairntir.db", HashEmbeddingProvider(dimension=32)) as owner:
        procedure_evidence = owner.add(
            Drawer(wing=WING, room="sources", content="local procedure proposal source")
        )
        assert procedure_evidence.id is not None
        registered = ProcedureBook(owner, {}).propose(
            wing=WING,
            spec=ProcedureSpec(
                "Candidate method",
                ("local case",),
                "Local situation",
                ("check source",),
                "source checked",
                ("return to old method",),
                (procedure_evidence.id,),
            ),
        )
        legacy_evidence = owner.add(
            Drawer(wing="cedar", room="discoveries", content="ordinary lesson source")
        )
        assert legacy_evidence.id is not None
        ordinary = record_discovery(
            owner,
            wing="cedar",
            title="Ordinary lesson",
            summary="Cited observation remains visible.",
            novelty="user",
            evidence_ids=(legacy_evidence.id,),
            state="candidate",
        )
        token = issue_grant(
            owner,
            scopes=[{"wing": WING}, {"wing": "cedar", "rooms": ["discoveries"]}],
            capabilities=["read"],
        )
        scoped = bind_grant(owner, token)
        before = owner._conn.total_changes
        listed = list_discoveries(scoped, wing=None, active_only=True, limit=None)
        assert {item.drawer_id for item in listed} == {
            ordinary.drawer_id,
            registered.drawer_id,
        }
        assert owner._conn.total_changes == before
