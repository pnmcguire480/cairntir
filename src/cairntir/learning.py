"""Append-only Discovery Ledger and human-readable learning log.

Learning claims are memory, not hidden model state.  Every discovery is a
drawer with explicit novelty scope, lifecycle state, and evidence references.
Transitions append a superseding drawer so the complete reasoning trail
remains inspectable.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal, cast

from cairntir.contracts import Store
from cairntir.errors import MemoryStoreError
from cairntir.memory.taxonomy import Drawer, Layer

DiscoveryState = Literal[
    "signal",
    "candidate",
    "corroborated",
    "promoted",
    "rejected",
    "expired",
]
NoveltyScope = Literal["user", "cairntir", "general"]

DISCOVERY_STATES: Final[tuple[DiscoveryState, ...]] = (
    "signal",
    "candidate",
    "corroborated",
    "promoted",
    "rejected",
    "expired",
)
NOVELTY_SCOPES: Final[tuple[NoveltyScope, ...]] = ("user", "cairntir", "general")
DISCOVERY_ROOM: Final[str] = "discoveries"
_DISCOVERY_KIND: Final[str] = "cairntir.discovery"
_ACTIVE_STATES: Final[frozenset[DiscoveryState]] = frozenset(
    {"candidate", "corroborated", "promoted"}
)
_ALLOWED_TRANSITIONS: Final[dict[DiscoveryState, frozenset[DiscoveryState]]] = {
    "signal": frozenset({"candidate", "rejected", "expired"}),
    "candidate": frozenset({"corroborated", "rejected", "expired"}),
    "corroborated": frozenset({"promoted", "rejected", "expired"}),
    "promoted": frozenset({"rejected", "expired"}),
    "rejected": frozenset(),
    "expired": frozenset(),
}


@dataclass(frozen=True, slots=True)
class Discovery:
    """Structured projection of a Discovery Ledger drawer."""

    drawer_id: int
    wing: str
    title: str
    summary: str
    state: DiscoveryState
    novelty: NoveltyScope
    evidence_ids: tuple[int, ...]
    created_at: datetime
    supersedes_id: int | None
    confidence: float | None = None
    observation_count: int | None = None
    baseline: str | None = None
    counterexample_ids: tuple[int, ...] = ()
    next_test: str | None = None
    pattern_key: str | None = None
    evidence_fingerprint: str | None = None


def record_discovery(
    store: Store,
    *,
    wing: str,
    title: str,
    summary: str,
    novelty: NoveltyScope,
    evidence_ids: tuple[int, ...],
    state: DiscoveryState = "signal",
    supersedes_id: int | None = None,
    transition_note: str | None = None,
    confidence: float | None = None,
    observation_count: int | None = None,
    baseline: str | None = None,
    counterexample_ids: tuple[int, ...] = (),
    next_test: str | None = None,
    pattern_key: str | None = None,
    evidence_fingerprint: str | None = None,
) -> Discovery:
    """Append one evidence-backed discovery or lifecycle transition."""
    clean_title = title.strip()
    clean_summary = summary.strip()
    if not clean_title:
        raise ValueError("discovery title must be non-empty")
    if not clean_summary:
        raise ValueError("discovery summary must be non-empty")
    if state not in DISCOVERY_STATES:
        raise ValueError(f"invalid discovery state {state!r}")
    if novelty not in NOVELTY_SCOPES:
        raise ValueError(f"invalid novelty scope {novelty!r}")
    if not evidence_ids:
        raise ValueError("a discovery requires at least one evidence drawer id")
    if any(drawer_id < 1 for drawer_id in evidence_ids):
        raise ValueError("evidence drawer ids must be positive")
    if len(set(evidence_ids)) != len(evidence_ids):
        raise ValueError("discovery evidence drawer ids must be unique")
    if confidence is not None and not 0.0 <= confidence <= 1.0:
        raise ValueError("discovery confidence must be between 0 and 1")
    if observation_count is not None and observation_count < 1:
        raise ValueError("discovery observation_count must be positive")
    if any(drawer_id not in evidence_ids for drawer_id in counterexample_ids):
        raise ValueError("counterexamples must be included in evidence_ids")
    missing = [drawer_id for drawer_id in evidence_ids if store.get(drawer_id) is None]
    if missing:
        raise MemoryStoreError(f"discovery evidence drawer(s) do not exist: {missing}")

    if (
        novelty == "general"
        and state in {"corroborated", "promoted"}
        and (not transition_note or "external" not in transition_note.lower())
    ):
        raise ValueError(
            "general novelty cannot be corroborated/promoted without a "
            "transition note naming external research"
        )

    evidence_refs = ", ".join(f"cairntir://drawer/{item}" for item in evidence_ids)
    content_lines = [
        f"Discovery: {clean_title}",
        f"State: {state}",
        f"Novelty scope: {novelty}",
        "",
        clean_summary,
        "",
        f"Evidence: {evidence_refs}",
    ]
    if transition_note:
        content_lines.extend(("", f"Transition note: {transition_note.strip()}"))

    layer = Layer.ESSENTIAL if state in {"corroborated", "promoted"} else Layer.ON_DEMAND
    saved = store.add(
        Drawer(
            wing=wing,
            room=DISCOVERY_ROOM,
            content="\n".join(content_lines),
            layer=layer,
            metadata={
                "kind": _DISCOVERY_KIND,
                "discovery_title": clean_title,
                "discovery_summary": clean_summary,
                "discovery_state": state,
                "novelty_scope": novelty,
                "evidence_drawer_ids": list(evidence_ids),
                "transition_note": transition_note,
                "confidence": confidence,
                "observation_count": observation_count,
                "baseline": baseline,
                "counterexample_drawer_ids": list(counterexample_ids),
                "next_falsifying_test": next_test,
                "pattern_key": pattern_key,
                "evidence_fingerprint": evidence_fingerprint,
            },
            supersedes_id=supersedes_id,
        )
    )
    return _from_drawer(saved)


def transition_discovery(
    store: Store,
    *,
    drawer_id: int,
    state: DiscoveryState,
    note: str,
) -> Discovery:
    """Append a lifecycle transition that supersedes the current discovery."""
    source = store.get(drawer_id)
    if source is None:
        raise MemoryStoreError(f"no drawer with id {drawer_id}")
    discovery = _from_drawer(source)
    clean_note = note.strip()
    if not clean_note:
        raise ValueError("a discovery transition requires a non-empty note")
    current_ids = {
        item.drawer_id for item in list_discoveries(store, wing=discovery.wing, limit=10_000)
    }
    if drawer_id not in current_ids:
        raise ValueError(
            f"discovery #{drawer_id} has already been superseded; transition its current leaf"
        )
    if state not in _ALLOWED_TRANSITIONS[discovery.state]:
        allowed = sorted(_ALLOWED_TRANSITIONS[discovery.state])
        raise ValueError(
            f"cannot transition discovery from {discovery.state!r} to {state!r}; "
            f"allowed: {allowed or '(terminal state)'}"
        )
    return record_discovery(
        store,
        wing=discovery.wing,
        title=discovery.title,
        summary=discovery.summary,
        novelty=discovery.novelty,
        evidence_ids=discovery.evidence_ids,
        state=state,
        supersedes_id=discovery.drawer_id,
        transition_note=clean_note,
        confidence=discovery.confidence,
        observation_count=discovery.observation_count,
        baseline=discovery.baseline,
        counterexample_ids=discovery.counterexample_ids,
        next_test=discovery.next_test,
        pattern_key=discovery.pattern_key,
        evidence_fingerprint=discovery.evidence_fingerprint,
    )


def propose_multi_episode_discoveries(
    store: Store,
    *,
    wing: str,
    min_observations: int = 3,
    confidence_threshold: float = 0.8,
) -> list[Discovery]:
    """Propose conservative candidates from repeated prediction outcomes.

    Automatic analysis may create or refresh ``candidate`` records. It never
    corroborates or promotes them; those transitions remain evidence- and
    human-governed.
    """
    if min_observations < 2:
        raise ValueError("min_observations must be at least 2")
    if not 0.5 < confidence_threshold <= 1.0:
        raise ValueError("confidence_threshold must be above 0.5 and at most 1.0")

    episodes: dict[str, list[Drawer]] = defaultdict(list)
    for drawer in store.list_by(wing=wing, limit=10_000):
        if (
            drawer.id is not None
            and drawer.claim
            and drawer.observed_outcome is not None
            and isinstance(drawer.metadata.get("success"), bool)
        ):
            episodes[_normalize_claim(drawer.claim)].append(drawer)

    current_by_pattern = {
        item.pattern_key: item
        for item in list_discoveries(store, wing=wing, limit=10_000)
        if item.pattern_key is not None
    }
    proposed: list[Discovery] = []
    for normalized_claim, observations in sorted(episodes.items()):
        if len(observations) < min_observations:
            continue
        successes = [item for item in observations if item.metadata["success"] is True]
        success_rate = len(successes) / len(observations)
        confidence = max(success_rate, 1.0 - success_rate)
        if confidence < confidence_threshold:
            continue

        evidence_ids = tuple(sorted(item.id for item in observations if item.id is not None))
        pattern_key = "claim:" + hashlib.sha256(normalized_claim.encode()).hexdigest()[:20]
        fingerprint = hashlib.sha256(
            json.dumps(evidence_ids, separators=(",", ":")).encode()
        ).hexdigest()
        previous = current_by_pattern.get(pattern_key)
        if previous is not None and previous.evidence_fingerprint == fingerprint:
            continue
        if previous is not None and previous.state in {"corroborated", "promoted"}:
            continue

        reliable = success_rate >= confidence_threshold
        minority = (
            [item for item in observations if item.metadata["success"] is False]
            if reliable
            else successes
        )
        counterexamples = tuple(item.id for item in minority if item.id is not None)
        predicted = Counter(
            item.predicted_outcome for item in observations if item.predicted_outcome is not None
        )
        baseline = predicted.most_common(1)[0][0] if predicted else "no shared prediction"
        direction = "held" if reliable else "failed"
        title = f"Repeated claim {direction}: {observations[0].claim}"
        summary = (
            f"Across {len(observations)} recorded episodes, this claim {direction} "
            f"{len(successes)} time(s) and failed {len(observations) - len(successes)} "
            f"time(s) (calibrated confidence {confidence:.0%}). This is an automatic "
            "candidate, not a promoted rule."
        )
        proposed.append(
            record_discovery(
                store,
                wing=wing,
                title=title,
                summary=summary,
                novelty="cairntir",
                evidence_ids=evidence_ids,
                state="candidate",
                supersedes_id=previous.drawer_id if previous is not None else None,
                confidence=confidence,
                observation_count=len(observations),
                baseline=baseline,
                counterexample_ids=counterexamples,
                next_test=(
                    "Record the next independent episode before using this pattern "
                    "as a reusable strategy."
                ),
                pattern_key=pattern_key,
                evidence_fingerprint=fingerprint,
            )
        )
    return proposed


def list_discoveries(
    store: Store,
    *,
    wing: str | None = None,
    state: DiscoveryState | None = None,
    active_only: bool = False,
    limit: int = 100,
) -> list[Discovery]:
    """Return only the current leaf of each append-only discovery chain."""
    if limit < 1:
        raise ValueError("limit must be positive")
    if state is not None and state not in DISCOVERY_STATES:
        raise ValueError(f"invalid discovery state {state!r}")
    drawers = store.list_by(wing=wing, room=DISCOVERY_ROOM, limit=max(limit * 10, 100))
    discovery_drawers = [
        drawer for drawer in drawers if drawer.metadata.get("kind") == _DISCOVERY_KIND
    ]
    superseded = {
        drawer.supersedes_id for drawer in discovery_drawers if drawer.supersedes_id is not None
    }
    leaves = [
        _from_drawer(drawer)
        for drawer in discovery_drawers
        if drawer.id is not None and drawer.id not in superseded
    ]
    if state is not None:
        leaves = [item for item in leaves if item.state == state]
    if active_only:
        leaves = [item for item in leaves if item.state in _ACTIVE_STATES]
    leaves.sort(key=lambda item: item.created_at, reverse=True)
    return leaves[:limit]


def format_discoveries(discoveries: list[Discovery], *, heading: str) -> str:
    """Render discoveries with stable drawer and evidence references."""
    lines = [f"# {heading}", ""]
    if not discoveries:
        lines.append("(none)")
        return "\n".join(lines) + "\n"
    for item in discoveries:
        evidence = ", ".join(f"#{drawer_id}" for drawer_id in item.evidence_ids)
        lines.extend(
            (
                f"## [{item.state}] {item.title}",
                f"- drawer: cairntir://drawer/{item.drawer_id}",
                f"- wing: {item.wing}",
                f"- novelty: {item.novelty}",
                f"- evidence: {evidence}",
                f"- learned: {item.created_at.isoformat()}",
                f"- confidence: {_format_confidence(item.confidence)}",
                f"- observations: {item.observation_count or 'not calibrated'}",
                f"- baseline: {item.baseline or 'not recorded'}",
                "- counterexamples: "
                + (
                    ", ".join(f"#{drawer_id}" for drawer_id in item.counterexample_ids)
                    or "none recorded"
                ),
                f"- next falsifying test: {item.next_test or 'not recorded'}",
                "",
                item.summary,
                "",
            )
        )
    return "\n".join(lines).rstrip() + "\n"


def human_learning_log(
    store: Store,
    *,
    wing: str | None = None,
    include_candidates: bool = True,
    limit: int = 100,
) -> str:
    """Render the easy-to-read log of current learning outcomes."""
    discoveries = list_discoveries(store, wing=wing, limit=limit)
    visible_states = (
        {"candidate", "corroborated", "promoted"}
        if include_candidates
        else {"corroborated", "promoted"}
    )
    visible = [item for item in discoveries if item.state in visible_states]
    visible.sort(key=lambda item: item.created_at)
    return format_discoveries(visible, heading="Cairntir Human Learning Log")


def _from_drawer(drawer: Drawer) -> Discovery:
    if drawer.metadata.get("kind") != _DISCOVERY_KIND:
        raise ValueError(f"drawer #{drawer.id} is not a Cairntir discovery")
    if drawer.id is None:
        raise MemoryStoreError("persisted discovery drawer has no id")
    state_raw = drawer.metadata.get("discovery_state")
    novelty_raw = drawer.metadata.get("novelty_scope")
    if state_raw not in DISCOVERY_STATES:
        raise MemoryStoreError(f"drawer #{drawer.id} has invalid discovery state {state_raw!r}")
    if novelty_raw not in NOVELTY_SCOPES:
        raise MemoryStoreError(f"drawer #{drawer.id} has invalid novelty scope {novelty_raw!r}")
    evidence_raw = drawer.metadata.get("evidence_drawer_ids")
    if not isinstance(evidence_raw, list) or not all(
        isinstance(item, int) and item > 0 for item in evidence_raw
    ):
        raise MemoryStoreError(f"drawer #{drawer.id} has invalid discovery evidence")
    title = drawer.metadata.get("discovery_title")
    summary = drawer.metadata.get("discovery_summary")
    if not isinstance(title, str) or not title.strip():
        raise MemoryStoreError(f"drawer #{drawer.id} has no discovery title")
    if not isinstance(summary, str) or not summary.strip():
        raise MemoryStoreError(f"drawer #{drawer.id} has no discovery summary")
    return Discovery(
        drawer_id=drawer.id,
        wing=drawer.wing,
        title=title,
        summary=summary,
        state=cast(DiscoveryState, state_raw),
        novelty=cast(NoveltyScope, novelty_raw),
        evidence_ids=tuple(evidence_raw),
        created_at=drawer.created_at,
        supersedes_id=drawer.supersedes_id,
        confidence=_optional_confidence(drawer),
        observation_count=_optional_positive_int(drawer, "observation_count"),
        baseline=_optional_metadata_text(drawer, "baseline"),
        counterexample_ids=_counterexample_ids(drawer),
        next_test=_optional_metadata_text(drawer, "next_falsifying_test"),
        pattern_key=_optional_metadata_text(drawer, "pattern_key"),
        evidence_fingerprint=_optional_metadata_text(drawer, "evidence_fingerprint"),
    )


def _normalize_claim(claim: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", claim.lower()))


def _format_confidence(value: float | None) -> str:
    return f"{value:.0%}" if value is not None else "not calibrated"


def _optional_confidence(drawer: Drawer) -> float | None:
    value = drawer.metadata.get("confidence")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MemoryStoreError(f"drawer #{drawer.id} has invalid discovery confidence")
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise MemoryStoreError(f"drawer #{drawer.id} has invalid discovery confidence")
    return result


def _optional_positive_int(drawer: Drawer, key: str) -> int | None:
    value = drawer.metadata.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise MemoryStoreError(f"drawer #{drawer.id} has invalid discovery {key}")
    return int(value)


def _optional_metadata_text(drawer: Drawer, key: str) -> str | None:
    value = drawer.metadata.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise MemoryStoreError(f"drawer #{drawer.id} has invalid discovery {key}")
    return value


def _counterexample_ids(drawer: Drawer) -> tuple[int, ...]:
    value = drawer.metadata.get("counterexample_drawer_ids", [])
    if not isinstance(value, list) or not all(
        isinstance(item, int) and not isinstance(item, bool) and item > 0 for item in value
    ):
        raise MemoryStoreError(f"drawer #{drawer.id} has invalid discovery counterexamples")
    return tuple(value)
