# Lineage: MemPalace

Cairntir's memory architecture is deeply influenced by **MemPalace** (https://github.com/milla-jovovich/mempalace) by @milla-jovovich. This document records what we learned, what we borrowed, and what we deliberately left behind. **No code from MemPalace is copied into Cairntir.** Concepts only.

## What MemPalace Is

MemPalace is a local-first memory backend for AI agents, v3.0.13 at the time of this writing. It stores verbatim conversation text in ChromaDB, organizes it via a "palace" metaphor (wings → rooms → closets → drawers), and exposes 19 MCP tools plus a 4-layer memory stack (identity / essential / on-demand / deep) for retrieval.

Its measured performance on LongMemEval is **96.6% R@5** in raw mode — meaning when asked to find a specific fact from a long conversation, it retrieves the relevant drawer in the top 5 results 96.6% of the time. For context: semantic search alone without metadata filters sits around 60.9% R@10. The taxonomy is doing the heavy lifting, and the measurement proves it.

MemPalace was the missing piece BrainStormer needed. BrainStormer had the reasoning vocabulary (Crucible, Quality, etc.) and lacked a real memory layer. MemPalace had a real memory layer and lacked a reasoning vocabulary. Cairntir is the merge.

## What We Borrowed (Concepts Only)

### Wing / Room / Drawer Taxonomy

The single most important idea in MemPalace. Organizing memories by project (wing) and topic (room) lets retrieval filter by metadata *before* semantic search runs, which is how you get from 60% recall to 95% recall. Cairntir uses the same three-level taxonomy.

- **Wing** = project
- **Room** = topic within a project
- **Drawer** = individual verbatim memory entry

We dropped MemPalace's "closet" level because it added ceremony without proportional benefit at solo-developer scale. Three levels, not four.

### 4-Layer Retrieval Model

MemPalace distinguishes between:
- **Identity** (who am I working with — always loaded)
- **Essential facts** (load at session start, small, per-wing)
- **On-demand** (retrieve when the conversation touches a topic)
- **Deep search** (explicit query interface, used rarely)

This matches how memory actually works and how token budgets actually need to be managed. Cairntir inherits this model wholesale.

### Verbatim Storage

MemPalace stores the original text, not summaries. This is the correct choice and Cairntir makes the same one. Storage is cheap; your future self needs the exact words.

### LongMemEval as the Bar

MemPalace's 96.6% R@5 gives Cairntir a concrete performance target. Cairntir's v0.1.0 bar is **80% R@5 on a LongMemEval subset**. Lower than MemPalace's, because we're smaller and newer, but measured. You cannot improve what you cannot measure.

## What We Deliberately Left Behind

### ChromaDB

MemPalace uses ChromaDB as its vector store. ChromaDB is battle-tested but brings:
- ~15 transitive dependencies
- Regular breaking API changes (MemPalace pins `chromadb>=0.5.0,<0.7`)
- Known macOS ARM64 segfault (MemPalace README references GitHub issue #74)
- Install complexity that scares off non-expert users

Cairntir uses **`sqlite-vec`** instead. One file. Zero extra dependencies. No version churn. Works identically on Windows, macOS, and Linux. Slower than ChromaDB at 100k+ vectors, but that is not a solo-developer scale problem.

If Cairntir ever hits ChromaDB-scale requirements, the migration is straightforward — the taxonomy is portable, the embeddings are portable, only the backend swaps. Starting with the heavier option would have been premature optimization.

### AAAK Compression

MemPalace includes an experimental "AAAK" compression dialect — an LLM-native lossy encoding designed to reduce token cost when reloading memories into context. It regresses against raw mode in MemPalace's own benchmarks (84.2% vs 96.6% R@5), and the regression is worst at small scales.

Cairntir operates entirely at small scales (solo developer, mostly under 1000 drawers per wing). AAAK's benefits would not materialize. Raw storage only. No AAAK.

### 19 MCP Tools

MemPalace exposes 19 MCP tools. Cairntir collapses the surface to **6**:

1. `cairntir_remember`
2. `cairntir_recall`
3. `cairntir_session_start`
4. `cairntir_timeline`
5. `cairntir_audit` (from BrainStormer)
6. `cairntir_crucible` (from BrainStormer)

Fewer tools = fewer decisions for the AI. Decisions are where things go wrong.

### Conversation Miners for 5 Chat Formats

MemPalace includes miners that parse five different chat export formats (ChatGPT, Claude, etc.) to retroactively populate memory. Clever, but Cairntir's model is **capture-as-you-go** via a daemon, not bulk-import-from-history. We skip the miners entirely.

### Temporal Knowledge Graph

MemPalace v3 includes a SQLite-backed temporal knowledge graph — entity-relationship-time triples with validity windows. The feature is powerful ("who decided X as-of date Y?") but adds complexity that is not yet earned by demand. Cairntir defers this to post-v0.1.0. If real users start asking temporal-attribution questions, we build it. If they don't, we don't.

### Agent-Specific Diaries

MemPalace supports per-agent wings so each agent can maintain its own memory. Interesting pattern but Cairntir's v1 does not run multi-agent pipelines, so there is nothing to specialize. Deferred.

## The Merge, Precisely

Cairntir is **MemPalace's memory model** (wing/room/drawer + 4-layer retrieval + verbatim) + **BrainStormer's reasoning vocabulary** (Crucible + Quality) + **a daemon** (replacing both BrainStormer's init/wrapup and MemPalace's manual capture) + **`sqlite-vec`** (replacing ChromaDB) + **a reason skill** (new — memory-backed thinking loop).

Neither predecessor is sufficient alone. Cairntir's identity is precisely this merge.

## Credit Where It's Due

MemPalace is excellent work. The fact that Cairntir does not ship MemPalace's code is not a judgment of MemPalace — it is a judgment that *reimplementing the concepts in a smaller, more opinionated form* serves Cairntir's audience better. Anyone who needs MemPalace's full 19-tool surface, temporal KG, multi-format miners, and ChromaDB scalability should use MemPalace directly. Cairntir is for people who want the 6-tool, one-file, zero-config version of the same idea.

**Thank you, @milla-jovovich, for proving that verbatim + taxonomy beats summarize + hope.** Cairntir stands on that proof.
