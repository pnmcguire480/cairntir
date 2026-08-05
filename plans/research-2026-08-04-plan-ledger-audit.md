# Plan ledger audit — every plan, compared against each other and against `main`

**Date:** 2026-08-04 · **Status:** research only. Nothing here is committed or implemented.
**Method:** all 17 files in `plans/` read in full; every load-bearing claim below was
re-verified against `origin/main` at `4483c96` (PR #42) with `git grep` / `git ls-tree` /
direct source reads — not taken from the plans' own status lines.
**Companion:** `plans/2026-08-04-ultimate-improvement-plan.md` (the execution plan built
from these findings).

---

## 1. Repository state at audit time

| Fact | Value | Verified |
|---|---|---|
| `origin/main` | `4483c96` — Merge PR #42 (wing-resolution docs) | `git fetch` + `git log` |
| local `main` | `0af5cbb` — **2 commits behind** `origin/main` | `rev-list --left-right --count` = 0 / 2 |
| primary checkout | on `feat/qwen-host` @ `b364338` (1 commit ahead of local main) | `git status` |
| open PR | **#43** — `feat(hosts): add Qwen Code as a fourth supported host` | `gh pr list` |
| untracked plan files | this audit's inputs: `2026-08-05-seams-cost-and-the-real-test.md`, `agents-library-routing.md`, `cairntir-improvement-plan-2026-08-04.md` | `git status` |
| local branches | `feat/cost-accounting`, `feat/handoff`, `feat/landed-commitments` — **fully merged** into `origin/main` (zero unique commits each) | `git log origin/main..<branch>` = empty |
| worktrees | 3 under `.claude/worktrees/` at `a004188` (vault-sync), `03943df` (model-provenance merge), `5370dfe` (handoff open predictions) — all three commits are on `origin/main` via PRs #34/#36/#37 | `git worktree list` |

So: nothing is stranded on branches. The only unmerged code is PR #43 (Qwen host),
which is based on the **pre-#42** main and needs a rebase before merge.

---

## 2. The 17 plans, classified

### Historical — delivered, keep as evidence

| Plan | Delivered in | Note |
|---|---|---|
| `purrfect-drifting-sparrow.md` | v0.1 bootstrap | The original repo plan. Everything in it shipped or evolved. |
| `v1.1-synergy-stack.md` | v1.1 | `cross_recall` ✅ (backend.py:307), reason loop ✅ (`reason_cmd` cli.py:796, `production/` package), recipe runtime ✅ (`recipe list` / `recipe run`). Its deferred calibration dashboard later shipped (`calibration.py`). |
| `v1.2-foundation-hardening.md` | v1.2 | Workstreams 0–5 shipped. **But two commitments from its source audit did not land with v1.2**: context budget (landed later, PR #35) and holdout evals (**still absent** — see §4 item H). |
| `release-1.3.0.md` | v1.3.0 | Shipped. Its two deliberate exclusions (embedder change, `session_start` narrowing) remain open and gated. |
| `2026-08-04-handoff-prompt.md` | n/a | Onboarding artifact for the honest-and-whole run. Historical. |

### Active ledgers — partially complete

| Plan | Landed | Still open |
|---|---|---|
| `2026-08-04-honest-and-whole.md` | P0 (anchors 11.2% → 52.1%, 7 unmapped wings resolved by PR #42), P1 all 5 items (PRs #35/#37/#40), P2 both items (PRs #35/#41) | **P3 — CodeGlass companion-first (§4 item I)** |
| `2026-08-05-completion.md` | items 1–2 (reattest PR #40, write-guard PR #41) and item 6 (`cairntir --version` exists on main — cli.py:137) | item 3 (P3 CodeGlass), item 4 (embedder bake-off — **Patrick-gated**), **item 5 (PyPI presence check — §3 defect D)** |
| `2026-08-05-seams-cost-and-the-real-test.md` | nothing — *"Nothing here has landed"* still true | **all of P4–P8; P9 = carried P3 (§§3–4)** |
| `cairntir-improvement-plan-2026-08-04.md` (the "big" plan) | Phase 0 partially stale-but-resolving: PR #42 merged, Qwen work became PR #43 | Phases 1–6 entirely open; hygiene lane mostly open (§4 item J) |

### Research / proposal documents — inputs, not commitments

`field-report-2026-08-02.md` · `research-2026-08-02-upgrade-candidates.md` ·
`research-2026-08-02-trends-and-practical-upgrades.md` · `next-map.md` ·
`signal-reader.md` · `codeglass-recovery.md` · `evolving-mind.md` ·
`agents-library-routing.md`. Findings extracted into §3 and §4 below.

---

## 3. Verified LIVE defects on `origin/main` (fix targets, not features)

**Defect A — settled predictions stay "open" forever (the seam).**
`CairntirBackend.settle` (backend.py:171) closes a prediction by **appending** an
observation drawer with `supersedes_id=drawer_id` and deliberately leaves the
original's `observed_outcome` = None (backend.py:232-234). `is_open_prediction`
(handoff.py:398) decides openness from the drawer's own fields only — its docstring
even says *"Revisit this if the reason-loop shape ever becomes the common way
predictions are written; today it is not"* — but PR #35 made that shape the **only**
sanctioned settlement path. Verified absent on `origin/main`: `settled_prediction_ids`,
`tests/integration/test_seams.py`, `scripts/check_seams.py`. Consequence: the open-
prediction count can only grow; handoff will report "40 open" when all 40 are closed,
and it spends handoff budget (10% reserve) on predictions that are not open.
**This is a speed and a correctness defect at once.**

**Defect B — calibration can never see MCP settlements.**
`calibration.py:42` counts only observations whose `metadata["success"]` is a boolean.
`settle` (backend.py) never writes that field. So every prediction settled through the
MCP surface is invisible to `cairntir_calibration`; the success rate stays `None`
forever unless a Reason-loop recipe writes the field by hand.

**Defect C — branched lineage silently picks the lowest-ID child.**
`temporal._find_child` (temporal.py:119-143): when two drawers supersede the same
parent, it returns the lowest id — deterministic, but it **hides the sibling branch**
from `walk_supersedes` and `as_of`. The improvement plan's gap #2, confirmed still
present in source.

**Defect D — release gate checks tags, not PyPI presence.**
`scripts/check_release_tags.py` mentions PyPI only in its docstring/history comments
(lines 7, 41); it verifies a tag exists, never that the tag published. This is the
exact class of miss that hid v1.1.1 and v1.1.3. Completion-backlog item 5, still open.

**Defect E — two CI gates are decorative.**
`check_store_health.py` exits 0 with `SKIP: no store at this location` on a runner
that has no `cairntir.db`; `vault-sync --check` same shape with the vault. Both have
never been capable of failing in CI. Their unit tests do run on every push, so the
mechanisms are tested — the CI *steps* are the theatre. P5 in the seams plan.

---

## 4. Qualifying features NOT implemented (the master list)

Every entry below was checked against `origin/main @ 4483c96`. "Qualifying" = still
wanted by at least one active plan or by Patrick's recorded rulings, and not superseded.

### Group A — Correctness & seams (highest priority; from seams plan P4–P5, big plan Phase 1–2)

| # | Feature | Source | Verified state |
|---|---|---|---|
| A1 | Fix the settle↔handoff seam (`settled_prediction_ids`, one wing scan) | seams P4.1 | absent |
| A2 | The seam test: `remember(predicted) → settle → handoff → count == 0` | seams P4.2 | absent — `tests/integration/` holds 3 files, no `test_seams.py` |
| A3 | Paired tests for the other 3 seams (write-guard↔health rule 3; `parse_anchors`↔`recall_for_change`; vault `--check`↔`apply_sync`) | seams P4.3 | absent |
| A4 | `scripts/check_seams.py` registry | seams P4.4 | absent |
| A5 | Calibration reads settlements (defect B) — one shared settlement projection, or settle writes an explicit verdict | big plan 1A/2A | absent |
| A6 | Branch-aware lineage; no silent lowest-ID winner (defect C) | big plan 2B | absent |
| A7 | Atomic idempotent settlement (`operation_id`, `expected_leaf_id`) | big plan 2C | absent — `settle`/`remember` have no operation key (only CodeGlass tools take `idempotency_key`) |
| A8 | Snapshot/freshness receipt on handoff; `based_on` staleness detection | big plan Phase 3 | absent |

### Group B — Gates that guard where the data lives (seams P5, completion #5)

| # | Feature | Source | Verified state |
|---|---|---|---|
| B1 | `cairntir doctor --gate` (store health + vault drift where a real store exists) | seams P5 | `doctor` exists (cli.py:167) but has **no `--gate` flag** |
| B2 | Make the two CI skips loud (or delete the steps) | seams P5 | still silent-skip |
| B3 | PyPI-presence release gate (defect D) | completion #5 | absent |

### Group C — Read-path speed & cost (field report, trends doc, P7)

| # | Feature | Source | Verified state |
|---|---|---|---|
| C1 | `recall` returns **full content for top-k hits** (kills the stub→get round trip) | field report finding 2 | absent — recall still emits snippet stubs (backend.py:801-804) |
| C2 | `get` with opt-in/out provenance (`fields`) | field report finding 2 | absent |
| C3 | Widen `cairntir cost` beyond Cairntir's own payload | seams P7 | absent (cost.py measures Cairntir payload only) |
| C4 | Cacheable / progressively-disclosed tool catalog (MCP 2026-07-28) | candidates #6 | absent |

### Group D — The acceptance test (P8, candidates #8, evolving-mind item 8)

| # | Feature | Source | Verified state |
|---|---|---|---|
| D1 | Holdout harness: fixed questions with known-correct drawer ids | seams P8 / candidates #8 | absent — no `evals/` dir, no `src/cairntir/evals/`, 0 holdout files (as #212 first reported) |
| D2 | Weak-model run of the acceptance test | Patrick's North Star | never executed |
| D3 | Knowledge-update metric over `supersedes_id` chains (benchmark mismatch) | candidates #9 | absent |

### Group E — Prediction-loop adoption (seams P6, field report finding 4)

| # | Feature | Source | Verified state |
|---|---|---|---|
| E1 | Measure `delta` writes since settle landed; if zero, make the write path ask (tool-description nudge, same shape as the anchor fix) | seams P6 | unmeasured as of this audit; store had `delta` 0/275 on 2026-08-04 (drawer #276) and 0/286 in the 08-04 audit (big plan §2) |
| E2 | MCP elicitation for predictions at decision time | candidates #4 | absent |
| E3 | `cairntir review signals` monthly settle cycle | signal-reader phase 3 | absent (settle covers the mechanics; no review command) |

### Group F — Retrieval quality (field report finding 3, trends doc)

| # | Feature | Source | Verified state |
|---|---|---|---|
| F1 | Two-cause ranking experiment (drawer size vs embedder truncation) | trends #2 | not run |
| F2 | Embed-time chunking of long drawers | trends #5 | **gated — requires live reindex, Patrick present** |
| F3 | Embedder bake-off (nomic / Qwen3-0.6B vs MiniLM) | trends #1, completion #4 | **gated — live reindex, Patrick present** |

### Group G — CodeGlass companion-first (honest-and-whole P3, seams P9, big plan Phase 6, codeglass-recovery)

| # | Feature | Verified state |
|---|---|---|
| G1 | The seam: CodeGlass through the public `Store` protocol only, removable | absent — `codeglass.py` lives inside `src/cairntir/` |
| G2 | Emergent pattern discovery from the vault link graph | absent — grep of `vault.py` / `obsidian.py` / `codeglass.py` finds no link/graph handling (only `Path.unlink()`) |
| G3 | Host-side deterministic evidence collector | absent (codeglass-recovery "pending") |
| G4 | Learner holdout study | absent |
| G5 | Standalone packaging | explicitly second; `codeglass-site`/`codeglass-dist` parent question still Patrick's |

### Group H — Unbuilt backlog from research docs & older plans

| # | Feature | Source | Verified state |
|---|---|---|---|
| H1 | Wing glossary drawer convention (identity-layer, supersede-not-edit) | next-map Track B | absent — `glossary` exists only as a CodeGlass field |
| H2 | Staleness flagging | next-map Track A | **ON HOLD by Patrick's ruling** — lifts only after a rename-survival test (synthetic fixture or a repo with renames; Cairntir's history has zero) |
| H3 | Agent Memory v1.6 (`agent:` wings for installed skills) | candidates #7 | absent |
| H4 | MCP sampling for the Reason loop | candidates #5 | absent — and candidates doc says verify client support first; big plan says reject Sampling as foundation (deprecated in SEP-2577) → **conflict between the two research docs; big plan's reading is newer and controls** |
| H5 | Guardian-agent architecture note | trends #6 | absent — `docs/architecture/` holds only `multi-host-continuity.md` |
| H6 | Retire the stale local-proposer roadmap entry (Gemma 4, 2026-04) | trends #7 | open |
| H7 | AgentMemory lineage assessment | trends #10 | absent |
| H8 | Standing landscape loop (Signal Reader pointed at Cairntir's own horizon) | candidates #10 | recipe docs exist (`docs/recipes/signal-reader/`), the loop has never run |
| H9 | `cairntir signal` interactive CLI | signal-reader phase 2 | absent |
| H10 | Evolving-mind remaining: independence tests, usefulness feedback, dismissible notifications, structured MCP resources, strategy holdouts, longitudinal proof | evolving-mind §"Still planned" | absent |

### Group I — Ecosystem / host lane (big plan hygiene)

| # | Feature | Verified state |
|---|---|---|
| I1 | Qwen host adapter | code on `feat/qwen-host` (b364338); **PR #43 open**, based pre-#42 → needs rebase + four-host continuity test |
| I2 | MCP 2026-07-28 compatibility audit | absent |
| I3 | Agents-library junction + pruning (≈8.4k → controlled roster) | **needs Patrick's hands — nothing under `~/.claude/` may be touched by an agent** (agents-library-routing §6) |

---

## 5. Where the plans disagree or overlap

1. **Settlement fix — two granularities, right order already implicit.** Seams P4.1 is
   the minimal one-scan fix; big plan 1A/2A is the full five-state truth model
   (`open / settled_scored / settled_unscored / contested / malformed`). Not a
   conflict: P4.1 is the first increment of 2A. The ultimate plan sequences them that
   way.
2. **MCP sampling.** Candidates doc (#5) proposes it as the Reason-loop future;
   trends doc says verify support first; big plan rejects it as foundation
   (deprecated by SEP-2577). **Big plan controls** (newest, and cites the SEP).
3. **Stale status lines.** `2026-08-05-completion.md` items 1–2 still read "in
   progress / not landed" — both landed (PRs #40, #41). `research-...-trends` says
   model capture "unbuilt" — corrected by `release-1.3.0.md` and superseded by the
   per-write `model` argument (PR #35). These documents are dated evidence, not live
   ledgers; the honest-and-whole commitments block is the live ledger.
4. **The P0 denominator.** Big plan §2 correctly notes P0's ≥60% target used
   "drawers that reference code" as denominator and was never recomputed honestly —
   52.1% store-wide is not the same number. Do not call P0 "accepted"; call it
   "mechanically landed, acceptance metric unrecomputed."
5. **`session_start` default behavior.** Release-1.3.0 explicitly deferred narrowing
   the default ("behaviour change for existing callers, deserves its own decision").
   Seams/trends docs push whole-drawer-only. The decision is still Patrick's; the
   budget parameter + handoff already give hosts the bounded path.

---

## 6. Why Cairntir does not yet run "fast and flawless" — the performance picture

All four are measured or source-verified, not asserted:

1. **The seam (defect A) inflates every handoff.** Open predictions lead the section
   order with a 10% budget reserve (handoff.py:~270-290). A count that never goes
   down means growing wasted budget and growing noise in the one brief agents read
   first.
2. **The read path still costs round trips.** `recall` returns stubs only → every
   usable hit needs a `get`; `get` always carries full provenance; `session_start`
   with no budget returns every stub (hosts that skip `handoff` pay the ~10k-token
   fixed cost). Field report finding 2, still structurally true on main.
3. **Ranking quality is capped by the 512-token embedder window.** 43% of drawers
   exceed it (trends doc, measured 2026-08-02); the two-cause experiment (F1) that
   would separate drawer-size from truncation has never been run. Poor ranking →
   more calls → slower sessions. The real fix (F2/F3) is Patrick-gated, but F1 is
   not.
4. **Reads that write.** Access-counter updates on reads can contend with writer
   transactions (big plan gap #5). Not yet characterized; the deterministic
   concurrency harness (big plan 1B) is the prerequisite.

---

## 7. What is gated and cannot be autonomous

- Embedder bake-off, chunking, or any live reindex — **Patrick present** (project
  rule since drawers #182/#210).
- Any live-store mutation — backup → snapshot-rehearse → verify → live, awake.
- Anything under `~/.claude/` (agents-library junction).
- CodeGlass standalone packaging and the `codeglass-site`/`codeglass-dist` parent
  question — Patrick's decision.
- Weak-model effect thresholds and settlement-shadow gates — Patrick approves the
  numbers before data collection (big plan §15).
