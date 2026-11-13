"""Behavior of the LongMemEval benchmark script used for C50 reproduction."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "longmemeval_bench.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("longmemeval_bench", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bench = _load()


def _question(qid: str, *, evidence: list[str], query: str) -> dict[str, Any]:
    sessions = {
        "s-garden": [
            {"role": "user", "content": "I planted heirloom tomatoes along the south fence."},
            {"role": "assistant", "content": "South-facing beds get the most sun."},
        ],
        "s-truck": [
            {"role": "user", "content": "My truck failed inspection on the oxygen sensor."},
        ],
        "s-bread": [
            {"role": "user", "content": "The sourdough starter needs feeding twice a day."},
        ],
    }
    return {
        "question_id": qid,
        "question_type": "single-session-user",
        "question": query,
        "answer_session_ids": evidence,
        "haystack_session_ids": list(sessions),
        "haystack_sessions": list(sessions.values()),
    }


def test_score_ranking_distinguishes_any_from_all() -> None:
    ranked = ["a", "b", "c", "d", "e", "f"]
    scores = bench.score_ranking(ranked, ["b", "f"])
    assert scores["any@5"] is True
    assert scores["all@5"] is False
    assert scores["all@10"] is True
    assert bench.score_ranking(ranked, ["z"])["any@10"] is False


def test_abstention_questions_are_skipped_and_left_out_of_recall(tmp_path: Path) -> None:
    from cairntir.memory.embeddings import HashEmbeddingProvider

    question = _question("q1_abs", evidence=[], query="anything")
    row = bench.run_question(question, HashEmbeddingProvider(), tmp_path / "scratch")
    assert row["skipped"] is True
    assert row["skip_reason"] == "abstention"
    summary = bench.summarize([row])
    assert summary["questions_total"] == 1
    assert summary["questions_evaluated"] == 0
    assert summary["recall_any_at_5"] is None


def test_run_question_maps_ranked_drawers_back_to_session_ids(tmp_path: Path) -> None:
    from cairntir.memory.embeddings import HashEmbeddingProvider

    question = _question(
        "q2", evidence=["s-truck"], query="My truck failed inspection on the oxygen sensor."
    )
    row = bench.run_question(question, HashEmbeddingProvider(), tmp_path / "scratch")
    assert row["skipped"] is False
    assert sorted(row["ranked"]) == ["s-bread", "s-garden", "s-truck"]
    assert row["scores"]["any@5"] is True
    assert not (tmp_path / "scratch").exists()


def test_summarize_recomputes_from_results_file(tmp_path: Path) -> None:
    rows = [
        {
            "question_id": f"q{i}",
            "question_type": "temporal-reasoning" if i % 2 else "single-session-user",
            "skipped": False,
            "skip_reason": None,
            "seconds": 1.0,
            "scores": bench.score_ranking(["x", "y"], ["x"] if i < 3 else ["nope"]),
        }
        for i in range(4)
    ]
    path = tmp_path / "results.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    summary = bench.summarize(bench.read_rows(path))
    assert summary["hits_any_at_5"] == 3
    assert summary["recall_any_at_5"] == 0.75
    assert summary["recall_any_at_5_by_type"]["temporal-reasoning"] == {"n": 2, "recall": 0.5}


def test_run_refuses_a_home_that_already_holds_a_memory_database(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "cairntir.db").write_bytes(b"")
    dataset = tmp_path / "data.json"
    dataset.write_text("[]", encoding="utf-8")
    with pytest.raises(SystemExit, match="already holds a memory database"):
        bench.main(["--dataset", str(dataset), "--home", str(home), "--out", str(tmp_path / "o")])
