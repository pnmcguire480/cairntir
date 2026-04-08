# Lineage: BrainStormer

Cairntir is the direct successor to **BrainStormer**, Patrick's prior attempt at an AI-assisted dev governance tool. This document records what we kept, what we dropped, and why.

## What BrainStormer Was

BrainStormer was (and still is, at `c:\Dev\SKILLS\BrainStormer\`) a pip-installable CLI that scaffolded governance files, ran quality audits, orchestrated 571 agents, and tried to solve cross-chat amnesia with an `init`/`wrapup` loop backed by `session.json`, `CLAUDE.md`, and an Obsidian vault sync.

It had eight skills (Crucible, Kernel, Comprehension, Ideation, Design, Quality, Auto-Research, HumanFlow), 20+ CLI commands, a plugin manifest, an MCP server, and a release pipeline. It was ambitious. It had good ideas.

It also had **224 silent `except: pass` blocks**, a dead license system contradicting its "free and open" identity, an "architecture of a learning system but runtime behavior of a static scaffolder," and — most damningly — *it did not actually solve cross-chat amnesia.* Patrick was still losing work to context loss while using BrainStormer. The core problem it was built to solve was not solved. An oracle round table analysis concluded that of the 12 harness primitives from Nate Jones's Claude Code framework, **zero were fully implemented**. The pattern: *infrastructure built, enforcement missing*.

Rather than continue layering on top of a broken foundation, Patrick chose to distill the good ideas into a clean new project. Cairntir is that distillation.

## What We Kept

### Vocabulary

BrainStormer's best contribution was its vocabulary. Cairntir inherits:

- **Crucible** (epistemic forge — assumption stress-testing) → Cairntir's `crucible` skill
- **PALADIN / Quality** (6-tier audit) → Cairntir's `quality` skill, distilled
- **Severity tiers** (P0/P1/P2/P3) → Cairntir uses the same severity language in audits
- **Agent species** — conceptual vocabulary, not implemented in v1
- **ETHOS** — the 5 principles (Comprehension Before Code, Quality Has No Shortcuts, Ideas Compound, User Sovereignty, Structured Completeness) — copied verbatim to `ETHOS.md` at the Cairntir repo root
- **The Stewardship Commonwealth** framing — governance as constraint, not control

### Key Insights

Several insights from BrainStormer's development shaped Cairntir directly:

- **"The Big Realization"** — BrainStormer *should* have been two commands (`init` + `wrapup`) + a persistent brain, not a 12-command toolbox. Cairntir takes this further: one daemon + auto-restore, zero commands for the common case.
- **Oracle Round Table** — Eight named thinkers (Diogenes, Socrates, Plato, Peter Joseph, Alan Watts, Jacque Fresco, Buckminster Fuller, Neil DeGrasse Tyson) audited BrainStormer pre-launch and unanimously found: great vision, docs not execution, landing page oversells. Cairntir ships execution first, docs second.
- **Harness Audit (Nate Jones gap analysis)** — The 12 primitives gap analysis documented in `HARNESS_AUDIT.md` justified rebuilding rather than patching. Three primitives mattered: error visibility, feedback loop closure, and machine-enforceable agent constraints. Cairntir is built around these three.

### Reference Material

The following BrainStormer files are preserved in `lineage/brainstormer/` as **read-only history**:

| File | Purpose |
|---|---|
| `crucible-SKILL.md` | Source for Cairntir's `crucible` skill |
| `quality-SKILL.md` | Source for Cairntir's `quality` skill |
| `severity-tiers.md` | P0–P3 severity language |
| `agent-species.md` | Taxonomy vocabulary |
| `ETHOS.md` | The 5 principles |
| `oracle-round-table-transcript.md` | Thinker critique that justified the rebuild |
| `HARNESS_AUDIT.md` | 12-primitive gap analysis |
| `project_v1_realization.md` | "The Big Realization" memory |
| `user_tsc_ethos.md` | Stewardship Commonwealth framing |
| `brainstormer-CLAUDE.md` | BrainStormer's own CLAUDE.md at the time of the split |

**These files are never modified.** They are the fossil record.

## What We Dropped

### 571 Agents

BrainStormer curated 571 agents (374 classified + 5 dark-factory + 23 oracle) across 6 species. They were impressive as a catalog and useless as a runtime — nobody can meaningfully route across 571 options. Cairntir ships zero agents in v1 and re-curates on demand in later phases.

### 20+ CLI Commands

BrainStormer had commands for init, wrapup, quality, status, doctor, sync, update, migrate, learn, agent, retro, hooks, daemon, demo, and more. Cairntir ships **two** commands: `cairntir` (umbrella) and `cairntir recall` (the only thing a human ever needs to type). Everything else is automatic via the daemon and MCP.

### init / wrapup Ceremony

BrainStormer required users to type `brainstormer init` and `brainstormer wrapup` at session boundaries. Users dropped out at the ceremony. Cairntir replaces both with a background daemon and an auto-called `cairntir_session_start` MCP tool. **The user does nothing.**

### The License System

BrainStormer had ~280 lines of HMAC-signed license key infrastructure for a product that is "free and open." Dead code. Removed entirely. Cairntir is MIT, no gates, no tiers, no keys.

### The 224 Silent Exceptions

BrainStormer had 224 `except: pass` blocks silently swallowing errors across init, wrapup, vault, scaffold, and detector. *"A governance tool that hides its own failures is governance theater."* Cairntir has a CI check that fails if a single bare `except:` or `except: pass` is introduced. Every exception is typed via `cairntir/errors.py` and surfaced.

### ChromaDB

BrainStormer never committed to a vector store. MemPalace (which informed Cairntir's memory layer) used ChromaDB and inherited its version churn and macOS ARM64 segfault. Cairntir chose `sqlite-vec` instead: one file, zero dependencies, no version churn.

### Obsidian Vault Sync

BrainStormer synced to an Obsidian vault one-way, async, unreliable. It was Patrick's attempt to create a "persistent brain" before the memory layer existed. Cairntir's memory layer replaces the need. Obsidian becomes an optional read-only render target post-v1.

### AAAK Compression

MemPalace had an experimental compression dialect called AAAK that regresses below ~1k tokens (which is the scale most BrainStormer session data lives at). Cairntir skips it entirely. Verbatim raw only.

### Eight Skills → Three Skills

BrainStormer: Crucible, Kernel, Comprehension, Ideation, Design, Quality, Auto-Research, HumanFlow.
Cairntir: Crucible, Quality, Reason.

- **Kernel** was project scaffolding — not memory, not reasoning. Out.
- **Comprehension** was "explain this code" — Claude already does that well without a skill. Out.
- **Ideation** was the brainstorming chain — useful but orthogonal to memory. Out for v1.
- **Design** was a 5-phase design pipeline — scope creep. Out.
- **Auto-Research** was Karpathy-style experiment loops — interesting but not memory. Out for v1.
- **HumanFlow** was anti-AI-detection voice — Patrick will handle voice himself. Out.

Three skills. You can hold them in your head.

## Why a Clean Break Instead of Refactoring

The honest answer: BrainStormer's problems were architectural, not cosmetic. 224 silent exceptions is a symptom of a codebase that does not take correctness seriously. Dead license code is a symptom of goal drift. A "learning system" that is actually a static scaffolder is a symptom of vaporware creeping into real code.

Refactoring would have required:
1. Deleting ~50% of the code
2. Rewriting the memory layer from scratch
3. Replacing the ceremony-based UX
4. Restoring the CI quality gates

At that point, you have built a new project inside the old one, and the old one's history is confusing rather than clarifying. A clean break at a new path (`c:\Dev\Cairntir\`) with BrainStormer preserved as `lineage/brainstormer/` is *clearer*, not wasteful.

BrainStormer remains as-is at `c:\Dev\SKILLS\BrainStormer\`. It is not deleted. It is not deprecated. It is simply superseded by a cleaner expression of the same ideas.

---

*"Sometimes the kindest thing you can do for a project is let it become the ancestor of something better."*
