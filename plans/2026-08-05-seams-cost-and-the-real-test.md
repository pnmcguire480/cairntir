# Cairntir — Seams, Cost, and the Test We Never Ran

**Date:** 2026-08-05
**Author:** Opus 5 (Claude Code), from the 2026-08-03 → 08-05 arc
**Audience:** the next agent to work this repo — written for Qwen, good for anyone
**Status:** Proposed. Not started. Nothing here has landed.
**Relationship to prior plans:** `plans/2026-08-04-honest-and-whole.md` closed
P0, P1 and P2. This picks up from there. P3 (CodeGlass) is carried forward
unchanged and restated at the end.

---

## Read this first

Everything below is either **measured** (a number I ran) or **reported** (a
subagent's finding, attributed). Where something is an estimate, it says so.
Nothing here is asserted from memory.

The prior plan asked *"is the store whole and honest?"* and answered it: anchor
coverage went **11.2% → 52.1%**, predictions became writable and settleable,
`DrawerStore.add()` grew a write-time guard, `session_start` got the budget
promised in v1.2, and the `untrusted` migration stamp was retired.

That same work produced a defect **none of the existing gates can see**. This
plan is organised around it.

---

## The organising finding: three kinds of truth, one guard

| # | Question | Guard | Status |
|---|---|---|---|
| 1 | Did we build what we said? | `scripts/check_landed_commitments.py` | **Works.** CI-enforced. |
| 2 | Is what we built still true of the data? | `scripts/check_store_health.py` | **Exists, runs where the data isn't.** |
| 3 | **Do the pieces still agree with each other?** | *nothing* | **Unguarded. Live defect today.** |

Category 3 is where the worst bugs live, because **every component passes its
own tests while the system as a whole is wrong.**

---

## P4 — Guard the seams

> **Highest priority. Contains a defect that is live in shipped code on `main`
> and producing a wrong number right now.**

### P4.1 — Fix the live seam *(do this first)*

**Verified on `main` on 2026-08-05** by reading both files.

`CairntirBackend.settle` (`src/cairntir/mcp/backend.py`) closes a prediction by
**appending** an observation drawer that supersedes it, and deliberately leaves
the original's `observed_outcome` as `None`. There is a passing test asserting
the original is untouched — `test_settle_appends_and_leaves_the_original_untouched`.
This is correct: *a store that rewrites its own predictions cannot be used to
check whether it was right.*

`is_open_prediction` (`src/cairntir/handoff.py`, ~line 398) decides openness by
reading `predicted_outcome` and `observed_outcome` **off the drawer itself**,
with no supersedes handling. It has four passing tests. This is also correct:
it is deterministic and auditable, and every id it prints can be checked with
one `cairntir_get`.

**Together, shipped, they mean every prediction settled through the only
sanctioned path stays listed as open forever.** The count can only grow. The
feature exists to say "3 open predictions" and will say "40" when all 40 are
closed.

Note the PR #37 docstring already names the trigger — *"revisit this if the
reason-loop shape ever becomes the common way predictions are written"* — but
PR #35 had made it the **only** way about an hour earlier, and nothing in the
repo could notice.

**The fix**, using the single wing scan `handoff` already performs:

```python
settled = {
    d.supersedes_id
    for d in scanned
    if d.observed_outcome and d.supersedes_id
}
# open iff:  is_open_prediction(d) and d.id not in settled
```

- One pass. **No per-drawer graph traversal** — that was PR #37's stated
  objection and this does not incur it.
- Determinism is preserved: derived from drawer fields only, no clock, no
  ranking, no embedder. `handoff` must stay byte-identical across repeat calls
  (it is what keeps a host's prompt cache warm) — there is an existing test for
  this; keep it passing.
- The budget contract is preserved: whole drawers or none, never truncated.
- **Document the real limit:** an observation drawer outside the scanned set
  will not clear its prediction. *Sometimes stale* beats *never clears*. Say so
  in the docstring rather than letting someone discover it.

### P4.2 — Write the test that would have caught it

One test, exercising **both** halves in sequence:

```
remember(predicted_outcome=...) → settle(...) → handoff() → assert count == 0
```

It must live somewhere it can see both sides — suggest
`tests/integration/test_seams.py`. Separate per-component tests are exactly what
green-lit this bug; adding more of them would not have helped.

### P4.3 — Cover the other seams

Known seams today, each needing **one paired test**:

| Seam | State |
|---|---|
| `settle` ↔ `is_open_prediction` | **broken** — P4.1 |
| write guard in `add()` ↔ `check_store_health.py` rule 3 | agree **by design**, never tested together |
| `parse_anchors` on write ↔ `recall_for_change` on read | agree, untested together |
| `vault-sync --check` drift ↔ `apply_sync` write | agree, untested together |
| `TOOL_SURFACE_VERSION` ↔ the tool list | **already fixed** 2026-08-04 — the precedent to copy |

### P4.4 — `scripts/check_seams.py`

A registry of *"these two things must agree"* plus the paired test proving it,
failing CI when a declared seam has no test. This is
`check_landed_commitments.py`'s idea applied to **agreement** rather than
existence.

### The law this establishes

> When two components must agree, either make them **share the code that defines
> the agreement**, or **test them together in one test**. Never only separately.

**This is not a new idea in this codebase — it is already applied correctly
twice**, and both times it was someone's good instinct rather than an enforced
rule:

- The anchor **nudge detector reuses `extract_path_candidates`** from the
  backfiller. They cannot disagree, because there is only one of them.
- The **write guard deliberately enforces the same line** as
  `check_store_health.py` rule 3 — quoted markup *with* metadata stays writable
  in both, by explicit design.

**Done when:** the open-prediction count goes *down* when a prediction is
settled, and every declared seam has one test exercising both sides.

---

## P5 — Put every check where its subject actually lives

> **The law:** a check that runs where its subject does not exist is **worse
> than no check**, because it advertises protection it cannot provide.

Two instances, both honest in their own source and both misleading as CI steps:

- **`scripts/check_store_health.py`** — lines 47–49 return
  `SKIP: no store at this location (fresh environment)` and **exit 0** when
  `db_path()` does not exist. A GitHub runner never has a `cairntir.db`, so
  **this step has never once been capable of failing in CI.**
- **`cairntir vault-sync --check`** — same shape, no vault on a runner. Its own
  author called it *"borderline theatre by your own standard"* in the PR body.
  He was right.

**Do:**

1. Move both to where the data is — a `cairntir doctor --gate` invoked from a
   local pre-commit hook and/or at session start, where a real store and vault
   exist and the check can genuinely go red.
2. **Delete the CI steps** rather than leave a green tick that means nothing.
   The unit tests already cover both mechanisms and *do* run on every push, so
   nothing is lost.
3. If a step is kept, make the skip loud — in its name, not in a log line
   nobody reads.

**Done when:** no CI step can pass by skipping, and the store gate runs
somewhere it can fail.

---

## P6 — Close the loops that are now openable but still unused

Every mechanism below now has a write path. **That guarantees nothing.** The
anchor lesson is exact: the contract was published *and validated on write* on
2026-08-02, and coverage was **still 11%** two days later. Publishing a contract
is not asking for compliance.

1. **Measure `delta` before building anything on it.** The write path landed
   2026-08-04 (`cairntir_settle`). Count how many deltas actually exist. If it
   is still zero, the mechanism is dark for exactly the reason anchors were, and
   the fix is the same shape: **make the write path ask.**
2. **Do not build calibration dashboards over an empty column.** Calibration
   only becomes meaningful once real deltas exist.
3. **Forward-only.** No backfill of predictions — matching the standing ruling
   on model provenance (Patrick, 2026-08-04: *"no need to back fill on that"*).

**Done when:** a non-zero number of predictions have been settled with a real
`delta` by an agent that was not told to do it as an experiment.

---

## P7 — Cost is a first-class constraint now

**The 2026-08-04 session ran out of budget mid-flight and killed a working
subagent.** That is data, not an inconvenience.

| Thing | Cost | Source |
|---|---|---|
| Agent roster, injected every session, every project | **~8,400 tokens** | subagent report, estimated at 4 chars/token |
| Same, if the full 660-agent library is linked | **~17,000 tokens** | same, estimate |
| Cairntir's whole 19-tool MCP catalog | 2,307 tokens | `cairntir cost`, already flagged **HIGH risk** |
| Five parallel subagents, one session | ~620k subagent tokens | measured; 4 completed, 1 killed by the limit |

The roster is **already ~4× the MCP catalog that Cairntir's own audit called a
high-risk gap.** And roughly **200 of the 228 undeployed agents are kebab-case
near-duplicates** of ones already present (`code-reviewer`/`Code Review`,
`cpp-pro`/`C++`) — paying twice for the same roster.

Drawer #212 named **controlled context** as the oldest invariant in this
lineage, rediscovered and lost three times. "Link all 660 agents everywhere" is
a proposal to spend 17k tokens per session against that invariant.

**Do:**

1. **Prune before linking.** Deleting the duplicate `thinkers/` bundle alone
   drops name collisions from **37 to 2**.
2. **Then** junction `~/.claude/agents` → `C:\Dev\AGENTS\agents`, with a backup
   and the rescue of the 8 agents that exist *only* in the global directory.
   One control point, zero drift.
   **⚠ Needs Patrick's hands. Nothing under `~/.claude/` may be modified by an
   agent.** Full sequencing is in `plans/agents-library-routing.md`.
3. **Widen `cairntir cost`** beyond Cairntir's own payload. Its current scope is
   deliberate and now too narrow to answer the question that actually bites.
4. **Budget parallel agents deliberately.** Five at once is affordable
   occasionally, not routinely. One well-scoped agent with sharp file ownership
   beats four speculative ones.

**Open question that is genuinely Patrick's:** he asked for all agents reachable
from every project. That is a real 17k/session cost against his own founding
invariant. Do not resolve it unilaterally — surface the number and let him
choose.

**Also worth knowing:** subagents **never fire automatically**. That is the
harness design, not a configuration gap, and no amount of file-linking changes
it. 402 of the 660 are already live via a stale April copy; 228 never deployed;
zero of the 402 say "proactively" in their description.

---

## P8 — Actually run the acceptance test

> *"to keep a solid memory so that EVEN IF I was using FREE AI with terrible
> output, it could over time follow the pieces to make the whole."*
> — Patrick, the acceptance test for the whole project

**It has never been executed. Not once.**

Everything to date has been measured **by proxy** — anchor coverage, drawer
counts, probe recalls. Those are *inputs* to the test, not the test.

`holdout` eval hooks remain at **0 files**, exactly as drawer #212 reported.
It is the oldest unbuilt thing in the project.

1. **Build the holdout harness.** A fixed set of questions with known-correct
   drawer ids, answerable from the store alone.
2. **Run it with a deliberately weak model.** Haiku, or a local Gemma. The point
   is the **floor**, not the ceiling.
3. **Measure the gap between weak and strong.** If a cheap model scores near a
   good one, the store is doing the work. If not, that gap *is* the roadmap —
   and it will point at retrieval quality, which has also never been tested.
   The drawer-size hypothesis from `plans/field-report-2026-08-02.md` is still
   untested: a known-correct drawer ranked **7th**, with every hit clustered
   between 1.03 and 1.15.

**Done when:** there is a number for *"how well can a weak model reassemble the
whole"*, tracked over time the way coverage is.

---

## P9 — CodeGlass alongside Cairntir *(carried forward)*

Unchanged from P3 of the prior plan. Patrick's ruling, 2026-08-05:
**companion-first** (*"i want it to be functional with cairntir is the
priority"*), standalone packaging second (*"maybe someone just wants codeglass
only"*). The never-built half is **emergent pattern discovery from the vault
link graph** — neither `obsidian.py` (projection out) nor `vault_sync.py`
(import in) touches link structure. The `codeglass-site` / `codeglass-dist`
parent-folder question is still Patrick's to decide (drawer #282).

---

## Sequencing, and why

1. **P4** — the only item containing a defect live in shipped code today.
2. **P5** — small, and until it is done two of this repo's trusted gates are decorative.
3. **P6** — cheap, and it tells you whether P8 has anything to measure.
4. **P7** — before any more parallel-agent work. The budget already bit once.
5. **P8** — schedule it deliberately, do not squeeze it in. It is the only item that tests the actual goal rather than a proxy.
6. **P9** — last. A new product surface, not a correction.

---

## House rules — do not re-derive these

- **Land on `main` through a pull request.** Zero reviews required.
- **Every exception typed and surfaced.** No silent `except: pass` — CI scans for it.
- **The gate**, all must pass before commit:
  `ruff check src tests scripts` · `ruff format --check src tests scripts` ·
  `mypy --strict src` · `check_no_silent_except.py` ·
  `check_landed_commitments.py` · `pytest -q`
- **Never write an unverified anchor.** A wrong path silently poisons structural
  recall and is worse than none. Verify against the repo on disk; report what
  you cannot verify rather than guessing.
- **Live store mutations: backup → sandbox → verify → live.** Backup with
  sqlite's `Connection.backup()`, **not** a file copy — the DB is WAL-mode and a
  plain copy can miss committed pages. Rehearse under `CAIRNTIR_HOME`, verify
  there, then apply. This has worked five times; do not shortcut it.
- **Verify with something independent.** A checker that imports the code it is
  checking will agree with that code's mistakes. The anchor backfill was
  confirmed by a checker that deliberately does not import Cairntir's resolver.
- **Ask before mutating existing rows.** Appending is safe; rewriting is not.
- **Never delete a commitment assertion to make the build green.** That is the
  defect this repo exists to prevent, wearing a disguise. Leave it red and say so.
- **Write commitments only for what has landed.** A green build must mean the
  code is there, not that someone intended it to be.

---

## Staged commitments

**Deliberately not a `cairntir-commitments` block.** Every assertion below is
false today, and writing a commitment before keeping it is the exact defect this
repo exists to prevent. Promote each line into the live block in
`plans/2026-08-04-honest-and-whole.md` **as it lands**.

```
# P4 — seams
symbol src/cairntir/handoff.py settled_prediction_ids
test   tests/integration/test_seams.py test_settling_a_prediction_closes_it_in_handoff
file   scripts/check_seams.py

# P5 — checks where the data is
param  src/cairntir/cli.py doctor_cmd:gate
test   tests/unit/test_doctor.py test_gate_fails_on_a_damaged_store

# P6 — deltas in practice
test   tests/integration/test_seams.py test_settle_writes_a_delta_a_later_session_can_read

# P8 — the acceptance test
file   evals/holdout/questions.jsonl
symbol src/cairntir/evals/holdout.py score
test   tests/integration/test_holdout.py test_weak_model_floor_is_tracked
```

---

## The one-paragraph version

Cairntir now stores well, connects well, and can be told it was wrong. What it
cannot yet do is **notice when two of its own parts stop agreeing** — which is
how a prediction can be settled and still counted as open, in shipped code,
today, with every test passing. Fix that; move the two decorative CI gates to
where their subjects actually live; find out whether anyone ever writes a
`delta`; get the per-session cost under control before spending more of it; and
then, finally, **run the test the whole project exists to pass** — with a bad
model — and write down the number.
