"""Versioned successor to the pinned 21-tool surface contract."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from pathlib import Path
from uuid import uuid4

from mcp import types

from cairntir.mcp.backend import CairntirBackend
from cairntir.mcp.server import _tool_specs, build_server
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.provenance import TOOL_SURFACE_VERSION

ROOT = next(
    parent for parent in Path(__file__).resolve().parents if (parent / "src/cairntir").is_dir()
)
TOOL_NAMES = {
    "cairntir_audit",
    "cairntir_calibration",
    "cairntir_codeglass_record",
    "cairntir_codeglass_retention",
    "cairntir_codeglass_teachback",
    "cairntir_correct",
    "cairntir_cross_recall",
    "cairntir_crucible",
    "cairntir_discover",
    "cairntir_discover_scan",
    "cairntir_discoveries",
    "cairntir_discovery_transition",
    "cairntir_get",
    "cairntir_handoff",
    "cairntir_hotfix",
    "cairntir_learning_log",
    "cairntir_recall",
    "cairntir_recall_for_change",
    "cairntir_remember",
    "cairntir_session_start",
    "cairntir_settle",
    "cairntir_timeline",
}


def test_v22_exact_names_and_object_root_schemas() -> None:
    specs = _tool_specs()
    assert len(specs) == 22
    assert {spec.name for spec in specs} == TOOL_NAMES
    assert len({spec.name for spec in specs}) == 22
    assert all(spec.inputSchema.get("type") == "object" for spec in specs)
    by_name = {spec.name: spec for spec in specs}
    correct = by_name["cairntir_correct"].inputSchema
    assert set(correct["required"]) == {
        "wing",
        "source_drawer_id",
        "source_identity",
        "source_sha256",
        "content",
        "idempotency_key",
    }
    assert correct["properties"]["source_drawer_id"]["type"] == "integer"
    handoff = by_name["cairntir_handoff"].inputSchema
    assert handoff["properties"]["task"]["type"] == "string"
    assert handoff["properties"]["candidate_limit"]["type"] == "integer"
    assert "task" not in handoff.get("required", [])


def test_correct_is_reachable_through_advertised_mcp_dispatch(tmp_cairntir_home: Path) -> None:
    with DrawerStore(
        tmp_cairntir_home / "cairntir.db", HashEmbeddingProvider(dimension=32)
    ) as store:
        source = store.add(
            Drawer(wing="surface-v22", room="database", content="Decision: use Postgres.")
        )
        assert source.id is not None
        original = store.get(source.id)
        request = types.CallToolRequest(
            method="tools/call",
            params=types.CallToolRequestParams(
                name="cairntir_correct",
                arguments={
                    "wing": source.wing,
                    "source_drawer_id": source.id,
                    "source_identity": store.portable_identity(source.id),
                    "source_sha256": hashlib.sha256(source.content.encode()).hexdigest(),
                    "content": "Decision REVERSED: use SQLite.",
                    "idempotency_key": str(uuid4()),
                },
            ),
        )
        result = asyncio.run(
            build_server(CairntirBackend(store)).request_handlers[types.CallToolRequest](request)
        ).root
        assert not result.isError
        assert len(result.content) == 1 and isinstance(result.content[0], types.TextContent)
        receipt = json.loads(result.content[0].text)
        assert receipt["schema"] == "cairntir.agent-correction-receipt.v1"
        assert receipt["source_drawer_id"] == source.id
        assert receipt["status"] == "committed"
        assert store.get(source.id) == original
        successor = store.get(receipt["correction_drawer_id"])
        assert successor is not None
        assert successor.supersedes_id == source.id
        assert successor.content == "Decision REVERSED: use SQLite."


def test_v22_write_provenance_matches_actual_surface(tmp_cairntir_home: Path) -> None:
    assert TOOL_SURFACE_VERSION == "22"
    with DrawerStore(
        tmp_cairntir_home / "cairntir.db", HashEmbeddingProvider(dimension=32)
    ) as store:
        saved = store.add(Drawer(wing="surface-v22", room="evidence", content="Portable evidence."))
        assert saved.id is not None
        assert store.get_provenance(saved.id).tool_surface_version == "22"


def test_readme_advertises_the_same_v22_surface() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    match = re.search(r"\*\*(\d+) tools\*\* over stdio", readme)
    assert match is not None
    assert int(match.group(1)) == len(TOOL_NAMES) == 22
