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


def _reason_episode(
    store: DrawerStore,
    *,
    room: str,
    claim: str,
    predicted: str,
    observed: str,
    success: bool,
) -> int:
    prediction = store.add(
        Drawer(
            wing="cairntir",
            room=room,
            content=f"Claim: {claim}\nPredicted: {predicted}",
            claim=claim,
            predicted_outcome=predicted,
            metadata={"source": "reason.predict"},
        )
    )
    assert prediction.id is not None
    observation = store.add(
        Drawer(
            wing="cairntir",
            room=room,
            content=f"Observed: {observed}",
            claim=claim,
            predicted_outcome=predicted,
            observed_outcome=observed,
            supersedes_id=prediction.id,
            metadata={"source": "reason.observe", "success": success},
        )
    )
    assert observation.id is not None
    return observation.id


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
    for success in (True, True, True, False):
        evidence_ids.append(
            _reason_episode(
                store,
                room="reason",
                claim="Scoped retrieval finds the project memory",
                predicted="the correct drawer appears",
                observed="found" if success else "missed",
                success=success,
            )
        )

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


def test_multi_episode_reflection_ignores_unbound_outcome_shaped_drawers(
    store: DrawerStore,
) -> None:
    for index in range(3):
        store.add(
            Drawer(
                wing="cairntir",
                room="reason",
                content=f"unbound observation {index}",
                claim="Repeated text alone is not learning",
                predicted_outcome="a candidate appears",
                observed_outcome="a candidate appears",
                metadata={"source": "reason.observe", "success": True},
            )
        )

    assert propose_multi_episode_discoveries(store, wing="cairntir") == []


def test_multi_episode_reflection_keeps_rooms_separate(store: DrawerStore) -> None:
    evidence_by_room: dict[str, list[int]] = {"alpha": [], "beta": []}
    for room in evidence_by_room:
        for index in range(2):
            evidence_by_room[room].append(
                _reason_episode(
                    store,
                    room=room,
                    claim="The scoped strategy works",
                    predicted="the operation completes",
                    observed=f"{room} observation {index}",
                    success=True,
                )
            )

    assert propose_multi_episode_discoveries(store, wing="cairntir") == []

    evidence_by_room["alpha"].append(
        _reason_episode(
            store,
            room="alpha",
            claim="The scoped strategy works",
            predicted="the operation completes",
            observed="alpha observation 3",
            success=True,
        )
    )
    proposed = propose_multi_episode_discoveries(store, wing="cairntir")

    assert len(proposed) == 1
    assert proposed[0].evidence_ids == tuple(evidence_by_room["alpha"])
    assert "'alpha'" in proposed[0].title


def test_multi_episode_reflection_counts_each_prediction_once(store: DrawerStore) -> None:
    claim = "One experiment is one episode"
    predicted = "one observation is counted"
    prediction = store.add(
        Drawer(
            wing="cairntir",
            room="reason",
            content=f"Claim: {claim}\nPredicted: {predicted}",
            claim=claim,
            predicted_outcome=predicted,
            metadata={"source": "reason.predict"},
        )
    )
    assert prediction.id is not None
    for index in range(3):
        store.add(
            Drawer(
                wing="cairntir",
                room="reason",
                content=f"duplicate observation {index}",
                claim=claim,
                predicted_outcome=predicted,
                observed_outcome="one observation is counted",
                supersedes_id=prediction.id,
                metadata={"source": "reason.observe", "success": True},
            )
        )

    assert propose_multi_episode_discoveries(store, wing="cairntir") == []
