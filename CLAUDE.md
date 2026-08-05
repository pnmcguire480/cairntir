# CLAUDE.md — Cairntir

> 🔄 **UPDATE EVERY SESSION**
> This is the first file any AI agent reads. Out-of-date info here cascades into bad decisions everywhere.

---

## Project Identity

- **Name:** Cairntir
- **Pronunciation:** *CAIRN-teer*
- **Etymology:** Cairn (stacked waypoint stones marking a path) + Palantir (seeing-stone across time and distance). A stack of stones that sees across time.
- **One-liner:** Memory-first reasoning layer for Claude Code. Kills cross-chat AI amnesia.
- **Owner:** Patrick McGuire (@pnmcguire480)
- **License:** MIT
- **Repo:** `c:\Dev\Cairntir\` — https://github.com/pnmcguire480/cairntir
- **Stage:** **v1.3.0 published** 2026-08-02 (PyPI + GitHub release, both artifacts attested). Latest on PyPI is `1.3.0`; the five live releases are 1.0.0, 1.1.0, 1.1.2, 1.2.0, 1.3.0. **1.0.1 and 1.1.3 were changelogged but never tagged and never published** — see `scripts/check_release_tags.py`, which now fails the build if that happens again. (Note: `v1.1.1` was tagged and GitHub-released but its PyPI publish failed, so it is not on PyPI.)

---

## The North Star

> **Cross-chat AI amnesia is the problem. Everything Cairntir does serves killing it.**

A fresh Claude Code chat opened in `c:\Dev\Cairntir\` on day 30 should feel like walking into a lit room. No re-briefing. No lost decisions. No "what were we doing?"

This is the one test that matters. If a feature doesn't serve it, we don't build it.

---

## The Mythos

Cairntir is **step one** on a longer road. The road leads to:

**AI + grand-scale 3D printing + post-scarcity tooling.**

If we can model it, we can make it. If we can remember it, we can build it again. Cairntir is the memory layer for that future. Today it remembers code decisions. Tomorrow it remembers which printed structure worked, which failed, what the temperature was, what the grain direction was, what the next iteration should try. The memory of a civilization that prints its own thingamajigs and gives them away for free.

That's the destination. Today we build the foundation.

---

## What Cairntir Is

A **memory-first reasoning layer** with three ingredients:

1. **Verbatim persistent memory** — `sqlite-vec` backend, nothing summarized away, queryable by semantic + metadata.
2. **Minimal skill dispatch** — 3 skills total: `crucible` (epistemic stress-test), `quality` (audit), `reason` (memory-backed thinking loop). Everything else was cargo cult.
3. **One loop, not two commands** — a daemon + MCP server auto-captures and auto-restores. No init/wrapup ceremony.

**Taxonomy:** Wings (projects) → Rooms (topics) → Drawers (verbatim entries). Four retrieval layers: identity / essential / on-demand / deep.

## What Cairntir Is NOT

- Not BrainStormer v2 — it's a distillation, not a port
- Not a MemPalace fork — it borrows concepts, not code
- Not a chatbot, not a code-completion tool, not an agent runtime
- Not a SaaS — MIT, open source, local-first
- Not configurable — opinionated, one way to do things

---

## Lineage

Cairntir is the distillation of two predecessors:

- **BrainStormer** (`c:\Dev\SKILLS\BrainStormer\`) — Patrick's prior attempt. Great vocabulary (Crucible, Quality/PALADIN, agent species, ETHOS) but Frankenstein runtime: 224 silent `except: pass` blocks, dead license code, "architecture of a learning system but runtime of a static scaffolder." See `lineage/brainstormer/` and `docs/lineage/brainstormer.md`.
- **MemPalace** (https://github.com/milla-jovovich/mempalace) — 96.6% LongMemEval R@5. Brilliant memory taxonomy (wings/rooms/drawers, 4-layer retrieval) but no reasoning layer. We borrow concepts, not code. See `docs/lineage/mempalace.md`.

**The merge:** MemPalace gives us memory. BrainStormer gives us reasoning vocabulary. Cairntir is both, simplified, opinionated, and shipped.

**Under assessment (not yet adopted):** `plans/next-map.md` scopes two further
sources — [code-review-graph](https://github.com/tirth8205/code-review-graph)
(structural anchors) and [mattpocock/skills](https://github.com/mattpocock/skills)
(shared-vocabulary glossary) — and states the binding attribution contract for
every future source: concepts never code, a lineage doc before a line of code,
credit by name, never restate their benchmarks as ours, never position as
"better than," and say plainly when their tool is the better fit. Full
assessment of code-review-graph is in drawer #173.

**Attribution status: both lineage docs are written**, each before a line of the
code it credits, per contract rule 2. `docs/lineage/mattpocock-skills.md` and
`docs/lineage/code-review-graph.md`, both 2026-08-01. `recall_for_change` is
therefore unblocked. Both docs also carry a **correction to Cairntir's own
earlier assessment** of the source — we had been unfair to each in a different
way, and the corrections are recorded rather than quietly edited away. Read a
source before characterizing it.

---

## Recipes (post-v1.0)

Recipes are repeatable protocols that chain the existing skills + memory
layer into named disciplines. **The three-skill core is locked.** Anything
that would have been a fourth skill becomes a recipe instead. Recipes live
under `docs/recipes/` and earn their place by use, not by governance.

**Shipped:**
- **Signal Reader** — five-step structural analysis of AI news events.
  Split the headline story from the structural story, name the constraint
  that moved, project gains/losses, crucible stress-test, commit as a
  prediction-bound drawer in a `signals` wing. Nate-style one-shot reads
  become compounding reads because Cairntir's prediction-bound drawers
  close the loop over months. See `docs/recipes/signal-reader/`.
  Plan: `plans/signal-reader.md`.
- **Decision Replay** — closes the prediction window on a past
  decision. `cairntir replay <id>` walks the supersedes chain, pulls
  the leaf's claim + predicted_outcome, runs one reason-loop step
  with `supersedes_id` set, drops a Crucible marker, and writes the
  new prediction-bound drawer onto the chain leaf. The first recipe
  that exercises *all three* v1.1 synergy components — recipe
  runtime + temporal walk + production reason loop — at once. See
  `docs/recipes/decision-replay/`.

---

## Current State

### Last Session

- **Date:** 2026-08-05 (**full audit + the stacked work finally merged — #36 and #37 landed**)
- **What was accomplished:** Patrick commissioned a fresh-eyes full audit. The
  headline finding: **the build on `main` is fully green** — ruff, `ruff
  format`, `mypy --strict` (49 files), silent-except, release-tags,
  landed-commitments, store-health, `uv build`, and 563 tests at 82.26%
  coverage all pass locally and in CI, and **v1.3.0 is published on both PyPI
  and GitHub**. The build was never broken; the work was *stuck*. Two green
  pull requests — **#36 (`cairntir vault-sync`) and #37 (handoff surfaces
  unsettled predictions)** — passed all 14 checks but were `CONFLICTING` on one
  file, `plans/2026-08-04-honest-and-whole.md`, because each predated PR #35
  and a naive merge would have deleted #35's landed commitments from the
  ledger. Resolved by reconciling the `cairntir-commitments` block to the
  **union** (47 commitments across 3 documents, all landed), re-basing each
  branch onto `main`, re-running the full gate green, and merging both. Also
  closed the five stale failing dependabot PRs (#1–#5, from April) and
  corrected this stale session block. **The record also skips the 2026-08-02 →
  08-04 sessions that were never logged here**: PRs #33–#35 merged and v1.3.0
  shipped in that gap. The recurring failure mode to watch is *work lands green
  but never merges*.
- **Next session:**
  1. **The embedder bake-off** remains the highest-value open item; it needs
     Patrick awake for the live reindex.
  2. **Still-not-landed in the plan ledger:** P1 item 4 (retire the `untrusted`
     migration stamp) and P2 item 1 (write-time guard in `DrawerStore.add()`).
     See the staging block in `plans/2026-08-04-honest-and-whole.md`.
  3. **Housekeeping:** remove the redundant pipx `cairntir 0.1.0` install
     (shadowed by the healthy system editable install); decide whether to
     re-open the GitHub Actions dependabot bumps that were just closed.

- **Prior session — 2026-08-02 (the research landed as code — four PRs opened):**
- **Date:** 2026-08-02, overnight (**the research landed as code — four PRs open, none merged**)
- **What was accomplished:** Patrick commissioned the research, read it, then
  went to sleep asking for the fixes and upgrades to be implemented and a
  release prepared. Four stacked pull requests, all green on 14/14 checks,
  **none merged** — merging was blocked by a permission gate, so `main` is
  untouched and the editable install still runs pre-handoff code until Patrick
  merges them.
  - **#25 — the two research documents.** The finding that reorders the others:
    the oldest idea in this lineage is not memory, it is **controlled context**.
    BabyTIEROS had always-load / load-when-relevant / never-load before any
    vector store existed; the 2026-07-27 audit found the policy survived and the
    budget did not, wrote the fix into the v1.2 core list, and **v1.2 shipped
    without it.** Patrick's Token Saver spec is the third independent
    rediscovery of the founding invariant of his own lineage.
  - **#26 — `cairntir_handoff(wing)`.** Finding 5, the stated goal: carry a chat
    across sessions with no `HANDOFF.md`. One call, one composed brief, a hard
    `budget_chars` ceiling. **Whole drawers or none** — anything that does not
    fit is named with its id and size instead of truncated. Measured on a copy
    of the live store: 7,737 → 4,261 tokens for `cairntir` (-44%), 8,201 → 3,880
    for `detroit-clone` (-52%), and the drawers it returns can actually answer
    something. Deterministic, so it does not disturb a host's prompt cache.
  - **#27 — `scripts/check_landed_commitments.py`.** The anti-pattern killer,
    and the only candidate addressing a defect present in all four generations:
    *we do not verify that a commitment landed.* Plans carry a fenced
    `cairntir-commitments` block asserting a file, symbol, **function
    parameter**, or test exists; CI fails if any is absent. `param` is the kind
    that earns its place — `session_start` existed the whole time the v1.2
    budget was outstanding, so only a parameter-level check catches it.
  - **#28 — `cairntir cost <wing>`.** Closes **P5**, the one primitive the
    2026-04-03 harness audit scored MISSING at risk HIGH. Reports the tool
    catalog (2,307 tokens across 19 tools, paid every session in every host),
    `session_start`, `handoff`, and drawer sizes against the embedder window.
    Honest in both directions: `handoff` is *not* universally cheaper and the
    report says "more expensive" when that is true. Plus the determinism suite
    protecting the 90% prompt-cache read discount.
  - **Deliberately not done: the embedder change.** `cost` now measures that 29%
    of `cairntir`-wing drawers exceed the ~2,048-char window, but chunking or
    swapping the model **requires reindexing the live store**, and this
    project's own rule (drawers #182, #210) is rehearse-on-snapshot with
    explicit approval first. Not something to do while the maintainer sleeps.
  - **A correction to the research:** practical upgrade 4 claims model capture
    "remains unbuilt." It is wrong. `--model`, `CAIRNTIR_MODEL`, and
    `WriteProvenance.create(model=...)` are all wired. No *host* sets it, which
    is a narrower and different problem. See `plans/release-1.3.0.md`.
  - **Status:** 525 tests passing, 82.62% coverage, ruff clean, format clean,
    mypy --strict clean across 49 source files, silent-except clean, mkdocs
    --strict clean, 13 commitments checked across 2 documents.
- **Next session:**
  1. **Merge #25 → #26 → #27 → #28, in that order.** They are stacked; merging
     out of order produces confusing diffs. Until they merge, none of this is in
     the editable install every AI host loads.
  2. **Then cut 1.3.0** — the number, its justification, and the exact sequence
     are in `plans/release-1.3.0.md`. It is a MINOR because a new MCP tool is
     `docs/release-cadence.md`'s own example of one, and because a user would
     need the changelog to know a new tool exists. Not a patch. The tag stays a
     human gate.
  3. **Then the embedder bake-off** — practical upgrade 1. Now that the cost is
     measured, this is the highest-value remaining item, and it needs Patrick
     awake for the live reindex.

- **Prior session — 2026-08-02 (structural recall actually works now — two defects found in live use):**
- **Date:** 2026-08-02 (**structural recall actually works now — two defects found in live use**)
- **What was accomplished:** Cairntir was used as the memory layer for a real
  session on another project (`detroit-clone`, bite B08), and the experience was
  written up as a field report rather than a feeling. Two confirmed defects came
  out of it, both now fixed and both found only because the tool was used in
  anger. The report is `plans/field-report-2026-08-02.md` and it is the driving
  document for the next several sessions.
  - **Anchors were accepted at write and rejected at read (PR #22).**
    `cairntir_remember` declared `metadata` as a bare `{"type": "object"}` — no
    properties, no description, no validation — so a writing agent never saw the
    anchor contract and guessed a list of path strings where `parse_anchors`
    requires a list of objects. The store accepted it and the failure surfaced
    weeks later, in a different tool, in a different session. **Structural recall
    was 0% functional in the `detroit-clone` wing** while reporting itself as
    installed and working. Fixed by publishing the anchor schema in the tool
    description *and* validating on write. The reader stays strict on purpose:
    accepting two shapes is exactly the drift Cairntir exists to oppose.
  - **The repair tool could not repair the damage (PR #23).** `add_anchors` is
    append-only and validates the *merged* list, so on a drawer whose existing
    anchors are the string form it raises before it can append. Drawer #182's
    backfill procedure had worked only because those drawers had *no* anchors.
    New `DrawerStore.repair_anchors` + `cairntir anchor <id> --repair` coerce the
    one case that is not a guess — a bare string could only have meant a path —
    and refuse anything else loudly.
  - **Live store repaired.** #199 and #204–#207 in `detroit-clone`, 33 anchors,
    rehearsed first on a read-only snapshot. Timestamped backup taken beside the
    live DB (`cairntir.db.backup-20260802T072414Z`). After: 210 drawers before
    and after, every drawer's content SHA-256 byte-identical, zero lost, zero
    malformed warnings. Verified through the MCP tool, not just the CLI.
  - **`AGENTS.md` rewritten as a pointer to this file.** It had drifted into a
    stale fork — still claiming the repo was local-only with a GitHub push
    pending, four days after v1.2.0 published. Two 600-line near-duplicates will
    always drift, so it is now thin: identity, the stable Must Do / Must Not
    rules, and the managed policy block. Everything that moves lives here.
  - **Root cause worth naming.** Three separate features were dead or unused for
    one reason: **the tool descriptions are the only documentation a writing
    agent ever reads, and they omitted the contracts that mattered.** Anchors
    were malformed, predictions were never written (0 in the entire corpus), and
    drawers are written 3–8k characters covering ten topics each. Fixing tool
    descriptions is probably the cheapest correctness work available.
  - **Status:** 466 tests passing, 82.04% coverage, ruff clean, mypy --strict
    clean, silent-except scan clean. PRs #22 and #23 both merged with 14/14
    checks green.
- **Next session:** two tracks, in order.
  1. **Finish the field report.** Finding 5 (`cairntir_handoff(wing)` — one call,
     one composed brief, no ranking) is the stated goal and is a composition
     problem, not a retrieval one. Then finding 2 (token cost — measure first),
     finding 3 (test the drawer-size hypothesis before touching retrieval), and
     finding 4 (predictions, nearly free while tool descriptions are being edited).
  2. **The research project Patrick asked for on 2026-08-02:** recover features
     already proposed but never built across Cairntir *and* BrainStormer history,
     survey current AI trends / workflows / repos, hunt for blind spots, and
     produce **10 upgrade recommendations for consideration, not implementation.**
     Explicitly gated behind track 1.

- **Prior session — 2026-07-31 (v1.2.0 SHIPPED — and the release gap that hid 1.1.3 for three months):**
- **Date:** 2026-07-31 (**v1.2.0 SHIPPED — and the release gap that hid 1.1.3 for three months**)
- **What was accomplished:**
  - **v1.2.0 is public.** Tag `v1.2.0` on `eaad14b`; `main` fast-forwarded from
    `b7f384e` (the RC branch was a strict superset — 6 ahead, 0 behind — so no
    merge commit). Release run `30675705402` green across all four jobs. Live on
    PyPI (`1.2.0` is latest) and as a GitHub release, both artifacts carrying
    build-provenance attestations. Pre-flight CI run `30427672275` was green on
    *exactly* the tagged commit: 9-job matrix (ubuntu/macos/windows ×
    py3.11/3.12/3.13) plus lint, LongMemEval R@5 gate, and package build.
  - **Found: 1.0.1 and 1.1.3 were never released.** Both were committed and
    changelogged; neither was ever tagged; the release workflow fires only on a
    pushed `v*.*.*` tag, so neither reached PyPI. Commit `325547c` — the
    cold-start fix taking first-run from ~12 min to 1.4s — sat unpublished from
    2026-05-03 to 2026-08-01 while every `pip install cairntir` kept resolving
    to 1.1.2 and hanging. Downloads at the time of discovery: 33/month, 4/week,
    0/day. This is a mechanical cause of the "no visibility" problem that
    precedes any marketing question. Verified `325547c` is an ancestor of
    `eaad14b`, so 1.2.0 closes it.
  - **Guarded against recurrence.** New `scripts/check_release_tags.py` fails
    when a released changelog header has no matching tag. The in-flight
    `pyproject` version is exempt (the header is written before the tag, which
    is the normal order) and the two historical gaps are recorded in
    `KNOWN_UNRELEASED` rather than hidden. Wired into the CI lint job and the
    release verification gate; both now check out with `fetch-depth: 0`.
    `tests/unit/test_release_tags.py` covers it and skips on shallow clones so
    forks fail on defects, not on clone depth. CHANGELOG entries for 1.0.1 and
    1.1.3 now say plainly that they were never released.
  - **Deliberately NOT done:** retroactively tagging 1.0.1/1.1.3. Pushing either
    tag would re-fire the release workflow against a stale commit and publish a
    months-old build. They stay changelog-only, annotated.
  - **RESOLVED 2026-08-01 — releases go through a pull request.** The `main`
    push had reported `Bypassed rule violations for refs/heads/main` because it
    went straight to `main`, skipping the PR. The rule is not onerous: it wants
    a PR plus `Build Package` and `LongMemEval R@5 Gate`, and **zero approving
    reviews**. For a solo maintainer that is one click. PR #16 was merged
    through it with no bypass. Go through the branch, never around it — `main`
    is what the release workflow builds from, so the full matrix must be green
    before `main` moves. The rule stays as configured.
  - **Memory:** drawer #173 (code-review-graph lineage assessment, deferred),
    drawer #174 (the release + the 1.1.3 correction, essential layer).
- **Next session:** `plans/next-map.md` — the ethically-scoped plan drawing on
  code-review-graph and mattpocock/skills. Attribution and lineage docs come
  before any code.

- **Prior session — 2026-07-29 (v1.2.0 live three-host acceptance complete):**
- **Date:** 2026-07-29 (**v1.2.0 live three-host acceptance complete**)
- **What was accomplished:** Closed the modernization arc at a safe,
  reviewable release boundary.
  - **Schema v6 trust receipts:** every new write records immutable host,
    model, session, capture path, trust, visibility, sensitivity, validity,
    client, and tool-surface provenance. Legacy rows migrate as explicitly
    untrusted and migrations create a timestamped backup first.
  - **Crash-safe workflows:** nested transactions/savepoints and durable
    `execute_once` receipts make Reason, recipes, replay, import, daemon
    capture, and CodeGlass all-or-nothing and duplicate-safe.
  - **Poisoned-memory boundary:** recalled content is JSON-encoded evidence
    with `instruction_authority=none`, trust/provenance, and suspicious prompt
    signals. Stored text cannot silently become agent policy.
  - **Three-host continuity:** Codex, Cursor, and Claude Code MCP launchers
    identify their host; an automated shared-store fixture proves verbatim
    cross-host recall with preserved model/session provenance.
  - **Functional growth:** repeated Reason episodes can propose calibrated
    Discovery Ledger candidates with confidence, observation count, baseline,
    counterexamples, fingerprint, and next test. Automation cannot promote
    itself. `cairntir calibration` reports outcomes and uncertainty.
  - **CodeGlass + Anthropicer:** evidence-cited five-part walkthroughs,
    immediate/delayed teach-back, retention tracking, learning-log candidates,
    and one-way Obsidian projection that preserves user notes and excludes
    secret memories. The actual vault is `C:\Dev\Anthropicer`; existing
    drawer projections live under `cairntir-sync/drawers/`.
  - **Lineage/public stability:** BabyTIEROS → BrainStormer → Cairntir outcomes
    are documented; no lineage artifact, three-skill behavior, or public v1
    contract was removed. MCP now exposes 17 tools.
  - **Migration proof:** a WAL-safe rehearsal and the explicitly approved live
    reindex both preserved the complete 123-drawer corpus byte-for-byte at the
    logical table level (SHA-256
    `2292d830767a60fa59fcd550f52aa16c51797873f62bfbb5bd4a3fb513515591`).
    The reindex itself was verified at 123 vectors, dimension 384, generation
    `3f7b6b69-44d2-48e0-96ea-b56cb8f04115`; SQLite, foreign keys, and durable
    workflows are clean. The required final Quality write then appended audit
    drawer #124; a follow-up doctor check reports 124 drawers / 124 vectors in
    the same verified generation. Timestamped backups remain beside the live
    database.
  - **Live host acceptance:** real Codex #125, Cursor #126, and Claude Code
    #130 writes formed one exact-recalled chain through the live store.
    Immutable receipts preserve `host=codex|cursor|claude`, unique sessions,
    MCP tool surface 17, source links, complete content, and hashes. Claude's
    first opaque request refusal positively exercised the poisoned-memory
    boundary. A Claude Desktop mismatch (#127) and two Windows test-harness
    truncations (#128/#129) remain append-only failure evidence rather than
    being rewritten as passes. Runtime model remains explicitly `unknown`
    because current hosts do not disclose it to the MCP subprocess.
  - **Release engineering:** all external GitHub Actions are pinned to immutable
    commits; release verification now precedes build; provenance attestation
    and PyPI trusted publishing are wired; manual dispatch cannot publish.
    Version metadata, lockfile, plugin manifest, changelog, and release notes
    agree on `1.2.0`.
  - **Installed-wheel acceptance:** found and fixed a real Windows
    `cp1252` help-rendering crash. A fresh isolated install imports as 1.2.0,
    renders redirected help, and discovers all three bundled recipes outside
    the source tree.
  - **Status:** all 372 tests passing, 81.12% coverage, Ruff clean,
    mypy --strict clean across 46 source files, silent-exception scan clean,
    strict docs clean, workflows parse, sdist/wheel build successfully, and
    final Quality drawer #131 records `96/100 — SHIP IT` to RC/remote CI.
    Post-audit doctor reports 131 drawers / 131 vectors with clean SQLite,
    foreign keys, and durable workflows.
- **Next session:** review and push the release-candidate branch; wait for
  remote CI on all supported platforms; only then create `v1.2.0`, which
  intentionally triggers publishing. After release, add honest runtime-model
  discovery where hosts expose it, then continue the Evolving Mind through
  contextual usefulness feedback, strategy holdouts, and longitudinal proof.

- **Prior session — 2026-05-08 (Decision Replay — synergy stack closure):**
- **Date:** 2026-05-08 (**Decision Replay — synergy stack closure**)
- **What was accomplished:** First recipe to exercise *all three* v1.1
  synergy components together. The cold-start patch series (1.1.0 →
  1.1.3) ate four days; once 1.1.3 was confirmed in practice
  (drawer #95, 2026-05-07), this session completed the synergy stack
  by writing the recipe that uses recipe runtime + temporal walk +
  production reason loop in one invocation.
  - **`cairntir replay <id>`:** new CLI command. Walks the supersedes
    chain from `<id>`, pulls the leaf's claim + predicted_outcome
    into a `ManualProposer`, prompts for the observed outcome and a
    verdict, runs the Decision Replay recipe with `supersedes_id`
    set to the leaf id. Output: a new prediction drawer with
    `supersedes_id == leaf_id`, a new observation drawer
    superseding the new prediction, a Crucible marker drawer, and a
    seed drawer in `replays/decision-replay`. Zero network calls.
  - **`docs/recipes/decision-replay/`:** bundled recipe.
    `recipe.toml` declares three inputs (`decision_drawer_id`,
    `current_evidence`, `horizon_months`) and the two-skill chain
    `["reason", "crucible"]`. README documents the protocol,
    anti-patterns, and how it closes the loop on Signal Reader
    outputs. Discoverable via `cairntir recipe-list`.
  - **`ReasonLoop.step(supersedes_id=…)`:** non-breaking extension.
    The reason loop now accepts an optional `supersedes_id` keyword;
    when supplied, the new prediction drawer carries that pointer.
    Default (`None`) preserves v0.6 semantics. Existing callers
    unaffected.
  - **`RecipeRunner.run(contract, inputs, supersedes_id=…)`:**
    matching extension at the recipe layer. Threads the pointer into
    the reason step when the chain includes `reason`.
  - **Tests added:** 7 — two for the new `ReasonLoop.step` modes,
    two for `RecipeRunner` with/without `supersedes_id`, one for
    bundled-recipe discovery, four for the CLI replay command (happy
    path + three error paths).
  - **Status:** 250 tests passing, 83% coverage, ruff +
    mypy --strict clean, silent-except scanner clean.
- **Next session:** outstanding synergy work per `docs/roadmap.md`
  Road to 2.0:
  - **Calibration dashboard** (`cairntir calibration --wing X`) —
    becomes load-bearing now that Decision Replay produces
    prediction/observation pairs across multiple chains. Read-only
    aggregates over prediction-bound drawers: % predictions
    confirmed, mean belief mass per wing, contradictions surfaced
    by `consolidate.detect_contradictions`. Stdlib-only, no new
    deps.
  - **Cross-wing timeline mode** — extend the existing
    `cairntir_timeline` MCP tool with an optional all-wings flag so
    "what was happening across every project on date X" becomes one
    call.
  - **Local-AI proposer** (Gemma via llama.cpp/Ollama) — bigger
    lift, defer until calibration shows the recipe shapes that
    actually pay off.
  - **v1.4 file-based team sync** — once the local recipe pipeline
    is well-exercised.

  Not committed yet — pick whichever is most pressing in the moment.

- **Prior session — 2026-05-07 (v1.1.3 cold-start fix confirmed):**
- **What was accomplished:** v1.1.3 (shipped 2026-05-03, defaulting
  to fastembed and dropping torch from the MCP hot path) confirmed
  in practice four days post-ship. Drawer #95 in `cairntir/journey`
  records the closure, supersedes #94 (the ship drawer), carries the
  prediction-bound metadata `claim` / `predicted_outcome` /
  `observed_outcome`. The cold-start arc — five prior patch commits
  that chased symptoms — is finally closed.

- **Prior session — 2026-04-08 (v1.0.0 — Library Extraction, shipped):**
- **What was accomplished:** v1.0.0 locked the seam. The full round-table
  committed arc from v0.2 through v0.6 is now the pre-v1.0 history,
  and today's session graduated Cairntir from "a tool" to "the thing
- **What was accomplished:** v1.0.0 locked the seam. The full round-table
  committed arc from v0.2 through v0.6 is now the pre-v1.0 history,
  and today's session graduated Cairntir from "a tool" to "the thing
  other tools store their memory in."
  - **Curated public surface:** `cairntir.__init__` now re-exports
    *only* protocols (`Store`, `EmbeddingProvider`, the four
    reason-loop ports), frozen value types (`Drawer`, `Layer`,
    `Hypothesis`, `Experiment`, `Outcome`, `BeliefUpdate`), typed
    exceptions (including new `CairntirDeprecationWarning`), and
    `__version__`. 24 names total, sorted, snapshot-tested.
  - **`cairntir.contracts` module:** new `Store` Protocol captures
    the full mutation + query surface DrawerStore has grown over six
    phases. Runtime-checkable so duck-typed impls pass isinstance.
  - **`cairntir.impl` namespace:** `DrawerStore`,
    `HashEmbeddingProvider`, `SentenceTransformerProvider`,
    `Retriever`, `RetrievalResult`, `ReasonLoop`, `SCHEMA_VERSION` —
    all reserved-right-to-change.
  - **Deprecation policy:** `CairntirDeprecationWarning` subclass of
    `DeprecationWarning`. Public surfaces must emit it for two minor
    releases before removal. No silent removals, ever.
  - **Contract suite:** `tests/contract/test_store_contract.py` runs
    14 protocol-level invariants against DrawerStore via a
    parametrized factory fixture. Every future Store impl drops into
    the list and inherits the whole battery.
  - **Property tests:** `tests/property/test_taxonomy_properties.py`
    uses Hypothesis to check that valid identifiers always round
    trip, whitespace content is always rejected, belief_mass always
    survives construction, and every Layer enum value is preserved.
    `hypothesis` added to dev deps.
  - **Public-API snapshot:** `tests/unit/test_public_api.py` fails
    fast on any `dir(cairntir)` drift (filtering submodules and the
    `from __future__` `annotations` sentinel). Also asserts
    `__all__` matches and `__version__.startswith("1.")`.
  - **Migration fixtures:** `test_migration_from_v2_database_*` and
    `test_migration_from_v3_database_*` hand-build pre-v4 databases
    with raw SQL and verify the forward-only ALTER TABLE chain
    upgrades them losslessly. With the existing v1→v4 test, every
    prior schema version now has a fixture kept in tree forever.
  - **Version bump:** `pyproject.toml` and `.claude-plugin/plugin.json`
    to `1.0.0`; CHANGELOG entry written.
  - **Deferred past v1.0:** splitting the CLI / MCP server / daemon
    into separate distributions is noted as follow-on work. Their
    modules still ride in the main package today; the protocol seam
    is the stable thing, and the concrete packaging story can shift
    without a breaking change.
  - **Status:** 138 tests passing, 88% coverage, ruff + mypy --strict
    clean, silent-except scanner clean, public-API snapshot green.
- **Next session:** v1.1 — Reach. Published to GitHub 2026-04-14 at
  https://github.com/pnmcguire480/cairntir with 19 topics and the
  v1.0.0 release cut. Next work is the Road to 2.0 committed in
  `docs/roadmap.md`: (1) PyPI publish so `pip install cairntir` works,
  (2) the amnesia blog post, (3) a reference Blender MCP plugin to
  prove the horizon thesis, (4) Awesome-MCP + LongMemEval submissions,
  (5) fix whatever the first external users break. v1.2 then lands
  the production Reason loop (ClaudeProposer + SandboxRunner) so
  recipes like Signal Reader become one-command instead of
  seven-step-walkthrough. Do not re-litigate the roadmap.

- **Prior session — 2026-04-08 (v0.6):**
- **What was accomplished:** v0.6 landed. New `cairntir.reason` package
  exposes the Reason skill as a *library*: four runtime-checkable
  Protocol ports (`HypothesisProposer`, `ExperimentRunner`,
  `BeliefStore`, `MemoryGateway`) and a pure `ReasonLoop.step()` that
  orchestrates one predict→observe→update cycle without importing
  sqlite, networks, or LLMs. Production wiring lives outside the
  library; the Reason skill's prose still drives the human contract.
  - **Model:** frozen dataclasses `Hypothesis`, `Experiment`, `Outcome`,
    `BeliefUpdate` in `cairntir.reason.model`. Stdlib-only.
  - **Ports:** four protocols in `cairntir.reason.ports`, all
    `@runtime_checkable` so fakes pass isinstance without inheritance.
  - **Loop:** `ReasonLoop.step(question, wing, room)` writes a
    prediction drawer (v0.2 contract: claim + predicted_outcome), asks
    the runner for an outcome, writes an observation drawer that
    supersedes the prediction with observed_outcome and a non-empty
    `delta` iff the prediction failed, then nudges the belief store
    (+1 on success, -1 on failure). Returns a `BeliefUpdate`. Two
    drawers per step, always, even when the runner fails. Verbatim
    is the floor; a failed step is not a skipped step.
  - **Contract enforcement:** empty `predicted_outcome` raises
    `ValueError` with "falsifiable prediction" message. Runner errors
    are never swallowed.
  - **Tests added:** 6 in `test_reason_loop.py` with dict-backed /
    counter-backed fakes: protocol conformance, successful step,
    failing step with delta + weaken, empty-prediction rejection,
    runner errors bubbling up, two-step mass accumulation.
  - **Status:** 115 tests passing, 88% coverage, ruff + mypy --strict
    clean.
- **Next session:** v1.0.0 — Library extraction. `cairntir.__init__`
  exposes ONLY protocols + dataclasses + exceptions (`Drawer`, `Layer`,
  `Wing`, `Room`, `Store`, `Retriever`, `EmbeddingProvider`, typed
  errors). Concrete impls move to `cairntir.impl.*`. CLI / MCP server /
  daemon split into separate distributions that import `cairntir`.
  Written deprecation policy with `CairntirDeprecationWarning`. Contract
  test suite every `Store` impl must pass. Property-based tests
  (Hypothesis) on taxonomy invariants and retrieval monotonicity.
  Public-API snapshot test that fails on `dir(cairntir)` drift.
  Migration tool with fixtures from every prior schema version. Tag,
  GitHub release, blog post. Do not re-litigate the roadmap.

- **Prior session — 2026-04-08 (v0.5):**
- **What was accomplished:** v0.5 landed. New `cairntir.portable` module
  speaks a versioned envelope format with sha256 content-addressing and
  optional HMAC-SHA256 signatures. Envelope shape: `format_version`,
  `content_hash`, `signature`, `provenance` (origin / exported_at /
  schema_version), and a `drawer` payload that strips local-only state
  (`id`, `access_count`, `last_accessed_at`) so portable drawers are
  born clean. `canonical_bytes()` produces sorted-keys UTF-8 JSON so the
  hash is deterministic across platforms and Python versions.
  - **Structural prohibition:** `ensure_no_external_urls(drawer)` scans
    content + metadata for `http://`, `https://`, `ftp://`, `file://`,
    `ssh://` and raises `ExternalUrlError` (subclass of
    `PortableFormatError`). Only `cairntir://` references are allowed.
    Export fails closed — a single violating drawer aborts the whole
    bundle before the file is written, so partial exports never happen.
  - **Transport-free:** `write_jsonl` / `read_jsonl` and
    `export_drawers` / `import_drawers` only speak the format. The
    module deliberately does not touch `DrawerStore` — gossip /
    torrent / git / USB / mailing list all work the same way.
  - **CLI:** `cairntir export <path> [--wing --room]` and `cairntir
    import <path>` wired on top of the existing store, verifying the
    content hash of every envelope before insertion.
  - **Tests added:** 21 in `test_portable.py` covering round-trip,
    deterministic hashing, hash-on-tamper, HMAC sign/verify, wrong-key
    rejection, unsigned-when-verified-fail-closed, format_version
    gating, every external scheme rejected by parametrize, JSONL
    reader/writer, and a full cross-store export→import that preserves
    claim/predicted_outcome/belief_mass across two separate sqlite
    files.
  - **Status:** 109 tests passing, 88% coverage, ruff + mypy --strict
    clean, silent-except scanner clean.
- **Next session:** v0.6 — Reason loop through clean ports.
  `cairntir.reason.model` (Hypothesis / Experiment / Outcome /
  BeliefUpdate) and `cairntir.reason.ports`
  (HypothesisProposer / ExperimentRunner / BeliefStore / MemoryGateway
  protocols). `ReasonLoop.step()` must be testable without LLMs,
  networks, or sqlite — production wiring lives outside the library.
  Do not re-litigate the roadmap.

- **Prior session — 2026-04-08 (v0.4):**
- **What was accomplished:** v0.4 landed. `Drawer` gained a
  `belief_mass: float = 1.0` field and the store migrated to schema v4
  (forward-only ALTER TABLE, `REAL NOT NULL DEFAULT 1.0`, backfilled
  for pre-v4 rows). Two new store methods — `reinforce(id, amount=1.0)`
  and `weaken(id, amount=1.0)` — adjust mass in-place and clamp at
  zero so a weakened drawer is punished, never deleted. New module
  `cairntir.memory.belief` exposes two pure functions:
  - `effective_distance(drawer, raw_distance)` folds the raw vector
    distance through `mass * (1 + delta_boost_if_surprise)` with a
    mass floor of 0.1 so zero-mass drawers stay retrievable at
    degraded rank.
  - `rerank_results([(drawer, distance), ...])` returns a new list
    sorted by effective distance, stable on ties, raw distance kept
    for caller inspection.
  `DrawerStore.search()` now takes `rerank_by_belief: bool = True` and
  calls the reranker by default. Opt out for pure vector order. The
  math is deliberately blunt — belief is a steering wheel, not an
  engine, and semantic closeness still dominates in doubt.
  - **Tests added:** 10 new tests in `test_belief.py` covering the
    scorer, the reranker's stable tie-breaking, reinforce/weaken mass
    clamping, missing-drawer errors, and an end-to-end store.search
    rerank that flips the top hit on identical-embedder queries.
  - **Status:** 88 tests passing, 90% coverage, ruff + mypy --strict
    clean.
- **Next session:** v0.5 — Portable Signed Format (anti-capture lock).
  Versioned, human-readable, signed interchange format for drawers.
  Content-addressed hashes; provenance as a first-class field.
  `cairntir export` / `cairntir import` over any substrate (USB, IPFS,
  git, mailing list). Structural prohibition: no drawer may reference
  a non-drawer URL. Do not re-litigate the roadmap.

- **Prior session — 2026-04-08 (v0.3):**
- **What was accomplished:** v0.3 landed in one pass. The store gained a
  v3 schema migration that adds `last_accessed_at` (backfilled from
  `created_at` for pre-v3 rows) and `access_count`, plus three new
  methods: `update_layer`, `stale_ids`, and a private `_touch` bumped by
  every `get()` and `search()` hit. That gives the forgetting curve its
  replay signal without touching the Drawer dataclass. A new module
  `cairntir.memory.consolidate` exposes three pure functions over the
  store:
  - `demote_stale(store, cold_after_days=...)` — drifts ON_DEMAND
    drawers untouched for N days to the DEEP layer. Idempotent.
    Demotion only, never deletion. Returns the demoted ids so the
    daemon can audit every pass.
  - `detect_contradictions(store, wing=...)` — groups drawers by
    normalized `claim`, flags pairs whose `predicted_outcome` or
    `observed_outcome` diverge. Never averages, never picks a winner,
    never mutates. Returns a list of `Contradiction` records.
  - `consolidate_room(store, wing, room, min_cluster=3)` — emits a
    derived ESSENTIAL drawer whose content is a verbatim concatenation
    with `[#id]` citations and `metadata.derived_from=[ids]`. Source
    drawers stay put. Idempotent for the same source set.
  - **Tests added:** 14 new tests across `test_consolidate.py` and
    `test_store.py` covering each function, idempotency, edge cases
    (missing outcomes, below-threshold clusters), and the touch/stale
    round trip.
  - **Status:** 78 tests passing, 89% coverage, ruff + mypy --strict
    clean, silent-except scanner clean.
- **Next session:** v0.4 — surprise and belief-as-distribution. Make
  `delta` a first-class retrieval signal (Room Prior residual).
  Retrieval distribution itself becomes the belief: successful uses
  raise drawer mass for a context, dead retrievals lower it. Bayesian
  bookkeeping over the verbatim corpus, no training pipeline. Roadmap
  is the plan; do not re-litigate it.

- **Prior session — 2026-04-08 (v0.2 kickoff):**
- **What was accomplished:** First cut of v0.2 shipped. Drawer schema
  gained five optional prediction-bound fields (`claim`,
  `predicted_outcome`, `observed_outcome`, `delta`, `supersedes_id`) as
  the AutoResearch Loop substrate. `DrawerStore` now carries a
  `SCHEMA_VERSION = 2` constant and a forward-only `_migrate()` pass
  that ALTERs pre-v2 tables in place and stamps `PRAGMA user_version`.
  Old rows deserialize with `None` for every new field; new inserts
  round-trip all five. Reason skill gained a mandatory Step 4.5
  ("predict") — no decision leaves the loop without a falsifiable
  claim + predicted outcome drawer. CI now runs the LongMemEval R@5
  subset as a separate `eval` job that fails on regression.
  - **Tests added:** `test_prediction_fields_round_trip`,
    `test_supersedes_chain_round_trips`,
    `test_migration_from_v1_database_preserves_old_rows` (hand-builds a
    v1-shaped DB, reopens through DrawerStore, checks idempotent
    re-migration).
  - **Status:** 65 tests passing, 89% coverage, ruff + mypy --strict
    clean, silent-except scanner clean.
- **Next session:** v0.3 — consolidation, forgetting curve,
  contradiction detector. Nightly consolidate pass clusters recent
  drawers and writes derived abstractions one layer up; replay-weighted
  demotion drifts stale drawers to a cold layer; contradiction detector
  flags, never averages. Do not re-litigate the roadmap.

- **Prior session — 2026-04-08 (round table, post-v0.1):**
- **What was accomplished:** Locked in the v0.1→v1.0 path. Eight-thinker
  round table (Karpathy, LeCun, Sutskever, Hinton, Fuller, Peter Joseph,
  Watts, Uncle Bob) reviewed the original Long Road. They converged hard
  on five themes that are now committed in `docs/roadmap.md` under "The
  Road to 1.0 — Round Table Edition":
  1. **Prediction-bound drawers** — `claim`, `predicted_outcome`,
     `observed_outcome`, `delta`, `supersedes_id` as the AutoResearch
     loop's substrate
  2. **Consolidation + forgetting curve** — sleep-cycle pass, demote
     unused, contradiction detector
  3. **Surprise as the load-bearing field** — delta is the gradient
     when there are no weights
  4. **Portable signed format** — anti-capture lock; format is the
     product
  5. **Cut Team Memory** — replicable beats shared
  Five new thinker subagents created in `c:\Dev\agents\agents\thinkers-named\science\`
  (ai-researchers/{karpathy, lecun, sutskever, hinton} +
  computing-pioneers/uncle-bob). Need `c:\Dev\agents\deploy.sh` to
  register them. The new roadmap shape: v0.2 prediction-bound drawers +
  eval-on-PR → v0.3 consolidation/forgetting/contradiction → v0.4
  surprise/belief-as-distribution → v0.5 portable signed format → v0.6
  Reason loop through clean ports → v1.0 library extraction
  (protocols-only public surface, split CLI/MCP/daemon into separate
  distributions, contract+property tests, public-API snapshot test,
  written deprecation policy, versioned migrations).
- **Next session — start here for the full auto run:**
  1. Read `docs/roadmap.md` "Road to 1.0 — Round Table Edition"
  2. Begin **v0.2**: prediction-bound drawer schema migration (add the
     five optional fields, version the schema, write forward-only
     migration with round-trip fixture test) + eval-on-PR (wire the
     LongMemEval subset into CI as a fail-on-regression gate)
  3. After v0.2 lands, march straight through v0.3 → v0.4 → v0.5 → v0.6
     → v1.0. The roadmap is the plan; do not re-litigate it.
  4. Each phase: small commits, conventional format, tests stay green,
     ruff + mypy --strict clean, no silent except.
  5. At v1.0: tag, GitHub release, blog post, update this Last Session.

- **Original v0.1.0 ship summary preserved below for posterity:**
  v0.1.0 shipped. All five phases landed in
  one arc — the memory layer, the MCP server, the three skills, and the
  one-loop daemon. The sniff test (a fresh chat in `c:\Dev\Cairntir\`
  understanding the project without re-briefing) passed manually before
  Cairntir's own memory was even built.
  - **Phase 1 — Memory Spike (`54fc5a2`):** `Drawer` / `Layer` taxonomy,
    sqlite-vec `DrawerStore`, `HashEmbeddingProvider` +
    `SentenceTransformerProvider`, 4-layer `Retriever`, LongMemEval eval
    skeleton. 29 tests, 81% coverage.
  - **Phase 2 — MCP Server (`8ba751a`):** six-tool `CairntirBackend`
    (transport-free) plus stdio `cairntir.mcp.server`. 39 tests, 82%.
  - **Phase 3 — Skills (`b36db98`):** distilled Crucible + Quality from
    the BrainStormer lineage, wrote the new Reason memory-backed
    thinking loop, bundled the `.md` files via `importlib.resources`,
    wired `backend.audit` / `backend.crucible` to the real skill text.
    45 tests, 83%.
  - **Phase 4 — Daemon (`b47e79b`):** spool-backed `CaptureDaemon` with
    atomic writes, quarantine-on-failure, and an asyncio poll loop.
    Retires init/wrapup ceremony. 54 tests, 85%.
  - **Phase 5 — v0.1.0:** version bump, changelog, Last Session, tag.
- **Next session:** open work for v0.2.0 is in `docs/roadmap.md`.
  Candidate first targets:
  - Real LongMemEval subset + sentence-transformers eval run (80% R@5 bar)
  - GitHub remote creation + initial push (still pending per Phase 0)
  - `cairntir` CLI surface (2 commands) on top of the backend
  - Claude Code plugin packaging

### What Works Right Now

- **Memory layer:** wing/room/drawer taxonomy over sqlite-vec, 4-layer retrieval,
  schema v6 with immutable write provenance and durable idempotency receipts.
- **MCP server:** 19 tools over stdio (`cairntir-mcp`, or `python -m cairntir.mcp.server`).
- **Handoff:** `cairntir_handoff(wing)` / `cairntir handoff <wing>` returns one
  composed brief under a hard character budget — protocol, recent deltas, open
  questions, and anchors for the files in play. Drawers come back **whole**;
  what does not fit is named with its id and size instead of being truncated.
  Measured against `session_start` on the live store: 7,737 → 4,261 tokens for
  `cairntir` (-44%) and 8,201 → 3,880 for `detroit-clone` (-52%), and the
  drawers it returns can actually answer something. Deterministic, so it stays
  prompt-cache friendly.
- **Three skills:** Crucible, Quality, Reason — bundled and loadable.
- **Recipes:** Signal Reader, Decision Replay, and the discovery/calibration ledger.
- **Structural recall:** `cairntir_recall_for_change(files=[…])` surfaces drawers
  anchored to the files a change touches. Anchors are validated on write, and
  `cairntir anchor <id> --repair` fixes drawers written before that guard existed.
- **CLI:** `cairntir` — recall, get, handoff, cost, anchor, recall-for-change,
  replay, export, import, calibration, doctor, register, and more.
- **Cost accounting:** `cairntir cost <wing>` reports what the read path costs —
  tool catalog, `session_start`, `handoff`, and drawer sizes against the
  embedder's ~2,048-char window. Closes P5. Measures Cairntir's own payload
  only; it is not a general token dashboard and must not become one.
- **Daemon:** `python -m cairntir.daemon` polls a spool dir and persists drawers.
- **Three-host continuity:** Claude Code, Codex, and Cursor read and write the
  same store with host/session provenance preserved.
- **Published:** PyPI (`pip install cairntir`) and GitHub releases, both with
  build-provenance attestations. Docs at
  https://pnmcguire480.github.io/cairntir/
- **Quality bar:** 466 tests passing, 82% coverage, ruff clean, mypy --strict
  clean across 47 source files, silent-exception scan clean.

### What's Not Built Yet

- **Token budget on `session_start`** — it still returns every identity +
  essential stub, truncated, plus an evidence block repeating them. `handoff`
  now exists as the bounded alternative and `session_start`'s description points
  at it, but `session_start` itself is unchanged and remains the expensive path.
  Finding 2.
- **Retrieval ranking quality** — semantic recall ranked a known-correct drawer
  7th with every hit clustered between 1.03 and 1.15. Hypothesis is drawer size,
  not the embedding model. Finding 3, needs the split test before any change.
- **Prediction/calibration in practice** — the machinery exists and has never
  been used: 0 prediction drawers written by an agent. Nothing in the write path
  asks for one. Finding 4.
- **Rename-survival testing for anchor staleness** — `symbol_source_hash` is
  stored and deliberately never compared. The hold lifts only when tested against
  a corpus that actually contains renames.

### Local Development Note

The maintainer's `cairntir-mcp` is an **editable install pointing at this repo**,
so every AI host loads Cairntir from this working tree. *Whatever branch is
checked out is what every agent runs.* Leave the repo on `main` at the end of a
session.

---

## AI Agent Rules

### Must Do
1. **Read this file first.** Every session.
2. **Read `docs/manifesto.md` and `docs/concept.md`** before proposing any feature.
3. **Read `plans/purrfect-drifting-sparrow.md`** — it is the execution plan, not decoration.
4. **Match the ethos.** See `ETHOS.md`. Comprehension before code. Quality has no shortcuts.
5. **Small commits, conventional format.** `feat:`, `fix:`, `docs:`, `chore:`, `test:`, `refactor:`.
6. **Every exception is typed and surfaced.** No silent `except: pass`. Ever. CI will fail you.
7. **Update "Last Session" below** at the end of every working session.
8. **Land work on `main` through a pull request.** Zero reviews are required — it is one click — and it keeps the full matrix green before `main` moves.
9. **Before closing a session, check `## [Unreleased]` for a `Fixed` entry a current user is hitting.** If there is one, that is a patch release now. See `docs/release-cadence.md`.
10. **When a plan promises a symbol, parameter, test, or file, write a `cairntir-commitments` block committing to it.** CI then fails if the release ships without it. Write the assertion with the promise, not after keeping it — v1.2 shipped without the context budget its own audit had committed to, and nothing noticed. See `docs/landed-commitments.md`.

### Must Not
1. **Never import code from BrainStormer or MemPalace.** Lineage is reference material, not source. We reimplement.
2. **Never add a feature not in the plan** without updating the plan first.
3. **Never hardcode paths.** Use `Path.home()`, `platformdirs`, or config.
4. **Never add dependencies** not listed in `pyproject.toml` without discussion.
5. **Never modify `lineage/`** — it's read-only history.
6. **Never treat a changelog entry as a release.** Only a pushed `v*.*.*` tag publishes. This gap silently swallowed 1.0.1 and 1.1.3.
7. **Never propose `2.0.0` for a merely breaking change.** It is reserved for a revolutionary change in what Cairntir is. Deprecated surfaces are removed in a MINOR after the two-minor window.

### When Uncertain
- Stop and ask. A question is cheaper than a wrong assumption.
- Default to the simpler option. Cairntir's whole identity is distillation.

---

## Skill Routing

| Intent | Skill | Future MCP tool |
|---|---|---|
| "stress test this assumption", "what could be wrong" | Crucible | `cairntir_crucible` |
| "audit this", "is it ready", "quality check" | Quality | `cairntir_audit` |
| "think about this with what we already know" | Reason | (invoked automatically) |
| "what did we decide about X" | — | `cairntir_recall` |
| "remember this" | — | `cairntir_remember` |
| "where are we" (session start) | — | `cairntir_session_start` |

---

## Key Files Every AI Agent Should Read

1. **This file** (`CLAUDE.md`)
2. `docs/manifesto.md` — WHY Cairntir exists
3. `docs/concept.md` — WHAT Cairntir is (three ingredients)
4. `docs/lineage/brainstormer.md` — what we kept/dropped from BrainStormer
5. `docs/lineage/mempalace.md` — same for MemPalace
6. `ETHOS.md` — the 5 principles
7. `HARNESS_AUDIT.md` — 12-primitive gap analysis (the rebuild justification)
8. `plans/purrfect-drifting-sparrow.md` — execution plan
9. `lineage/brainstormer/project_v1_realization.md` — "The Big Realization"
10. `docs/release-cadence.md` — commit vs. merge vs. tag, when to release, how
    the version number is chosen

Reading all 10 in a fresh chat should produce full context awareness. That's the sniff test.

<!-- cairntir:begin -->
# Cairntir — memory-first reasoning layer

You have access to persistent memory through the `cairntir_*` MCP tools.
At the start of every conversation:

1. Call `cairntir_session_start` with the wing matching the current project.
   Use the lowercase folder name in the working directory as the wing. If the
   correct wing is ambiguous, ask the user.
2. Read the returned identity and essential drawers before answering anything
   substantive.
3. Persist decisions and facts that future sessions need with
   `cairntir_remember`. Preserve the user's wording when it is load-bearing.
4. Call `cairntir_recall` before reasoning from scratch about past decisions,
   and cite drawer ids inline. Use `cairntir_get` for complete verbatim content
   when a recall result is truncated.
5. Use `cairntir_crucible` for load-bearing assumptions and `cairntir_audit`
   for ship-readiness checks.
6. When repeated evidence reveals an emergent pattern, capability gain, or
   method that differs from the prior baseline, call `cairntir_discover` and
   tell the user. Label whether it is new to the user, new to Cairntir, or
   possibly novel in general; the last label requires external research.

If session start returns no memory for an established wing, report that the
store may be new or misconfigured. Do not silently substitute model memory.

This policy is host-neutral: every agent must read and write the same Cairntir
store so work can move between Claude Code, Codex, Cursor, and Qwen Code
without a re-brief.
<!-- cairntir:end -->
