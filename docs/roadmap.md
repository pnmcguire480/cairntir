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

## v0.1.0 — First Public Release ✅
- ~~PyPI publish~~ **intentionally skipped** — install from source / Claude Code plugin; local-first
- GitHub Release with notes
- Docs site live at `pnmcguire480.github.io/cairntir/`
- Discord or GitHub Discussions for community
- Blog post: "The Amnesia Problem and What It Cost Me"

---

## The Road to 1.0 — Round Table Edition

This section is **committed**, not directional. It is the path from v0.1.0 to
v1.0.0, locked in 2026-04-08 after a round table of eight thinkers
(Karpathy, LeCun, Sutskever, Hinton, Fuller, Peter Joseph, Alan Watts, Uncle
Bob) reviewed the original "Long Road" plan and converged on five themes:

1. **Prediction-bound drawers** — every drawer can carry `claim`,
   `predicted_outcome`, `observed_outcome`, `delta`, `supersedes_id`. The
   AutoResearch Loop's substrate. Karpathy, LeCun, Hinton, Sutskever,
   Fuller, and Uncle Bob all flagged this independently.
2. **Consolidation + forgetting** — verbatim is the floor, not the ceiling.
   Sleep-cycle pass that promotes derived drawers and demotes unused ones.
   Hinton, Watts, LeCun.
3. **Surprise as the load-bearing field** — store what the system did not
   expect, not just what happened. Reconstruction-error / delta is the
   gradient when there are no weights. LeCun, Fuller, Hinton, Karpathy.
4. **Portable signed format = anti-capture** — format is the product, not
   the implementation. Content-addressed, signed, gossip-importable.
   Peter Joseph, Fuller.
5. **Cut Team Memory** — replicable beats shared. Team capability falls out
   of the portable format for free. Karpathy, Fuller.

### v0.2 — Prediction-Bound Drawers + Eval-on-Every-PR
- Drawer schema migration: add `claim`, `predicted_outcome`,
  `observed_outcome`, `delta`, `supersedes_id` (all optional, append-only)
- Versioned schema with forward-only migrations + round-trip fixture tests
- LongMemEval subset wired into CI; PR fails on regression
- Reason skill must emit a prediction drawer before acting

### v0.3 — Consolidation, Forgetting, Contradiction
- Nightly `consolidate` pass: cluster recent drawers, write derived
  abstractions one layer up, keep verbatim underneath
- Replay-weighted forgetting curve: drawers untouched in N days drift
  to a cold layer (demotion, not deletion)
- Contradiction detector during consolidation — flag, never average

### v0.4 — Surprise & Belief-as-Distribution
- `delta` becomes a first-class retrieval signal (Room Prior residual)
- Retrieval distribution itself is the belief: successful uses raise
  drawer mass for that context, dead retrievals lower it
- Bayesian bookkeeping over a verbatim corpus, no training pipeline

### v0.5 — Portable Signed Format (Anti-Capture Lock)
- Versioned, human-readable, signed interchange format for drawers
- Content-addressed hashes; provenance as a first-class field
- `cairntir export` / `cairntir import` over any substrate (USB, IPFS,
  git, mailing list) — gossip + torrents, no server, ever
- Structural prohibition: no drawer may reference a non-drawer URL

### v0.6 — Reason Loop Through Clean Ports
- `cairntir.reason.model`: Hypothesis / Experiment / Outcome / BeliefUpdate
- `cairntir.reason.ports`: HypothesisProposer / ExperimentRunner /
  BeliefStore / MemoryGateway protocols
- `ReasonLoop.step()` — testable without LLMs, networks, or sqlite
- Production wiring lives outside the library

### v1.0.0 — Library Extraction
- `cairntir.__init__` exposes ONLY protocols + dataclasses + exceptions:
  `Drawer`, `Layer`, `Wing`, `Room`, `Store`, `Retriever`,
  `EmbeddingProvider`, typed errors. That is the entire contract.
- Concrete impls move to `cairntir.impl.*` (importable, but reservedright-to-change)
- CLI / MCP server / daemon split into separate distributions
  (`cairntir-cli`, `cairntir-mcp`, `cairntir-daemon`) that import `cairntir`
- Written deprecation policy: 2 minor versions warning minimum;
  `CairntirDeprecationWarning` subclass; no silent removals
- Contract test suite that every `Store` impl must pass
- Property-based tests (Hypothesis) on taxonomy invariants and retrieval
  monotonicity
- Public-API snapshot test that fails on `dir(cairntir)` drift
- Migration tool with fixtures from every prior schema version, kept
  forever
- Integration guide: *"How to put Cairntir behind your own tool"*

**Cut from the original v0.2-v1.0 plan:**
- v0.4 Team Memory — deferred indefinitely; replicable format makes it
  unnecessary
- v0.2 Temporal Knowledge Graph as a *standalone* feature — falls out of
  prediction-bound drawers + supersedes edges naturally; do not force
  triples up front

---

## Recipes — post-v1.0 protocols on the stable surface

A **recipe** is a repeatable protocol that chains existing primitives
(the three skills + the memory layer) into a named discipline. Recipes
land under `docs/recipes/` and live or die by use, not by governance.

The three-skill core (crucible / quality / reason) is locked by design.
Recipes are the escape valve: anything that would have been a fourth
skill becomes a recipe instead. This keeps the protocol surface narrow
and the pattern surface unbounded.

### Signal Reader *(shipped 2026-04-14)*

Five-step structural-analysis protocol: split the headline story from
the structural story, name the constraint that moved, project gains and
losses, stress-test through Crucible, commit as a prediction-bound
drawer in a `signals` wing. Every read carries a falsifiable claim; the
belief-as-distribution scorer tracks calibration across months.
[docs/recipes/signal-reader/](recipes/signal-reader/)

### Candidate recipes *(not committed — surface when demand appears)*
- **Codebase Autopsy** — read under a PR the same way Signal Reader
  reads under a news event. Which architectural constraint actually
  moved? Who on the team gains leverage, who loses it?
- **Decision Replay** — given a past decision drawer and its supersedes
  chain, replay it against today's context. Would the decision hold?
- **Vendor Drift** — sustained structural watch on a third-party tool
  or API you depend on. Belief mass tracks whether your read of the
  vendor's trajectory is calibrated.

---

## Beyond v1.0.0 — The Long Road

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
