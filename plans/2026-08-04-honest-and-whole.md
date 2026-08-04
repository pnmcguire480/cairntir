# Cairntir — Honest and Whole

**Date:** 2026-08-04
**Author:** Opus 5, from the 2026-08-03/04 memory-bank survey (drawers #235, #236, #237, #274, #275)
**Status:** Proposed. Not started.

---

## The goal, in Patrick's words

> "to keep a solid memory so that EVEN IF I was using FREE AI with terrible output, it could over time follow the pieces to make the whole."

That is the acceptance test for everything below. Not "is the store correct" — **can a weak model reassemble the picture without knowing the right question to ask.**

Two properties, and the work splits cleanly along them:

- **WHOLE** — the pieces are connected, and connection does not depend on the reader being clever.
- **HONEST** — the store can tell you when it was wrong.

Cairntir is currently good at storing and bad at both of these. Everything here is measured, not asserted.

---

## Measured baseline (2026-08-04, live store, 275 drawers)

| Fact | Value | Why it matters |
|---|---|---|
| Drawers carrying anchors | **30 / 275 (10.9%)** | `recall_for_change` is the only retrieval path that needs no good question. It is 89% dark. |
| Wings with **zero** anchors | **19 of 22** | Only `cairntir`, `detroit-clone`, `triangulate` have any. |
| `claim` populated | **2 / 275** | The v0.2 prediction-bound drawer — the epistemic core — is unused. |
| `predicted_outcome` | **2 / 275** | |
| `observed_outcome` | **1 / 275** | |
| `delta` (surprise signal) | **0 / 275** | Never written once. Described in the model docstring as "load-bearing in v0.4." |
| `trust='untrusted'` | **123 / 275** | A v6 migration artifact, not a judgement. Half the bank renders with a security banner it did not earn. |
| `session_start` budget param | **absent** | Verified today: `session_start(*, wing, query)`. The v1.2 commitment named in #212 still has not landed. |
| Write-time content/anchor guard | **absent** | `DrawerStore.add()` validates the embedding dimension and nothing else. The 2026-08-02 damage can recur tonight. |
| `holdout` eval hooks | **0 files** | Still absent, as #212 reported. |
| `vault_sync.py` wired to CLI/CI | **no** | A loose script. It will drift back out of sync exactly as its predecessor did. |

---

## P0 — WHOLE: make structural recall real

**The single highest-leverage change in this plan.**

Semantic recall rewards whoever asks the best question. A weak model asks bad questions and gets nothing back. `recall_for_change(store, files)` fires from *the files being edited* — it requires no cleverness from the agent at all. That is the mechanism that makes the stated goal achievable, and it covers 10.9% of the store.

1. **Backfill anchors across the 19 wings that have none.** Most drawers name their files in prose (`sim-core/src/tech.rs`, `app/lib/claims.ts`). Extract candidate paths, verify each against the real repo on disk, and write only verified hits. **Never write an unverified path** — a wrong anchor is worse than none, because it silently poisons structural recall. Report unverifiable candidates for a human instead of guessing.
2. **Make anchoring the default, not an option.** `cairntir_remember`'s tool description must state the anchor contract inline. Drawer #210's own diagnosis: agents "had no way to see the anchor contract — the tool declared `metadata` as a bare object — so they guessed."
3. **Wire `vault_sync.py` as `cairntir vault-sync`** with a `--check` mode in CI that fails when vault files exist with no corresponding drawer. Otherwise this plan reproduces the defect it exists to fix.

**Done when:** anchor coverage ≥ 60% of drawers that reference code, every wing with a repo has ≥1 anchored drawer, and `check_store_health.py` reports coverage as a tracked metric.

### Item 1 — LANDED 2026-08-04

Verified extraction lives in `cairntir.memory.anchors` (`RepoIndex`,
`extract_path_candidates`, `propose_anchors`) and is driven by
`scripts/backfill_anchors.py`. A candidate is written **only** when it names
exactly one real file: an exact hit, a segment-boundary suffix matching one
indexed file, or a bare filename matching one file whose basename is not
generic. Two matches is a guess, not a near-miss, and is rejected. The only
prefix that may be stripped is the repo's own directory name, so
`C:\Dev\MinnieSweets\catering.html` resolves while `vendor/package.json` does
not silently become the root `package.json`.

Applied to the live store after a WAL-safe backup and a full sandbox rehearsal:

| | before | after |
|---|---|---|
| Drawers carrying anchors | 31 / 278 (11.2%) | **113 / 278 (40.6%)** |
| Wings with zero anchors | 19 of 22 | **9 of 22** |
| Content hashes changed | — | **0** |
| Drawers lost | — | **0** |

80 drawers gained 382 anchors, every one independently confirmed to resolve to
a real file by a checker that does not import Cairntir's own resolver. Probe
files that returned 0 drawers before return 1–5 after.

Two of the nine remaining zero-anchor wings (`transcript-capture`,
`video-capture`) are correct zeroes — their drawers name no resolvable files.
The other seven are **unmapped, not skipped**: `ground-zero` (two candidate
directories exist), `codeglass` (two candidates), `getkith` (closest directory
name does not match the wing), `agents` (probable but unconfirmed), and
`dev` / `larder` / `quietpdf` (no directory found). Guessing any of these would
break the rule this phase exists to enforce.

---

## P1 — HONEST: make the store able to be wrong

The `claim` / `predicted_outcome` / `observed_outcome` / `delta` fields exist on every drawer and are used **twice in 275 rows**. `delta` — the surprise signal, the thing that would let the store learn — has never been written. This is a fully-built epistemic mechanism with no wire to it, which is the exact defect the lineage keeps repeating.

1. **Make prediction-bound writes reachable.** `cairntir_remember` does not expose `claim`/`predicted_outcome` at all. Nothing can populate them through the MCP surface. Expose them, and document when to use them: any drawer asserting a load-bearing decision should carry a falsifiable prediction.
2. **Add `cairntir_settle`** — the missing other half. Given a drawer id and an observation, write `observed_outcome` and `delta`. A prediction nobody can settle is not a prediction.
3. **Surface unsettled predictions in `handoff`.** "3 open predictions in this wing" is the honest opening line of a session.
4. **Retire the `untrusted` migration stamp.** 123 drawers carry it because of the v6 migration on 2026-07-29, not because anything is suspect. Either re-attest them as `legacy_migrated` or document the meaning where a reader will see it. Right now the banner cries wolf on 45% of the bank, which trains every agent to ignore it.

5. **Record which model authored each drawer.** Added 2026-08-04 at Patrick's
   request: *"drawers need to be marked by what ai generated them so we can
   strengthen weaknesses between models as well as code habits and such."*

   **Done, forward-only** — explicitly no backfill (Patrick: *"no need to back
   fill on that. 95% is opus 4.6 anyways"*). `provenance.model` already existed
   and worked; it read `unknown` on 279 of 280 drawers because nothing ever set
   it. The reason is structural: **no host discloses the running model to the
   MCP subprocess.** `cairntir-mcp --model` / `$CAIRNTIR_MODEL` exist, but a
   value fixed at process start keeps asserting the first model after the user
   switches — worse than `unknown`, because it looks like data.

   So the model is a **per-write** argument. The writing agent is the only party
   that knows its own identity, so `cairntir_remember` now takes `model` and the
   tool description tells the agent to state it. Same lesson as the anchor
   contract in drawer #275: *the tool description is the only documentation a
   writing agent ever reads.*

   Host attribution was already working and needs nothing: `claude` 87,
   `legacy` 123, `cli` 36, `codex` 15, `unknown` 18, `cursor` 1.

**Done when:** predictions can be written and settled through the MCP surface, and `handoff` shows open ones.

---

## P2 — Close the two verified regressions

1. **Write-time guard in `DrawerStore.add()`.** Reject content containing tool-call markup; validate `metadata.anchors` via the existing `parse_anchors`. `check_store_health.py` catches this *after* the fact; nothing prevents it. The bug fired 2026-04-26, 2026-05-08, and five times on 2026-08-02.
2. **`session_start` context budget.** Still absent, still the v1.2 commitment from #212. `handoff` already has `budget_chars`; `session_start` should honour one too, or be documented as deprecated in favour of `handoff`.

---

## Explicit non-goals

- Not touching the embedding model or vector schema. It works.
- Not syncing vault `rules/*.md` to all wings — the old convention would mint ~80 duplicates.
- Not syncing project `dashboard.md` files — they are stale CLAUDE.md snapshots and would poison recall.
- Not repairing the 7 leaked-envelope drawers. **Already done 2026-08-04**, see #275.

---

## A note on the commitments block below

`scripts/check_landed_commitments.py` will read this block and **fail CI until every assertion is true.** That is intentional and it is the point: this repo's oldest defect is commitments that vanish quietly. A red build is the ratchet.

If a red build is disruptive while the work is in flight, move the block down to only the phase being actively worked — but move it, never delete a line to make the build pass. That would be the defect itself, wearing a disguise.

```cairntir-commitments
file   scripts/check_store_health.py
file   scripts/repair_leaked_metadata.py
file   scripts/vault_sync.py
symbol src/cairntir/memory/anchors.py recall_for_change
symbol src/cairntir/memory/store.py repair_anchors
file   scripts/backfill_anchors.py
symbol src/cairntir/memory/anchors.py RepoIndex
symbol src/cairntir/memory/anchors.py propose_anchors
test   tests/unit/test_anchors.py test_backfilled_anchors_are_verified_against_disk
test   tests/unit/test_anchors.py test_repo_index_will_not_drop_a_prefix_the_author_asserted
param  src/cairntir/mcp/backend.py remember:model
param  src/cairntir/memory/store.py add:model
test   tests/integration/test_mcp_backend.py test_remember_records_the_authoring_model
test   tests/integration/test_mcp_backend.py test_two_models_in_one_session_are_recorded_separately
# P0 item 3 — LANDED 2026-08-04. `vault_sync.py` is no longer a loose script:
# the logic is `cairntir.vault`, the command is `cairntir vault-sync`, and
# `--check` exits non-zero on drift. Supersedes the staging entry further down.
symbol src/cairntir/cli.py vault_sync_cmd
symbol src/cairntir/vault.py plan_sync
symbol src/cairntir/vault.py apply_sync
param  src/cairntir/cli.py vault_sync_cmd:check
test   tests/unit/test_vault_sync.py test_check_exits_nonzero_when_a_walkthrough_has_no_drawer
test   tests/unit/test_vault_sync.py test_check_writes_nothing_even_when_it_finds_drift
```

The block asserts only what has **actually landed**. The first five lines lock in
the 2026-08-04 repair work; the last five lock in P0 item 1. Add the rest as each
piece lands — and if a phase slips, the assertion stays out of the block rather
than being written optimistically, because a green build must mean the code is
there, not that someone intended it to be.

```
# P0 item 2 — make anchoring the default (NOT LANDED)
param  src/cairntir/mcp/backend.py remember:anchors

# P0 item 3 — wire vault_sync to the CLI (NOT LANDED)
symbol src/cairntir/cli.py vault_sync_cmd

# P1
param  src/cairntir/mcp/backend.py remember:claim
symbol src/cairntir/mcp/backend.py settle
test   tests/unit/test_predictions.py test_settle_writes_delta

# P2
param  src/cairntir/mcp/backend.py session_start:budget_chars
test   tests/unit/test_store.py test_add_rejects_tool_call_markup
```
