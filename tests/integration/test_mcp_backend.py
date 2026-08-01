"""Integration tests for the transport-free MCP backend."""

from __future__ import annotations

import hashlib
import json
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


def test_recall_for_change_surfaces_anchored_drawer(backend: CairntirBackend) -> None:
    backend.remember(
        wing="cairntir",
        room="architecture",
        content="cold start went from twelve minutes to 1.4s by defaulting to fastembed",
        metadata={
            "anchors": [
                {"path": "src/cairntir/memory/embeddings.py", "symbol": "production_provider"}
            ]
        },
    )
    backend.remember(wing="cairntir", room="identity", content="unanchored drawer")

    reply = backend.recall_for_change(files=["src/cairntir/memory/embeddings.py"])

    assert "1 anchored drawer(s)" in reply
    assert "via src/cairntir/memory/embeddings.py:production_provider" in reply
    assert "cold start" in reply
    assert "unanchored drawer" not in reply
    # Recalled content must ride inside the prompt-safety evidence boundary.
    assert "instruction_authority" in reply


def test_recall_for_change_reports_no_match_without_failing(backend: CairntirBackend) -> None:
    backend.remember(
        wing="cairntir",
        room="architecture",
        content="anchored elsewhere",
        metadata={"anchors": [{"path": "src/cairntir/cli.py"}]},
    )
    reply = backend.recall_for_change(files=["src/cairntir/memory/store.py"])
    assert "No anchored drawers touch" in reply
    assert "Scanned 1 anchored drawer(s)" in reply


def test_recall_for_change_warns_about_malformed_anchors(backend: CairntirBackend) -> None:
    """A malformed anchor must be visible in the reply, never silently dropped."""
    backend.remember(
        wing="cairntir",
        room="architecture",
        content="good",
        metadata={"anchors": [{"path": "src/cairntir/cli.py"}]},
    )
    backend.remember(
        wing="cairntir",
        room="architecture",
        content="bad",
        metadata={"anchors": [{"symbol": "missing path"}]},
    )
    reply = backend.recall_for_change(files=["src/cairntir/cli.py"])
    assert "WARNING" in reply
    assert "malformed metadata.anchors" in reply
    assert "#2" in reply


@pytest.mark.parametrize("files", [[], [""], ["  "]])
def test_recall_for_change_rejects_empty_file_list(
    backend: CairntirBackend, files: list[str]
) -> None:
    with pytest.raises(MCPError, match="at least one non-empty file path"):
        backend.recall_for_change(files=files)


def test_recall_receipt_links_to_complete_verbatim_get(backend: CairntirBackend) -> None:
    content = "A deliberately long educational drawer. " + ("evidence " * 40)
    backend.remember(
        wing="cairntir",
        room="exact",
        content=content,
        metadata={"source": "test", "nested": {"verified": True}},
    )

    hits = backend.recall(query="deliberately long educational drawer")
    assert "ref=cairntir://drawer/1" in hits
    assert f"len={len(content)}" in hits
    assert f"sha256={hashlib.sha256(content.encode()).hexdigest()}" in hits
    assert "truncated=true" in hits

    payload = json.loads(backend.get(drawer_id=1))
    assert payload["resource"] == "cairntir://drawer/1"
    assert payload["content"] == content
    assert payload["content_length"] == len(content)
    assert payload["metadata"]["nested"]["verified"] is True


def test_get_missing_drawer_errors(backend: CairntirBackend) -> None:
    with pytest.raises(MCPError, match="no drawer"):
        backend.get(drawer_id=999)


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


def test_discovery_ledger_surfaces_active_learning_at_session_start(
    backend: CairntirBackend,
) -> None:
    backend.remember(
        wing="cairntir",
        room="evidence",
        content="Three independent scoped retrieval tests passed.",
    )
    recorded = backend.discover(
        wing="cairntir",
        title="Scoped retrieval became reliable",
        summary="Filtering before KNN consistently preserves relevant wing-local hits.",
        novelty="cairntir",
        evidence_ids=[1],
        state="candidate",
    )
    assert "Recorded discovery #2 [candidate]" in recorded

    session = backend.session_start(wing="cairntir")
    assert "Active discoveries" in session
    assert "Scoped retrieval became reliable" in session
    assert "cairntir://drawer/1" in session

    log = backend.learning_log(wing="cairntir")
    assert "Human Learning Log" in log
    assert "Scoped retrieval became reliable" in log


def test_discovery_transition_keeps_only_current_leaf(backend: CairntirBackend) -> None:
    backend.remember(wing="cairntir", room="evidence", content="The method repeated.")
    backend.discover(
        wing="cairntir",
        title="Method emerged",
        summary="A repeatable workflow reduced repair time.",
        novelty="user",
        evidence_ids=[1],
        state="candidate",
    )
    corroborated = backend.transition_discovery(
        drawer_id=2,
        state="corroborated",
        note="Three independent examples reproduced the method.",
    )
    assert "drawer #3" in corroborated
    transitioned = backend.transition_discovery(
        drawer_id=3,
        state="promoted",
        note="Patrick reviewed and accepted the method.",
    )
    assert "drawer #4" in transitioned
    listing = backend.discoveries(wing="cairntir")
    assert "cairntir://drawer/4" in listing
    assert "cairntir://drawer/3" not in listing
    assert "cairntir://drawer/2" not in listing
    assert "[promoted]" in listing


def test_discover_rejects_invalid_novelty(backend: CairntirBackend) -> None:
    with pytest.raises(MCPError, match="invalid novelty"):
        backend.discover(
            wing="cairntir",
            title="Bad novelty",
            summary="This label is unsupported.",
            novelty="world-changing",
            evidence_ids=[1],
        )


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


# ------------------------------------------------------------ v1.1: cross_recall


def test_cross_recall_searches_every_wing(backend: CairntirBackend) -> None:
    backend.remember(wing="stars-2026", room="notes", content="deterministic lockstep was key")
    backend.remember(wing="ground-zero", room="notes", content="pure engine functions — no react")
    backend.remember(wing="cairntir", room="notes", content="lazy embedder fixed cold-start")

    out = backend.cross_recall(query="pure engine functions", limit=5)
    # The query text lands in one wing but the tool reports cross-wing provenance.
    assert "across" in out and "wing(s)" in out
    assert "[ground-zero]" in out


def test_cross_recall_finds_answer_in_another_wing(backend: CairntirBackend) -> None:
    backend.remember(
        wing="stars-2026",
        room="decisions",
        content="wasm32 determinism requires f64 rounding discipline",
    )
    # Question asked while the active wing is cairntir; answer lives in stars-2026.
    out = backend.cross_recall(query="wasm32 determinism requires f64 rounding discipline")
    assert "[stars-2026]" in out


def test_cross_recall_empty_query_errors(backend: CairntirBackend) -> None:
    with pytest.raises(MCPError):
        backend.cross_recall(query="   ")


def test_cross_recall_no_hits_is_friendly(backend: CairntirBackend) -> None:
    out = backend.cross_recall(query="nothing like this was ever stored")
    assert "No drawers matched" in out
