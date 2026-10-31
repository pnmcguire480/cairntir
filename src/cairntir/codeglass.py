"""Evidence-cited CodeGlass walkthroughs, teach-back, and retention."""

from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Final, Literal

from cairntir.contracts import Store
from cairntir.errors import MemoryStoreError, ProjectionError
from cairntir.learning import list_discoveries, record_discovery
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer, Layer
from cairntir.procedures import (
    PracticeLifecycleReceipt,
    PracticeSupersessionReceipt,
    ProcedureBook,
    ProcedureError,
    practice_read_view,
)
from cairntir.provenance import Sensitivity

ReaderLevel = Literal["novice", "intermediate", "expert"]
TeachBackPhase = Literal["immediate", "delayed"]

READER_LEVELS: Final[tuple[ReaderLevel, ...]] = ("novice", "intermediate", "expert")
TEACH_BACK_PHASES: Final[tuple[TeachBackPhase, ...]] = ("immediate", "delayed")
CODEGLASS_ROOM: Final[str] = "codeglass"
CHECK_REPORT_SCHEMA: Final[str] = "cairntir.codeglass-check-report.v1"
HUMANFLOW_SCHEMA: Final[str] = "cairntir.humanflow-walkthrough.v1"
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
    check_report_schema: str | None = None,
    humanflow_metadata: dict[str, Any] | None = None,
) -> Drawer:
    """Persist a complete, cited walkthrough after deterministic validation."""
    if humanflow_metadata is not None and (
        check_report_schema != CHECK_REPORT_SCHEMA
        or set(humanflow_metadata)
        != {
            "humanflow_schema",
            "bundle_sha256",
            "response_sha256",
            "adapter",
            "humanflow_reader_level",
            "claim_anchors",
            "claims",
        }
        or humanflow_metadata["humanflow_schema"] != HUMANFLOW_SCHEMA
        or any(
            not isinstance(humanflow_metadata[key], str)
            or re.fullmatch(r"[0-9a-f]{64}", humanflow_metadata[key]) is None
            for key in ("bundle_sha256", "response_sha256")
        )
    ):
        raise ValueError("unsupported HumanFlow metadata")
    clean_target = target.strip()
    if check_report_schema not in (None, CHECK_REPORT_SCHEMA):
        raise ValueError("unsupported CodeGlass check report schema")
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
                **({"check_report_schema": check_report_schema} if check_report_schema else {}),
                **(humanflow_metadata or {}),
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


def render_check_report(report: dict[str, Any]) -> str:
    """Render an evidence snapshot without executing checks or inferring rule credit."""

    def cell(value: object) -> str:
        text = "UNKNOWN" if value is None else str(value)
        text = html.escape(text, quote=True)
        for character in "|`[]()":
            text = text.replace(character, f"&#{ord(character)};")
        return text.replace("\r", "").replace("\n", "<br>")

    def link(drawer_id: int | None) -> str:
        return f"[[cairntir-sync/receipts/drawer-{drawer_id}]]" if drawer_id else "UNKNOWN"

    lines = [
        "## Check outcomes",
        "Publication snapshot. Historical outcomes and current artifact availability are separate.",
        "Errors prevented: UNKNOWN. Test passes do not establish rule causation.",
    ]
    for attempt in report["attempts"]:
        lines.extend(("", f"### Attempt {cell(attempt['attempt_id'])}"))
        for source in attempt["source_inputs"]:
            lines.append(f"Source: {cell(source['path'])} — {cell(source['sha256'])}")
        for stage in attempt["stages"]:
            required = stage["required"]
            lines.extend(
                (
                    "",
                    f"#### {cell(stage['stage_id'])}: {cell(stage['status'])}",
                    f"Command: {cell(stage['command_status'])}; "
                    f"artifacts: {cell(stage['artifact_availability'])}.",
                    f"Required minimum: {required['passed']}/{required['total']} passed; "
                    f"{required['executed']}/{required['total']} executed; "
                    f"{required['collected']}/{required['total']} collected. "
                    "Whole-suite completeness: UNKNOWN.",
                    f"Code coverage: {cell(stage['coverage'])}",
                    f"Stage receipt: {link(stage['stage_result_id'])}",
                    "",
                    "| Check | Outcome | Required | JUnit SHA256 | Evidence |",
                    "| --- | --- | --- | --- | --- |",
                )
            )
            for case in stage["cases"]:
                lines.append(
                    f"| {cell(case['classname'])} / {cell(case['name'])} | "
                    f"{cell(case['outcome'])} | {case['required']} | "
                    f"{cell(case['junit_sha256'])} | {link(case['stage_result_id'])} |"
                )
            lines.extend(f"Diagnostic: {cell(item)}" for item in stage["diagnostics"])
    lines.extend(("", "## Attempt changes"))
    if not report["trend"]:
        lines.append("No adjacent measured attempts to compare.")
    for trend in report["trend"]:
        lines.append(
            f"{cell(trend['stage_id'])}: {cell(trend['from_attempt_id'])} → "
            f"{cell(trend['to_attempt_id'])}: {cell(trend['comparability'])}"
        )
        lines.extend(
            f"- {cell(row['classname'])} / {cell(row['name'])}: "
            f"{cell(row['from'])} → {cell(row['to'])}"
            for row in trend["changes"]
        )
    lines.extend(("", "## Explicit practice observations"))
    if not report["observations"]:
        lines.append("No practice attribution supplied; impact remains UNKNOWN.")
    for row in report["observations"]:
        lines.extend(
            (
                f"- {link(row['receipt_id'])}: {cell(row['origin'])}, "
                f"{cell(row['scope'])} {link(row['stage_result_id'])}; "
                f"procedure {link(row['procedure_id'])}, root {link(row['root_id'])}, "
                f"version {cell(row['version'])}, revision {cell(row['revision_sha256'])}.",
                f"  Triggered: {cell(row['triggered'])}; "
                f"false positive: {cell(row['false_positive'])}; "
                f"overridden: {cell(row['overridden'])}; "
                f"baseline impact: {cell(row['baseline_impact'])}; "
                f"practice impact: {cell(row['practice_impact'])}; "
                f"unit: {cell(row['impact_unit'])}; "
                f"supersedes: {link(row['supersedes_id'])}.",
            )
        )
    lines.extend(("", "## Captured event evidence"))
    events = report.get("event_ids", [])
    lines.append(
        ", ".join(cell(item) for item in events)
        if events
        else "UNKNOWN: no event references available."
    )
    return "\n".join(lines)


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
            for discovery in list_discoveries(store, wing=delayed.wing, limit=None)
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


@dataclass(frozen=True, slots=True)
class PracticeRegisterRevision:
    """One original stored revision and its content and metadata fingerprints."""

    drawer_id: int
    supersedes_id: int | None
    state: str
    revision_sha256: str
    content: str
    content_sha256: str
    metadata_sha256: str
    owner: str | None
    version: str | None
    rationale: str | None
    review_due: str | None


@dataclass(frozen=True, slots=True)
class PracticeRegisterRow:
    """The actual current leaf, governance and retrievable family history."""

    root_id: int
    current_id: int
    status: str
    title: str
    owner: str | None
    version: str | None
    rationale: str | None
    review_due: str | None
    due: bool | None
    review_id: int | None
    history: tuple[PracticeRegisterRevision, ...]
    lifecycle: tuple[PracticeLifecycleReceipt, ...] = ()
    assigned_tier: str | None = None
    effective_tier: str | None = None
    mode: str | None = None


@dataclass(frozen=True, slots=True)
class PracticeConflictRow:
    """A public comparison of original rules with explicit revision freshness."""

    conflict_id: int
    first_id: int
    second_id: int
    first_severity: str
    second_severity: str
    first_context: tuple[str, ...]
    second_context: tuple[str, ...]
    situation: tuple[str, ...]
    status: str
    winner_id: int | None
    basis: str | None
    current: bool
    source_ids: tuple[int, ...]
    origin: str
    first_title: str
    second_title: str


@dataclass(frozen=True, slots=True)
class PracticeRegisterSnapshot:
    """A complete authorized wing register evaluated at an explicit review date."""

    wing: str
    as_of: str
    rows: tuple[PracticeRegisterRow, ...]
    conflicts: tuple[PracticeConflictRow, ...] = ()
    supersessions: tuple[PracticeSupersessionReceipt, ...] = ()


def build_practice_register(
    store: DrawerStore, *, wing: str, as_of: str
) -> PracticeRegisterSnapshot:
    """Read authenticated current practice families without changing the store."""
    if not isinstance(wing, str) or not wing.strip():
        raise ValueError("practice register requires an explicit wing")
    if not isinstance(as_of, str) or date.fromisoformat(as_of).isoformat() != as_of:
        raise ValueError("practice register date must be YYYY-MM-DD")
    view = practice_read_view(store)
    book = ProcedureBook(view, {})
    checked: dict[int, Drawer] = {}
    now = datetime.now(UTC)

    def source(drawer_id: int) -> Drawer:
        if drawer_id in checked:
            return checked[drawer_id]
        drawer = view.get(drawer_id)
        provenance = view.get_provenance(drawer_id)
        if (
            drawer is None
            or drawer.wing != wing
            or provenance is None
            or provenance.sensitivity is Sensitivity.SECRET
            or (provenance.valid_from is not None and provenance.valid_from > now)
            or (provenance.valid_until is not None and provenance.valid_until <= now)
        ):
            raise ProjectionError("practice register unavailable")
        checked[drawer_id] = drawer
        for relation in view.portable_relations(drawer_id):
            source(relation["target_drawer_id"])
        return drawer

    rows: list[PracticeRegisterRow] = []
    titles: dict[int, str] = {}
    conflicts: list[PracticeConflictRow] = []
    with book.complete_history(wing=wing):
        current = book.list(wing=wing, active_only=False)
        roots: set[int] = set()
        for procedure in current:
            family = book.history(procedure.drawer_id)
            if not family or family[-1] != procedure or family[0].drawer_id in roots:
                raise ProcedureError("practice family changed or is incomplete")
            roots.add(family[0].drawer_id)
            history: list[PracticeRegisterRevision] = []
            for revision in family:
                titles[revision.drawer_id] = revision.spec.title
                drawer = source(revision.drawer_id)
                for evidence_id in revision.spec.evidence_ids:
                    source(evidence_id)
                if revision.evaluation_id is not None:
                    evaluation = book.get_evaluation(revision.evaluation_id)
                    source(evaluation.drawer_id)
                    for case in evaluation.cases:
                        for evidence_id in (
                            case.evidence_id,
                            case.baseline_prediction_id,
                            case.baseline_observation_id,
                            case.candidate_prediction_id,
                            case.candidate_observation_id,
                        ):
                            source(evidence_id)
                governance = revision.spec.governance
                metadata = json.dumps(
                    drawer.metadata,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
                history.append(
                    PracticeRegisterRevision(
                        revision.drawer_id,
                        revision.supersedes_id,
                        revision.state,
                        revision.revision_sha256,
                        drawer.content,
                        hashlib.sha256(drawer.content.encode("utf-8")).hexdigest(),
                        hashlib.sha256(metadata.encode("utf-8")).hexdigest(),
                        governance.owner if governance else None,
                        governance.version if governance else None,
                        governance.rationale if governance else None,
                        governance.review_due if governance else None,
                    )
                )
            reviews = book.review_history(procedure.drawer_id)
            for review in reviews:
                source(review.drawer_id)
                for evidence_id in (
                    *review.assessment.evidence_ids,
                    *review.assessment.observation_ids,
                ):
                    source(evidence_id)
            matching = [
                review
                for review in reviews
                if review.assessment.revision_sha256 == procedure.revision_sha256
            ]
            latest = matching[-1] if matching else None
            if latest is not None and latest.reviewed_on > as_of:
                raise ProcedureError("register date precedes a recorded review")
            governance = procedure.spec.governance
            deadline = (
                latest.next_review_due if latest else governance.review_due if governance else None
            )
            status = (
                "active_governance_incomplete"
                if procedure.state == "promoted" and governance is None
                else "active"
                if procedure.state == "promoted"
                else "withdrawn"
                if procedure.state in {"expired", "rejected"}
                else "pending"
            )
            lifecycle = book.lifecycle_history(procedure.drawer_id)
            for event in lifecycle:
                source(event.drawer_id)
                for evidence_id in event.evidence_ids:
                    source(evidence_id)
            latest_phase = lifecycle[-1] if lifecycle else None
            phase_applies = (
                latest_phase is not None
                and latest_phase.epoch_id == book._practice_epoch(procedure)
                and procedure.state not in {"expired", "rejected"}
            )
            if latest_phase is not None:
                status = (
                    latest_phase.state
                    if phase_applies
                    else "withdrawn"
                    if procedure.state in {"expired", "rejected"}
                    else "awaiting_lifecycle_reset"
                )
            rows.append(
                PracticeRegisterRow(
                    family[0].drawer_id,
                    procedure.drawer_id,
                    status,
                    procedure.spec.title,
                    governance.owner if governance else None,
                    governance.version if governance else None,
                    governance.rationale if governance else None,
                    deadline,
                    deadline <= as_of if deadline else None,
                    latest.drawer_id if latest else None,
                    tuple(history),
                    lifecycle,
                    latest_phase.assigned_tier if latest_phase and phase_applies else None,
                    latest_phase.effective_tier if latest_phase and phase_applies else None,
                    latest_phase.mode
                    if latest_phase and phase_applies
                    else ("UNAPPLIED" if latest_phase else None),
                )
            )
        supersessions = book._supersessions(wing)
        for directive in supersessions:
            source(directive.drawer_id)
            for evidence_id in directive.evidence_ids:
                source(evidence_id)
        receipts = book.list_conflicts(wing=wing)
        for receipt in receipts:
            first, second = receipt.first, receipt.second
            references = tuple(
                sorted(
                    {
                        first.procedure_id,
                        second.procedure_id,
                        first.evidence_id,
                        second.evidence_id,
                        receipt.conflict_evidence_id,
                    }
                )
            )
            source(receipt.drawer_id)
            for reference in references:
                source(reference)
            if first.procedure_id not in titles or second.procedure_id not in titles:
                raise ProcedureError("conflict practice history is incomplete")
            eligible = {
                item.procedure_id
                for item in book._scan_practices(wing=wing, context=receipt.situation)
                if item.mode == "ACTIVE"
            }
            fresh = first.procedure_id in eligible and second.procedure_id in eligible
            conflicts.append(
                PracticeConflictRow(
                    receipt.drawer_id,
                    first.procedure_id,
                    second.procedure_id,
                    first.severity,
                    second.severity,
                    first.context,
                    second.context,
                    receipt.situation,
                    receipt.status if fresh else "stale_revision",
                    receipt.winner_id if fresh else None,
                    receipt.basis if fresh else None,
                    fresh,
                    references,
                    receipt.origin,
                    titles[first.procedure_id],
                    titles[second.procedure_id],
                )
            )
        if book.list_conflicts(wing=wing) != receipts:
            raise ProcedureError("practice conflicts changed during read")
        if book.list(wing=wing, active_only=False) != current:
            raise ProcedureError("practice register changed during read")
    return PracticeRegisterSnapshot(wing, as_of, tuple(rows), tuple(conflicts), supersessions)
