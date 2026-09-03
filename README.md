# Cairntir

**Persistent memory for AI coding agents — one local memory shared by Claude
Code, OpenAI Codex, Cursor, Qwen Code, and every MCP client.**

Cairntir is an open-source, local-first memory MCP server. It preserves project
decisions, facts, outcomes, and unfinished work across chats and across coding
agents, so a new session can recover the real context instead of asking you to
explain the project again.

> Current release: **[Cairntir 1.9.0](https://github.com/pnmcguire480/cairntir/releases/tag/v1.9.0)** ·
> [PyPI](https://pypi.org/project/cairntir/1.9.0/) ·
> [Changelog](CHANGELOG.md#190--2026-09-03) ·
> [Verified release record](docs/release/v1.9.0.md)

[![PyPI version](https://img.shields.io/pypi/v/cairntir.svg?cacheSeconds=300)](https://pypi.org/project/cairntir/)
[![PyPI downloads](https://img.shields.io/pypi/dm/cairntir.svg)](https://pypi.org/project/cairntir/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/pnmcguire480/cairntir/actions/workflows/ci.yml/badge.svg)](https://github.com/pnmcguire480/cairntir/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![MCP compatible](https://img.shields.io/badge/MCP-compatible-purple.svg)](https://modelcontextprotocol.io/)

## Why Cairntir exists

AI coding assistants start each session cold. They forget architectural
decisions, repeat failed approaches, and lose the reason behind unusual code.
Static instruction files help with rules, but they are not searchable project
memory and they do not record what happened.

Cairntir gives coding agents durable, cross-session memory in a SQLite database
you own. Writes remain verbatim. Every memory carries provenance. Retrieval is
budgeted so the agent receives complete evidence it can use, not a flood of
truncated context.

The result is simple: reopen a project weeks later and walk into a lit room.

## Install

```bash
pip install --upgrade cairntir
cairntir setup
```

Restart the configured agents, then verify the installation:

```bash
cairntir version
cairntir doctor
```

`cairntir setup` creates the local store, detects installed hosts, and connects
every supported agent it can find. Missing CLIs are skipped rather than treated
as failures. For one host or one project, use:

```bash
cairntir init --host codex
cairntir init --host all --user
```

New to MCP or terminal tools? Start with the
[plain-English setup guide](docs/cairntir-for-dummies.md).

## What changed in 1.9.0

Cairntir 1.9.0 makes repair and learning evidence fail closed:

- **Bounded hotfix ledgers** preserve cited recommendations, exact authority,
  one-attempt execution receipts, independent verification, rollback, and a
  terminal result without giving Cairntir execution power.
- **Reason-loop boundary validation** rejects blank, cross-scope, mismatched,
  incomplete, or falsely idempotent adapter output before it can become
  evidence.
- **Verdict and surprise stay independent.** Explicit `delta` survives through
  `Outcome`, replay, recipes, adapters, and all shipped CLI reasoning paths.
- **Discovery uses exact evidence pairs.** Only uniquely bound predictions and
  observations in the same room count toward a human-reviewed candidate.

Read the complete [1.9.0 changelog](CHANGELOG.md#190--2026-09-03) and
[release acceptance record](docs/release/v1.9.0.md).

## How persistent memory works

1. **Write.** `cairntir_remember` stores a verbatim drawer with its project,
   topic, retrieval layer, source host, model, trust level, and optional code
   anchors.
2. **Store.** One local SQLite + `sqlite-vec` database remains authoritative.
   The schema migrates forward with backup-first safety.
3. **Read.** `cairntir_handoff(wing)` returns whole relevant drawers under a
   hard character budget. Semantic and structural recall handle deeper search.
4. **Close.** Prediction-bound drawers record claim → expected outcome → actual
   outcome → surprise. Settlements append evidence instead of rewriting history.

Nothing is silently summarized at write time. A drawer is returned whole or
named for deliberate retrieval; it is never cut in half to fill a context
window.

## Cross-session and cross-agent memory

| Integration | Support |
|---|---|
| Automatic host setup | Claude Code, Cline, Codex CLI, Copilot CLI, Cursor, Gemini CLI, OpenCode, Qwen Code |
| Bounded transcript recovery | Claude Code, Codex, Qwen Code |
| Generic MCP connection | Claude Desktop, Windsurf, Zed, and other stdio MCP clients |
| Shared storage | Every configured host reads and writes the same local store with per-write provenance |

Cursor is a first-class configured host. Transcript recovery remains
unsupported there because Cursor does not publish a stable transcript schema;
Cairntir reports that limit instead of guessing at private data.

## Core capabilities

| Capability | What it does |
|---|---|
| Budgeted handoff | Restores recent decisions, open work, and anchored evidence without truncation |
| Semantic recall | Searches the memory store by meaning with `sqlite-vec` |
| Structural recall | Finds memories attached to the files a code change touches |
| Cross-wing recall | Searches every project while preserving project provenance |
| Prediction tracking | Scores whether recorded claims and expected outcomes held |
| Discovery Ledger | Exposes evidence-backed patterns through a reviewed lifecycle |
| Bounded hotfix ledger | Orders evidence, exact authority, one-attempt execution receipts, independent verification, and terminal settlement |
| Portable memory | Exports and imports content-addressed, signed JSONL envelopes |
| Transcript recovery | Recovers unfinished requests without automatic storage |
| Local-first operation | Keeps the authoritative memory database on your machine |

## Common commands

```bash
cairntir handoff myproject
cairntir recall "why did we choose Postgres?" --wing myproject
cairntir recall-for-change src/auth.py
cairntir recover --host codex --wing myproject
cairntir cost myproject
cairntir calibration --wing myproject
cairntir hotfix status --wing myproject --case-id hf-abc123
cairntir export memories.jsonl
```

For recovered transcript text, storage requires explicit consent:

```bash
cairntir recover --host codex --wing myproject --write 1
```

## Context-budget evidence

On one real store measured 2026-08-02, the deterministic handoff used 44–52%
fewer tokens than the older session-start path while returning complete drawers
instead of truncated stubs:

| Project | `session_start` | `handoff` | Difference |
|---|---:|---:|---:|
| `cairntir` | 7,737 tokens | 4,261 tokens | −44% |
| `detroit-clone` | 8,201 tokens | 3,880 tokens | −52% |

These are dated measurements of two stores, not a universal benchmark. Run
`cairntir cost yourproject` to measure your own corpus. CI separately enforces a
LongMemEval R@5 regression floor; Cairntir does not reuse another project's
benchmark as its own.

## MCP server and library surface

The MCP server exposes **21 tools** over stdio for exact memory, handoff,
semantic and structural recall, audit, reasoning, calibration, discovery, and
bounded hotfix records. Tool builders can use the stable Python Protocol surface
with a custom backend; see the [integration guide](docs/integration-guide.md).

```text
cairntir/
├── src/cairntir/
│   ├── contracts.py      # stable Store protocol
│   ├── memory/           # SQLite, sqlite-vec, belief scoring, consolidation
│   ├── mcp/              # host-neutral stdio server
│   ├── hotfix.py         # bounded append-only repair ledger
│   ├── reason/           # testable reasoning loop and ports
│   └── cli.py            # cairntir setup | init | handoff | recover | recall | replay | hotfix | doctor | export | import
├── tests/                # unit, contract, property, integration, evaluation
├── docs/                 # guides, architecture, recipes, release evidence
└── plans/                # live plans and dated decision history
```

## Recipes

Recipes combine memory and the three core reasoning skills without expanding
the primitive skill set:

- [Finalization Mode](docs/recipes/finalization-mode/) — finish a roadmap
  against frozen acceptance criteria and bounded repair rounds.
- [Bounded Hotfix](docs/recipes/bounded-hotfix/) — compare cited repair paths,
  bind one attempt to exact authority, independently verify it, and stop.
- [CodeGlass](docs/recipes/codeglass/) — turn unfamiliar code into durable,
  evidence-cited understanding.
- [Decision Replay](docs/recipes/decision-replay/) — revisit a past prediction
  and record what reality taught you.
- [Signal Reader](docs/recipes/signal-reader/) — convert AI news analysis into
  falsifiable, longitudinal evidence.

## Cairntir compared with static memory files

| | Cairntir | `CLAUDE.md` / rules files |
|---|---|---|
| Persistent across sessions | Yes | Yes |
| Shared across coding agents | Yes | Only when every host reads the same file |
| Semantic and structural search | Yes | No |
| Verbatim provenance | Yes | Manual |
| Outcome and calibration tracking | Yes | No |
| Automatic context budgeting | Yes | No |
| Local and inspectable | Yes | Yes |

Rules files remain useful for instructions. Cairntir complements them with
searchable evidence and history; it does not replace project policy.

## Documentation

- [Changelog](CHANGELOG.md)
- [Cairntir 1.9.0 release acceptance](docs/release/v1.9.0.md)
- [Cairntir 1.8.0 published evidence](docs/release/v1.8.0.md)
- [How to use Cairntir](docs/how-to-use.md)
- [Plain-English setup](docs/cairntir-for-dummies.md)
- [Integration guide](docs/integration-guide.md)
- [Architecture and concepts](docs/concept.md)
- [Roadmap](docs/roadmap.md)
- [Origin, lineage, and long-term vision](docs/conception.md)
- [Release and deprecation policy](docs/deprecation-policy.md)

## Name and principles

**Cairntir** combines *cairn*, a stack of stones marking a path, with
*palantír*, a seeing-stone across time and distance. Pronounced *CAIRN-teer*.

The project is MIT-licensed, local-first, append-only where history matters,
and built without telemetry. Read [ETHOS.md](ETHOS.md) and
[CONTRIBUTING.md](CONTRIBUTING.md) before contributing.

> *A stack of stones that sees across time.*
