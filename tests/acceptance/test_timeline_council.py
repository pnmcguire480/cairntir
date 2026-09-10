"""Independent acceptance for filtering a timeline before limiting its entries."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_mcp_notifications_council import cache, run_stdio, seed

from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer


@pytest.mark.asyncio
async def test_timeline_limit_applies_to_matching_entity_entries(tmp_path: Path) -> None:
    home = tmp_path / "home"
    seed(home)
    cache(home, "0.0.0")
    with DrawerStore(home / "cairntir.db", HashEmbeddingProvider(dimension=32)) as store:
        target = store.add(
            Drawer(wing="audit", room="evidence", content="Needle relationship was recorded.")
        ).id
        store.add(Drawer(wing="audit", room="evidence", content="An unrelated later message."))
    results = await run_stdio(
        home, [("cairntir_timeline", {"wing": "audit", "entity": "Needle", "limit": 1})]
    )
    assert not results[0].isError, results[0]
    assert f"cairntir://drawer/{target}" in results[0].content[0].text, results[0]
