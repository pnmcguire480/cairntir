from __future__ import annotations

from pathlib import Path

import pytest

from cairntir.codeglass import (
    TeachBackResponse,
    record_teachback,
    record_walkthrough,
    render_retention,
    retention_report,
)
from cairntir.learning import list_discoveries
from cairntir.mcp.backend import CairntirBackend
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer


@pytest.fixture
def store(tmp_path: Path) -> DrawerStore:
    result = DrawerStore(tmp_path / "codeglass.db", HashEmbeddingProvider(dimension=16))
    yield result
    result.close()


def _evidence(store: DrawerStore) -> int:
    saved = store.add(
        Drawer(
            wing="cairntir",
            room="evidence",
            content="ReasonLoop.step lives at src/cairntir/reason/loop.py.",
        )
    )
    assert saved.id is not None
    return saved.id


def _sections() -> dict[str, str]:
    return {
        "what": "It records a prediction and observation. [source:src/reason/loop.py:74]",
        "how": "It calls proposer, runner, then beliefs. [source:src/reason/loop.py:116]",
        "where": "The orchestration lives in ReasonLoop. [source:src/reason/loop.py:35]",
        "when": "It runs when a Reason step is requested. [source:src/reason/loop.py:52]",
        "why": "Inferred: prediction makes learning falsifiable. [source:docs/concept.md:1]",
    }


def test_walkthrough_requires_citations_and_complete_sections(store: DrawerStore) -> None:
    evidence_id = _evidence(store)
    bad = _sections()
    bad["why"] = "Because it seemed useful."
    with pytest.raises(ValueError, match="WHY requires"):
        record_walkthrough(
            store,
            wing="cairntir",
            target="Reason loop",
            reader_level="novice",
            sections=bad,
            evidence_ids=(evidence_id,),
            glossary="Prediction: a testable expectation.",
            danger_zones="Do not swallow runner failures.",
        )

    saved = record_walkthrough(
        store,
        wing="cairntir",
        target="Reason loop",
        reader_level="novice",
        sections=_sections(),
        evidence_ids=(evidence_id,),
        glossary="Prediction: a testable expectation.",
        danger_zones="Do not swallow runner failures.",
    )
    assert saved.metadata["kind"] == "codeglass.walkthrough"
    assert "## WHAT" in saved.content
    assert saved.layer.value == "deep"


def test_teachback_measures_delayed_retention_and_updates_learning_log(
    store: DrawerStore,
) -> None:
    evidence_id = _evidence(store)
    walkthrough = record_walkthrough(
        store,
        wing="cairntir",
        target="Reason loop",
        reader_level="novice",
        sections=_sections(),
        evidence_ids=(evidence_id,),
        glossary="Prediction: a testable expectation.",
        danger_zones="Do not swallow runner failures.",
    )
    assert walkthrough.id is not None
    immediate = record_teachback(
        store,
        walkthrough_id=walkthrough.id,
        phase="immediate",
        responses=(
            TeachBackResponse("What comes first?", "Prediction.", 1.0),
            TeachBackResponse("What records reality?", "Observation.", 1.0),
        ),
        mastered_concepts=("prediction", "observation"),
    )
    delayed = record_teachback(
        store,
        walkthrough_id=walkthrough.id,
        phase="delayed",
        responses=(
            TeachBackResponse("What is surprise?", "The delta.", 0.8),
            TeachBackResponse("Why atomic?", "Avoid half-memory.", 0.8),
        ),
        mastered_concepts=("prediction",),
        misunderstood_concepts=("belief mass",),
    )

    report = retention_report(store, walkthrough_id=walkthrough.id)
    assert immediate.supersedes_id == walkthrough.id
    assert delayed.supersedes_id == immediate.id
    assert report.immediate_drawer_id == immediate.id
    assert report.delayed_drawer_id == delayed.id
    assert report.immediate_score == pytest.approx(1.0)
    assert report.delayed_score == pytest.approx(0.8)
    assert report.retention_delta == pytest.approx(-0.2)
    assert report.misunderstood_concepts == ("belief mass",)
    assert "retention change: -20%" in render_retention(report)

    discoveries = list_discoveries(store, wing="cairntir")
    assert len(discoveries) == 1
    assert "CodeGlass learning retained" in discoveries[0].title
    assert discoveries[0].evidence_ids == (immediate.id, delayed.id)


def test_backend_exact_retry_does_not_duplicate_walkthrough(store: DrawerStore) -> None:
    evidence_id = _evidence(store)
    backend = CairntirBackend(store)
    kwargs = {
        "wing": "cairntir",
        "target": "Reason loop",
        "reader_level": "novice",
        **_sections(),
        "evidence_ids": [evidence_id],
        "glossary": "Prediction: a testable expectation.",
        "danger_zones": "Do not swallow runner failures.",
    }
    first = backend.codeglass_record(**kwargs)
    replay = backend.codeglass_record(**kwargs)
    assert "walkthrough #" in first
    assert "no duplicate" in replay
    walkthroughs = [
        drawer
        for drawer in store.list_by(room="codeglass")
        if drawer.metadata.get("kind") == "codeglass.walkthrough"
    ]
    assert len(walkthroughs) == 1


def test_backend_teachback_and_retention_surface(store: DrawerStore) -> None:
    evidence_id = _evidence(store)
    backend = CairntirBackend(store)
    stored = backend.codeglass_record(
        wing="cairntir",
        target="Reason loop",
        reader_level="novice",
        **_sections(),
        evidence_ids=[evidence_id],
        glossary="Prediction: a testable expectation.",
        danger_zones="Do not swallow runner failures.",
    )
    walkthrough_id = int(stored.split("#", 1)[1].split()[0].rstrip("."))
    immediate = backend.codeglass_teachback(
        walkthrough_id=walkthrough_id,
        phase="immediate",
        responses=[
            {"question": "What comes first?", "answer": "Prediction.", "score": 1.0},
            {"question": "What records reality?", "answer": "Observation.", "score": 1.0},
        ],
        mastered_concepts=["prediction"],
    )
    delayed = backend.codeglass_teachback(
        walkthrough_id=walkthrough_id,
        phase="delayed",
        responses=[
            {"question": "What is delta?", "answer": "Surprise.", "score": 0.75},
            {"question": "Why atomic?", "answer": "No half-memory.", "score": 0.75},
        ],
        misunderstood_concepts=["belief mass"],
    )
    assert "immediate teach-back" in immediate
    assert "delayed teach-back" in delayed
    retention = backend.codeglass_retention(walkthrough_id=walkthrough_id)
    assert "immediate teach-back: 100%" in retention
    assert "delayed teach-back: 75%" in retention
    assert "belief mass" in retention
