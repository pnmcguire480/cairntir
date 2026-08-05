from __future__ import annotations

from pathlib import Path

import pytest

from cairntir.calibration import calibration_report, render_calibration
from cairntir.mcp.backend import CairntirBackend
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer


def test_calibration_counts_resolved_unresolved_and_uncertainty(tmp_path: Path) -> None:
    with DrawerStore(
        tmp_path / "calibration.db",
        HashEmbeddingProvider(dimension=16),
    ) as store:
        for index, success in enumerate((True, True, False), start=1):
            prediction = store.add(
                Drawer(
                    wing="cairntir",
                    room="predictions",
                    content=f"prediction {index}",
                    claim="the build remains green",
                    predicted_outcome="tests pass",
                )
            )
            store.add(
                Drawer(
                    wing="cairntir",
                    room="predictions",
                    content=f"observation {index}",
                    claim="the build remains green",
                    predicted_outcome="tests pass",
                    observed_outcome="tests pass" if success else "tests fail",
                    supersedes_id=prediction.id,
                    metadata={"success": success},
                )
            )
        store.add(
            Drawer(
                wing="cairntir",
                room="predictions",
                content="still waiting",
                claim="the next release remains green",
                predicted_outcome="tests pass",
            )
        )

        report = calibration_report(store, wing="cairntir")

    assert report.predictions == 4
    assert report.resolved == 3
    assert report.confirmed == 2
    assert report.failed == 1
    assert report.unresolved == 1
    assert report.success_rate == pytest.approx(2 / 3)
    assert report.confidence_low is not None
    assert report.confidence_high is not None
    assert report.confidence_low < report.success_rate < report.confidence_high
    assert report.contradictions >= 1
    rendered = render_calibration(report)
    assert "66.7%" in rendered
    assert "unresolved predictions: 1" in rendered


def test_calibration_denominator_moves_after_a_settle(tmp_path: Path) -> None:
    """MCP settlements must reach calibration (defect B).

    ``settle`` used to write no ``metadata["success"]``, so every prediction
    settled through the MCP surface was invisible to the report and the
    success rate stayed ``None`` forever. The verdict derivable from the
    delta contract — no delta means the prediction held — is now persisted
    in the same field the reason loop has always used.
    """
    with DrawerStore(
        tmp_path / "settle-calibration.db",
        HashEmbeddingProvider(dimension=16),
    ) as store:
        backend = CairntirBackend(store)
        backend.remember(
            wing="cairntir",
            room="predictions",
            content="the seam fix lands green",
            predicted_outcome="the gate stays green",
        )

        before = calibration_report(store, wing="cairntir")
        assert before.resolved == 0
        assert before.success_rate is None

        backend.settle(drawer_id=1, observed_outcome="the gate stayed green")

        after = calibration_report(store, wing="cairntir")

    assert after.resolved == 1
    assert after.confirmed == 1
    assert after.failed == 0
    assert after.unresolved == 0
    assert after.success_rate == 1.0
