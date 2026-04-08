# Concept

Cairntir is a **memory-first reasoning layer** for Claude Code. Three ingredients, in order of importance.

## 1. Verbatim Persistent Memory

Every meaningful moment in a Claude Code session — a decision, a trade-off explanation, a design choice, a bug's root cause, a failed attempt — gets stored as a **drawer**: a piece of verbatim text with an embedding and metadata.

- **Storage:** `sqlite-vec`. One file on disk. Zero extra dependencies beyond what Python already has. No version churn. Backup = copy a file.
- **Embeddings:** Local `sentence-transformers` by default. No network required. No OpenAI API key to lose.
- **Metadata:** Wing (project), room (topic), timestamp, author (user or agent), source (chat / cli / daemon).
- **Retention:** Forever by default. Pruning is opt-in, not automatic. Storage is cheap; your future self is not replaceable.

**Non-goals:** No summarization. No compression. No "smart" trimming. If you wanted a paragraph, you'd have written one.

## 2. Minimal Skill Dispatch

Three skills. Not eight. Not eighty. Three.

### `crucible` — Epistemic Stress Test
Given a claim or a plan, crucible challenges it. It asks: *What assumptions are we making? Which ones are load-bearing? Which ones could be wrong? What would falsify them?* Inherited from BrainStormer's Crucible skill, which was its best idea.

### `quality` — Audit On Demand
Given a piece of work (code, doc, design), quality runs a 6-tier audit: correctness, security, performance, maintainability, accessibility, and integrity. Distilled from BrainStormer's PALADIN. Produces a score and a punch list. Does not block; advises.

### `reason` — Memory-Backed Thinking
Given a question, reason loads the relevant memories (via the 4-layer retrieval below) and thinks out loud with them. This is the skill that makes Cairntir different from a plain vector store. Retrieval is not the end; **reasoning over what you retrieved** is.

Everything else — agent routing, pipelines, multi-step orchestration — is built on top of these three. If you find yourself wanting a fourth skill, you are probably re-inventing BrainStormer and you should stop.

## 3. One Loop, Not Two Commands

BrainStormer had `init` and `wrapup`. Both were ceremonial. Users dropped out at the ceremony.

Cairntir replaces both with:

- **A daemon** (`cairntir daemon`) that watches the working directory and the active Claude Code session and auto-captures meaningful moments into drawers in the background.
- **An MCP tool** (`cairntir_session_start`) that Claude calls automatically at the start of every session to load the 4-layer context.

The user does nothing. The memory is just there, like gravity.

---

## Taxonomy

Memory is organized in a nested structure borrowed from [MemPalace](https://github.com/milla-jovovich/mempalace) (concepts only — reimplemented, not copied):

```
Wing (project)
 └── Room (topic)
      └── Drawer (verbatim entry)
```

**Wings** correspond to projects. `cairntir` is a wing. `stars-2026` is a wing. Cross-wing queries are possible but rare.

**Rooms** correspond to topics within a project. Common rooms: `decisions`, `bugs`, `session-end`, `architecture`, `agent-crucible`, `agent-quality`. Rooms are created on demand.

**Drawers** are individual memory entries. Each drawer has:

- `id` (UUID)
- `wing` (project name)
- `room` (topic name)
- `content` (verbatim text)
- `embedding` (vector)
- `metadata` (timestamp, author, source, custom tags)

## 4-Layer Retrieval

Retrieval is tiered by cost and frequency:

### Layer 0 — Identity (always loaded)
"Who am I working with, what are their preferences, what is the style of this project."
Small, hand-curated, rarely changes. Loaded at the start of every session in every wing.

### Layer 1 — Essential (loaded per wing)
"What is this project, what decisions are load-bearing, what did we agree on."
Pulled automatically when a session opens in a wing. Limited to ~20 drawers, ranked by metadata weight (decisions > status > chatter).

### Layer 2 — On-Demand (retrieved by topic)
"What have we said about X?" Triggered when the conversation touches a topic. Semantic search over the wing, filtered by room if inferrable. Limited to top-10 results.

### Layer 3 — Deep (explicit search)
"Find me every drawer about the cache TTL decision across all projects." The full query interface. Used rarely. Accessed via `cairntir recall` CLI or `cairntir_recall` MCP tool.

## The 6 MCP Tools

The MCP surface is deliberately small.

1. `cairntir_remember(wing, room, content, metadata?)` — store a drawer
2. `cairntir_recall(query, wing?, room?, limit=10)` — semantic + metadata search
3. `cairntir_session_start(wing)` — 4-layer context bootstrap (the amnesia killer)
4. `cairntir_timeline(wing, entity)` — chronological view of a topic across drawers
5. `cairntir_audit(wing)` — run the `quality` skill on current work
6. `cairntir_crucible(claim)` — run the `crucible` skill on a claim or plan

That's the whole surface. MemPalace's 19 tools collapsed into 6. BrainStormer's 12 collapsed into 6. **You can hold the whole API in your head.**

---

## What Cairntir Deliberately Does Not Do

- **Does not summarize.** Verbatim only.
- **Does not auto-prune.** Storage is cheap.
- **Does not call out to the cloud by default.** Local-first. Embeddings and storage run on your machine.
- **Does not orchestrate multi-agent pipelines.** Use Claude Code for that.
- **Does not try to be a project manager, a ticket tracker, a documentation generator, or a build tool.** It remembers. That is enough.
- **Does not silently eat exceptions.** Every error is typed, logged, and surfaced. CI enforces this.

Simplicity is the entire product.
