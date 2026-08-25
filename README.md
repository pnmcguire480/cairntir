<!--
Cairntir — host-neutral memory-first reasoning layer for AI coding agents.
Keywords: Claude Code memory, Claude Code plugin, MCP server, AI memory,
cross-session memory, persistent context, Claude memory, Anthropic MCP,
kill AI amnesia, Claude Code extension, Python MCP server, sqlite-vec
memory, Claude Code MCP, Anthropic Claude memory, Model Context Protocol.
-->

# Cairntir

### **One evolving memory for Codex, Cursor, Claude Code, and every MCP agent.**

Cairntir is a local-first, open-source memory system for Codex, Cursor,
[Claude Code](https://claude.com/claude-code), and every other
[Model Context Protocol](https://modelcontextprotocol.io/) client. It kills
cross-chat and cross-agent AI amnesia: a lesson written through one host is
available to the next. Evidence stays verbatim, while an append-only Discovery
Ledger exposes what Cairntir is learning instead of hiding it in an opaque
optimization loop.

> *A stack of stones that sees across time.*
>
> Cairntir = **cairn** (stacked waypoint stones marking a path) + **palantír** (seeing-stone across time and distance). Pronounced *CAIRN-teer*.

[![PyPI version](https://img.shields.io/pypi/v/cairntir.svg)](https://pypi.org/project/cairntir/)
[![PyPI downloads](https://img.shields.io/pypi/dm/cairntir.svg)](https://pypi.org/project/cairntir/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![mypy: strict](https://img.shields.io/badge/mypy-strict-blueviolet.svg)](https://mypy.readthedocs.io/)
[![ruff](https://img.shields.io/badge/ruff-clean-green.svg)](https://github.com/astral-sh/ruff)
[![CI](https://github.com/pnmcguire480/cairntir/actions/workflows/ci.yml/badge.svg)](https://github.com/pnmcguire480/cairntir/actions/workflows/ci.yml)
[![MCP compatible](https://img.shields.io/badge/MCP-compatible-purple.svg)](https://modelcontextprotocol.io/)

---

## The one-minute pitch

Every time you open a new Claude Code chat, Claude forgets everything from the last one. You explain the same architectural decision again. You re-litigate yesterday's trade-off. You hallucinate a reason for a choice you can't remember making. It's the single biggest productivity tax on working with LLMs day-to-day, and it's fixed by a file.

**Cairntir is that file.** It's a SQLite database on your hard drive that stores every decision, fact, and hard-won lesson Claude writes down — verbatim, forever, no summarization — and gives it back the next time you open a chat. Every session, in every project, on day 30, walks into a lit room.

It ships as an [MCP server](https://modelcontextprotocol.io/), so it works with **Claude Code, Claude Desktop, Cursor, Windsurf, and every other MCP-compatible client** without modification.

And it is built for a hard monthly ceiling, not an expense account. The design
rule is **never return a token the model cannot use** — because on a $20 plan,
context you paid for and can't read is the expensive kind.

---

## Install

```bash
pip install cairntir           # live on PyPI
cairntir setup                 # store + every host it can find
```

Restart the configured hosts. `setup` does not require the Claude Code
CLI — a Cursor-only machine completes the same command. Missing CLIs
are skipped, not fatal. Cursor's global MCP entry is installed
automatically, but its global User Rule must be pasted into
**Cursor Settings → Rules → User Rules** because Cursor does not publish a
file-backed global-rule surface; `setup` prints the text. Project-local
Cursor setup is fully automatic: `cairntir init --host cursor`.

To (re)wire one host later: `cairntir init --host all --user`.

**Once installed, Cairntir stays on.** Every `cairntir` CLI invocation silently re-verifies the user-scope MCP registration and re-registers the stable `cairntir-mcp` launcher if Claude Code can't find it. Moving venvs, upgrading Python, or reinstalling no longer breaks the wiring — `pip install cairntir` is TRUE, `pip uninstall cairntir` is FALSE, nothing in between. When a newer release lands on PyPI, the next CLI run and the next MCP tool response prepend a one-line update banner; nothing is interrupted.

Both side effects are opt-out for CI / air-gapped use:

- `CAIRNTIR_DISABLE_AUTOREGISTER=1` — skip the silent self-heal MCP registration.
- `CAIRNTIR_DISABLE_UPDATE_CHECK=1` — skip the background PyPI version check and never print the update banner.

Not sure about any of those steps? Read **[docs/cairntir-for-dummies.md](docs/cairntir-for-dummies.md)** — zero-prior-knowledge getting-started guide.

---

## Day 30

This is the whole point. It's why it exists.

You open a Claude Code chat in a project you haven't touched in three weeks. Normally this starts with: *"OK, remind me — what are we doing here, which database did we pick, why does `auth.py` have that weird hack in it, and what was blocking the last PR?"*

With Cairntir installed:

1. The chat starts. The installed policy tells the agent to call `cairntir_handoff` before answering anything.
2. Cairntir composes one brief: the operating protocol, the last few session deltas **in full text**, open questions, and — if Claude passes the files it's about to touch — the memory anchored to that code.
3. Claude reads them. It now knows you picked Postgres, why you picked it, what the hack in `auth.py` is protecting, and what's on next session's list.
4. You type your question. The answer comes back with real context — and drawer id citations, so you can click through to the source.

That's walking into a lit room. That's the North Star. Every feature in this repo is measured against whether it makes that experience feel inevitable.

---

## The budget is the feature

A memory layer that dumps everything it has is just a slower way to run out of
context. Cairntir's read path is built around one rule:

> **Never return a token the model cannot use.**

`cairntir_handoff(wing)` returns **whole drawers under a hard character
budget**. Nothing is truncated — a drawer either comes back complete or it is
listed by id and size so you can fetch exactly the one you want. Truncation is
the anti-pattern here: it pays the full token cost *and* destroys the
information.

Measured against the older `session_start`, on a real store, 2026-08-02:

| wing | `session_start` | `handoff` | |
|---|---:|---:|---:|
| `cairntir` | 7,737 tok | 4,261 tok | **−44%** |
| `detroit-clone` | 8,201 tok | 3,880 tok | **−52%** |

The saving is the less interesting half. On the `cairntir` wing, `session_start`
spent its 7,737 tokens on **54 truncated stubs** that could not answer anything;
`handoff` spent 4,261 on **9 complete drawers that could**, and named the 13 it
skipped so you could fetch any of them deliberately. Cheaper *and* usable is the
only version of cheaper worth having.

Those are one store on one day, not a benchmark. `session_start` grows with the
wing, so the gap widens as a project accumulates history — which is exactly when
you need the budget. Run `cairntir cost` on your own store rather than taking
these numbers as a promise.

The default drawer-only handoff is deterministic — no ranking, no embedder,
pure SQL — so repeat calls are byte-identical and stay friendly to your host's
prompt cache.

And you can audit it yourself, which is the point:

```bash
cairntir cost myproject
```

That reports what the tool catalog, `session_start`, and `handoff` each cost,
plus how much of your corpus exceeds the embedder's input window. Cairntir
measures its own overhead rather than asking you to trust it.

## If the session dies before the first memory write

Transcript recovery is explicit and read-only:

```bash
cairntir recover --host codex --wing myproject
cairntir handoff myproject --recover-from codex
```

Qwen Code, Claude Code, and Codex adapters inspect only a bounded tail from the
newest non-live project session. Recovered user messages are returned whole
under their own character budget with `trust=untrusted` and
`instruction_authority=none`. They never become drawers automatically.
`cairntir recover --host codex --wing myproject --write 1` is the explicit
consent path for one returned message. Cursor reports unsupported because its
documented local SQLite history has no stable transcript schema Cairntir can
read honestly.

---

## Why this and not the other ones

| | Cairntir | [MemPalace](https://github.com/milla-jovovich/mempalace) | Ad-hoc CLAUDE.md files |
|---|---|---|---|
| Verbatim storage | ✅ | ✅ | ✅ |
| Wing / room / drawer taxonomy | ✅ | ✅ | ❌ |
| 4-layer retrieval (identity / essential / on-demand / deep) | ✅ | ✅ | ❌ |
| Semantic search | ✅ `sqlite-vec` | ✅ | ❌ |
| **Prediction-bound drawers** (claim → predicted → observed → delta → supersedes) | ✅ | ❌ | ❌ |
| **Belief-as-distribution ranking** (reinforce / weaken, surprise-weighted) | ✅ | ❌ | ❌ |
| **Portable signed format** (content-addressed, HMAC-signed, gossip-able) | ✅ | ❌ | ❌ |
| **Consolidation + forgetting curve** (sleep-cycle pass, contradiction detection) | ✅ | ❌ | ❌ |
| **Library seam** (Protocol surface + contract test suite for custom backends) | ✅ | ❌ | ❌ |
| **Clean-ports Reason loop** (LLM-agnostic, testable without network) | ✅ | ❌ | ❌ |
| **Budgeted handoff** (whole drawers under a hard ceiling, never truncated) | ✅ | ❌ | ❌ |
| **Self-measured token cost** (`cairntir cost` audits its own overhead) | ✅ | ❌ | ❌ |
| MCP server | ✅ stdio | ✅ | ❌ |
| One-command install wizard | ✅ `cairntir setup` | ❌ | N/A |

**Cairntir borrows MemPalace's taxonomy — credit where due** — and layers on the reasoning discipline the round-table of eight thinkers committed to in the v0.2–v1.0 arc. See [docs/lineage/mempalace.md](docs/lineage/mempalace.md) for the full "what we kept, what we didn't" breakdown.

---

## The six moving parts

1. **`Drawer`** — one verbatim memory entry. Content, metadata, retrieval layer, optional prediction fields (`claim`, `predicted_outcome`, `observed_outcome`, `delta`, `supersedes_id`), belief mass. Frozen pydantic model.
2. **`DrawerStore`** — SQLite + sqlite-vec backend. Forward-only schema
   migrations (v1 → v6 so far), with explicit embedding identity, immutable
   provenance, durable workflow receipts, and backup-first migration/reindex.
   Contract-tested via
   [tests/contract/test_store_contract.py](tests/contract/test_store_contract.py).
3. **MCP server** — **20 tools** over stdio: exact memory, scoped and
   cross-wing recall, **structural recall for a set of changed files**,
   **the budgeted handoff brief**, session start, timeline, audit, Crucible,
   Discovery Ledger/calibration, and CodeGlass operations. Runs via
   `python -m cairntir.mcp.server`.
4. **Three skills** — `crucible` (stress-test assumptions), `quality` (audit a wing), `reason` (memory-backed thinking loop with a mandatory predict step). Bundled as markdown, loaded via `importlib.resources`.
5. **Reason loop** — `ReasonLoop.step()` over four Protocol ports (`HypothesisProposer`, `ExperimentRunner`, `BeliefStore`, `MemoryGateway`). Testable without LLMs, networks, or SQLite. See [docs/integration-guide.md](docs/integration-guide.md).
6. **Discovery Ledger** — evidence-backed signals move through `signal →
   candidate → corroborated → promoted/rejected/expired` as append-only
   drawers. Repeated Reason episodes can propose calibrated candidates but
   cannot promote themselves. Active discoveries appear at session start;
   `cairntir learning-log` gives the human-readable learning history.

---

## Who it's for

- **Solo developers** who work with Claude Code daily and lose an hour every Monday re-explaining Friday's decisions.
- **Small teams** that want a per-developer memory layer today and a portable, gossip-able shared memory tomorrow (the v0.5 portable format makes team sync a file-copy, no server).
- **Tool builders** embedding Claude or an MCP client in their own product. Cairntir's v1.0 contract is a stable Protocol surface you can implement a custom backend against — Redis, Postgres, a hosted vector DB, whatever you already run.
- **Researchers** tracking which hypotheses held, which failed, and by how much. The prediction-bound drawer schema (v0.2) is a log-structured experiment journal; the belief-as-distribution scorer (v0.4) is the scoreboard.
- **People building toward post-scarcity manufacturing.** Yes, really — see [the horizon](#the-horizon) at the bottom of this README.

---

## Compatible with

**First-class adapters** (`cairntir setup` / `cairntir init --host`):
**Claude Code, Codex, Cursor, and Qwen Code**, sharing one store with
per-write host provenance.

**Any other MCP client** — Claude Desktop, Windsurf, Zed, and the rest of
the [MCP client list](https://modelcontextprotocol.io/clients) — can
point at `cairntir-mcp` themselves. There is no `init` target for those
names; they are generic stdio, not first-class hosts.

Pairs naturally with:
- **Git hooks** — auto-capture commit messages as drawers via the daemon's spool directory.
- **Obsidian / Anthropicer** — project the learning log and verified
  CodeGlass walkthroughs one-way with `cairntir obsidian-project`; SQLite
  stays authoritative and human notes are preserved.
- **Linear / GitHub issues** — daemon picks up mentions and cross-references to drawer ids.
- **VS Code** — decision-marker extension (planned, not shipped) writes to the spool as you type.

---

## Recipes — protocols built on the three skills

Cairntir's core surface is three skills (crucible / quality / reason) and a
memory layer. **Recipes** chain those primitives into repeatable protocols
for specific use cases without expanding the skill set. They live under
[docs/recipes/](docs/recipes/).

### Signal Reader — structural analysis of AI news

Read *under* the news cycle. Split the headline story from the structural
story, name the constraint that actually moved, project gains and losses,
stress-test through Crucible, write the result as a **prediction-bound
drawer** in a `signals` wing. Every committed read carries a falsifiable
claim; the belief-as-distribution scorer tracks your calibration across
months.

Nate-style one-shot structural reads produce analysis. Cairntir's version
produces *compounding* analysis — three months of committed reads tell
you which constraint categories you read well and which you consistently
miss.

> **Recipe:** [docs/recipes/signal-reader/](docs/recipes/signal-reader/)
> **Worked example:** [march-2026.md](docs/recipes/signal-reader/examples/march-2026.md) — five structural reads run through the full protocol, formatted as prediction-bound drawers ready for `cairntir_remember`.
> **Trigger:** *"signal-read this"*, *"what's the structural story?"*, *"run the fog protocol"*.

### Decision Replay — close the loop on a past call

`cairntir replay <id>` walks the supersedes chain from a decision, pulls the
leaf's claim and predicted outcome, asks what actually happened, and writes the
result back onto the chain as a new prediction-bound drawer with a Crucible
marker. It is how a guess from three months ago becomes a scored one.

> **Recipe:** [docs/recipes/decision-replay/](docs/recipes/decision-replay/)

### CodeGlass — turn unfamiliar code into durable understanding

Evidence-cited five-part walkthroughs, immediate and delayed teach-back, and
retention tracking, so reading a codebase produces something that survives the
session. Built for people who ship useful software without formal CS training.

> **Recipe:** [docs/recipes/codeglass/](docs/recipes/codeglass/)

More recipes will land as patterns prove themselves. The governance rule
is firm: three skills, unbounded recipes, never a fourth core primitive.

---

## Example: what lives in a Cairntir database

```
cairntir recall "database decisions" --wing myapp

#12  [essential]  we picked Postgres over SQLite for the live tier
                  reason: SQLite couldn't handle the concurrent-write
                  pattern we measured in load testing on 2026-01-15
                  cited by: #47 #91 #103

#47  [on_demand]  followup: connection pooling broke at 500qps
                  observed_outcome: pgbouncer in transaction mode fixed it
                  supersedes: #18 (wrong prediction about prepared statements)

#91  [on_demand]  migration 0042 was safe because rows < 50M
                  claim: ALTER TABLE ... ADD COLUMN NOT NULL is safe
                    at this scale
                  predicted_outcome: no downtime
                  observed_outcome: no downtime, 3s lock window

#103 [deep]       original pre-Postgres analysis from 2025-12
                  (demoted by the forgetting curve)
```

Every one of those is the literal text Claude wrote during a session you had weeks ago. Nothing is summarized or interpreted. If you want to know why you made a decision, the decision is right there, timestamped, citable, and searchable.

---

## Project structure

This is a **seam sketch**, not an inventory. `src/cairntir/` has many
more modules than this block names. `addons/cairntir_blender/` is the
working Blender add-on; `examples/blender-mcp-plugin/` is a scaffold
only. `plans/README.md` says which plans are live.

```
cairntir/
├── src/cairntir/
│   ├── __init__.py         # v1.0 public protocol surface — the stable seam
│   ├── contracts.py        # Store protocol every backend must satisfy
│   ├── impl/               # Concrete impls — reserved right to change
│   ├── memory/             # DrawerStore, belief scorer, consolidate, embeddings
│   ├── reason/             # ReasonLoop + four Protocol ports
│   ├── mcp/                # Host-neutral MCP stdio server
│   ├── portable.py         # Signed envelope format (v0.5)
│   ├── skills/             # crucible.md, quality.md, reason.md
│   ├── handoff.py          # Budgeted brief composition — whole drawers only
│   ├── cost.py             # What Cairntir's own read path costs
│   ├── daemon/             # Auto-capture spool watcher
│   └── cli.py              # cairntir setup | init | handoff | recover | cost | recall | replay | doctor | export | import
├── scripts/
│   ├── check_release_tags.py         # A changelog entry is not a release
│   └── check_landed_commitments.py   # A plan that promises something must deliver it
├── tests/
│   ├── unit/               # The bulk of the suite
│   ├── contract/           # Store contract suite — every impl must pass
│   ├── property/           # Hypothesis-driven invariants
│   ├── integration/        # MCP backend + daemon
│   └── eval/               # LongMemEval R@5 subset (fail-on-regression CI gate)
├── addons/cairntir_blender/ # Working Blender add-on (not in the wheel)
├── plans/                  # Live plans + dated history — see plans/README.md
└── docs/
    ├── how-to-use.md               # Human front door (must match the shipped product)
    ├── cairntir-for-dummies.md     # Zero-knowledge getting-started guide
    ├── conception.md               # Origin story + ethos + horizon
    ├── concept.md                  # What Cairntir is (the three ingredients)
    ├── manifesto.md                # Why Cairntir exists
    ├── integration-guide.md        # How to embed Cairntir in your own tool
    ├── deprecation-policy.md       # What "stable" means at v1.0
    ├── release-cadence.md          # Commit vs. merge vs. tag, and how a version is chosen
    ├── landed-commitments.md       # How CI verifies a plan actually shipped
    ├── roadmap.md                  # v0.2 → v1.0 arc + beyond
    └── lineage/                    # What we kept from BrainStormer + MemPalace
```

---

## Conception — the 30-second version

Cairntir is the distillation of two predecessors:

- **[MemPalace](https://github.com/milla-jovovich/mempalace)** — brilliant wing/room/drawer taxonomy, 96.6% LongMemEval R@5, but no reasoning layer. We borrowed the concepts, not the code. **That 96.6% is MemPalace's number, not ours.** Cairntir's CI gate is 80% R@5 on a 10-question internal subset.
- **BrainStormer** — the author's prior attempt. Great vocabulary (Crucible, Quality, ETHOS), terrible runtime (224 silent `except: pass` blocks, "architecture of a learning system, runtime of a static scaffolder"). Preserved as read-only lineage; reimplemented from scratch.

On 2026-04-08, a **round table of eight thinkers** — Karpathy, LeCun, Sutskever, Hinton, Fuller, Peter Joseph, Alan Watts, Uncle Bob — reviewed the long-road plan and converged on five themes that are now the committed v0.2 → v1.0 arc:

1. **Prediction-bound drawers** — every drawer carries `claim`, `predicted_outcome`, `observed_outcome`, `delta`. The gradient when there are no weights.
2. **Consolidation + forgetting** — verbatim is the floor, not the ceiling. Sleep-cycle pass, replay-weighted demotion, contradiction detection.
3. **Surprise as the load-bearing field** — store what the system did *not* expect. Reconstruction error is the learning signal.
4. **Portable signed format = anti-capture** — format is the product, not the implementation. Content-addressed, HMAC-signed, gossip-importable. A SaaS can be captured. A file on a USB stick cannot.
5. **Cut Team Memory as a feature** — replicable beats shared. Team capability falls out of the portable format for free.

Full story: **[docs/conception.md](docs/conception.md)**.

---

## Standing on other people's work

Cairntir borrows concepts, never code. Every source gets a lineage doc naming
the author, what we kept, and — the part that actually matters — **what we
dropped and why**. The doc lands *before* the feature it credits, so it is
structurally impossible to ship first and credit afterward. We never reuse
anyone's benchmark numbers as our own, and every lineage doc says plainly when
the other project is the better fit.

| Source | What Cairntir took | Status |
|---|---|---|
| **[MemPalace](https://github.com/milla-jovovich/mempalace)** by [@milla-jovovich](https://github.com/milla-jovovich) | Wing / room / drawer taxonomy, 4-layer retrieval, verbatim storage | Shipped — [lineage](docs/lineage/mempalace.md) |
| **BrainStormer** (the author's own prior attempt) | Reasoning vocabulary — Crucible, Quality, ETHOS | Shipped — [lineage](docs/lineage/brainstormer.md) |
| **[mattpocock/skills](https://github.com/mattpocock/skills)** by [@mattpocock](https://github.com/mattpocock) | The premise that a shared project vocabulary is a first-class artifact | **Scoped, not built** — [lineage](docs/lineage/mattpocock-skills.md) |
| **[code-review-graph](https://github.com/tirth8205/code-review-graph)** by [@tirth8205](https://github.com/tirth8205) | Structural recall — memory reachable by what you're changing, not only what you asked | Shipped in 1.2.0 — [lineage](docs/lineage/code-review-graph.md) |

On the two current sources, plainly:

**mattpocock/skills is the better tool for most people right now.** If you want
engineering practices your agent will actually follow — test-first discipline,
structured debugging, real code review, triage — install his, not ours. Cairntir
has no equivalent and isn't building one. The two compose rather than compete:
his skills make an agent better *within* a session, and none of them — none of
anyone's — remember anything after that session ends. That gap is the layer
Cairntir works on.

**code-review-graph is the better tool whenever the question is about your code
rather than about your collaboration.** What a change breaks, which modules
cluster, where the architectural bridges are, risk-scored PR comments — Cairntir
answers none of that and isn't going to. It runs happily as a second MCP server
alongside Cairntir; that's a supported setup, not a fallback. Cairntir reads what
you *said about* your code, never the code itself.

---

## The horizon

This section is mythos, not a commitment. But every contributor deserves to know what Cairntir is ultimately pointed at.

> **AI + grand-scale 3D printing + post-scarcity tooling.**

AI can model anything. Tomorrow, AI will print anything — not just at desktop scale, but at construction scale. Construction-scale 3D printing already exists (WinSun, ICON, Apis Cor). The bottleneck is no longer atoms or machines. **The bottleneck is knowledge that compounds across iterations.**

Every time a printer runs, it produces data: which temperature worked, which infill density failed, which nozzle wore out after how many meters, which grain orientation was load-bearing. Today, almost all of that data is lost. The next print starts from the same ignorance as the last.

Cairntir is a memory layer that does not care what kind of thing is being remembered. Today it remembers code decisions. Tomorrow, with a Blender MCP plugin or a printer-control adapter, it can remember print parameters and outcomes — per-material rooms, per-iteration drawers, contradiction detection over 20 failed attempts that identifies the one variable nobody was tracking. The MCP surface is already generic. The memory layer does not need to know.

> *"I'm going to take my chances with the best outcome for earthlings, the environment, and tech, all in one go. And if it doesn't, then I'll still die knowing that I tried."* — Patrick McGuire, 2026-04-08

Cairntir is that bet made small. If the bet is wrong, it's still a useful tool that kills a real annoyance for solo developers. That's already enough. If the bet is right, it's an early load-bearing beam in a much larger structure.

Either way, we build.

---

## Addendum — where the stack stands

Current release is **1.7.1** (2026-08-25). Release history lives in
[CHANGELOG.md](CHANGELOG.md) and
[docs/release/v1.7.1.md](docs/release/v1.7.1.md), not in a second table here.

### How it works, end to end

Four verbs: **write, store, read, close.**

1. **Write.** `cairntir_remember` stores a *drawer*: verbatim content, a
   retrieval layer, immutable provenance (host, model, session, trust),
   optionally structural anchors to code locations, optionally a bound claim
   with a predicted outcome. No summarization at write time — verbatim is the
   floor, not the ceiling.
2. **Store.** One SQLite + sqlite-vec database per machine. Wings per project,
   rooms per topic, four retrieval layers (identity / essential / on-demand /
   deep). Forward-only migrations, backup-first, embedding identity stamped
   and checked. The bank is auditable: `cairntir status`, `cairntir doctor`,
   `cairntir export`.
3. **Read.** Start with `cairntir_handoff(wing)`: the operating protocol, the
   most recent session deltas in full text, open questions, and the memory
   anchored to the files in play — all under a character budget, deterministic
   and prompt-cache friendly. Have a question? `cairntir_recall` answers it
   semantically, with top hits optionally delivered whole. Have a diff instead
   of a question? `cairntir_recall_for_change(files)` needs no question at
   all. Nothing is ever truncated: a drawer comes back complete or is named so
   you can fetch it deliberately.
4. **Close.** Predictions are settled by appending an observation
   (`cairntir_settle`) — the original is never rewritten, because a store that
   edits its own predictions cannot be used to check whether it was right.
   `cairntir_calibration` reports how often the store's claims actually held.
   The Discovery Ledger records emergent patterns with an explicit lifecycle.
   Memory you cannot check is just confidence.

### What it helps with, concretely

- **Reopening a project three weeks later** and walking into a lit room — the
  decisions, the reasons behind them, and what was left blocked, each with a
  drawer id you can cite.
- **Moving work between hosts and agents.** Claude Code, Codex, Cursor, and
  Qwen Code read and write one store with per-write provenance; the handoff is
  the re-brief, so work moves without re-explaining.
- **Budget-constrained continuity.** The handoff and the cost command exist so
  a $20/month model can carry real context — never return a token the model
  cannot use.
- **A decision journal that scores itself.** Claim → predicted → observed →
  delta. Not just what you decided; whether you were right, and by how much
  reality surprised you.
- **Auditability.** Local-first, append-only, exportable, and every drawer
  carries its trust level and provenance. Nobody else's server, nobody else's
  say.

### What just changed, and why

The short version: **enforcement caught up with infrastructure.** The repo's
oldest defect class is infrastructure built correctly and never wired —
commitments that quietly vanish, checks that run where their subject does not
exist, loops that open but nobody closes. v1.4.0 wired the layer that catches
that class instead of discovering it months later:

- **Anchors went from ~11% to over 40% of the live store**, and
  `cairntir_remember` now asks for them as a first-class argument instead of a
  key buried in free-form metadata. Reason: structural recall is the only read
  path that requires no good question from the reader — the mechanism that
  makes the "even a free model can follow the pieces" goal reachable.
  Publishing a contract is not the same as asking for compliance.
- **Settled predictions actually close.** An open-prediction list that never
  shrinks is noise; the handoff was lying by omission.
- **The integrity gate moved to where the data lives** — pre-commit
  (`cairntir doctor --gate`) instead of a CI runner that has no store.
- **The release gate verifies PyPI presence.** v1.1.1 was tagged, released on
  GitHub, and never reached PyPI — unnoticed for three months. That class of
  miss now fails the build.
- **Qwen Code became the fourth host.** Continuity is host-neutral or it is a
  lie; the same store, the same provenance, one more front door.
- **Bounded transcript recovery closes the last pre-write gap.** The
  [recovery plan](plans/2026-08-05-transcript-recovery.md) became v1.8.0 after
  the real killed Qwen request that created the plan was recovered from its
  host transcript. Recovery stays opt-in, untrusted, budgeted, and read-only.

---

## Links

- **Why I built this (blog post):** [docs/blog/amnesia-problem.md](docs/blog/amnesia-problem.md)
- **Getting started (plain English):** [docs/cairntir-for-dummies.md](docs/cairntir-for-dummies.md)
- **Origin story + ethos:** [docs/conception.md](docs/conception.md)
- **Integration guide (embedding Cairntir in your tool):** [docs/integration-guide.md](docs/integration-guide.md)
- **v1.0 deprecation policy:** [docs/deprecation-policy.md](docs/deprecation-policy.md)
- **Roadmap:** [docs/roadmap.md](docs/roadmap.md)
- **Manifesto (the why):** [docs/manifesto.md](docs/manifesto.md)
- **Ethos:** [ETHOS.md](ETHOS.md)
- **Changelog:** [CHANGELOG.md](CHANGELOG.md)

---

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) and [ETHOS.md](ETHOS.md) before opening a PR. The short version:

- **Comprehension before code.** Read the two manifestos and the roadmap first.
- **Small commits, conventional format.** `feat:`, `fix:`, `docs:`, `chore:`, `test:`, `refactor:`.
- **Every exception is typed and surfaced.** No silent `except: pass`. Ever. CI will fail you.
- **Quality has no shortcuts.** `ruff` + `mypy --strict` + `pytest` must all be green.
- **Never import from BrainStormer or MemPalace.** Lineage is reference material, not source. We reimplement.

## License

MIT. See [LICENSE](LICENSE).

---

<sub>**Keywords for people who found this by searching:** Claude Code memory, persistent context for Claude, kill AI amnesia, Claude Code MCP server, cross-session memory, Claude Desktop memory, Cursor MCP memory, Model Context Protocol Python, sqlite-vec memory, Anthropic Claude memory layer, verbatim memory for LLMs, LongMemEval, prediction-bound memory, belief-as-distribution retrieval, content-addressed memory, signed memory format, local-first AI memory, open-source Claude memory, MCP Python server template, how to make Claude remember between sessions.</sub>
