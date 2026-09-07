from __future__ import annotations

import pytest

from cairntir.codeglass import TeachBackResponse, record_teachback, record_walkthrough
from cairntir.errors import MemoryStoreError
from cairntir.learning import record_discovery
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore


def evidence(store):
    return [
        (row.id, row.content, row.metadata, row.supersedes_id) for row in store.list_by(limit=None)
    ]


@pytest.fixture()
def learning(seeded):
    database, _, _ = seeded
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        walkthrough = {
            "wing": "recovery",
            "target": "backup restoration",
            "reader_level": "expert",
            "sections": dict.fromkeys(("what", "how", "where", "when", "why"), "unknown"),
            "evidence_ids": (1,),
            "glossary": "snapshot: recoverable database",
            "danger_zones": "Do not overwrite the source.",
        }
        yield store, walkthrough


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("target", ""),
        ("reader_level", "unknown"),
        ("sections", {}),
        ("evidence_ids", ()),
        ("evidence_ids", (1, 1)),
        ("evidence_ids", (9999,)),
        ("glossary", " "),
        ("danger_zones", ""),
    ],
)
def test_invalid_walkthrough_cannot_be_persisted_as_cited_evidence(learning, field, value):
    store, valid = learning
    before = evidence(store)
    with pytest.raises((ValueError, MemoryStoreError)):
        record_walkthrough(store, **(valid | {field: value}))
    assert evidence(store) == before
    saved = record_walkthrough(store, **valid)
    assert saved.metadata["target"] == "backup restoration"
    assert "Do not overwrite the source." in saved.content
    assert len(evidence(store)) == len(before) + 1


@pytest.mark.parametrize("section", ["what", "how", "where", "when", "why"])
@pytest.mark.parametrize("unsupported_claim", ["", "The backup always succeeds."])
def test_each_walkthrough_claim_requires_a_citation_or_explicit_unknown(
    learning, section, unsupported_claim
):
    store, valid = learning
    sections = valid["sections"] | {section: unsupported_claim}
    before = evidence(store)
    with pytest.raises(ValueError, match=section.upper()):
        record_walkthrough(store, **(valid | {"sections": sections}))
    assert evidence(store) == before


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("phase", "unknown"),
        ("walkthrough_id", 9999),
        ("walkthrough_id", 1),
        ("responses", ()),
        ("responses", (TeachBackResponse("Q", "A", 1),)),
        ("responses", (TeachBackResponse("Q", "A", 1),) * 4),
        ("responses", (TeachBackResponse("", "A", 1),) * 2),
        ("responses", (TeachBackResponse("Q", "", 1),) * 2),
        ("responses", (TeachBackResponse("Q", "A", -0.1),) * 2),
        ("responses", (TeachBackResponse("Q", "A", 1.1),) * 2),
        ("responses", (TeachBackResponse("Q", "A", float("nan")),) * 2),
    ],
)
def test_invalid_teachback_cannot_record_false_comprehension(learning, field, value):
    store, walkthrough = learning
    saved = record_walkthrough(store, **walkthrough)
    valid = {
        "walkthrough_id": saved.id,
        "phase": "immediate",
        "responses": (
            TeachBackResponse("What survives?", "All rows.", 1),
            TeachBackResponse("How restore?", "Unsure.", 0),
        ),
    }
    before = evidence(store)
    with pytest.raises((ValueError, MemoryStoreError)):
        record_teachback(store, **(valid | {field: value}))
    assert evidence(store) == before
    result = record_teachback(store, **valid)
    assert "Score: 50%" in result.content
    assert "All rows." in result.content and "Unsure." in result.content
    assert len(evidence(store)) == len(before) + 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("evidence_ids", ()),
        ("evidence_ids", (0,)),
        ("evidence_ids", (1, 1)),
        ("confidence", -0.1),
        ("confidence", 1.1),
        ("confidence", float("nan")),
        ("observation_count", 0),
        ("counterexample_ids", (2,)),
    ],
)
def test_invalid_discovery_evidence_cannot_create_a_learning_claim(learning, field, value):
    store, _ = learning
    valid = {
        "wing": "recovery",
        "title": "Restoration",
        "summary": "Verified restoration.",
        "novelty": "user",
        "evidence_ids": (1,),
    }
    before = evidence(store)
    with pytest.raises(ValueError):
        record_discovery(store, **(valid | {field: value}))
    assert evidence(store) == before
    result = record_discovery(store, **valid)
    assert result.title == "Restoration" and result.evidence_ids == (1,)
    assert len(evidence(store)) == len(before) + 1
