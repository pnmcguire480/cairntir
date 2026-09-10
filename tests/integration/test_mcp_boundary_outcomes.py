"""Retain independently observed rejection and recovery outcomes through actual MCP stdio."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
import sys
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer

ORIGINAL = "  Keep my original café 日本語 evidence.\nPreserve its exact whitespace.\t"


def evidence_rows(home: Path) -> dict[str, list]:
    """Compare evidence while permitting the documented get access counters to advance."""
    with sqlite3.connect((home / "cairntir.db").as_uri() + "?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        return {
            "drawers": [
                {
                    key: value
                    for key, value in dict(row).items()
                    if key not in {"access_count", "last_accessed_at"}
                }
                for row in connection.execute("SELECT * FROM drawers ORDER BY id")
            ],
            "portable_records": [
                dict(row)
                for row in connection.execute("SELECT * FROM portable_records ORDER BY rowid")
            ],
        }


@asynccontextmanager
async def open_peer(tmp_cairntir_home: Path):
    with DrawerStore(
        tmp_cairntir_home / "cairntir.db", HashEmbeddingProvider(dimension=32)
    ) as store:
        saved = store.add(
            Drawer(
                wing="audit",
                room="evidence",
                content=ORIGINAL,
                metadata={"audit": "original", "anchors": [{"path": "src/existing.py"}]},
            )
        )
    original_rows = evidence_rows(tmp_cairntir_home)
    env = dict(os.environ)
    env.pop("CAIRNTIR_GRANT_FILE", None)
    env.update(
        CAIRNTIR_ENABLE_EMBEDDER_WARMUP="0",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
    )
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "cairntir.mcp.server", "--host", "codex"],
        env=env,
        cwd=tmp_cairntir_home,
    )
    with (tmp_cairntir_home / "stderr.txt").open("w", encoding="utf-8") as errlog:
        async with (
            asyncio.timeout(40),
            stdio_client(parameters, errlog=errlog) as (reader, writer),
            ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=15)) as session,
        ):
            await session.initialize()
            await session.list_tools()
            initial = await session.call_tool("cairntir_get", {"drawer_id": saved.id})
            assert not initial.isError, initial
            original = json.loads(initial.content[0].text)
            assert original["content"] == ORIGINAL
            assert original["content_hash"] == hashlib.sha256(ORIGINAL.encode()).hexdigest()
            yield session, tmp_cairntir_home, original, original_rows
    assert evidence_rows(tmp_cairntir_home) == original_rows


async def assert_rejected(peer, name: str, arguments: dict, detail: str) -> None:
    session, home, original, original_rows = peer
    rejected = await session.call_tool(name, arguments)
    recovered = await session.call_tool("cairntir_get", {"drawer_id": original["id"]})
    assert not recovered.isError, (name, arguments, recovered)
    assert json.loads(recovered.content[0].text) == original
    assert evidence_rows(home) == original_rows, (name, arguments)
    assert rejected.isError, (name, arguments, rejected)
    assert detail in rejected.content[0].text, (name, arguments, rejected)


async def check_rejections(home: Path, cases: list, *, resume: bool = False) -> None:
    async with open_peer(home) as peer:
        for name, arguments, detail in cases:
            await assert_rejected(peer, name, arguments, detail)
        if resume:
            resumed = await peer[0].call_tool("cairntir_handoff", {"wing": "audit", "resume": True})
            assert not resumed.isError, resumed
            receipt = json.loads(resumed.content[0].text)
            assert receipt["status"] == "none"
            assert receipt["checkpoint"] is None
            assert receipt["task_id"] is None
            assert receipt["candidates"] == []


async def test_invalid_identifiers_and_tool_routing_preserve_known_evidence(
    tmp_cairntir_home: Path,
) -> None:
    cases = [
        ("cairntir_get", {"drawer_id": 999}, "no drawer with id 999"),
        ("cairntir_get", {"drawer_id": True}, "not of type 'integer'"),
        ("cairntir_get", {"drawer_id": 10**100}, "too large to convert to SQLite INTEGER"),
        (
            "cairntir_get",
            {"drawer_id": 1, "unadvertised": True},
            "unexpected keyword argument 'unadvertised'",
        ),
        ("does_not_exist", {}, "unknown tool 'does_not_exist'"),
    ]
    await check_rejections(tmp_cairntir_home, cases)


async def test_conflicting_memory_anchors_cannot_append_ambiguous_evidence(
    tmp_cairntir_home: Path,
) -> None:
    case = (
        "cairntir_remember",
        {
            "wing": "audit",
            "room": "evidence",
            "content": "This rejected request must not become stored evidence.",
            "anchors": [{"path": "src/one.py"}],
            "metadata": {"anchors": [{"path": "src/two.py"}]},
        },
        "pass anchors either as the 'anchors' argument or as metadata.anchors, not both",
    )
    await check_rejections(tmp_cairntir_home, [case])


async def test_absent_support_cannot_create_outcomes_or_learning_receipts(
    tmp_cairntir_home: Path,
) -> None:
    cases = [
        (
            "cairntir_settle",
            {"drawer_id": 1, "observed_outcome": "The proposed prediction held."},
            "carries no predicted_outcome",
        ),
        (
            "cairntir_discover",
            {
                "wing": "audit",
                "title": "Unsupported discovery",
                "summary": "Evidence must exist before this can be recorded.",
                "novelty": "user",
                "evidence_ids": [999],
            },
            "discovery evidence drawer(s) do not exist: [999]",
        ),
        (
            "cairntir_discovery_transition",
            {"drawer_id": 999, "state": "rejected", "note": "Review the absent discovery."},
            "no drawer with id 999",
        ),
        (
            "cairntir_codeglass_teachback",
            {
                "walkthrough_id": 999,
                "phase": "immediate",
                "responses": [
                    {"question": "What changed?", "answer": "The implementation.", "score": 1},
                    {"question": "Why?", "answer": "Unknown.", "score": 0},
                ],
            },
            "no walkthrough drawer with id 999",
        ),
        (
            "cairntir_hotfix",
            {"action": "status", "wing": "audit", "case_id": "missing"},
            "hotfix 'missing' does not exist",
        ),
        (
            "cairntir_hotfix",
            {
                "action": "open",
                "wing": "audit",
                "payload": {
                    "title": "Unverifiable case",
                    "stage": "verification",
                    "symptom": "No acceptance condition was supplied.",
                    "acceptance": [],
                },
                "idempotency_key": "no-acceptance",
            },
            "should be non-empty",
        ),
    ]
    await check_rejections(tmp_cairntir_home, cases)


async def test_empty_retrieval_selectors_are_rejected_instead_of_returning_absence(
    tmp_cairntir_home: Path,
) -> None:
    cases = [
        ("cairntir_cross_recall", {"query": " "}, "requires a non-empty query"),
        (
            "cairntir_recall_for_change",
            {"files": [" "]},
            "requires at least one non-empty file path",
        ),
        (
            "cairntir_timeline",
            {"wing": "audit", "entity": " "},
            "requires a non-empty entity",
        ),
    ]
    await check_rejections(tmp_cairntir_home, cases)


async def test_incompatible_handoff_modes_do_not_silently_select_a_fallback(
    tmp_cairntir_home: Path,
) -> None:
    cases = [
        (
            "cairntir_handoff",
            {"wing": "audit", "resume": True, "task": "An incompatible task search."},
            "resume cannot combine with task search",
        ),
        (
            "cairntir_handoff",
            {"wing": "audit", "candidate_limit": 1},
            "candidate_limit requires a task",
        ),
    ]
    await check_rejections(tmp_cairntir_home, cases, resume=True)


async def test_invalid_review_budgets_cannot_produce_empty_success_receipts(
    tmp_cairntir_home: Path,
) -> None:
    cases = [
        ("cairntir_session_start", {"wing": "audit", "budget_chars": 0}, "minimum of 1"),
        ("cairntir_discoveries", {"limit": 0}, "minimum of 1"),
        ("cairntir_learning_log", {"limit": 0}, "minimum of 1"),
        (
            "cairntir_discover_scan",
            {"wing": "audit", "min_observations": 1},
            "minimum of 2",
        ),
    ]
    await check_rejections(tmp_cairntir_home, cases)
