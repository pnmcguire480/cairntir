from __future__ import annotations

import json

import pytest
from test_recovery_outcomes import TEXT, contents

from cairntir.context import compose_task_context
from cairntir.errors import EmbeddingSpaceError, ProvenanceError, RetrievalError
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("task", ""),
        ("task", 1),
        ("wing", " "),
        ("wing", None),
        ("budget_chars", True),
        ("budget_chars", 0),
        ("budget_chars", 1),
        ("candidate_limit", False),
        ("candidate_limit", 0),
        ("files", "file.py"),
        ("files", [""]),
        ("files", [None]),
        ("files", {}),
    ],
)
def test_invalid_context_request_is_explicit_and_never_updates_retrieval_state(
    seeded, field, value
):
    database, _, _ = seeded
    before = contents(database)
    arguments = {"wing": "recovery", "task": TEXT, "budget_chars": 10000}
    arguments[field] = value
    with (
        DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store,
        pytest.raises(RetrievalError),
    ):
        compose_task_context(store, **arguments)
    assert contents(database) == before


@pytest.mark.parametrize("anchors", [["path.py"], [{"symbol": "missing_path"}], 1])
def test_malformed_anchors_are_excluded_and_identified_without_guessing_a_repair(seeded, anchors):
    database, _, _ = seeded
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        store._conn.execute(
            "UPDATE drawers SET metadata=? WHERE id=1", (json.dumps({"anchors": anchors}),)
        )
        store._conn.commit()
        before = contents(database)
        result = json.loads(
            compose_task_context(store, wing="recovery", task=TEXT, budget_chars=10000)
        )
        assert all(item["drawer_id"] != 1 for item in result["evidence"])
        assert {"drawer_id": 1, "reasons": ["malformed_anchor"]} in result["excluded"]
        assert contents(database) == before


@pytest.mark.parametrize("provenance", ["{", "{}", '{"trust":"invalid"}'])
def test_invalid_provenance_prevents_context_from_claiming_trusted_evidence(seeded, provenance):
    database, _, _ = seeded
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        store._conn.execute("UPDATE drawers SET provenance=? WHERE id=1", (provenance,))
        store._conn.commit()
        before = contents(database)
        with pytest.raises(ProvenanceError, match="invalid provenance"):
            compose_task_context(store, wing="recovery", task=TEXT, budget_chars=10000)
        assert contents(database) == before


def test_cyclic_supersession_cannot_select_a_false_current_request(seeded):
    database, _, _ = seeded
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        store._conn.execute("UPDATE drawers SET supersedes_id=2 WHERE id=1")
        store._conn.execute("UPDATE drawers SET supersedes_id=1 WHERE id=2")
        store._conn.commit()
        before = contents(database)
        with pytest.raises(RetrievalError, match="cycle"):
            compose_task_context(store, wing="recovery", task=TEXT, budget_chars=10000)
        assert contents(database) == before


def test_equal_vector_count_with_wrong_identity_cannot_produce_a_false_context_success(seeded):
    database, _, _ = seeded
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        row = store._conn.execute("SELECT * FROM vec_drawers WHERE drawer_id=1").fetchone()
        store._conn.execute("DELETE FROM vec_drawers WHERE drawer_id=1")
        columns = list(row.keys())
        values = [999 if name == "drawer_id" else row[name] for name in columns]
        placeholders = ",".join("?" for _ in columns)
        store._conn.execute(f"INSERT INTO vec_drawers VALUES ({placeholders})", values)  # noqa: S608
        store._conn.commit()
        assert store.embedding_status().verified
        before = contents(database)
        with pytest.raises(EmbeddingSpaceError, match="missing stored vectors"):
            compose_task_context(store, wing="recovery", task=TEXT, budget_chars=10000)
        assert contents(database) == before
