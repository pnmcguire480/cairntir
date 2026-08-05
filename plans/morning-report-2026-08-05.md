# Morning report — overnight improvement run, 2026-08-05

**Run:** `plans/2026-08-04-ultimate-improvement-plan.md`, packages W1–W5.
**Result: all five packages landed.** `main` moved `aa31984 → 1053a6e` (four
squash-merged PRs, 56 CI runs green). Nothing Patrick-gated was touched: no
live-store mutation, no embedder work, nothing under `~/.claude/`, CodeGlass
companion untouched, staleness flagging still ON HOLD.

## How the night actually went

The scheduled task fired at 00:37 and the run executed **W1** autonomously
(PR #44, drawer #290), created the W2 worktree, and then the loop died with
zero W2 commits. Patrick found the stall in the morning. **W2–W5 were
completed by hand in the recovery session**, package by package, each with its
own worktree, full gate, PR, CI watch, merge, and post-merge file-on-main
verification — a merge report is a claim, not a fact.

## What landed, per package

| Pkg | PR | Merge | What it did |
|---|---|---|---|
| W1 | #44 | `aa31984` | Settled predictions now close in `handoff` (`settled_prediction_ids`, one wing scan); `settle` writes the `success` verdict calibration reads; `tests/integration/test_seams.py` pairs four seams both-sides; `scripts/check_seams.py` fails CI if a declared seam loses its test. |
| W2 | #45 | `fb89bd7` | The five store-integrity rules moved to `src/cairntir/health.py` (one implementation, two front-ends); `cairntir doctor --gate` runs them where the data lives, wired into pre-commit; `check_release_tags.py` verifies **PyPI presence**, failing closed on network; the two decorative CI steps renamed so the skip is in the name. Live-store smoke: 290 drawers, 153 anchored, store whole, gate ok. |
| W3 | #46 | `8c73557` | `cairntir_recall(..., full_content=N)` delivers top hits whole — kills the `get` round trip; oversize hits named, never truncated; default 0 byte-identical. |
| W4 | #43 | **open** | `feat/qwen-host` rebased onto current main (clean), qwen added to the four-host continuity fixture, gate green locally (634 tests) and on the PR (14 checks). **Not merged — Patrick's call.** |
| W5 | #47 | `1053a6e` | Read-only measurement (below) + `_prediction_nudge`: `remember` now asks for a `predicted_outcome` when a drawer carries a claim without one. Advisory only. The anchor lesson applied to the epistemic core. |

## The W5 measurement (read-only, live store, 292 drawers)

`claim` 5 · `predicted_outcome` 5 · `observed_outcome` 1 · **`delta` 0** ·
settlements through MCP since settle landed: **0**. The mechanism was dark for
the reason the seams plan predicted — nothing ever asked. The nudge is the
ask; drawer #293's prediction tests whether asking works.

## Commitments promoted

`check_landed_commitments.py` now checks **72 assertions across 3 documents**
(was 58 before the run). Every promotion happened in the same commit as the
code it asserts, and the gate ran green before each merge.

## The discovery that matters most: the running server was stale

The live proof of W1 initially **failed in-session**: settling #288 appended a
correct observation (#294, `supersedes_id=288`, `observed_outcome` set), but
the next handoff still listed #288 open and calibration did not count it. The
cause is not the code — it is deployment: the maintainer's install is
**editable**, so whatever branch the primary checkout sits on is what every AI
host runs, and the checkout was still on `feat/qwen-host @ b364338` — pre-W1.
The fixed code was on `main` and invisible to every running host.

**Fixed in-session:** the primary checkout now sits on `main @ 1053a6e` (all
five packages). `feat/qwen-host` survives as the remote PR branch. The three
settlements (#288→#294, #290→#295, #289→#296) were recorded through the
pre-W1 process, so they carry no `metadata.success` — they are
`settled_unscored` in the truth model's terms, and the observations say so.

**What this still costs:** every already-running host process holds the old
modules in memory until it restarts. The open-count decrease becomes visible
on the next host restart — that re-verification is owed (drawer #295).

## Morning chores for Patrick (or the next integrator)

1. **Restart the AI hosts** (or reboot) so `cairntir-mcp` reloads from the
   checkout now on `main`. Then `cairntir_handoff(wing="cairntir")` should
   show #288/#289/#290 closed — the owed re-verification of drawer #295.
2. **Review and merge PR #43** (Qwen host) — rebased, CI green, four-host
   fixture proven. After the merge, the stale local branches
   (`feat/cost-accounting`, `feat/handoff`, `feat/landed-commitments`,
   `fix/settlement-seam`) can be deleted.
3. **Commit the untracked plan files** (this report, the audit, the ultimate
   plan, the three older untracked plans) or decide which stay local.
4. **Decide on the two skipping CI steps** — renamed loud, not deleted;
   deletion was kept as Patrick's call.
5. The `w1-settlement-seam` worktree at `C:\Dev\cairntir-wt\` is parked on a
   merged branch; safe to remove (`git worktree remove`).
6. **Embedder bake-off** is the highest-value item still standing and needs
   Patrick present (live reindex). `cairntir cost` measures the problem: 29%
   of `cairntir`-wing drawers exceed the ~2,048-char window.
7. The three older `.claude/worktrees/` hold merged commits (vault-sync,
   model-provenance, open-predictions) — audit and clear when convenient.

## The diff between plan and reality

- The overnight loop survived exactly one package. The plan's stop conditions
  were never breached — the runner simply died. Recovery-by-hand worked
  because the plan was written as a cold-start brief; that design choice paid.
- W6 (holdout harness) was correctly never started: W1–W5 were not all merged
  before 04:00, and a half-built harness would read as a green gate.
- One deviation from the brief's letter: W4's rebase used a **detached-HEAD
  worktree** and a lease-protected force-push rather than touching the primary
  checkout, because the primary checkout carries the open PR branch and
  Patrick's untracked files. Same outcome, safer path.

## Next daytime program (from the audit, unchanged)

CodeGlass companion-first (the seam, then vault link-graph pattern discovery),
the holdout harness + weak-model acceptance test, the settlement truth-model
contract, and branch-aware lineage. All in
`plans/research-2026-08-04-plan-ledger-audit.md` §4, groups A–I.
