"""The installed-package recall oracle must require retrieved evidence, not echoed input."""

from __future__ import annotations

import runpy
from pathlib import Path

import pytest

from cairntir.mcp.backend import CairntirBackend
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer

VERIFIER = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/verify_package.py"))
REQUEST = VERIFIER["REQUEST"]
QUERY = VERIFIER["RECALL_QUERY"]
require_recalled_drawer = VERIFIER["require_recalled_drawer"]


def result(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": False}


def test_accepts_exact_retrieved_evidence_for_a_paraphrased_query(tmp_path: Path) -> None:
    assert QUERY not in REQUEST and "café 日本語 🌲" not in QUERY
    with DrawerStore(tmp_path / "store.db", HashEmbeddingProvider(dimension=32)) as store:
        saved = store.add(Drawer(wing="package", room="tasks", content=REQUEST))
        response = CairntirBackend(store).recall(query=QUERY, wing="package", full_content=5)
    require_recalled_drawer(result(response), saved.id, REQUEST)


@pytest.mark.parametrize("query", [REQUEST, QUERY], ids=["original-echo", "paraphrase-echo"])
def test_rejects_zero_hits_even_when_the_backend_echoes_the_query(
    tmp_path: Path, query: str
) -> None:
    with DrawerStore(tmp_path / "store.db", HashEmbeddingProvider(dimension=32)) as store:
        saved = store.add(Drawer(wing="package", room="tasks", content=REQUEST))
        response = CairntirBackend(store).recall(query=query, wing="absent", full_content=5)
    assert response.startswith("No drawers matched ")
    assert repr(query) in response
    with pytest.raises(AssertionError, match="PACKAGE_RECALL:"):
        require_recalled_drawer(result(response), saved.id, REQUEST)


@pytest.mark.parametrize("failure", ["different-drawer", "altered-content"])
def test_rejects_hits_with_the_wrong_identity_or_inexact_content(
    tmp_path: Path, failure: str
) -> None:
    with DrawerStore(tmp_path / "store.db", HashEmbeddingProvider(dimension=32)) as store:
        saved = store.add(Drawer(wing="package", room="tasks", content=REQUEST.strip()))
        if failure == "different-drawer":
            store.add(Drawer(wing="returned", room="tasks", content=REQUEST))
        response = CairntirBackend(store).recall(
            query=QUERY,
            wing="returned" if failure == "different-drawer" else "package",
            full_content=5,
        )
    assert "1 hit(s)" in response
    with pytest.raises(AssertionError, match="PACKAGE_RECALL:"):
        require_recalled_drawer(result(response), saved.id, REQUEST)
