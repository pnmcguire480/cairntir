"""Original D16 legacy-to-configured manual admission budget workflow."""

from . import oracles
from .fixture import Harness, Model


def item(wing="alpha", content="Exact source Ω: a retry failed; inspect this evidence.", **kw):
    return {"wing": wing, "content": content, **kw}


def retained_one_shot_and_budget(r):
    with Model(r.root) as model:
        ids = r.seed(item("alpha"), item("beta"))
        r.cli(
            "dream",
            "enable",
            "--scope",
            "all-local",
            "--model",
            "acceptance-synthetic",
            "--endpoint",
            model.endpoint,
        )
        first = r.cli("dream", "tick", "--max-wings", "1", "--timeout-seconds", "2")
        assert first["schema"] == "cairntir.dream-tick.v1" and first["status"] == "candidate"
        assert len(model.calls) == 1
        oracles.source_bindings(r.cli("dream", "candidate", first["candidate_id"]), [ids[0]])
        r.configure(
            poll_seconds=0.2,
            review_seconds=120,
            retry_seconds=1,
            inference_seconds=2,
            max_calls=1,
            window_seconds=8,
            max_pending=8,
        )
        second = r.cli("dream", "tick", "--timeout-seconds", "2")
        assert second["status"] == "candidate"
        r.seed(item("gamma", "Another eligible wing remains due during the manual call budget."))
        blocked = r.cli("dream", "tick", "--timeout-seconds", "2")
        assert blocked["status"] == "no_work" and len(model.calls) == 2
        assert r.status()["controller"]["requests_in_window"] == 1


def test_retained_one_shot_and_budget(tmp_path):
    run = Harness(tmp_path / "evidence")
    try:
        retained_one_shot_and_budget(run)
    finally:
        run.cleanup()
