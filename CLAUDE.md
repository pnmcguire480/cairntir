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
- **Repo:** `c:\Dev\Cairntir\` (local — GitHub push pending)
- **Stage:** [x] v0.1 [x] v0.2 [x] v0.3 [x] v0.4 [x] v0.5 [x] v0.6 [x] **v1.0.0 shipped + public on GitHub** → next: **v1.1 (Reach)** on the Road to 2.0

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

---

## Current State

### Last Session

- **Date:** 2026-04-08 (**v1.0.0 — Library Extraction, shipped**)
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

- Memory layer: wing/room/drawer taxonomy over sqlite-vec with 4-layer retrieval
- MCP server: six tools exposed over stdio (`python -m cairntir.mcp.server`)
- Three skills: Crucible, Quality, Reason — bundled and loadable
- Daemon: `python -m cairntir.daemon` polls a spool dir and persists drawers
- 54 tests, 85% coverage, ruff clean, mypy --strict clean

### What's Not Built Yet

- GitHub remote (local repo only so far)
- CLI wrapper (`cairntir` + `cairntir recall`)
- Claude Code plugin bundle
- Real LongMemEval benchmark run
- Published PyPI release

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

### Must Not
1. **Never import code from BrainStormer or MemPalace.** Lineage is reference material, not source. We reimplement.
2. **Never add a feature not in the plan** without updating the plan first.
3. **Never hardcode paths.** Use `Path.home()`, `platformdirs`, or config.
4. **Never add dependencies** not listed in `pyproject.toml` without discussion.
5. **Never modify `lineage/`** — it's read-only history.

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

Reading all 9 in a fresh chat should produce full context awareness. That's the sniff test.
