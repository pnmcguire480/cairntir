# LongMemEval retrieval benchmark

This is the first full LongMemEval run, measured for roadmap item C50 on 12 November 2026.
C50 stays **open**. It also needs an independent clean-machine reproduction by
someone else, and two parts of its original wording are not met (see
[Limits](#limits)).

## Result

| Measure (session level, 470 questions) | Value |
| --- | --- |
| R@5, any evidence session in the top 5 | **96.38%** (453/470) |
| R@5, all evidence sessions in the top 5 | 87.02% (409/470) |
| R@10, any | 97.87% (460/470) |
| R@10, all | 93.83% (441/470) |

R@5 (any) by question type: knowledge-update 100% (72), multi-session 99.17%
(121), single-session-assistant 100% (56), single-session-preference 93.33%
(30), single-session-user 93.75% (64), temporal-reasoning 92.13% (127).

This number was not tuned. All settings were written down before the full run
and were not changed after the results came in.

## What was measured

- **Software:** Cairntir 1.13.0, installed from PyPI into its own virtual
  environment (not a source checkout), Python 3.12.14, Windows 10.
- **Embedder:** the production embedder `jinaai/jina-embeddings-v2-small-en`
  (FastEmbed, ONNX), embedding space
  `fastembed/text-embedding-v2/sha256=ec062705e326bcb995eb8eb7b4ab5f3e128482809c05a58d595081ef0e9a5372`.
- **Dataset:** LongMemEval_S cleaned, `longmemeval_s_cleaned.json` from the
  MIT-licensed Hugging Face dataset `xiaowu0162/longmemeval-cleaned`, 277,383,467
  bytes, SHA-256
  `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`.
- **Denominator:** all 500 questions were processed. The 30 abstention
  questions (`_abs`) have no evidence session and are skipped, so recall is
  over 470.
- **Method:** each question gets a fresh, isolated store. Every haystack session
  (38 to 62 per question) becomes one drawer, with its turns as `role: content`
  lines. The question is the query, and `DrawerStore.search` ranks with its
  default settings.
- **Run time:** 13,197 seconds (3 h 40 min) wall clock on a 16-thread desktop,
  about 28 seconds per question. Other jobs were sharing the machine.
- **Control:** a deliberately non-semantic embedder (`--embedder hash`) scores
  6/30 R@5 on the first 30 questions. The production embedder scores 28/30 on
  the same 30, so the benchmark does tell a bad retriever from a good one.

Command, run from the folder that holds the dataset:

```bash
python -I scripts/longmemeval_bench.py --dataset longmemeval_s_cleaned.json --home c50-home --out c50-out
```

`--summarize c50-out/results.jsonl` recomputes every figure from the
per-question file alone. For this run the recomputed figures match the summary
exactly.

## Limits

- **Retrieval only.** LongMemEval also scores question answering: a reader
  model answers from what was retrieved, and a judge model grades the answer.
  That half was not run, because it needs a reader and a judge model that are
  not available here without a new dependency or a paid API.
- **Belief masses.** C50's original wording asks for "production-calibrated
  belief masses rather than fixture beliefs". Every fresh store holds only the
  default mass (1.0) that writes receive, so the belief reranker cannot change
  any ranking in this run. A haystack has no settled predictions or retrieval
  history to calibrate from.
- **Not independent.** The person who wrote the script also ran it. The
  independent half of C50 is the outside reproduction.
- LongMemEval_M (2.7 GB, about 500 sessions per question) was not run.

## Reproduction tolerance

An outside run reproduces this result when it uses the same command, the same
dataset SHA-256 and Cairntir 1.13.0, and its `hits_any_at_5` is within 5 of
453. This tolerance was set before the full result was known. Different
processors and ONNX builds can flip close rankings.
