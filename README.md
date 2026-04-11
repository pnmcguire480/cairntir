<!--
Cairntir — memory-first reasoning layer for Claude Code.
Keywords: Claude Code memory, Claude Code plugin, MCP server, AI memory,
cross-session memory, persistent context, Claude memory, Anthropic MCP,
kill AI amnesia, Claude Code extension, Python MCP server, sqlite-vec
memory, Claude Code MCP, Anthropic Claude memory, Model Context Protocol.
-->

# Cairntir

### **The memory layer Claude Code should have shipped with.**

Cairntir is a local-first, open-source memory system for [Claude Code](https://claude.com/claude-code) and every other [Model Context Protocol](https://modelcontextprotocol.io/) client. It kills cross-chat AI amnesia — the thing where you open a fresh session and your AI has forgotten every decision, every trade-off, every hard-won lesson from yesterday. Nothing is summarized, truncated, or rewritten: what the model wrote down, you can read back, verbatim, six months from now.

> *A stack of stones that sees across time.*
>
> Cairntir = **cairn** (stacked waypoint stones marking a path) + **palantír** (seeing-stone across time and distance). Pronounced *CAIRN-teer*.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![mypy: strict](https://img.shields.io/badge/mypy-strict-blueviolet.svg)](https://mypy.readthedocs.io/)
[![ruff](https://img.shields.io/badge/ruff-clean-green.svg)](https://github.com/astral-sh/ruff)
[![Tests: 162](https://img.shields.io/badge/tests-162_passing-brightgreen.svg)](tests/)
[![MCP compatible](https://img.shields.io/badge/MCP-compatible-purple.svg)](https://modelcontextprotocol.io/)

---

## The one-minute pitch

Every time you open a new Claude Code chat, Claude forgets everything from the last one. You explain the same architectural decision again. You re-litigate yesterday's trade-off. You hallucinate a reason for a choice you can't remember making. It's the single biggest productivity tax on working with LLMs day-to-day, and it's fixed by a file.

**Cairntir is that file.** It's a SQLite database on your hard drive that stores every decision, fact, and hard-won lesson Claude writes down — verbatim, forever, no summarization — and gives it back the next time you open a chat. Every session, in every project, on day 30, walks into a lit room.

It ships as an [MCP server](https://modelcontextprotocol.io/), so it works with **Claude Code, Claude Desktop, Cursor, Windsurf, and every other MCP-compatible client** without modification.

---

## Install

```bash
pip install cairntir           # or: git clone + pip install -e .
cairntir setup                 # interactive wizard — one command, seven steps
```

Then fully quit Claude Code (check the system tray), reopen it in any folder, and ask *"what is cairntir?"* in a fresh chat. If it answers with real knowledge and offers to check memory, you're done.

Not sure about any of those steps? Read **[docs/cairntir-for-dummies.md](docs/cairntir-for-dummies.md)** — zero-prior-knowledge getting-started guide.

---

## Day 30

This is the whole point. It's why it exists.

You open a Claude Code chat in a project you haven't touched in three weeks. Normally this starts with: *"OK, remind me — what are we doing here, which database did we pick, why does `auth.py` have that weird hack in it, and what was blocking the last PR?"*

With Cairntir installed:

1. The chat starts. Claude's system prompt tells it to call `cairntir_session_start` before answering anything.
2. Cairntir returns your **identity drawers** (who you are, how you work, the North Star) and the **essential drawers** for this project (current state, decisions, blockers).
3. Claude reads them. It now knows you picked Postgres, why you picked it, what the hack in `auth.py` is protecting, and what's on next session's list.
4. You type your question. The answer comes back with real context — and drawer id citations, so you can click through to the source.

That's walking into a lit room. That's the North Star. Every feature in this repo is measured against whether it makes that experience feel inevitable.

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
| MCP server | ✅ stdio | ✅ | ❌ |
| One-command install wizard | ✅ `cairntir setup` | ❌ | N/A |

**Cairntir borrows MemPalace's taxonomy — credit where due** — and layers on the reasoning discipline the round-table of eight thinkers committed to in the v0.2–v1.0 arc. See [docs/lineage/mempalace.md](docs/lineage/mempalace.md) for the full "what we kept, what we didn't" breakdown.

---

## The five moving parts

1. **`Drawer`** — one verbatim memory entry. Content, metadata, retrieval layer, optional prediction fields (`claim`, `predicted_outcome`, `observed_outcome`, `delta`, `supersedes_id`), belief mass. Frozen pydantic model.
2. **`DrawerStore`** — SQLite + sqlite-vec backend. Forward-only schema migrations (v1 → v4 so far). Contract-tested via [tests/contract/test_store_contract.py](tests/contract/test_store_contract.py).
3. **MCP server** — six tools over stdio: `cairntir_session_start`, `cairntir_recall`, `cairntir_remember`, `cairntir_timeline`, `cairntir_audit`, `cairntir_crucible`. Runs via `python -m cairntir.mcp.server`.
4. **Three skills** — `crucible` (stress-test assumptions), `quality` (audit a wing), `reason` (memory-backed thinking loop with a mandatory predict step). Bundled as markdown, loaded via `importlib.resources`.
5. **Reason loop** — `ReasonLoop.step()` over four Protocol ports (`HypothesisProposer`, `ExperimentRunner`, `BeliefStore`, `MemoryGateway`). Testable without LLMs, networks, or SQLite. See [docs/integration-guide.md](docs/integration-guide.md).

---

## Who it's for

- **Solo developers** who work with Claude Code daily and lose an hour every Monday re-explaining Friday's decisions.
- **Small teams** that want a per-developer memory layer today and a portable, gossip-able shared memory tomorrow (the v0.5 portable format makes team sync a file-copy, no server).
- **Tool builders** embedding Claude or an MCP client in their own product. Cairntir's v1.0 contract is a stable Protocol surface you can implement a custom backend against — Redis, Postgres, a hosted vector DB, whatever you already run.
- **Researchers** tracking which hypotheses held, which failed, and by how much. The prediction-bound drawer schema (v0.2) is a log-structured experiment journal; the belief-as-distribution scorer (v0.4) is the scoreboard.
- **People building toward post-scarcity manufacturing.** Yes, really — see [the horizon](#the-horizon) at the bottom of this README.

---

## Compatible with

Cairntir is an MCP server. Anything that speaks [Model Context Protocol](https://modelcontextprotocol.io/) can talk to it unchanged:

- **[Claude Code](https://claude.com/claude-code)** (primary target — this is the reason Cairntir exists)
- **[Claude Desktop](https://claude.ai/download)**
- **[Cursor](https://cursor.sh/)**
- **[Windsurf](https://codeium.com/windsurf)**
- **[Zed](https://zed.dev/)** (MCP client support rolling out)
- Any other [MCP-compatible client](https://modelcontextprotocol.io/clients)

Pairs naturally with:
- **Git hooks** — auto-capture commit messages as drawers via the daemon's spool directory.
- **Obsidian / any markdown tool** — export drawers to portable signed envelopes, import them into a vault, edit them by hand, import them back.
- **Linear / GitHub issues** — daemon picks up mentions and cross-references to drawer ids.
- **VS Code** — decision-marker extension (planned, not shipped) writes to the spool as you type.

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

```
cairntir/
├── src/cairntir/
│   ├── __init__.py         # v1.0 public protocol surface — the stable seam
│   ├── contracts.py        # Store protocol every backend must satisfy
│   ├── impl/               # Concrete impls — reserved right to change
│   ├── memory/             # DrawerStore, belief scorer, consolidate, embeddings
│   ├── reason/             # ReasonLoop + four Protocol ports
│   ├── mcp/                # MCP stdio server (six tools)
│   ├── portable.py         # Signed envelope format (v0.5)
│   ├── skills/             # crucible.md, quality.md, reason.md
│   ├── daemon/             # Auto-capture spool watcher
│   └── cli.py              # cairntir setup | init | recall | status | export | import | migrate
├── tests/
│   ├── unit/               # 140+ unit tests
│   ├── contract/           # Store contract suite — every impl must pass
│   ├── property/           # Hypothesis-driven invariants
│   ├── integration/        # MCP backend + daemon
│   └── eval/               # LongMemEval R@5 subset (fail-on-regression CI gate)
└── docs/
    ├── cairntir-for-dummies.md     # Zero-knowledge getting-started guide
    ├── conception.md               # Origin story + ethos + horizon
    ├── concept.md                  # What Cairntir is (the three ingredients)
    ├── manifesto.md                # Why Cairntir exists
    ├── integration-guide.md        # How to embed Cairntir in your own tool
    ├── deprecation-policy.md       # What "stable" means at v1.0
    ├── roadmap.md                  # v0.2 → v1.0 arc + beyond
    └── lineage/                    # What we kept from BrainStormer + MemPalace
```

---

## Conception — the 30-second version

Cairntir is the distillation of two predecessors:

- **[MemPalace](https://github.com/milla-jovovich/mempalace)** — brilliant wing/room/drawer taxonomy, 96.6% LongMemEval R@5, but no reasoning layer. We borrowed the concepts, not the code.
- **BrainStormer** — the author's prior attempt. Great vocabulary (Crucible, Quality, ETHOS), terrible runtime (224 silent `except: pass` blocks, "architecture of a learning system, runtime of a static scaffolder"). Preserved as read-only lineage; reimplemented from scratch.

On 2026-04-08, a **round table of eight thinkers** — Karpathy, LeCun, Sutskever, Hinton, Fuller, Peter Joseph, Alan Watts, Uncle Bob — reviewed the long-road plan and converged on five themes that are now the committed v0.2 → v1.0 arc:

1. **Prediction-bound drawers** — every drawer carries `claim`, `predicted_outcome`, `observed_outcome`, `delta`. The gradient when there are no weights.
2. **Consolidation + forgetting** — verbatim is the floor, not the ceiling. Sleep-cycle pass, replay-weighted demotion, contradiction detection.
3. **Surprise as the load-bearing field** — store what the system did *not* expect. Reconstruction error is the learning signal.
4. **Portable signed format = anti-capture** — format is the product, not the implementation. Content-addressed, HMAC-signed, gossip-importable. A SaaS can be captured. A file on a USB stick cannot.
5. **Cut Team Memory as a feature** — replicable beats shared. Team capability falls out of the portable format for free.

Full story: **[docs/conception.md](docs/conception.md)**.

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

## Links

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
