# Cairntir — Ultimate improvement plan (overnight run, 2026-08-04 → 08-05)

**Status:** proposed; the overnight run is authorized to execute **Groups W1–W5 only**,
under the constraints below. W6 is stretch. Everything else waits for daytime work or
Patrick.
**Built from:** `plans/research-2026-08-04-plan-ledger-audit.md` (all 17 plans read,
every claim re-verified against `origin/main @ 4483c96`).
**Supersedes nothing:** the honest-and-whole commitments block stays the live ledger;
this plan promotes staged assertions into it only as each lands.

---

## The goal, unchanged

> "to keep a solid memory so that EVEN IF I was using FREE AI with terrible output,
> it could over time follow the pieces to make the whole." — Patrick

Tonight's work is judged by that: fix the defects that make the store *dishonest*
(settled predictions counted as open, calibration blind to settlements, hidden lineage
branches) and cut the round-trips that make it *slow* — without touching anything
Patrick gated.

## Hard constraints for the overnight run (non-negotiable)

1. **No live-store mutation.** No backup/reindex/reattest/anchor-backfill against the
   real `cairntir.db`. Read-only store inspection is fine.
2. **No embedder work** (bake-off, chunking, reindex) — Patrick-gated.
3. **Nothing under `~/.claude/` or `C:\Users\pnmcg\.claude\`** — Patrick's hands only.
4. **No self-modifying behavior, no prompt-policy changes, no new dependencies.**
5. **Land through PRs on `main`.** Zero reviews required (house rule), but every merge
   must be followed by verifying the files exist on `origin/main` — a merge report is
   a claim, not a fact (release-1.3.0 lesson).
6. **The gate, before every commit:**
   `ruff check src tests scripts` · `ruff format --check src tests scripts` ·
   `mypy --strict src` · `check_no_silent_except.py` · `check_landed_commitments.py` ·
   `pytest -q`.
7. **Write commitments only for what has landed.** Promote staged assertions into the
   honest-and-whole block as each package lands; never delete an assertion to go green.
8. **Untracked files are user-owned.** Never `git add .`; add only files a package
   owns. The `.claude/` directory and the three untracked plan files stay untouched
   (this plan's two new files get committed by the morning integrator, not the
   overnight runner, unless they land on a docs PR).
9. **Worktree discipline:** one worktree + branch per package; never implement in the
   primary checkout (it stays on `feat/qwen-host` with PR #43 open); workers don't
   merge their own contested results.
10. **Record as you go** with `cairntir_remember` (wing `cairntir`, room
    `improvement-run`, `model` declared per write, verified anchors only). If the run
    dies mid-flight, the next session picks up from drawers + this file.

## Work packages (ordered)

### W1 — Close the live seam (audit defects A + B; seams P4.1–P4.4)

*The only package fixing a defect live in shipped code. Do it first.*

Branch `fix/settlement-seam`, from current `origin/main`.

1. **`settled_prediction_ids(scanned)`** in `src/cairntir/handoff.py`: one pass over
   the wing scan already performed by `compose` —
   `{d.supersedes_id for d in scanned if d.observed_outcome and d.supersedes_id}`;
   open iff `is_open_prediction(d) and d.id not in settled`. No per-drawer graph
   traversal. Determinism and budget contracts preserved (existing byte-identity and
   whole-drawer tests must stay green). Document the real limit in the docstring: an
   observation drawer outside the scanned set will not clear its prediction —
   *sometimes stale beats never clears*.
2. **Calibration sees settlements (defect B), minimal shape:** `settle` persists an
   explicit boolean verdict derivable from the existing delta contract (delta absent
   ⇒ prediction held exactly ⇒ success True; non-empty delta ⇒ False) into the
   observation drawer's `metadata["success"]`, so `calibration.py` counts MCP
   settlements without a schema change. Original prediction stays immutable. Add one
   unit test proving calibration's denominator moves after a settle.
3. **The seam test** in `tests/integration/test_seams.py`:
   `remember(predicted_outcome=...) → settle(...) → handoff() → open count == 0`,
   and a second case: divergent second observation ⇒ count still 1 (no silent
   winner).
4. **Paired seam tests (P4.3):** write-guard in `add()` ↔ `check_store_health.py`
   rule 3; `parse_anchors` on write ↔ `recall_for_change` on read;
   `vault-sync --check` drift ↔ `apply_sync`.
5. **`scripts/check_seams.py`:** a registry of declared seams + the paired test that
   proves each; fails when a declared seam has no test. Wire into the gate list in
   CI alongside `check_landed_commitments.py`.
6. Update the `is_open_prediction` docstring (the "today it is not" sentence is now
   false).

**Done when:** settling a prediction makes the handoff count go down; calibration
counts it; every declared seam has a two-sided test; commitments promoted:
`symbol src/cairntir/handoff.py settled_prediction_ids`,
`test tests/integration/test_seams.py test_settling_a_prediction_closes_it_in_handoff`,
`file scripts/check_seams.py`,
`test tests/integration/test_seams.py test_settle_writes_a_delta_a_later_session_can_read`.

### W2 — Guards where the data lives (seams P5; completion #5)

Branch `feat/doctor-gate`, from `main` after W1 lands.

1. **`cairntir doctor --gate`**: runs store health + vault drift check where a real
   store exists; exits non-zero on damage or drift. Unit test on a temp store
   (`test tests/unit/test_doctor.py test_gate_fails_on_a_damaged_store` — staged
   assertion from the seams plan).
2. **Pre-commit hook** calling `cairntir doctor --gate` (advisory loudness; the hook
   must not block commits in environments without a store — skip-loud, not skip-silent).
3. **CI steps made loud:** rename the two skipping steps so the skip is in the step
   name (e.g. "store health (SKIP: no store on CI runners)"), per the seams plan's
   kept-step option. No deletion tonight — deletion is Patrick's call.
4. **PyPI presence gate (defect D):** extend `scripts/check_release_tags.py` to
   verify each released tag published to PyPI (JSON API, generous timeout, clear
   error on network failure), with an allowlist for the known-unreleased 1.0.1/1.1.3
   and any version explicitly marked unreleased. Test with a stubbed response.

**Done when:** `doctor --gate` can genuinely fail on a damaged store; no CI step can
pass by *silently* skipping; the tag gate catches a tag-without-PyPI.

### W3 — Faster read path (field report finding 2; audit §6.2)

Branch `feat/recall-full-hits`, from `main` after W2 lands.

1. **`cairntir_recall(..., full_content: int = 0)`** — return the top-N hits with
   complete content (subject to the existing budget/whole-drawer discipline: a hit
   too large is omitted by name, never truncated). Default 0 keeps today's behavior
   byte-identical for every existing caller. One good drawer beats ten headlines and
   removes a round trip.
2. Tool description updated to say when to use it (the tool description is the only
   documentation a writing/reading agent ever reads — field report root cause).
3. Tests: N=0 unchanged output (byte-identity on a fixture store); N=2 returns whole
   drawers; oversize hit omitted not truncated.
4. **Not tonight:** `get` `fields` argument and `session_start` default narrowing —
   both are caller-contract decisions for Patrick (release-1.3.0 precedent).

**Done when:** a host can answer a one-question session in two calls
(`handoff` → `recall(full_content=2)`) instead of three-plus.

### W4 — Rebase and prove the Qwen host (big plan Phase 0 / hygiene; PR #43)

Branch: existing `feat/qwen-host` (worktree-safe: do this in a **new worktree**,
never in the primary checkout).

1. Rebase `feat/qwen-host` onto current `origin/main` (post-#42). Resolve only in
   favor of both changes coexisting; if the rebase produces a real conflict, stop
   and record it — do not guess.
2. Run the full gate plus the host adapter tests; add `qwen` to any host-matrix
   fixtures that enumerate hosts, so the four-host continuity test (Claude, Codex,
   Cursor, Qwen → same store, same drawer ids) covers it.
3. Force-push the rebased branch to `origin/feat/qwen-host` (the PR retargets
   automatically). Merging PR #43 is **not** part of the overnight run — it is
   Patrick's or the morning integrator's call after reading the diff.

**Done when:** PR #43 sits on current main with green CI and a four-host fixture.

### W5 — Measure the dark loops (seams P6; read-only)

No branch — inspection and one nudge.

1. Count, read-only, on the live store: drawers with `delta` written since
   2026-08-04; predictions written via MCP since settle landed; how many settled.
   Record the numbers as a drawer (room `improvement-run`), not as a code change.
2. If `delta` is still zero (expected), apply the anchor-lesson fix: the `settle`
   and `remember` tool descriptions already invite predictions; add the missing
   *ask* — when `remember` stores a drawer carrying a load-bearing decision with no
   `predicted_outcome`, the confirmation nudges (advisory, never fatal), reusing the
   existing nudge machinery from PR #35 so detector and contract agree by
   construction. Code change lands in W1's branch if W1 is still open, else its own
   tiny PR.

### W6 — STRETCH ONLY if W1–W5 are all merged and green before 04:00 local

**Holdout harness scaffold (D1):** `evals/holdout/questions.jsonl` seeded from
read-only store inspection (questions whose known-correct drawer ids are verified by
the harness itself at load time), `src/cairntir/evals/holdout.py` `score` function
that grades a transcript's recalled ids, and one integration test on a fixture
store. **No weak-model run tonight** — that is the deliberately-scheduled P8 event
with Patrick. If started and not clean by 05:00, revert the branch and record why;
a half-built harness is worse than none (it would read as a green gate).

## Explicitly NOT tonight (and why)

- Embedder bake-off / chunking / reindex (F2, F3) — live store, Patrick present.
- Full settlement truth model states `contested/adjudicated/expired` beyond W1's
  minimal verdict (A5 full contract) — thresholds are Patrick's (§15 big plan).
- Branch-aware lineage rebuild (A6) and atomic idempotent settlement (A7) — need the
  deterministic concurrency characterization harness first (big plan 1B); day work.
- Snapshot-receipt handoff (A8) — Phase 3, after the settlement contract is stable.
- CodeGlass companion work (G1–G5) — the next daytime program, not an overnight
  increment; the seam design deserves Patrick's eyes.
- Glossary drawer (H1), agent memory (H3), MCP sampling/elicitation (H4, E2),
  guardian note (H5), AgentMemory lineage (H7) — valid, lower priority, day work.
- Staleness flagging (H2) — ON HOLD by Patrick's ruling until rename survival is
  tested. Do not lift the hold.
- Anything in `agents-library-routing.md` — Patrick's hands.

## Morning report (the runner writes it before ending)

File: `plans/morning-report-2026-08-05.md` plus one summary drawer in wing
`cairntir`, room `improvement-run`. Contents:

- per package: branch, PR number, merge status, files-on-main verification output;
- gate output of the final full run on `main`;
- the W5 store measurements (delta count, prediction/settle counts);
- anything stopped and why;
- the exact list of commitments promoted into the honest-and-whole block;
- the diff between this plan and reality — if any package changed shape, say so
  plainly rather than quietly re-scoping it.

## Stop conditions (any one ⇒ stop, record, do not push through)

- a gate stays red after two genuine fix attempts on the same failure;
- the primary checkout or live store changes during the run (another actor is
  awake — stop and hand back);
- a rebase in W4 produces a real conflict;
- any test would pass only by weakening an assertion;
- uncertainty about whether an action touches the live store ⇒ don't.

## Success, in one paragraph

By morning: a settled prediction clears the handoff's open list and shows up in
calibration; every declared seam has a test that exercises both sides; `doctor --gate`
can fail where the data actually lives; the release gate sees PyPI, not just tags;
a host can get a whole answer in two calls; PR #43 sits green on current main; and
every one of those facts is pinned by a commitment that CI will fail if a later
change quietly un-lands. That is the store one step more honest and one step faster,
with nothing gated touched.
