from __future__ import annotations

from pathlib import Path

import pytest

from cairntir.errors import MemoryStoreError
from cairntir.learning import (
    format_discoveries,
    human_learning_log,
    list_discoveries,
    propose_multi_episode_discoveries,
    record_discovery,
    transition_discovery,
)
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer, Layer


@pytest.fixture
def store(tmp_path: Path) -> DrawerStore:
    result = DrawerStore(tmp_path / "learning.db", HashEmbeddingProvider(dimension=16))
    yield result
    result.close()


def _evidence(store: DrawerStore, content: str = "Repeated result observed.") -> int:
    saved = store.add(
        Drawer(
            wing="cairntir",
            room="tests",
            content=content,
            layer=Layer.ON_DEMAND,
        )
    )
    assert saved.id is not None
    return saved.id


def test_record_and_list_discovery_with_evidence(store: DrawerStore) -> None:
    evidence_id = _evidence(store)
    discovery = record_discovery(
        store,
        wing="cairntir",
        title="Scoped retrieval is more reliable",
        summary="Filtering before KNN prevents crowded global neighbors hiding wing hits.",
        novelty="cairntir",
        evidence_ids=(evidence_id,),
        state="candidate",
    )
    assert discovery.drawer_id > evidence_id
    assert discovery.evidence_ids == (evidence_id,)
    assert discovery.state == "candidate"

    listed = list_discoveries(store, wing="cairntir")
    assert listed == [discovery]
    rendered = format_discoveries(listed, heading="Discoveries")
    assert f"cairntir://drawer/{discovery.drawer_id}" in rendered
    assert f"evidence: #{evidence_id}" in rendered


def test_transition_is_append_only_and_listing_returns_chain_leaf(store: DrawerStore) -> None:
    evidence_id = _evidence(store)
    candidate = record_discovery(
        store,
        wing="cairntir",
        title="A reusable method emerged",
        summary="The same repair sequence succeeded on three independent failures.",
        novelty="user",
        evidence_ids=(evidence_id,),
        state="candidate",
    )
    corroborated = transition_discovery(
        store,
        drawer_id=candidate.drawer_id,
        state="corroborated",
        note="Three independent examples reproduced the method.",
    )
    promoted = transition_discovery(
        store,
        drawer_id=corroborated.drawer_id,
        state="promoted",
        note="Patrick reviewed the evidence and promoted the method.",
    )
    assert corroborated.supersedes_id == candidate.drawer_id
    assert promoted.supersedes_id == corroborated.drawer_id
    assert store.get(candidate.drawer_id) is not None
    assert list_discoveries(store) == [promoted]
    with pytest.raises(ValueError, match="already been superseded"):
        transition_discovery(
            store,
            drawer_id=candidate.drawer_id,
            state="rejected",
            note="A stale branch must not be created.",
        )


def test_learning_log_filters_states_and_can_hide_candidates(store: DrawerStore) -> None:
    evidence_id = _evidence(store)
    record_discovery(
        store,
        wing="cairntir",
        title="Unreviewed signal",
        summary="One observation may become a pattern.",
        novelty="cairntir",
        evidence_ids=(evidence_id,),
        state="signal",
    )
    record_discovery(
        store,
        wing="cairntir",
        title="Candidate method",
        summary="Two observations support this method.",
        novelty="user",
        evidence_ids=(evidence_id,),
        state="candidate",
    )
    promoted = record_discovery(
        store,
        wing="cairntir",
        title="Promoted lesson",
        summary="The reviewed method consistently reduced rework.",
        novelty="user",
        evidence_ids=(evidence_id,),
        state="promoted",
    )

    full = human_learning_log(store)
    assert "Candidate method" in full
    assert "Promoted lesson" in full
    assert "Unreviewed signal" not in full

    promoted_only = human_learning_log(store, include_candidates=False)
    assert "Candidate method" not in promoted_only
    assert f"cairntir://drawer/{promoted.drawer_id}" in promoted_only


def test_general_novelty_promotion_requires_external_research_note(
    store: DrawerStore,
) -> None:
    evidence_id = _evidence(store)
    with pytest.raises(ValueError, match="external research"):
        record_discovery(
            store,
            wing="cairntir",
            title="Possibly novel method",
            summary="A method that may differ from published baselines.",
            novelty="general",
            evidence_ids=(evidence_id,),
            state="promoted",
        )

    result = record_discovery(
        store,
        wing="cairntir",
        title="Externally checked method",
        summary="The comparison found a meaningful difference from reviewed baselines.",
        novelty="general",
        evidence_ids=(evidence_id,),
        state="corroborated",
        transition_note="External research compared three primary-source baselines.",
    )
    assert result.state == "corroborated"


def test_discovery_rejects_missing_or_empty_evidence(store: DrawerStore) -> None:
    with pytest.raises(ValueError, match="at least one"):
        record_discovery(
            store,
            wing="cairntir",
            title="No evidence",
            summary="This must not become learning.",
            novelty="user",
            evidence_ids=(),
        )
    with pytest.raises(MemoryStoreError, match="do not exist"):
        record_discovery(
            store,
            wing="cairntir",
            title="Missing evidence",
            summary="The cited drawer is absent.",
            novelty="user",
            evidence_ids=(999,),
        )
    evidence_id = _evidence(store, "Duplicate evidence should be rejected.")
    with pytest.raises(ValueError, match="must be unique"):
        record_discovery(
            store,
            wing="cairntir",
            title="Duplicate evidence",
            summary="One observation must not count twice.",
            novelty="user",
            evidence_ids=(evidence_id, evidence_id),
        )


def test_transition_rejects_non_discovery_drawer(store: DrawerStore) -> None:
    evidence_id = _evidence(store)
    with pytest.raises(ValueError, match="not a Cairntir discovery"):
        transition_discovery(
            store,
            drawer_id=evidence_id,
            state="promoted",
            note="Should fail.",
        )


def test_multi_episode_reflection_proposes_calibrated_candidate_once(
    store: DrawerStore,
) -> None:
    evidence_ids: list[int] = []
    for index, success in enumerate((True, True, True, False), start=1):
        saved = store.add(
            Drawer(
                wing="cairntir",
                room="reason",
                content=f"observation {index}",
                claim="Scoped retrieval finds the project memory",
                predicted_outcome="the correct drawer appears",
                observed_outcome="found" if success else "missed",
                metadata={"source": "reason.observe", "success": success},
            )
        )
        assert saved.id is not None
        evidence_ids.append(saved.id)

    proposed = propose_multi_episode_discoveries(
        store,
        wing="cairntir",
        confidence_threshold=0.75,
    )
    assert len(proposed) == 1
    candidate = proposed[0]
    assert candidate.state == "candidate"
    assert candidate.confidence == pytest.approx(0.75)
    assert candidate.observation_count == 4
    assert candidate.evidence_ids == tuple(evidence_ids)
    assert candidate.counterexample_ids == (evidence_ids[-1],)
    assert candidate.next_test is not None

    assert (
        propose_multi_episode_discoveries(
            store,
            wing="cairntir",
            confidence_threshold=0.75,
        )
        == []
    )
