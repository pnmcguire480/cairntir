# LongMemEval submission — draft

**Target:** [LongMemEval benchmark](https://github.com/xiaowu0162/LongMemEval)

## What LongMemEval measures

A set of multi-session memory-recall questions designed to test
whether an assistant retains information across sessions. The
headline metric is **Recall@5** on the single-session-user split:
does the true relevant drawer land in the top-5 retrieval hits?

MemPalace (the predecessor we borrowed concepts from) hit **96.6%
R@5**. That's our north star.

## Where Cairntir stands today

- `tests/eval/test_longmemeval_subset.py` runs a hand-curated
  paraphrased subset with sentence-transformers (`all-MiniLM-L6-v2`).
  The fail-on-regression bar is **80% R@5**, which the suite passes.
- The test suite is gated behind `pytest -m eval` and runs in a
  dedicated CI job so main cannot merge with a regression.
- The subset is deliberately small (10 question/drawer pairs + 15
  distractors). Enough to catch regressions, not enough to match
  the published benchmark.

## What a real submission requires

1. **Full LongMemEval dataset.** Clone the official repo, download
   their test set from the release page, place it under
   `tests/eval/data/` (gitignored — too big to commit, licensed
   separately anyway).
2. **Run Cairntir's retriever over the full test set.** The
   existing test file is the scaffold; point it at
   `tests/eval/data/` instead of the inline fixture.
3. **Report R@5, R@10, and latency.** Latency matters — a memory
   system that takes 5 seconds per query is not usable even if it
   scores 99%.
4. **Write a short methodology section** describing our embedder,
   rerank settings, and any pre-processing.
5. **Compare head-to-head with MemPalace** on the same test set.
   We borrowed their taxonomy; the honest thing is to report where
   we win, where we lose, and where we draw.

## Preliminary hypothesis

- We **should** win on questions where `supersedes_id` matters —
  questions that depend on "what was the last word on X" rather
  than "has X been mentioned at all."
- We **might** win on questions where `belief_mass` matters — a
  repeated fact from a well-used drawer should outrank a random
  mention in a distractor.
- We **might** lose on questions where the signal is purely lexical
  and MemPalace's retrieval happens to match the dataset
  distribution better.

These are falsifiable — which is the whole v0.2 point.

## Submission format

LongMemEval accepts submissions via pull request to the benchmark
repo. The PR adds a row to the leaderboard table with:

- Method name: `Cairntir v1.x`
- Embedder: `all-MiniLM-L6-v2` (same as MemPalace baseline; level
  the comparison field)
- Reranker: belief-mass + delta-boost (Cairntir-specific, describe
  in the methodology note)
- R@5 / R@10 / median latency
- Link to this repo + the specific commit hash that produced the
  numbers
- MIT license reminder

## Before submitting

- [ ] Finish v1.2 (production Reason loop) so the reranker has
      production-calibrated belief masses rather than fixtures
- [ ] Run the full dataset, not just the subset, end-to-end
- [ ] Independent reproduction: someone else on a clean machine
      can clone the repo, run `pytest -m longmemeval_full`, and
      get the same numbers within a reasonable tolerance

## Why this matters

Two reasons, neither of them ego:

1. **Honest benchmarking pressures the design.** If we claim the
   prediction-bound schema and belief rerank are improvements, a
   head-to-head on a public benchmark either proves it or forces
   us to rethink.
2. **Visibility on the leaderboard drives adoption.** Solo
   developers evaluating memory systems Google the benchmark.
   Being on the leaderboard makes Cairntir discoverable in a
   context where the reader is already sold on the problem.

## Notes

Do not overclaim in the submission. If we score 75% R@5 on the
real dataset, submit 75%. MemPalace got 96.6% through deliberate
optimization over many iterations; matching that is a v1.x goal,
not a v1.1 one.
