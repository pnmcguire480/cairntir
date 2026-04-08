# Cairntir

> *A stack of stones that sees across time.*

**Cairntir** is a memory-first reasoning layer for Claude Code. It kills cross-chat AI amnesia — the thing where you open a new conversation and your AI forgets every decision, every trade-off, every hard-won lesson from yesterday.

It is the foundation for something bigger: **AI + grand-scale 3D printing + post-scarcity tooling**. If we can model it, we can make it. If we can remember it, we can build it again. Cairntir is the memory.

Today it remembers your code decisions. Tomorrow it remembers which printed structure worked, which failed, what the next iteration should try. One day, a civilization that prints its own thingamajigs and gives them away for free will need a memory layer. This is that layer's first draft.

---

## Status

🚧 **Pre-alpha — Phase 0 bootstrap complete.** Core memory layer (Phase 1) starts next session.

- **License:** MIT
- **Language:** Python 3.11+
- **Stack:** `sqlite-vec` (embedded vector store), `uv` (package manager), `ruff` + `mypy --strict` (quality gates), `pytest` (tests), `mkdocs-material` (docs)
- **Distribution at launch:** `pip install cairntir` + Claude Code plugin

---

## The Three Ingredients

1. **Verbatim persistent memory.** `sqlite-vec` backend. Nothing summarized away. One file, zero dependencies, queryable by semantic + metadata.
2. **Minimal skill dispatch.** Three skills: `crucible` (stress-test assumptions), `quality` (audit), `reason` (memory-backed thinking loop). Everything else is cargo cult.
3. **One loop, not two commands.** A daemon + MCP server auto-captures and auto-restores. No `init`/`wrapup` ceremony. It just works.

**Taxonomy:** Wings (projects) → Rooms (topics) → Drawers (verbatim entries). Four retrieval layers: identity / essential / on-demand / deep.

---

## Why Cairntir Exists

Read [`docs/manifesto.md`](docs/manifesto.md).

The short version: AI assistants forget. You lose work. You re-explain the same context in every new chat. Every tool that tries to fix this either summarizes (lossy) or hand-waves (useless). Cairntir stores **verbatim** and retrieves **semantically**, with a taxonomy that makes retrieval reach ~95% recall instead of ~60%.

## Lineage

Cairntir is a distillation of two predecessors:

- **[BrainStormer](lineage/brainstormer/)** — Patrick's prior governance attempt. Great vocabulary (Crucible, Quality, agent species). Poor runtime (224 silent exceptions, dead code, static scaffolder pretending to be a learning system). Cairntir inherits the vocabulary, drops the Frankenstein.
- **[MemPalace](https://github.com/milla-jovovich/mempalace)** — Brilliant memory architecture (96.6% LongMemEval recall, wings/rooms/drawers taxonomy). Cairntir borrows the **concepts** and reimplements. No code copied.

See [`docs/lineage/brainstormer.md`](docs/lineage/brainstormer.md) and [`docs/lineage/mempalace.md`](docs/lineage/mempalace.md) for the full merge analysis.

---

## Quickstart (Phase 2+)

*Not yet buildable. This is the target UX:*

```bash
pip install cairntir
cairntir init
# Claude Code automatically uses Cairntir via MCP from here on
```

Or as a Claude Code plugin:

```
/cairntir:recall "why did we switch from Zustand to Jotai"
/cairntir:remember "decided to use sqlite-vec over chromadb because of version churn"
/cairntir:reason "what should we do next based on the last three sessions"
```

---

## Roadmap

- **Phase 0** — Professional repo bootstrap ✅ *(complete)*
- **Phase 1** — Memory spike: sqlite-vec backend, taxonomy, retrieval, embeddings *(next)*
- **Phase 2** — MCP server: 6 tools over stdio + Claude Code plugin
- **Phase 3** — Skills port: crucible, quality, reason
- **Phase 4** — Daemon: auto-capture, auto-restore
- **v0.1.0** — First public release
- **Beyond** — 3D printing bridge (see [`docs/roadmap.md`](docs/roadmap.md))

---

## Contributing

Read [`CONTRIBUTING.md`](CONTRIBUTING.md). TL;DR: conventional commits, 80% test coverage, `ruff` + `mypy --strict` zero warnings, no silent exceptions, no hardcoded paths. Quality has no shortcuts.

## Code of Conduct

Contributor Covenant 2.1. See [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

## Security

Found a vulnerability? See [`SECURITY.md`](SECURITY.md).

## Governance

See [`GOVERNANCE.md`](GOVERNANCE.md).

---

## Acknowledgments

- **[MemPalace](https://github.com/milla-jovovich/mempalace)** by @milla-jovovich — for proving verbatim + taxonomy beats summarize + hope.
- **[Claude Code](https://claude.com/claude-code)** by Anthropic — for building the harness that makes this worth building.
- **The Stewardship Commonwealth** framing — for reminding us that governance is constraint, not control.

Built by [Patrick McGuire](https://github.com/pnmcguire480) in the hope that it helps.

> *"If it doesn't, I'll still die knowing I tried."*
