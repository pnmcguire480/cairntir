"""Original pure receipt/status/source-binding oracles used by D16."""

from datetime import datetime


def timestamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert result.tzinfo is not None, value
    return result.timestamp()


def status(value):
    assert value["schema"] == "cairntir.dream-status.v1"
    c = value["controller"]
    required = {
        "running",
        "controller_id",
        "pid",
        "state",
        "config",
        "last_run",
        "next_run_at",
        "queued_jobs",
        "deferred_wings",
        "foreground_active",
        "requests_in_window",
        "budget_resets_at",
        "active_inference",
    }
    assert required <= c.keys(), required - c.keys()
    assert type(c["running"]) is bool and type(c["foreground_active"]) is bool
    assert c["state"] in {"stopped", "idle", "running", "foreground", "budget_wait", "model_wait"}
    for name in ("queued_jobs", "deferred_wings", "requests_in_window"):
        assert type(c[name]) is int and c[name] >= 0
    assert c["queued_jobs"] <= c["config"]["max_pending"]
    assert c["requests_in_window"] <= c["config"]["max_calls"]
    if c["running"]:
        assert type(c["pid"]) is int and c["pid"] > 0 and c["controller_id"]
    else:
        assert c["pid"] is None and c["controller_id"] is None
    if c["active_inference"] is not None:
        active = c["active_inference"]
        assert {"attempt_id", "pid", "started_at"} <= active.keys()
        assert active["attempt_id"] and type(active["pid"]) is int and active["pid"] > 0
        assert active["pid"] != c["pid"]
        timestamp(active["started_at"])
    if c["last_run"] is not None:
        receipts({"schema": "cairntir.dream-controller-receipts.v1", "receipts": [c["last_run"]]})
    if c["next_run_at"] is not None:
        timestamp(c["next_run_at"])
    return c


def receipts(value):
    assert value["schema"] == "cairntir.dream-controller-receipts.v1"
    rows = value["receipts"]
    required = {
        "receipt_id",
        "job_id",
        "attempt_id",
        "controller_id",
        "wing",
        "reason",
        "evidence_ids",
        "status",
        "candidate_id",
        "started_at",
        "finished_at",
        "next_run_at",
        "error",
        "uncertain",
    }
    assert len({r["receipt_id"] for r in rows}) == len(rows)
    attempts = [r["attempt_id"] for r in rows if r["attempt_id"] is not None]
    assert len(set(attempts)) == len(attempts), "attempt IDs reused"
    previous = float("-inf")
    for r in rows:
        assert required <= r.keys(), required - r.keys()
        assert r["status"] in {"candidate", "no_work", "model_unavailable", "interrupted"}
        assert r["reason"] in {"new_evidence", "periodic_review", "retry", "empty"}
        assert type(r["uncertain"]) is bool
        started, finished = timestamp(r["started_at"]), timestamp(r["finished_at"])
        assert started <= finished and previous <= finished
        previous = finished
        assert r["next_run_at"] is not None
        assert timestamp(r["next_run_at"]) >= finished
        assert len(r["evidence_ids"]) <= 6
        assert len(set(r["evidence_ids"])) == len(r["evidence_ids"])
        if r["reason"] != "empty":
            assert r["job_id"] and r["attempt_id"] and r["controller_id"] and r["wing"]
        if r["status"] == "candidate":
            assert r["candidate_id"] and r["evidence_ids"]
        else:
            assert r["candidate_id"] is None
        if r["status"] in {"model_unavailable", "interrupted"}:
            assert r["error"]
    return rows


def source_bindings(candidate, expected):
    assert candidate["schema"] == "cairntir.dream-candidate.v1"
    assert candidate["status"] == "pending"
    assert set(candidate["evidence_ids"]) == set(expected)
