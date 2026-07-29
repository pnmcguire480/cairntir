# Evolution Audit — BabyTIEROS → BrainStormer → Cairntir

**Date:** 2026-07-27
**Session intent:** AUDIT_ANALYSIS
**Memory receipts:** drawers #110, #111, and #112

## Question

Were important capabilities accidentally removed as BabyTIEROS became
BrainStormer and BrainStormer became Cairntir?

## Answer

Yes, but the answer is narrower than “put BrainStormer back.”

Cairntir correctly removed the all-in-one scaffold, agent marketplace,
licensing, telemetry, and orchestration surface. Restoring those would recreate
the complexity Cairntir was built to escape.

The investigation did identify lost outcomes that matter to a trustworthy
agent-memory substrate:

1. diagnosable system health;
2. complete structured audit trails;
3. explicit context budgets;
4. measurable handoff/capture completeness;
5. human approval around dangerous state changes;
6. independent holdout and first-use testing;
7. decision-rationale and pattern capture;
8. longitudinal quality/calibration history;
9. a human-readable Obsidian projection.

Those outcomes belong in Cairntir, but mostly as core invariants, recipes, or
projections — not as resurrected BrainStormer subsystems.

## Evidence standard

- **High confidence:** direct current artifact or executable-code evidence.
- **Medium confidence:** multiple surviving documents agree, but the earliest
  original history is incomplete.
- **Low confidence:** plausible lineage inference without a direct artifact.

Primary evidence:

- BabyTIEROS skill, templates, scaffolder, eval set, tier reference, and chunk
  completion gate under `C:\Dev\AGENTS\skills\babytier-os\`
- archived BrainStormer runtime and tests under
  `C:\Dev\SKILLS\BrainStormer\`
- BrainStormer's `HARNESS_AUDIT.md`, which distinguishes implemented,
  partial, advisory-only, and missing runtime behavior
- current Cairntir source, tests, plans, and live database behavior

## Feature survival map

| Capability | BabyTIEROS | BrainStormer | Cairntir | Disposition | Confidence |
|---|---|---|---|---|---|
| Persistent project identity and current state | `CLAUDE.md`, `CONTEXT.md` | Init/wrapup maintained Last Session and vault copies | IDENTITY/ESSENTIAL drawers and `session_start` | **Preserved, stronger storage; fix identity scope and truncation** | High |
| Session handoff | Explicit outgoing/incoming checklist | Structured wrapup → returning init, plus autosave | Daemon capture + session-start | **Outcome preserved, completeness receipt lost; restore as capture/session events** | High |
| Context budgeting | “Always/load when relevant/never load” | Hot/warm context assembler with token estimate | Four retrieval layers, fixed limits/snippets | **Partially preserved; restore explicit token/character budgets** | High |
| Spec and non-goal discipline | `SPEC.md`, priorities, acceptance criteria, out-of-scope | Kernel scaffold + Quality Stage 1 | Project AGENTS/roadmap + Quality Stage 1 | **Preserved as project governance; do not add to memory core** | High |
| Decision rationale / WHY | Architecture decision log and chunk decision gate | CodeGlass decision archaeology, pattern and assumption ledgers | Prediction fields and supersession, but rationale is untyped text | **Restore typed rationale/evidence as metadata or recipe output** | High |
| Assumption stress testing | Escalation and architecture checkpoints | Crucible | Crucible | **Preserved and distilled successfully** | High |
| Quality / ship gate | Chunk gates, human understanding, hidden sniff tests | PALADIN stages, entropy, adversarial verification, quality history | Quality skill with compliance + score | **Core survived; trends, independent holdouts, and some gates were lost** | High |
| Human-only holdout tests | `SNIFFTEST.md` explicitly hidden from agents | Preserved in scaffold; PALADIN adversarial stage | Tests/evals are visible to the implementing agent | **Restore an operator-owned holdout suite outside agent context** | High |
| Model/task tier routing | Five capability tiers with escalation/delegation | Kernel maturity/model routing and agent species, mostly advisory | No model router | **Correctly removed from core; store agent/model provenance and outcomes only** | High |
| Human approval checkpoints | Dependencies, schema, auth, deployment, deletion, large refactors, production data | Kernel/daemon profiles and project rules | Host instructions exist; memory mutations lack typed risk policy | **Restore for reindex, identity promotion, trust changes, import, and destructive repair** | High |
| Chunk completion / entropy gate | Build, tests, review, understanding, entropy delta, architecture alignment, scope threshold | Quality/CodeGlass/pattern system | Quality checks repo health but not memory workflow completion | **Reintroduce as a Foundation Quality recipe, not core schema logic** | Medium |
| Structured ledgers | Lessons-learned table | Session, quality, failure, assumption, pattern, and routing TSV schemas; only half populated | Drawers can represent events, but event types and automatic coverage are incomplete | **Restore a typed event vocabulary and automatic receipts** | High |
| Project health doctor | Documentation checklist | Implemented `brainstormer doctor` plus MCP handler | Missing | **Restore immediately as `cairntir doctor`** | High |
| Crash recovery | Session handoff rules | Partial autosave and per-step continuation; important writes non-atomic | Atomic spool creation, but capture and Reason workflows are not idempotent | **Restore as durable runs, idempotency, recovery, WAL, and backups** | High |
| Cross-project knowledge graph | Durable docs and explicit file index | Obsidian vault, wikilinks, project registry, dashboards | Wings and cross-recall; portable sync planned | **Semantic capability preserved; human-readable graph projection lost** | High |
| Obsidian integration | Not a core runtime, but documents were vault-ready | One-way sync with user-note preservation | Anthropicer contains a small manual `cairntir-sync` projection | **Build an optional read-only/projected Obsidian view after core integrity** | High |
| Pattern and rule learning | Lessons learned and decision log | Diff-derived rule proposals, confidence, prune, pattern detection | Belief mass and agent memory, but no verified strategy/rule lifecycle | **Restore as experience-memory recipes with outcome and validity** | High |
| Retrospectives | Revision history and lessons learned | Git-derived `retro` command | Decision Replay covers one decision, not whole-session learning | **Add a retrospective recipe if repeated use earns it** | High |
| Stack/maturity detection | Tier assignment embedded in scaffold | Runtime detection routed init and agents | Wing is supplied by caller/project instructions | **Do not restore to core; optional host adapter may write project-profile drawers** | High |
| Agent catalogs/species | Small tier/skill registry | 571-agent catalog and six species; metadata largely advisory | Removed | **Correct removal; orchestration belongs to the host** | High |
| Daemon budgets and kill conditions | Escalation to capable tier/human | Daemon profiles declared budgets, allowlists, review triggers, kill conditions | Capture daemon has no quotas/backpressure; does not run agents | **Restore ingestion quotas/backpressure, not agent execution governance** | High |
| Migration from other AI tools | Scaffold helped organize existing docs | Cursor/Windsurf/Copilot/Aider migration command | Portable Cairntir import only | **Optional import recipes/adapters; not a ship blocker** | High |
| Local-first/offline ownership | Local files and local-model tier | Filesystem/Obsidian, one dependency, offline core | Local SQLite, portable format, local Ollama | **Preserved; remove surprising default network/update behavior** | High |
| Licensing, telemetry, marketplace | None central | Large commercial/distribution surface | Removed except update notifier and auto-registration | **Correct removal; make remaining network/config mutations explicit** | High |
| Auto-research / prediction loop | Chunk hypotheses implicit in specs and gates | Auto-Research and Crucible evolution loop | Prediction-bound drawers, Reason loop, Decision Replay | **Preserved in substantially stronger form** | High |
| Comprehension / decision archaeology | Architecture and scenario documents | CodeGlass WHAT/HOW/WHERE/WHEN/WHY and pattern scan | Recall + Reason retrieve context but do not generate a durable system map | **Recipe candidate: cited comprehension/decision-archaeology projection** | High |
| Ideation and design | `SPEC.md`, `ART.md`, scenarios | Dedicated ideation and design skills | Removed from three-skill core | **Correct core removal; reusable recipes may live outside Cairntir** | High |

## Non-obvious findings

### 1. The oldest surviving invariant is not memory; it is controlled context

BabyTIEROS separated always-load, relevant-load, and never-load material before
Cairntir had vector retrieval. Cairntir's four layers are the semantic
descendant of that policy, but the explicit budget and exclusion contract was
lost.

**Why it matters:** the current 100-character snippets and fixed limits are not
just an MCP formatting defect. They are a regression from the lineage's
original context-control discipline.

**Confidence:** High.

### 2. BrainStormer's ledgers were the right shape but the wrong substrate

Session, quality, failure, assumption, pattern, and routing ledgers expressed
exactly the events needed to learn whether the system was working. Half were
never populated, and session reconstruction was fragmented across TSV,
Markdown, JSONL, and marker files.

**Why it matters:** Cairntir should not revive six TSV files. It should define
those event types as provenance-aware drawers linked by stable workflow IDs.

**Confidence:** High.

### 3. Human-only testing became more important, not less

BabyTIEROS hid `SNIFFTEST.md` from the implementation agent to prevent test
targeting. Modern agents can inspect and optimize against nearly every test and
benchmark in their context.

**Why it matters:** Cairntir needs operator-owned holdouts for cold-start
continuity, stale-memory rejection, poisoning, scope isolation, and recovery.
Those tests should not be loaded into ordinary implementation sessions.

**Confidence:** High.

### 4. The Obsidian brain was removed before its human-interface value was
separated from its storage role

BrainStormer used Obsidian as both database and user interface. Cairntir
correctly replaced it as the authoritative store, but also lost the useful
human-readable projection, wikilinks, annotations, and dashboards.

**Why it matters:** Anthropicer should become a projection/inspection surface,
never the source of truth. This keeps SQLite correctness while restoring human
legibility.

**Confidence:** High.

### 5. Cairntir preserved epistemic learning better than operational learning

Claims, predicted outcomes, observations, deltas, supersession, belief mass,
and Decision Replay preserve evolving beliefs. Routing mistakes, workflow
failures, incomplete captures, operator interventions, and useful/unused
retrievals are much less completely recorded.

**Why it matters:** the next memory schema should add operational receipts
before adding more inference.

**Confidence:** High.

### 6. “Minimum sufficient tier” should survive as measurement, not routing

The five-tier router aged quickly because model capabilities and prices move.
Its enduring principle is to match cost/capability to task complexity.

**Why it matters:** Cairntir should record model/agent identity, latency, cost,
task type, result, and operator verdict. A host can then route using evidence.
Cairntir should not become the router.

**Confidence:** Medium.

### 7. CodeGlass proved the teaching outcome, not the generator

CodeGlass was built for a specific person and audience: Patrick and other
vibecoders who can build useful software without formal computer-science
training, but need the system to turn unfamiliar code into durable
understanding.

The surviving evidence separates two very different things:

- Anthropicer contains substantial walkthroughs that explain WHAT, HOW, WHERE,
  WHEN, and WHY, trace data journeys, name patterns, compare alternatives, and
  identify danger zones. These show that the human/AI-assisted teaching
  workflow could produce genuinely useful learning artifacts.
- BrainStormer's executable `learn walkthrough --from-diff` path did not
  generate that depth. It extracted a commit subject, changed filenames, and
  newly added function/class names using regular expressions. Its WHY section
  remained a placeholder for manual completion.
- BrainStormer's wrapup and autosave “CodeGlass” paths were separate static
  scanners. They logged keyword matches, TODOs, magic numbers, possible
  decisions, and possible rules. They did not generate educational
  walkthroughs or verify that the reader understood the code.

**Verdict:** the concept succeeded; the rewrite automation was half-built and
the runtime claims overstated what it actually generated. The good Anthropicer
walkthroughs must not be treated as proof that the generator produced them.

**Preservation requirement:** restore the learning outcome as a cited,
evidence-aware CodeGlass recipe. Do not restore the old regex generator.

A modern CodeGlass output must:

1. target a declared reader level, including “no formal CS training”;
2. explain WHAT/HOW/WHERE/WHEN/WHY in plain language;
3. include data/control flow, glossary, analogies, danger zones, and “what
   breaks if this changes”;
4. cite every factual code claim to a file, line, commit, test result, or
   Cairntir drawer;
5. label rationale as observed, inferred, or unknown instead of inventing WHY;
6. include a short teach-back/comprehension check;
7. persist raw evidence, the walkthrough, user annotations, and later
   usefulness as linked drawers;
8. project the verified result into Anthropicer/Obsidian without making the
   vault authoritative.

**Confidence:** High.

## Recovery decisions

### Restore in the v1.2 core

- embedding/index health in `doctor`;
- typed operational receipts for failures, routing/provenance, and workflow
  transitions;
- explicit context budgets and complete-drawer access;
- durable/idempotent workflows and capture-completeness signals;
- human approval boundaries for reindex, trust, import, and identity promotion;
- quality/calibration history as queryable drawers;
- operator-owned holdout eval hooks.

### Restore as recipes

- decision archaeology / WHY capture;
- CodeGlass project comprehension and teaching walkthroughs;
- chunk/foundation quality gate;
- retrospectives;
- verified pattern/rule promotion.

### Restore as an optional projection

- Anthropicer/Obsidian pages, wikilinks, dashboards, and user annotations;
- one-way projection from verified Cairntir drawers;
- no direct database authority and no silent write-back.

### Keep out of Cairntir

- agent marketplace/catalog;
- model-tier orchestration;
- licensing and telemetry;
- generic project scaffolding;
- content ideation and visual-design skills;
- agent execution runtime.

## Change to the foundation-hardening plan

The original v1.2 plan remains valid, with one added invariant:

> Every new mechanism must show which ancestral user outcome it preserves,
> replaces, or deliberately rejects.

This prevents both kinds of regression: accidentally stripping away hard-won
capabilities, and rebuilding BrainStormer's complexity under new names.
