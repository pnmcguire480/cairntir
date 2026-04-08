"""Integration tests for the transport-free MCP backend."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from cairntir.errors import MCPError
from cairntir.mcp.backend import CairntirBackend
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Layer


@pytest.fixture()
def backend(tmp_path: Path) -> Iterator[CairntirBackend]:
    with DrawerStore(tmp_path / "mcp.db", HashEmbeddingProvider(dimension=32)) as store:
        yield CairntirBackend(store)


def test_remember_then_recall_roundtrip(backend: CairntirBackend) -> None:
    reply = backend.remember(
        wing="cairntir", room="phase-2", content="MCP server wired with 6 tools"
    )
    assert "Stored drawer #1" in reply
    assert "cairntir/phase-2" in reply

    hits = backend.recall(query="MCP server wired with 6 tools")
    assert "#1" in hits
    assert "MCP server wired" in hits


def test_recall_empty_query_errors(backend: CairntirBackend) -> None:
    with pytest.raises(MCPError):
        backend.recall(query="   ")


def test_remember_rejects_bad_layer(backend: CairntirBackend) -> None:
    with pytest.raises(MCPError):
        backend.remember(wing="cairntir", room="x", content="y", layer="nope")


def test_session_start_renders_layers(backend: CairntirBackend) -> None:
    backend.remember(wing="cairntir", room="who", content="Patrick owns this", layer="identity")
    backend.remember(wing="cairntir", room="state", content="phase 2 shipping", layer="essential")
    out = backend.session_start(wing="cairntir")
    assert "Identity (1)" in out
    assert "Essential (1)" in out
    assert "Patrick owns this" in out
    assert "phase 2 shipping" in out


def test_session_start_with_query_pulls_on_demand(backend: CairntirBackend) -> None:
    backend.remember(wing="cairntir", room="notes", content="kill cross chat amnesia forever")
    out = backend.session_start(wing="cairntir", query="kill cross chat amnesia forever")
    assert "On-demand" in out
    assert "amnesia" in out


def test_timeline_filters_by_entity(backend: CairntirBackend) -> None:
    backend.remember(wing="cairntir", room="decisions", content="decided on sqlite-vec")
    backend.remember(wing="cairntir", room="decisions", content="unrelated note")
    backend.remember(wing="cairntir", room="decisions", content="sqlite-vec benchmarks passed")

    out = backend.timeline(wing="cairntir", entity="sqlite-vec")
    assert "2 entries" in out
    assert "decided on sqlite-vec" in out
    assert "unrelated note" not in out


def test_timeline_empty_entity_errors(backend: CairntirBackend) -> None:
    with pytest.raises(MCPError):
        backend.timeline(wing="cairntir", entity="")


def test_audit_emits_quality_skill_with_essentials(backend: CairntirBackend) -> None:
    backend.remember(
        wing="cairntir",
        room="state",
        content="phase 3 in progress",
        layer=Layer.ESSENTIAL.value,
    )
    out = backend.audit(wing="cairntir")
    assert "name: quality" in out
    assert "QUALITY — The Ship Gate" in out
    assert "essential drawers=1" in out
    assert "phase 3 in progress" in out


def test_audit_reports_empty_essential_layer(backend: CairntirBackend) -> None:
    out = backend.audit(wing="cairntir")
    assert "essential drawers=0" in out
    assert "the essential layer is empty" in out


def test_crucible_emits_skill_with_claim(backend: CairntirBackend) -> None:
    out = backend.crucible(claim="cairntir will kill amnesia")
    assert "name: crucible" in out
    assert "CRUCIBLE — The Epistemic Forge" in out
    assert "## Claim under crucible" in out
    assert "cairntir will kill amnesia" in out


def test_crucible_rejects_empty(backend: CairntirBackend) -> None:
    with pytest.raises(MCPError):
        backend.crucible(claim="  ")
