"""Run the full LongMemEval retrieval benchmark through Cairntir's public store API.

Each question gets a fresh, isolated store. Every haystack session becomes one
drawer holding all of its turns as ``role: content`` lines, the question is the
query, and ``DrawerStore.search`` ranks with its default settings. A question is
a hit at k when an evidence session (``answer_session_ids``) appears in the top
k. Abstention questions (ids ending in ``_abs``) have no evidence session and
are skipped, as in the LongMemEval paper's retrieval evaluation.

The script imports only ``cairntir`` and the standard library, so it runs
against a published wheel installed from PyPI as well as a source checkout.

Run (one line):

    python scripts/longmemeval_bench.py --dataset longmemeval_s_cleaned.json
        --home <empty folder> --out <results folder>

Results are appended to ``<out>/results.jsonl`` one question per line, so an
interrupted run continues where it stopped. ``<out>/summary.json`` is rewritten
at the end. ``--summarize <results.jsonl>`` recomputes the numbers from the
per-question file alone.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import sys
import time
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RANKS = (5, 10)
SEARCH_LIMIT = max(RANKS)


def sha256_file(path: Path) -> str:
    """Return the SHA-256 of ``path`` as lowercase hex."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def session_text(turns: Sequence[dict[str, Any]]) -> str:
    """Render one haystack session as the verbatim drawer content."""
    return "\n".join(f"{turn['role']}: {turn['content']}" for turn in turns)


def is_abstention(question: dict[str, Any]) -> bool:
    """Return whether LongMemEval marks this question as an abstention case."""
    return str(question["question_id"]).endswith("_abs")


def score_ranking(ranked: Sequence[str], evidence: Sequence[str]) -> dict[str, bool]:
    """Session-level hits for one question: any/all evidence in the top k."""
    wanted = set(evidence)
    scores: dict[str, bool] = {}
    for k in RANKS:
        top = set(ranked[:k])
        scores[f"any@{k}"] = bool(wanted & top)
        scores[f"all@{k}"] = wanted <= top
    return scores


def summarize(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-question rows into recall figures and counts."""
    evaluated = [row for row in rows if not row["skipped"]]
    summary: dict[str, Any] = {
        "questions_total": len(rows),
        "questions_evaluated": len(evaluated),
        "questions_skipped": len(rows) - len(evaluated),
        "skip_reasons": sorted({str(row["skip_reason"]) for row in rows if row["skipped"]}),
        "embedding_seconds_sum": round(sum(float(row["seconds"]) for row in rows), 3),
    }
    for k in RANKS:
        for kind in ("any", "all"):
            key = f"{kind}@{k}"
            hits = sum(1 for row in evaluated if row["scores"][key])
            summary[f"recall_{kind}_at_{k}"] = (
                round(hits / len(evaluated), 6) if evaluated else None
            )
            summary[f"hits_{kind}_at_{k}"] = hits
    by_type: dict[str, dict[str, int]] = {}
    for row in evaluated:
        bucket = by_type.setdefault(str(row["question_type"]), {"n": 0, "any@5": 0})
        bucket["n"] += 1
        bucket["any@5"] += int(bool(row["scores"]["any@5"]))
    summary["recall_any_at_5_by_type"] = {
        name: {"n": b["n"], "recall": round(b["any@5"] / b["n"], 6)}
        for name, b in sorted(by_type.items())
    }
    return summary


def read_rows(path: Path) -> list[dict[str, Any]]:
    """Read the per-question JSON-lines file."""
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _embedder(kind: str) -> Any:
    from cairntir.memory.embeddings import HashEmbeddingProvider, production_embedding_provider

    if kind == "hash":
        return HashEmbeddingProvider()
    return production_embedding_provider()


def _identity(embedder: Any) -> dict[str, Any]:
    import cairntir
    from cairntir.memory.embeddings import embedding_space_id

    identity: dict[str, Any] = {
        "cairntir_version": cairntir.__version__,
        "cairntir_location": str(Path(cairntir.__file__).resolve().parent),
        "embedding_space_id": embedding_space_id(embedder),
        "embedder_class": type(embedder).__name__,
        "model": getattr(embedder, "_model_name", None),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
    }
    manifest = getattr(embedder, "artifact_manifest", None)
    if callable(manifest):
        identity["model_artifacts"] = manifest()
    return identity


def run_question(question: dict[str, Any], embedder: Any, scratch: Path) -> dict[str, Any]:
    """Build one fresh store for ``question``, search it, and score the ranking."""
    from cairntir.memory.store import DrawerStore
    from cairntir.memory.taxonomy import Drawer

    base = {
        "question_id": question["question_id"],
        "question_type": question["question_type"],
        "evidence": list(question["answer_session_ids"]),
        "sessions": len(question["haystack_sessions"]),
    }
    if is_abstention(question):
        return {**base, "skipped": True, "skip_reason": "abstention", "seconds": 0.0}
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)
    started = time.perf_counter()
    session_by_drawer: dict[int, str] = {}
    with DrawerStore(scratch / "question.db", embedder) as store:
        for session_id, turns in zip(
            question["haystack_session_ids"], question["haystack_sessions"], strict=True
        ):
            stored = store.add(
                Drawer(wing="longmemeval", room="haystack", content=session_text(turns))
            )
            if stored.id is None:
                raise RuntimeError(f"store returned no id for session {session_id}")
            session_by_drawer[stored.id] = str(session_id)
        results = store.search(question["question"], wing="longmemeval", limit=SEARCH_LIMIT)
    seconds = time.perf_counter() - started
    shutil.rmtree(scratch)
    ranked = [session_by_drawer[int(drawer.id)] for drawer, _ in results if drawer.id is not None]
    return {
        **base,
        "skipped": False,
        "skip_reason": None,
        "ranked": ranked,
        "scores": score_ranking(ranked, base["evidence"]),
        "seconds": round(seconds, 3),
    }


def _questions(dataset: Path, limit: int | None) -> Iterator[dict[str, Any]]:
    """Yield questions in file order, releasing each one once it is consumed.

    The parsed LongMemEval_S file takes about 3 GB of memory; dropping each
    finished question keeps a five-hour run from holding all of it.
    """
    with dataset.open(encoding="utf-8") as handle:
        questions: list[dict[str, Any]] = json.load(handle)
    if limit is not None:
        del questions[limit:]
    questions.reverse()
    while questions:
        yield questions.pop()


def run(args: argparse.Namespace, command: str) -> dict[str, Any]:
    """Run (or continue) the benchmark and write the summary."""
    home: Path = args.home.resolve()
    if (home / "cairntir.db").exists():
        raise SystemExit(f"--home already holds a memory database: {home}")
    home.mkdir(parents=True, exist_ok=True)
    os.environ["CAIRNTIR_HOME"] = str(home)
    out: Path = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    results_path = out / "results.jsonl"
    done = {row["question_id"] for row in read_rows(results_path)}
    dataset_sha256 = sha256_file(args.dataset)
    embedder = _embedder(args.embedder)
    started_at = datetime.now(UTC).isoformat()
    started = time.perf_counter()
    count = 0
    with results_path.open("a", encoding="utf-8") as sink:
        for question in _questions(args.dataset, args.limit):
            count += 1
            if question["question_id"] in done:
                continue
            row = run_question(question, embedder, home / "scratch")
            sink.write(json.dumps(row, sort_keys=True) + "\n")
            sink.flush()
            if not row["skipped"]:
                print(
                    f"[{count}] {row['question_id']} any@5={row['scores']['any@5']} "
                    f"{row['seconds']}s",
                    flush=True,
                )
    rows = read_rows(results_path)
    summary = {
        "command": command,
        "dataset": str(args.dataset.resolve()),
        "dataset_sha256": dataset_sha256,
        "embedder": args.embedder,
        "limit": args.limit,
        "search": {"limit": SEARCH_LIMIT, "ranking": "DrawerStore.search defaults"},
        "drawer_unit": "one drawer per haystack session, turns as 'role: content' lines",
        "this_invocation_started_at": started_at,
        "this_invocation_wall_seconds": round(time.perf_counter() - started, 3),
        **_identity(embedder),
        **summarize(rows),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--dataset", type=Path, help="LongMemEval JSON file")
    parser.add_argument("--home", type=Path, help="empty folder used as CAIRNTIR_HOME")
    parser.add_argument("--out", type=Path, help="folder for results.jsonl and summary.json")
    parser.add_argument("--limit", type=int, default=None, help="only the first N questions")
    parser.add_argument("--embedder", choices=("production", "hash"), default="production")
    parser.add_argument("--summarize", type=Path, help="recompute numbers from results.jsonl")
    args = parser.parse_args(argv)
    if args.summarize is not None:
        print(json.dumps(summarize(read_rows(args.summarize)), indent=2))
        return 0
    if args.dataset is None or args.home is None or args.out is None:
        parser.error("--dataset, --home and --out are required unless --summarize is given")
    command = " ".join([Path(sys.executable).name, *sys.argv])
    summary = run(args, command)
    print(json.dumps({k: v for k, v in summary.items() if k != "model_artifacts"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
