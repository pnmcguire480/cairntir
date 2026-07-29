"""Evidence-cited CodeGlass walkthroughs, teach-back, and retention."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Final, Literal

from cairntir.contracts import Store
from cairntir.errors import MemoryStoreError
from cairntir.learning import list_discoveries, record_discovery
from cairntir.memory.taxonomy import Drawer, Layer

ReaderLevel = Literal["novice", "intermediate", "expert"]
TeachBackPhase = Literal["immediate", "delayed"]

READER_LEVELS: Final[tuple[ReaderLevel, ...]] = ("novice", "intermediate", "expert")
TEACH_BACK_PHASES: Final[tuple[TeachBackPhase, ...]] = ("immediate", "delayed")
CODEGLASS_ROOM: Final[str] = "codeglass"
_WALKTHROUGH_KIND: Final[str] = "codeglass.walkthrough"
_TEACHBACK_KIND: Final[str] = "codeglass.teachback"
_SECTION_NAMES: Final[tuple[str, ...]] = ("what", "how", "where", "when", "why")
_CITATION_RE = re.compile(r"\[source:[^\]\r\n]+\]", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class TeachBackResponse:
    """One question, the learner's answer, and a reviewed 0-1 score."""

    question: str
    answer: str
    score: float


@dataclass(frozen=True, slots=True)
class RetentionReport:
    """Immediate-versus-delayed comprehension for one walkthrough."""

    walkthrough_id: int
    immediate_score: float | None
    delayed_score: float | None
    retention_delta: float | None
    mastered_concepts: tuple[str, ...]
    misunderstood_concepts: tuple[str, ...]
    immediate_drawer_id: int | None
    delayed_drawer_id: int | None


def record_walkthrough(
    store: Store,
    *,
    wing: str,
    target: str,
    reader_level: ReaderLevel,
    sections: dict[str, str],
    evidence_ids: tuple[int, ...],
    glossary: str,
    danger_zones: str,
) -> Drawer:
    """Persist a complete, cited walkthrough after deterministic validation."""
    clean_target = target.strip()
    if not clean_target:
        raise ValueError("CodeGlass target must be non-empty")
    if reader_level not in READER_LEVELS:
        raise ValueError(f"invalid reader_level {reader_level!r}")
    if set(sections) != set(_SECTION_NAMES):
        raise ValueError(f"CodeGlass sections must be exactly {list(_SECTION_NAMES)}")
    if not evidence_ids:
        raise ValueError("CodeGlass requires at least one evidence drawer")
    if len(set(evidence_ids)) != len(evidence_ids):
        raise ValueError("CodeGlass evidence drawer ids must be unique")
    missing = [drawer_id for drawer_id in evidence_ids if store.get(drawer_id) is None]
    if missing:
        raise MemoryStoreError(f"CodeGlass evidence drawer(s) do not exist: {missing}")

    cleaned: dict[str, str] = {}
    for name in _SECTION_NAMES:
        value = sections[name].strip()
        if not value:
            raise ValueError(f"CodeGlass {name.upper()} section must be non-empty")
        if value.lower() != "unknown" and _CITATION_RE.search(value) is None:
            raise ValueError(
                f"CodeGlass {name.upper()} requires a [source:...] citation or 'unknown'"
            )
        cleaned[name] = value
    if not glossary.strip():
        raise ValueError("CodeGlass glossary must be non-empty")
    if not danger_zones.strip():
        raise ValueError("CodeGlass danger_zones must be non-empty")

    evidence = ", ".join(f"cairntir://drawer/{drawer_id}" for drawer_id in evidence_ids)
    body = [
        f"# CodeGlass — {clean_target}",
        "",
        f"Reader level: {reader_level}",
        f"Evidence: {evidence}",
        "",
    ]
    for name in _SECTION_NAMES:
        body.extend((f"## {name.upper()}", cleaned[name], ""))
    body.extend(("## GLOSSARY", glossary.strip(), "", "## DANGER ZONES", danger_zones.strip()))
    return store.add(
        Drawer(
            wing=wing,
            room=CODEGLASS_ROOM,
            content="\n".join(body),
            layer=Layer.DEEP,
            metadata={
                "kind": _WALKTHROUGH_KIND,
                "target": clean_target,
                "reader_level": reader_level,
                "evidence_drawer_ids": list(evidence_ids),
                "walkthrough_fingerprint": walkthrough_fingerprint(
                    wing=wing,
                    target=clean_target,
                    reader_level=reader_level,
                    sections=cleaned,
                    evidence_ids=evidence_ids,
                ),
            },
        )
    )


def walkthrough_fingerprint(
    *,
    wing: str,
    target: str,
    reader_level: ReaderLevel,
    sections: dict[str, str],
    evidence_ids: tuple[int, ...],
) -> str:
    """Return the stable regeneration key for one evidence/explanation set."""
    payload = {
        "wing": wing,
        "target": target.strip(),
        "reader_level": reader_level,
        "sections": sections,
        "evidence_ids": sorted(evidence_ids),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def record_teachback(
    store: Store,
    *,
    walkthrough_id: int,
    phase: TeachBackPhase,
    responses: tuple[TeachBackResponse, ...],
    mastered_concepts: tuple[str, ...] = (),
    misunderstood_concepts: tuple[str, ...] = (),
) -> Drawer:
    """Record a two- or three-question teach-back result."""
    if phase not in TEACH_BACK_PHASES:
        raise ValueError(f"invalid teach-back phase {phase!r}")
    if len(responses) not in (2, 3):
        raise ValueError("CodeGlass teach-back requires two or three responses")
    walkthrough = store.get(walkthrough_id)
    if walkthrough is None:
        raise MemoryStoreError(f"no walkthrough drawer with id {walkthrough_id}")
    if walkthrough.metadata.get("kind") != _WALKTHROUGH_KIND:
        raise ValueError(f"drawer #{walkthrough_id} is not a CodeGlass walkthrough")
    for response in responses:
        if not response.question.strip() or not response.answer.strip():
            raise ValueError("teach-back questions and answers must be non-empty")
        if not 0.0 <= response.score <= 1.0:
            raise ValueError("teach-back scores must be between 0 and 1")

    score = sum(response.score for response in responses) / len(responses)
    lines = [
        f"# CodeGlass teach-back — {phase}",
        f"Walkthrough: cairntir://drawer/{walkthrough_id}",
        f"Score: {score:.0%}",
        "",
    ]
    for index, response in enumerate(responses, start=1):
        lines.extend(
            (
                f"## Question {index}",
                response.question.strip(),
                "",
                "### Learner answer",
                response.answer.strip(),
                "",
                f"Reviewed score: {response.score:.0%}",
                "",
            )
        )
    lines.extend(
        (
            "## Mastered concepts",
            ", ".join(mastered_concepts) or "none recorded",
            "",
            "## Misunderstood concepts",
            ", ".join(misunderstood_concepts) or "none recorded",
        )
    )
    parent_id = walkthrough_id
    if phase == "delayed":
        immediate = next(
            (
                drawer
                for drawer in store.list_by(
                    wing=walkthrough.wing,
                    room=CODEGLASS_ROOM,
                    limit=100_000,
                )
                if drawer.metadata.get("kind") == _TEACHBACK_KIND
                and drawer.metadata.get("walkthrough_id") == walkthrough_id
                and drawer.metadata.get("phase") == "immediate"
                and drawer.id is not None
            ),
            None,
        )
        if immediate is not None and immediate.id is not None:
            parent_id = immediate.id

    saved = store.add(
        Drawer(
            wing=walkthrough.wing,
            room=CODEGLASS_ROOM,
            content="\n".join(lines),
            layer=Layer.ON_DEMAND,
            metadata={
                "kind": _TEACHBACK_KIND,
                "walkthrough_id": walkthrough_id,
                "phase": phase,
                "score": score,
                "mastered_concepts": list(mastered_concepts),
                "misunderstood_concepts": list(misunderstood_concepts),
            },
            supersedes_id=parent_id,
        )
    )
    if phase == "delayed":
        _record_retention_discovery(store, saved)
    return saved


def retention_report(store: Store, *, walkthrough_id: int) -> RetentionReport:
    """Compare the latest immediate and delayed teach-back receipts."""
    teachbacks = [
        drawer
        for drawer in store.list_by(room=CODEGLASS_ROOM, limit=100_000)
        if drawer.metadata.get("kind") == _TEACHBACK_KIND
        and drawer.metadata.get("walkthrough_id") == walkthrough_id
    ]
    immediate = next(
        (drawer for drawer in teachbacks if drawer.metadata.get("phase") == "immediate"),
        None,
    )
    delayed = next(
        (drawer for drawer in teachbacks if drawer.metadata.get("phase") == "delayed"),
        None,
    )
    immediate_score = _score(immediate)
    delayed_score = _score(delayed)
    delta = (
        delayed_score - immediate_score
        if delayed_score is not None and immediate_score is not None
        else None
    )
    return RetentionReport(
        walkthrough_id=walkthrough_id,
        immediate_score=immediate_score,
        delayed_score=delayed_score,
        retention_delta=delta,
        mastered_concepts=_concepts(delayed or immediate, "mastered_concepts"),
        misunderstood_concepts=_concepts(delayed or immediate, "misunderstood_concepts"),
        immediate_drawer_id=immediate.id if immediate is not None else None,
        delayed_drawer_id=delayed.id if delayed is not None else None,
    )


def render_retention(report: RetentionReport) -> str:
    """Render a concise human learning receipt."""
    immediate = _format_score(report.immediate_score)
    delayed = _format_score(report.delayed_score)
    delta = (
        f"{report.retention_delta:+.0%}" if report.retention_delta is not None else "not available"
    )
    return "\n".join(
        (
            f"# CodeGlass retention — walkthrough #{report.walkthrough_id}",
            f"- immediate teach-back: {immediate}",
            f"- delayed teach-back: {delayed}",
            f"- retention change: {delta}",
            "- mastered: " + (", ".join(report.mastered_concepts) or "none recorded"),
            "- revisit: " + (", ".join(report.misunderstood_concepts) or "none recorded"),
        )
    )


def _record_retention_discovery(store: Store, delayed: Drawer) -> None:
    walkthrough_id = int(delayed.metadata["walkthrough_id"])
    report = retention_report(store, walkthrough_id=walkthrough_id)
    if report.immediate_drawer_id is None or report.delayed_drawer_id is None:
        return
    delayed_score = report.delayed_score or 0.0
    result = "retained" if delayed_score >= 0.8 else "needs reinforcement"
    pattern_key = f"codeglass-retention:{walkthrough_id}"
    previous = next(
        (
            discovery
            for discovery in list_discoveries(store, wing=delayed.wing, limit=10_000)
            if discovery.pattern_key == pattern_key
        ),
        None,
    )
    if previous is not None and previous.state in {"corroborated", "promoted"}:
        return
    evidence_fingerprint = hashlib.sha256(
        f"{report.immediate_drawer_id}:{report.delayed_drawer_id}".encode()
    ).hexdigest()
    record_discovery(
        store,
        wing=delayed.wing,
        title=f"CodeGlass learning {result} for walkthrough #{walkthrough_id}",
        summary=(
            f"Immediate score {_format_score(report.immediate_score)}; delayed score "
            f"{_format_score(report.delayed_score)}. "
            f"Concepts to revisit: {', '.join(report.misunderstood_concepts) or 'none'}."
        ),
        novelty="user",
        evidence_ids=(report.immediate_drawer_id, report.delayed_drawer_id),
        state="candidate",
        supersedes_id=previous.drawer_id if previous is not None else None,
        confidence=delayed_score,
        observation_count=2,
        baseline="immediate teach-back score",
        next_test="Repeat the teach-back after another delay using new questions.",
        pattern_key=pattern_key,
        evidence_fingerprint=evidence_fingerprint,
    )


def _score(drawer: Drawer | None) -> float | None:
    if drawer is None:
        return None
    value = drawer.metadata.get("score")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MemoryStoreError(f"drawer #{drawer.id} has invalid CodeGlass score")
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise MemoryStoreError(f"drawer #{drawer.id} has invalid CodeGlass score")
    return result


def _concepts(drawer: Drawer | None, key: str) -> tuple[str, ...]:
    if drawer is None:
        return ()
    value = drawer.metadata.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise MemoryStoreError(f"drawer #{drawer.id} has invalid CodeGlass {key}")
    return tuple(value)


def _format_score(value: float | None) -> str:
    return f"{value:.0%}" if value is not None else "not recorded"
