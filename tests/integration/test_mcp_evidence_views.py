"""A completed learning episode remains connected across public MCP evidence views."""

from __future__ import annotations

import asyncio
import os
import sqlite3
import sys
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from cairntir.codeglass import record_walkthrough
from cairntir.learning import list_discoveries, transition_discovery
from cairntir.mcp.backend import CairntirBackend
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer, Layer

WING = "learning"
IDENTITY = "Record a prediction before teaching, then check understanding after a delay."


def stored_evidence(home: Path) -> list:
    with sqlite3.connect((home / "cairntir.db").as_uri() + "?mode=ro", uri=True) as connection:
        return connection.execute(
            "SELECT id, content, metadata, supersedes_id FROM drawers ORDER BY id"
        ).fetchall()


def seed_learning_episode(home: Path) -> dict:
    with DrawerStore(home / "cairntir.db", HashEmbeddingProvider(dimension=32)) as store:
        backend = CairntirBackend(store)
        identity = store.add(
            Drawer(wing=WING, room="identity", content=IDENTITY, layer=Layer.IDENTITY)
        )
        prediction = store.add(
            Drawer(
                wing=WING,
                room="decisions",
                content="A cited lesson should preserve understanding after a delay.",
                claim="The reader retains at least 80% after the lesson.",
                predicted_outcome="Delayed reviewed teach-back score is at least 80%.",
            )
        )
        walkthrough = record_walkthrough(
            store,
            wing=WING,
            target="Checking retained understanding",
            reader_level="novice",
            sections={
                "what": "A prediction can be checked. [source:lesson.md:1]",
                "how": "Compare a delayed observation with it. [source:lesson.md:2]",
                "where": "The lesson records both stages. [source:lesson.md:3]",
                "when": "Check again after a delay. [source:lesson.md:4]",
                "why": "Immediate recall does not prove retention. [source:lesson.md:5]",
            },
            evidence_ids=(prediction.id,),
            glossary="Prediction: a falsifiable expectation.",
            danger_zones="Do not confuse immediate recall with retained understanding.",
        )
        immediate_args = {
            "walkthrough_id": walkthrough.id,
            "phase": "immediate",
            "responses": [
                {"question": "What comes first?", "answer": "Prediction.", "score": 1.0},
                {"question": "What checks it?", "answer": "Observation.", "score": 1.0},
            ],
            "mastered_concepts": ["prediction", "observation"],
            "idempotency_key": "lesson-immediate",
        }
        delayed_args = {
            "walkthrough_id": walkthrough.id,
            "phase": "delayed",
            "responses": [
                {"question": "What comes first?", "answer": "Prediction.", "score": 0.8},
                {"question": "What is belief mass?", "answer": "Uncertain.", "score": 0.8},
            ],
            "mastered_concepts": ["prediction"],
            "misunderstood_concepts": ["belief mass"],
            "idempotency_key": "lesson-delayed",
        }
        backend.codeglass_teachback(**immediate_args)
        backend.codeglass_teachback(**delayed_args)
        candidate = list_discoveries(store, wing=WING)[0]
        reviewed = transition_discovery(
            store,
            drawer_id=candidate.drawer_id,
            state="corroborated",
            note="Reviewed both scored answers and confirmed the delayed result.",
        )
        backend.settle(
            drawer_id=prediction.id,
            observed_outcome="Delayed teach-back retained 80% of the reviewed answers.",
            held=True,
        )
        return {
            "identity": identity.id,
            "walkthrough": walkthrough.id,
            "candidate": candidate.drawer_id,
            "reviewed": reviewed.drawer_id,
            "title": reviewed.title,
            "evidence_ids": reviewed.evidence_ids,
            "delayed_args": delayed_args,
        }


async def successful_text(session: ClientSession, name: str, arguments: dict) -> str:
    result = await session.call_tool(name, arguments)
    assert not result.isError, (name, result)
    return result.content[0].text


async def test_completed_learning_episode_connects_session_review_and_retention(
    tmp_cairntir_home: Path,
) -> None:
    episode = seed_learning_episode(tmp_cairntir_home)
    before = stored_evidence(tmp_cairntir_home)
    model_cache = tmp_cairntir_home / "unprovisioned-model-cache"
    env = dict(os.environ)
    env.pop("CAIRNTIR_GRANT_FILE", None)
    env.update(
        CAIRNTIR_ENABLE_EMBEDDER_WARMUP="0",
        FASTEMBED_CACHE_PATH=str(model_cache),
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
            context = await successful_text(session, "cairntir_session_start", {"wing": WING})
            assert IDENTITY in context
            assert f"cairntir://drawer/{episode['identity']}" in context
            assert "Active discoveries" in context
            assert episode["title"] in context
            assert f"cairntir://drawer/{episode['reviewed']}" in context

            listing = await successful_text(
                session, "cairntir_discoveries", {"wing": WING, "state": "corroborated"}
            )
            log = await successful_text(
                session, "cairntir_learning_log", {"wing": WING, "include_candidates": False}
            )
            evidence = ", ".join(f"#{drawer_id}" for drawer_id in episode["evidence_ids"])
            for text in (listing, log):
                assert f"[corroborated] {episode['title']}" in text
                assert f"cairntir://drawer/{episode['reviewed']}" in text
                assert f"cairntir://drawer/{episode['candidate']}" not in text
                assert f"evidence: {evidence}" in text
                assert "Immediate score 100%; delayed score 80%" in text

            calibration = await successful_text(session, "cairntir_calibration", {"wing": WING})
            assert "prediction drawers: 1" in calibration
            assert "resolved observations: 1" in calibration
            assert "confirmed / failed: 1 / 0" in calibration
            assert "unresolved predictions: 0" in calibration
            assert "empirical success rate: 100.0%" in calibration
            assert "resolved outcomes by room: decisions=1" in calibration

            retention = await successful_text(
                session, "cairntir_codeglass_retention", {"walkthrough_id": episode["walkthrough"]}
            )
            assert f"walkthrough #{episode['walkthrough']}" in retention
            assert "immediate teach-back: 100%" in retention
            assert "delayed teach-back: 80%" in retention
            assert "retention change: -20%" in retention
            assert "mastered: prediction" in retention
            assert "revisit: belief mass" in retention

            replay = await successful_text(
                session, "cairntir_codeglass_teachback", episode["delayed_args"]
            )
            assert f"delayed teach-back #{episode['evidence_ids'][1]}" in replay
            assert "replayed; no duplicate" in replay
            scan = await successful_text(session, "cairntir_discover_scan", {"wing": WING})
            assert "No new multi-episode discovery candidates" in scan
            assert "existing candidates were left unchanged" in scan

    assert stored_evidence(tmp_cairntir_home) == before
    assert not model_cache.exists()
