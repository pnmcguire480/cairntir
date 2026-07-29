"""Read-only calibration reports over prediction-bound memory."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from cairntir.contracts import Store
from cairntir.memory.consolidate import detect_contradictions


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    """Empirical outcome quality for one wing."""

    wing: str
    predictions: int
    resolved: int
    confirmed: int
    failed: int
    unresolved: int
    success_rate: float | None
    confidence_low: float | None
    confidence_high: float | None
    mean_prediction_belief_mass: float | None
    contradictions: int
    outcomes_by_room: dict[str, int]


def calibration_report(store: Store, *, wing: str) -> CalibrationReport:
    """Aggregate resolved and unresolved prediction-bound drawers."""
    drawers = store.list_by(wing=wing, limit=100_000)
    predictions = [
        drawer
        for drawer in drawers
        if drawer.predicted_outcome is not None and drawer.observed_outcome is None
    ]
    observations = [
        drawer
        for drawer in drawers
        if drawer.observed_outcome is not None and isinstance(drawer.metadata.get("success"), bool)
    ]
    resolved_prediction_ids = {
        drawer.supersedes_id for drawer in observations if drawer.supersedes_id is not None
    }
    unresolved = sum(
        1
        for drawer in predictions
        if drawer.id is not None and drawer.id not in resolved_prediction_ids
    )
    confirmed = sum(1 for drawer in observations if drawer.metadata["success"] is True)
    failed = len(observations) - confirmed
    rate = confirmed / len(observations) if observations else None
    low, high = _wilson_interval(confirmed, len(observations))
    prediction_by_id = {drawer.id: drawer for drawer in predictions if drawer.id is not None}
    masses = [
        prediction_by_id[prediction_id].belief_mass
        for prediction_id in resolved_prediction_ids
        if prediction_id in prediction_by_id
    ]
    rooms = Counter(drawer.room for drawer in observations)
    return CalibrationReport(
        wing=wing,
        predictions=len(predictions),
        resolved=len(observations),
        confirmed=confirmed,
        failed=failed,
        unresolved=unresolved,
        success_rate=rate,
        confidence_low=low,
        confidence_high=high,
        mean_prediction_belief_mass=sum(masses) / len(masses) if masses else None,
        contradictions=len(detect_contradictions(store, wing=wing)),
        outcomes_by_room=dict(sorted(rooms.items())),
    )


def render_calibration(report: CalibrationReport) -> str:
    """Render a compact, layperson-readable calibration dashboard."""
    if report.success_rate is None:
        rate = "not enough resolved predictions"
        interval = "not available"
    else:
        rate = f"{report.success_rate:.1%}"
        interval = (
            f"{report.confidence_low:.1%}-{report.confidence_high:.1%}"
            if report.confidence_low is not None and report.confidence_high is not None
            else "not available"
        )
    mass = (
        f"{report.mean_prediction_belief_mass:.2f}"
        if report.mean_prediction_belief_mass is not None
        else "not available"
    )
    rooms = (
        ", ".join(f"{room}={count}" for room, count in report.outcomes_by_room.items()) or "none"
    )
    return "\n".join(
        (
            f"# Cairntir calibration — wing={report.wing!r}",
            f"- prediction drawers: {report.predictions}",
            f"- resolved observations: {report.resolved}",
            f"- confirmed / failed: {report.confirmed} / {report.failed}",
            f"- unresolved predictions: {report.unresolved}",
            f"- empirical success rate: {rate}",
            f"- 95% uncertainty interval: {interval}",
            f"- mean prediction belief mass: {mass}",
            f"- contradictions surfaced: {report.contradictions}",
            f"- resolved outcomes by room: {rooms}",
        )
    )


def _wilson_interval(successes: int, total: int) -> tuple[float | None, float | None]:
    if total == 0:
        return None, None
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1.0 + z**2 / total
    centre = proportion + z**2 / (2.0 * total)
    spread = z * math.sqrt(proportion * (1.0 - proportion) / total + z**2 / (4.0 * total**2))
    return (centre - spread) / denominator, (centre + spread) / denominator
