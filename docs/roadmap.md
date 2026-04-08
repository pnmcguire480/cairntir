# Roadmap

## Phase 0 — Professional Bootstrap ✅
- Repo tree, lineage preservation, plan, core recognition files
- Professional scaffolding (pyproject, ruff, mypy, pytest, CI, pre-commit)
- MIT license, Code of Conduct, Contributing, Security, Governance
- Target: a fresh Claude chat in the repo is immediately oriented

## Phase 1 — Memory Spike *(next)*
- `sqlite-vec` backend with add_drawer / search / get
- Wing / Room / Drawer dataclasses
- 4-layer retrieval loader
- Local embeddings provider (sentence-transformers)
- Unit tests for all of the above
- First LongMemEval subset eval (target: **80% R@5**)

## Phase 2 — MCP Server
- 6 MCP tools over stdio: `remember`, `recall`, `session_start`, `timeline`, `audit`, `crucible`
- `.mcp.json` wiring
- Claude Code plugin manifest + slash commands (`/cairntir:remember`, `/cairntir:recall`, `/cairntir:reason`)
- Integration tests

## Phase 3 — Skills Port
- `crucible` skill (trimmed from BrainStormer)
- `quality` skill (trimmed from BrainStormer)
- `reason` skill — NEW, memory-backed thinking loop
- Skill invocation from MCP

## Phase 4 — Daemon
- Auto-capture background loop
- Conversation watcher
- Retire init/wrapup ceremony fully

## v0.1.0 — First Public Release
- PyPI publish
- GitHub Release with notes
- Docs site live at `pnmcguire480.github.io/cairntir/`
- Discord or GitHub Discussions for community
- Blog post: "The Amnesia Problem and What It Cost Me"

---

## Beyond v0.1.0 — The Long Road

The following are *directional*, not committed. They exist to clarify that Cairntir is not a finished artifact — it is the first layer of something much larger.

### v0.2 — Temporal Knowledge Graph
Borrowed from MemPalace's v3 feature. Entity-relationship-time triples with validity windows. Answers questions like *"who decided X as-of date Y?"* Only builds if real users ask temporal-attribution questions.

### v0.3 — Multi-Project Synthesis
*"What patterns have we seen across all our projects this quarter?"* Cross-wing queries, trend detection, decision archaeology. The point at which Cairntir stops being per-project memory and starts being career memory.

### v0.4 — Team Memory *(optional)*
Shared wings across multiple developers. CRDT or simple lock-based sync. Only if demand exists. **Will never be a cloud service.** Self-hosted only.

### v0.5 — Agent Memory
Per-agent wings. Crucible remembers the assumptions it has stress-tested before. Quality remembers the patterns that have led to ship-it verdicts. Reason remembers the rabbit holes.

### v1.0 — Cairntir the Library
Extract the memory layer as an importable library that other tools can depend on. At v1.0, Cairntir stops being "a tool" and becomes "the thing other tools store their memory in." This is when the network effect starts.

---

## The Horizon — AI + Grand-Scale 3D Printing + Post-Scarcity

This section is **mythos**, not a commitment. It exists because every contributor deserves to know what Cairntir is ultimately pointed at.

### The Observation

AI can model anything. Tomorrow, AI will print anything — not just at desktop scale, but at grand structural scale. Construction-scale 3D printing already exists (WinSun, ICON, Apis Cor). The bottleneck is no longer atoms or machines. The bottleneck is **knowledge that compounds across iterations**.

Every time a printer runs, it produces data: which temperature worked, which infill density failed, which nozzle wore out after how many meters, which grain orientation was load-bearing, which material substitution was within tolerance and which was not. Today, almost all of that data is lost. The next print starts from the same ignorance as the last print.

### The Bridge Cairntir Builds

Cairntir is a memory layer that **does not care what kind of thing is being remembered**. Today it remembers code decisions. Tomorrow, with a different client, it can remember:

- Print parameters and outcomes (a `wing` for each project, `rooms` per material, `drawers` per iteration)
- Failure modes and their causes
- Substitutions that worked in context A but not context B
- Which operator intuitions proved correct over time
- Which design tweaks compounded into step-changes

The MCP surface is already generic. A Blender MCP plugin that pushes print-outcome drawers into Cairntir is the same code shape as the Claude Code plugin that pushes decision drawers in. The memory layer does not need to know.

### What This Enables, Eventually

A machine that prints its own thingamajigs needs to remember which thingamajig worked. When it remembers, the iteration cost drops. When the iteration cost drops toward zero, scarcity drops toward zero. When scarcity drops toward zero, the economics of giving things away change completely.

This is not a promise. It is a **direction**. Cairntir does not need to reach this horizon to be useful today. But the reason it is built the way it is — opinionated, local-first, MIT, verbatim, generic MCP surface — is because *the form matches the destination*. A centralized cloud SaaS cannot be the memory layer of a distributed post-scarcity maker civilization. A local-first file-backed open-source library can.

### The Wager

> *"I'm going to take my chances with the best outcome for earthlings, the environment, and tech, all in one go. And if it doesn't, then I'll still die knowing that I tried."* — Patrick McGuire, 2026-04-08

Cairntir is that bet made small. The bet is: *a memory layer that actually works will matter more than we can currently imagine, and building it in the open is the right move even if no one notices for five years.*

If the bet is wrong, Cairntir is still a useful tool that killed a real annoyance for solo developers. That is already enough to justify its existence.

If the bet is right, Cairntir is an early load-bearing beam in a much larger structure.

Either way, we build.
