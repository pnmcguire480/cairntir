"""Durable host-call scheduling for evidence-backed advisory practice reviews."""

from __future__ import annotations

import calendar
import json
from copy import deepcopy
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

from cairntir.codeglass import build_practice_register
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.procedures import (
    PracticeReviewAssessment,
    PracticeReviewPolicy,
    ProcedureBook,
    ProcedureError,
    _hash,
    _json,
    _practice_date,
    _practice_id,
    _text,
    _validate_review_policy,
    practice_read_view,
)
from cairntir.provenance import Sensitivity

_ROOM = "practice-schedules"
_CONFIG = "cairntir.practice-schedule.v1"
_PROPOSAL = "cairntir.practice-review-proposal.v1"
_TICK = "cairntir.practice-review-tick.v1"


def _lookback(day: date) -> str:
    year, month = divmod(day.year * 12 + day.month - 4, 12)
    return date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1])).isoformat()


def _basis(assessment: PracticeReviewAssessment) -> dict[str, Any]:
    material: dict[str, Any] = json.loads(_json(asdict(assessment)))
    for name in ("period_start", "period_end", "as_of", "assessment_sha256"):
        material.pop(name)
    return material


def _advice(assessment: PracticeReviewAssessment) -> tuple[str, str]:
    measured = assessment.metrics[0]
    policy = assessment.policy
    details = []
    for reason, value, count, threshold, sign in (
        (
            "trigger-rate",
            measured.trigger_rate,
            measured.trigger_known,
            policy.minimum_trigger_rate,
            "<",
        ),
        (
            "false-positive-rate",
            measured.false_positive_rate,
            measured.false_positive_known,
            policy.maximum_false_positive_rate,
            ">",
        ),
        (
            "override-rate",
            measured.override_rate,
            measured.override_known,
            policy.maximum_override_rate,
            ">",
        ),
        ("impact", measured.mean_impact, measured.impact_known, policy.minimum_mean_impact, "<"),
    ):
        if reason in assessment.reasons:
            details.append(f"observed {reason} {value} (denominator {count}) {sign} {threshold}")
    if details:
        return "revise", "Advisory revision: " + "; ".join(
            details
        ) + ". Measurements are attributed, not independently proven."
    return (
        "inspect-evidence",
        f"Inspect evidence for review due {assessment.effective_review_due}; "
        "missing measures remain unknown.",
    )


def _render(report: dict[str, Any]) -> str:
    clock = "simulated clock" if report["simulated_clock"] else "current UTC clock"
    lines = [
        f"# Practice review queue: {report['wing']}",
        f"As of {report['as_of']} ({clock}); next scan {report['next_scan_on']}.",
        "Field-duration completeness is unknown. Proposals do not approve or change practices.",
    ]
    if not report["proposals"]:
        lines.append("No currently justified review proposals.")
    for proposal in report["proposals"]:
        lines.extend(
            [
                f"\n## Practice #{proposal['procedure_id']} — version {proposal['version']}",
                f"Proposal [#{proposal['proposal_id']}]"
                f"(cairntir://drawer/{proposal['proposal_id']}): "
                f"{proposal['suggested_action']}",
                proposal["rationale"],
                "Reasons: " + ", ".join(proposal["assessment"]["reasons"]),
            ]
        )
        for cohort in proposal["assessment"]["metrics"]:
            values = []
            for label, field, known, unknown in (
                ("trigger rate", "trigger_rate", "trigger_known", "trigger_unknown"),
                (
                    "false-positive rate",
                    "false_positive_rate",
                    "false_positive_known",
                    "false_positive_unknown",
                ),
                ("override rate", "override_rate", "override_known", "override_unknown"),
                ("mean impact", "mean_impact", "impact_known", "impact_unknown"),
            ):
                value = "unknown" if cohort[field] is None else str(cohort[field])
                values.append(
                    f"{label}: {value} (known {cohort[known]}, unknown {cohort[unknown]})"
                )
            lines.append(
                f"{cohort['origin']}: {cohort['observation_count']} observations; "
                + "; ".join(values)
            )
        lines.append(
            "Sources: "
            + " ".join(f"[#{key}](cairntir://drawer/{key})" for key in proposal["evidence_ids"])
        )
    if report["legacy_incomplete"]:
        lines.append(
            "Legacy practices need explicit governance before scheduled review: "
            + ", ".join(str(key) for key in report["legacy_incomplete"])
        )
    return "\n".join(lines) + "\n"


class PracticeReviewScheduler:
    """Persist cadence and advisory proposals without executing or approving a rule."""

    def __init__(self, store: DrawerStore) -> None:
        """Bind the existing store and its authorized non-touch read view."""
        self._store = store
        self._view = practice_read_view(store)
        self._book = ProcedureBook(self._view, {})

    def _source(self, key: int, wing: str, seen: set[int] | None = None) -> Drawer:
        _practice_id(key)
        seen = set() if seen is None else seen
        drawer = self._view.get(key)
        provenance = self._view.get_provenance(key)
        now = datetime.now(UTC)
        if (
            drawer is None
            or drawer.wing != wing
            or provenance is None
            or provenance.sensitivity is Sensitivity.SECRET
            or (provenance.valid_from is not None and provenance.valid_from > now)
            or (provenance.valid_until is not None and provenance.valid_until <= now)
        ):
            raise ProcedureError("practice review unavailable")
        if key not in seen:
            seen.add(key)
            for relation in self._view.portable_relations(key):
                self._source(relation["target_drawer_id"], wing, seen)
        return drawer

    def _entries(self, wing: str) -> list[dict[str, Any]]:
        entries = []
        for drawer in sorted(
            self._view.list_by(wing=wing, room=_ROOM, limit=None, include_expired=True),
            key=lambda row: row.id or 0,
        ):
            if drawer.id is None:
                raise ProcedureError("practice review unavailable")
            record = self._view._procedure_evaluation(drawer.id)
            if record is None:
                if drawer.metadata.get("kind") in {_CONFIG, _PROPOSAL, _TICK}:
                    raise ProcedureError("unregistered practice schedule record")
                continue
            if set(record) != {"kind", "material", "drawer_id", "record_sha256"}:
                raise ProcedureError("invalid practice schedule record")
            kind, material = record["kind"], record["material"]
            if kind not in {_CONFIG, _PROPOSAL, _TICK} or not isinstance(material, dict):
                raise ProcedureError("invalid practice schedule record")
            source = self._source(drawer.id, wing)
            fingerprint = _hash({"kind": kind, "material": material})
            if (
                record["drawer_id"] != drawer.id
                or record["record_sha256"] != fingerprint
                or material.get("wing") != wing
                or source.content != _json({"kind": kind, "material": material})
                or source.supersedes_id != material.get("supersedes_id")
                or source.metadata != {"kind": kind, "evidence_ids": material.get("evidence_ids")}
            ):
                raise ProcedureError("practice schedule fingerprint mismatch")
            entries.append({**material, "_id": drawer.id, "_kind": kind, "_sha": fingerprint})
        return entries

    def _current(self, entries: list[dict[str, Any]]) -> dict[str, Any] | None:
        current = None
        for entry in entries:
            if entry["_kind"] != _CONFIG:
                continue
            if entry["supersedes_id"] != (current["_id"] if current else None):
                raise ProcedureError("practice schedule has a stale or ambiguous branch")
            _practice_date(entry["first_scan_on"], "first_scan_on")
            self._cadence(entry["scan_interval_days"])
            _validate_review_policy(PracticeReviewPolicy(**entry["policy"]))
            current = entry
        return current

    @staticmethod
    def _cadence(value: int) -> None:
        if type(value) is not int or value < 1 or value > 366:
            raise ProcedureError("scan interval must be 1-366 days")

    def _save(
        self, kind: str, material: dict[str, Any], entries: list[dict[str, Any]]
    ) -> dict[str, Any]:
        fingerprint = _hash({"kind": kind, "material": material})
        existing = next(
            (entry for entry in entries if entry["_kind"] == kind and entry["_sha"] == fingerprint),
            None,
        )
        if existing is not None:
            return existing
        authorize = getattr(self._store, "authorize", None)
        if callable(authorize):
            authorize("write", wing=material["wing"], room=_ROOM)
        drawer = self._store.add(
            Drawer(
                wing=material["wing"],
                room=_ROOM,
                content=_json({"kind": kind, "material": material}),
                supersedes_id=material["supersedes_id"],
                metadata={"kind": kind, "evidence_ids": material["evidence_ids"]},
            )
        )
        if drawer.id is None:
            raise ProcedureError("practice schedule write has no identity")
        self._store._register_procedure_evaluation(
            drawer.id,
            {
                "kind": kind,
                "material": material,
                "drawer_id": drawer.id,
                "record_sha256": fingerprint,
            },
        )
        entry = {**deepcopy(material), "_id": drawer.id, "_kind": kind, "_sha": fingerprint}
        entries.append(entry)
        return entry

    @staticmethod
    def _configuration(entry: dict[str, Any]) -> dict[str, Any]:
        return {
            "schedule_id": entry["_id"],
            "schedule_sha256": entry["_sha"],
            **{
                name: deepcopy(entry[name])
                for name in ("wing", "first_scan_on", "scan_interval_days", "policy")
            },
        }

    def configure(
        self,
        *,
        wing: str,
        first_scan_on: str,
        policy: PracticeReviewPolicy,
        scan_interval_days: int = 1,
        supersedes_id: int | None = None,
    ) -> dict[str, Any]:
        """Append explicit configuration; caller-owned transactions stay provisional."""
        try:
            _text(wing, "wing")
            _practice_date(first_scan_on, "first_scan_on")
            _validate_review_policy(policy)
            self._cadence(scan_interval_days)
            if supersedes_id is not None:
                _practice_id(supersedes_id)
            requested = {
                "wing": wing,
                "first_scan_on": first_scan_on,
                "scan_interval_days": scan_interval_days,
                "policy": asdict(policy),
            }
            with self._store.transaction(), self._book.complete_history(wing=wing):
                entries = self._entries(wing)
                current = self._current(entries)
                if current and all(current[name] == value for name, value in requested.items()):
                    if supersedes_id not in (None, current["_id"], current["supersedes_id"]):
                        raise ProcedureError("schedule change requires latest supersedes_id")
                    return self._configuration(current)
                if supersedes_id != (current["_id"] if current else None):
                    raise ProcedureError("schedule change requires latest supersedes_id")
                material = {
                    **requested,
                    "supersedes_id": supersedes_id,
                    "evidence_ids": [supersedes_id] if supersedes_id is not None else [],
                }
                return self._configuration(self._save(_CONFIG, material, entries))
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ProcedureError("invalid practice review configuration") from exc

    def tick(self, *, wing: str, as_of: str | None = None) -> dict[str, Any]:
        """Run a bounded advisory scan; simulated clocks have separate durable cadence."""
        try:
            _text(wing, "wing")
            today = datetime.now(UTC).date().isoformat()
            when = today if as_of is None else as_of
            day = _practice_date(when, "as_of")
            simulated = when != today
            start = _lookback(day)
            with self._store.transaction(), self._book.complete_history(wing=wing):
                register = build_practice_register(self._view, wing=wing, as_of=when)
                entries = self._entries(wing)
                schedule = self._current(entries)
                if schedule is None:
                    raise ProcedureError("practice review is not configured")
                policy = PracticeReviewPolicy(**schedule["policy"])
                assessments = [
                    self._book.assess_review(
                        item.drawer_id,
                        period_start=start,
                        period_end=when,
                        as_of=when,
                        policy=policy,
                    )
                    for item in self._book.list(wing=wing)
                    if item.spec.governance is not None
                ]
                for assessment in assessments:
                    for key in (assessment.procedure_id, *assessment.evidence_ids):
                        self._source(key, wing)
                previous = [
                    entry
                    for entry in entries
                    if entry["_kind"] == _TICK
                    and entry["schedule_id"] == schedule["_id"]
                    and entry["simulated_clock"] is simulated
                ]
                last = previous[-1] if previous else None
                next_scan = last["next_scan_on"] if last else schedule["first_scan_on"]
                periodic = when >= next_scan
                if periodic:
                    next_scan = (day + timedelta(days=schedule["scan_interval_days"])).isoformat()
                proposals = []
                for assessment in assessments:
                    if not assessment.reasons:
                        continue
                    action, rationale = _advice(assessment)
                    refs = sorted(
                        {
                            schedule["_id"],
                            assessment.procedure_id,
                            assessment.root_id,
                            *assessment.evidence_ids,
                        }
                    )
                    material = {
                        "wing": wing,
                        "schedule_id": schedule["_id"],
                        "basis": _basis(assessment),
                        "suggested_action": action,
                        "rationale": rationale,
                        "evidence_ids": refs,
                        "supersedes_id": None,
                    }
                    saved = self._save(_PROPOSAL, material, entries)
                    proposals.append(
                        {
                            "proposal_id": saved["_id"],
                            "procedure_id": assessment.procedure_id,
                            "root_id": assessment.root_id,
                            "revision_sha256": assessment.revision_sha256,
                            "version": assessment.version,
                            "assessment": json.loads(_json(asdict(assessment))),
                            "suggested_action": action,
                            "rationale": rationale,
                            "evidence_ids": list(assessment.evidence_ids),
                        }
                    )
                legacy = [
                    row.current_id
                    for row in register.rows
                    if row.status == "active_governance_incomplete"
                ]
                basis = _hash(
                    {
                        "assessments": [_basis(value) for value in assessments],
                        "legacy_incomplete": legacy,
                    }
                )
                changed = last is None or last["input_sha256"] != basis
                if periodic or changed:
                    refs = sorted(
                        {
                            schedule["_id"],
                            *(proposal["proposal_id"] for proposal in proposals),
                            *(key for assessment in assessments for key in assessment.evidence_ids),
                        }
                    )
                    self._save(
                        _TICK,
                        {
                            "wing": wing,
                            "schedule_id": schedule["_id"],
                            "as_of": when,
                            "simulated_clock": simulated,
                            "next_scan_on": next_scan,
                            "proposal_ids": [proposal["proposal_id"] for proposal in proposals],
                            "input_sha256": basis,
                            "assessments": [
                                json.loads(_json(asdict(value))) for value in assessments
                            ],
                            "evidence_ids": refs,
                            "supersedes_id": None,
                        },
                        entries,
                    )
                for assessment in assessments:
                    for key in (assessment.procedure_id, *assessment.evidence_ids):
                        self._source(key, wing)
                report = {
                    "status": "scanned" if periodic or changed else "waiting",
                    "wing": wing,
                    "schedule_id": schedule["_id"],
                    "as_of": when,
                    "simulated_clock": simulated,
                    "next_scan_on": next_scan,
                    "proposals": proposals,
                    "legacy_incomplete": legacy,
                }
                report["rendered"] = _render(report)
                return report
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ProcedureError("practice review unavailable") from exc
