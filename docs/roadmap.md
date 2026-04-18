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

## The Road to 2.0 — Memory That Thinks Back

This section is **committed**, not directional. It is the path from v1.0.0
(shipped 2026-04-14) to v2.0.0, written 2026-04-14 in full awareness of
what the v0.2 → v1.0 arc actually taught us.

### The v2 North Star

> *A cairn is useful to a traveler. A cairntir is useful to a civilization.*

v1.0 killed cross-chat amnesia for **one developer's sessions**. v2 kills
cross-chat amnesia for **every agent, every project, every collaborator
the memory touches**. The fundamental shift: at v1.0 Cairntir is a
passive store that humans query through Claude. At v2 Cairntir is an
active participant — it runs recipes, it drives the Reason loop against
real LLMs, it syncs across machines over files, and it grows structural
memory whether or not any particular human is looking.

Five themes, shipped as six versioned phases.

1. **Real production reasoning.** The v0.6 Reason loop has clean
   Protocol ports but no concrete adapters. v2 ships reference adapters
   against Claude so the loop actually runs, the calibration numbers
   actually compound, and the Signal Reader recipe can be invoked
   autonomously instead of hand-walked through each step.
2. **Cross-wing and temporal.** The deferred MemPalace v3 feature
   finally lands — but falls out of existing `supersedes_id` chains, not
   a new triple store. Answers "what did we decide about X across every
   project?" and "what did I believe about X as-of date Y?"
3. **File-based team sync, no server ever.** The portable signed format
   (v0.5) made this inevitable; v2 wires the watcher. One folder shared
   via git / iCloud / Dropbox / Syncthing becomes a team memory
   substrate. Content hashes deduplicate; signatures authenticate.
4. **Recipe runtime.** Recipes become executable. A "signal-read this
   URL" command that actually invokes the protocol, writes the drawers,
   runs Crucible, commits predictions — all without a human driving each
   step.
5. **Agent Memory.** Per-agent wings. Crucible remembers which
   assumptions it has stress-tested before. Quality remembers which
   patterns lead to ship-it verdicts. Reason remembers the rabbit holes
   it's fallen down. The three skills get their own memory of their own
   work.

### v1.1 — Reach *(the post-launch phase)*

- PyPI publish: `pip install cairntir` goes live
- Blog post: *"The Amnesia Problem and What It Cost Me"*
- Reference Blender MCP plugin: the horizon → product bridge, proves
  the "Cairntir doesn't care what kind of thing is being remembered"
  thesis by actually remembering something that isn't code
- Fix whatever the first wave of external users breaks
- Submit to Awesome MCP lists + LongMemEval leaderboard

### v1.2 — Production Reason Loop — **delivered ahead of schedule in v1.1 (2026-04-18), stdlib-only**

Shipped in `cairntir.production`: `ManualProposer`, `StoreBackedMemory`,
`StoreBackedBeliefs`, `NullRunner`. CLI `cairntir reason "<q>" --wing X`
runs a real predict→observe→update cycle with the caller-supplied
hypothesis. Zero network calls — Cairntir is not a second inference
provider; the claim and predicted outcome come from wherever the
caller chooses (human at a terminal, Claude Code session driving the
CLI, a recipe's declared inputs).

**Future additions (separate phases, not v1.1):**

- **Local-AI proposer — Gemma 4 via llama.cpp or Ollama.** Implements
  `HypothesisProposer` as a Python process driving a local model,
  no billed API, no telemetry. Aligns with Cairntir's local-first
  ethos and matches the pattern already proven in Transcript
  Capture (Whisper.cpp + Gemma for summarization). Planned once
  the synergy stack has been exercised in the field and recipe
  patterns clarify which inference shapes actually pay off.
- **`SandboxRunner`** — a real `ExperimentRunner` that executes
  shell commands. Its own security project; `NullRunner` covers
  the manual-verdict case recipes need today.
- **Calibration dashboard** (`cairntir calibration --wing signals`)
  — useful but not load-bearing until there are enough prediction-
  bound drawers to be worth visualizing.

### v1.3 — Cross-Wing Queries + Temporal View — **v1.3-partial delivered in v1.1 (2026-04-18)**

Shipped: `cairntir_cross_recall` MCP tool + `cairntir cross-recall` CLI;
`cairntir.memory.temporal.walk_supersedes` / `as_of` as pure query
functions over the existing `supersedes_id` column. **Still outstanding
for a follow-up phase:**

- `cairntir timeline --entity X` cross-wing mode (the existing
  `cairntir_timeline` tool is still per-wing)
- **Decision Replay** recipe — given a past decision drawer, replay
  it against today's context and flag contradictions
- Per-wing belief-mass cross-comparison (`cross_recall` returns raw
  semantic distance for now; cross-wing belief reranking is a
  research question)

### v1.4 — File-Based Team Sync

- `cairntir sync <directory>` — watches a folder, auto-imports new
  envelopes as they appear, auto-exports on drawer commit
- Content-hash deduplication means syncing the same folder via two
  different transports is idempotent and conflict-free
- Signatures gate imports — set a `--trust <keyfile>` flag and
  unsigned or wrong-key envelopes land in a quarantine wing, not the
  main store
- Documentation: *"Syncing Cairntir with git"*, *"Syncing with
  Syncthing"*, *"Syncing with a USB stick"* — all three work the same
  way because the substrate is irrelevant to the format

### v1.5 — Recipe Runtime — **delivered ahead of schedule in v1.1 (2026-04-18)**

Shipped: `cairntir.recipes` package with `RecipeContract`, `load_recipe`,
`discover_recipes`, `RecipeRunner`. `cairntir recipe-list` and
`cairntir recipe-run` CLI. `docs/recipes/signal-reader/recipe.toml`
bundled as the first shipped recipe. Recipe contracts declare input
schema + output wing + ordered skill chain; malformed recipes fail
loudly via `RecipeError`. Project recipes shadow user recipes when
names collide.

### v1.6 — Agent Memory

- Per-agent wings: every skill gets its own wing under a reserved
  `agent:` prefix (e.g. `agent:crucible`, `agent:reason`)
- Crucible learns: at the end of a stress-test, writes what the
  assumption was, what the stress pattern revealed, and whether the
  user accepted or rejected the verdict. Next time a similar
  assumption comes in, Crucible recalls the prior pass
- Quality learns: which code shapes consistently earn ship-it vs
  block verdicts, per user and per wing
- Reason learns: which rabbit holes yielded useful structural
  insights and which produced nothing — so the cost of future
  exploration drops
- No new primitives — this is Cairntir eating its own dog food
  using only the memory + recipe surface v1.0 already shipped

### v2.0.0 — Distribution Split + Breaking Changes

- The deferred v1.0 commitment finally lands: split into three
  packages that depend on `cairntir`:
  - `cairntir-cli` — the human-facing commands (setup, recall,
    status, export, import, migrate, sync, recipe, reason)
  - `cairntir-mcp` — the stdio MCP server + tool specs
  - `cairntir-daemon` — the auto-capture spool watcher
- `cairntir` itself becomes a small library: Protocol surface, value
  types, exceptions, `impl/`. Everything else lives in the satellites.
- Any deprecations accumulated across v1.1–v1.6 land and their
  two-minor-release windows close
- The public API snapshot test gets a new baseline
- Tag, GitHub release, blog post: *"v2 — Memory That Thinks Back"*

**Cut from v2:**
- Team-memory-as-a-feature (CRDTs, conflict resolution): file-based
  sync makes this a non-problem; if it turns out to be wrong we'll
  rebuild it in v3
- Triple store / entity-resolution pipeline: the temporal view over
  supersedes chains answers 90% of the questions a triple store
  would; don't build the infrastructure for the remaining 10%
- Hosted SaaS / team sync service: **never**. The horizon does not
  route through a centralized service. Every feature must survive
  the "this could live on a USB stick" test.

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
