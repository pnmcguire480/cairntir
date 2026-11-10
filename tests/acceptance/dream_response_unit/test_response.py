"""Actual worker response bounds through the public Dream CLI."""

import pytest

from . import fixture as H  # noqa: N812 - Preserve the original test's helper binding.


@pytest.fixture
def harness(tmp_path):
    run = H.Harness(tmp_path / "evidence")
    try:
        run.seed()
        yield run
    finally:
        run.cleanup()


@pytest.mark.parametrize("mode", ["malformed", "oversized", "invalid-proposals", "redirect"])
def test_actual_controller_response_bounds(harness, mode):
    r = harness
    sink_root = r.root / "sink"
    sink_root.mkdir()
    with H.Model(sink_root) as sink, H.Model(r.root, mode) as model:
        model.redirect = sink.endpoint + "/must-not-receive-evidence"
        r.enable(model.endpoint, configured=True, timeout=2.5)
        before = r.snapshot()
        result = r.cli("tick", "--timeout-seconds", "3")
        assert result["status"] == "model_unavailable"
        assert len(model.calls) == 1 and not sink.calls
        receipts = r.cli("receipts", "--limit", "100")["receipts"]
        failures = [row for row in receipts if row["status"] == "model_unavailable"]
        assert len(failures) == 1 and failures[0]["attempt_id"] and failures[0]["error"]
        assert r.candidates() == 0 and r.snapshot() == before
        assert r.cli("status")["controller"]["requests_in_window"] == 1
