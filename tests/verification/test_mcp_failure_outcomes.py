from __future__ import annotations

import pytest
from test_recovery_outcomes import TEXT, contents

from cairntir.errors import MCPError, MemoryStoreError
from cairntir.mcp.backend import CairntirBackend
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore


@pytest.mark.parametrize(
    "arguments",
    [
        {"resume": "true"},
        {"resume": True, "task": TEXT},
        {"resume": True, "files": ["src/store.py"]},
        {"resume": True, "candidate_limit": 1},
        {"resume": True, "recover_transcripts": True},
        {"task": TEXT, "recover_transcripts": True},
        {"candidate_limit": 1},
        {"budget_chars": 0},
    ],
)
def test_ambiguous_mcp_handoff_arguments_cannot_silently_select_another_mode(seeded, arguments):
    database, task, expected = seeded
    before = contents(database)
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        backend = CairntirBackend(store)
        with pytest.raises(MCPError):
            backend.handoff(wing="recovery", **arguments)
        assert contents(database) == before
        assert (
            backend.handoff(wing="recovery", resume=True, task_id=task, budget_chars=8192)
            == expected
        )


@pytest.mark.parametrize(
    ("method", "arguments"),
    [
        ("session_start", {"wing": "recovery", "budget_chars": 0}),
        ("crucible", {"claim": " "}),
        ("discoveries", {"state": "invented"}),
        ("discoveries", {"limit": 0}),
        ("learning_log", {"limit": 0}),
        ("discover_scan", {"wing": "recovery", "min_observations": 1}),
        ("discover_scan", {"wing": "recovery", "confidence_threshold": 2}),
        ("transition_discovery", {"drawer_id": 1, "state": "invented", "note": "reject"}),
        ("transition_discovery", {"drawer_id": 999, "state": "rejected", "note": "reject"}),
    ],
)
def test_invalid_mcp_learning_request_reports_error_without_appending_false_evidence(
    seeded, method, arguments
):
    database, _, _ = seeded
    before = contents(database)
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        backend = CairntirBackend(store)
        with pytest.raises((MCPError, MemoryStoreError)):
            getattr(backend, method)(**arguments)
        assert contents(database) == before
        assert "No new multi-episode" in backend.discover_scan(wing="recovery")
