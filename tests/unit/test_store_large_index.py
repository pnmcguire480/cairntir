"""Semantic search must keep answering past sqlite-vec's per-query limit of 4,096."""

from __future__ import annotations

from pathlib import Path

import pytest

from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer, Layer


class _SmallWindowEmbedder(HashEmbeddingProvider):
    """Split drawers into tiny chunks so a real store passes the limit cheaply."""

    max_input_chars = 4


def _chunk_heavy_store(path: Path) -> DrawerStore:
    return DrawerStore(path, _SmallWindowEmbedder(dimension=32))


def _drawer(content: str, *, wing: str = "cairntir") -> Drawer:
    return Drawer(wing=wing, room="phase-1", content=content, layer=Layer.ON_DEMAND)


def test_search_works_once_the_store_passes_the_vector_engine_k_limit(tmp_path: Path) -> None:
    """A store over 4,096 chunks must still answer, not fail every search."""
    with _chunk_heavy_store(tmp_path / "cairntir.db") as chunked:
        unique = "".join(f"{index:04d}" for index in range(4100))
        saved = chunked.add(_drawer(unique))
        assert chunked._require_embedding_space().vector_count == 4100

        results = chunked.search("0007", limit=1)

    assert [drawer.id for drawer, _ in results] == [saved.id]
    assert results[0][1] == pytest.approx(0.0, abs=1e-5)


def test_one_huge_drawer_cannot_hide_other_drawers_past_the_k_limit(tmp_path: Path) -> None:
    """Every chunk of one drawer outranking the limit must not crowd out the next drawer."""
    embedder = _SmallWindowEmbedder(dimension=32)
    with _chunk_heavy_store(tmp_path / "cairntir.db") as chunked:
        crowd = chunked.add(_drawer("same" * 4200))
        other = chunked.add(_drawer("next"))
        outside = chunked.add(_drawer("next", wing="elsewhere"))

        results = chunked.search("same", wing="cairntir", limit=2)

    assert [drawer.id for drawer, _ in results] == [crowd.id, other.id]
    assert outside.id not in {drawer.id for drawer, _ in results}
    assert results[0][1] == pytest.approx(0.0, abs=1e-5)
    # The exact path must rank with the same distance measure as the normal path.
    same, following = embedder.embed(["same", "next"])
    expected = sum((a - b) ** 2 for a, b in zip(same, following, strict=True)) ** 0.5
    assert results[1][1] == pytest.approx(expected, abs=1e-5)


@pytest.mark.slow
def test_search_past_the_k_limit_returns_a_large_request_in_order(tmp_path: Path) -> None:
    """A request larger than the engine's limit gets every drawer, closest first."""
    with _chunk_heavy_store(tmp_path / "cairntir.db") as chunked:
        for index in range(4100):
            chunked.add(_drawer(f"{index:04d}"))

        results = chunked.search("0007", limit=4100, rerank_by_belief=False)

    assert len({drawer.id for drawer, _ in results}) == 4100
    assert results[0][0].content == "0007"
    distances = [distance for _, distance in results]
    assert distances == sorted(distances)
