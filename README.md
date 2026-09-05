# Cairntir

Persistent, local-first memory for AI coding agents. Claude Code, Codex,
Cursor, Qwen Code, and other MCP clients share one searchable project history.

[![PyPI](https://img.shields.io/pypi/v/cairntir.svg)](https://pypi.org/project/cairntir/)
[![CI](https://github.com/pnmcguire480/cairntir/actions/workflows/ci.yml/badge.svg)](https://github.com/pnmcguire480/cairntir/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Cairntir stores decisions, facts, unfinished work, and outcomes as verbatim
*drawers* in a SQLite database you own. A budgeted handoff restores complete
drawers across sessions; semantic and file-anchored recall find deeper evidence.

Current published release: [1.9.0](https://github.com/pnmcguire480/cairntir/releases/tag/v1.9.0).
See the [changelog](CHANGELOG.md) and [release evidence](docs/release/v1.9.0.md).

## Install

```bash
pip install --upgrade cairntir
cairntir setup
```

Python 3.11+ is required. Setup initializes the store and configures supported
hosts it detects. Restart your agent afterward.

```bash
cairntir version
cairntir doctor
```

For one host or project, use `cairntir init --host codex`; add `--user` for
user-scope configuration. Cursor's global User Rule requires a manual paste;
setup prints the rule and reports that step.

Follow the [getting-started guide](docs/how-to-use.md) for configuration,
verification, recovery, and troubleshooting.

## Use

Ask your agent to remember a decision in your project's wing, then start the
next task with `cairntir_handoff(wing="myproject")`. A wing is a project, a
room is a topic, and a drawer is one verbatim memory.

```bash
cairntir handoff myproject
cairntir recall "why did we choose Postgres?" --wing myproject
cairntir recall-for-change src/auth.py
cairntir recover --host codex --wing myproject
cairntir cost myproject
```

Handoff returns whole drawers or names those omitted by its character budget.
It includes recent default-layer writes, open predictions, and optional code
anchors. Settlements append observed outcomes without rewriting predictions.

## Host support

| Surface | Support |
|---|---|
| Setup | Claude Code, Cline, Codex CLI, Copilot CLI, Cursor, Gemini CLI, OpenCode, Qwen Code |
| Transcript recovery | Claude Code, Codex, Qwen Code |
| Other MCP clients | Configure the `cairntir-mcp` stdio command manually |
| Cursor transcripts | Unsupported; an explicit receipt explains the limitation |

Transcript recovery is opt-in, separately budgeted, read-only, and untrusted.
It reads bounded host-owned transcript tails; it cannot recover text the host
never persisted. Saving a recovered request requires explicit selection with
`cairntir recover ... --write N`. Memory is not automatically made
authoritative merely because it appeared in a transcript or imported file.

## Data and safety

The authoritative store is local SQLite with `sqlite-vec`. Embeddings run
locally; first use may download the embedding model. Optional update checks
contact PyPI, and explicitly selected LLM adapters can contact their provider.
Cairntir is not a sandbox for the agent using it.

Portable JSONL verifies content hashes and optionally HMAC signatures through
the Python API. The CLI imports as untrusted and does not verify signatures.
Version 1 cannot safely import source-local history references; use a database
backup for linked history. Export/import also enforce the format's external-URL
restriction. See [data handling](docs/concept.md) for backup and trust boundaries.

## Build and integrate

The MCP server exposes **21 tools** over stdio. Stable Python protocols support
custom backends; see the [integration guide](docs/integration-guide.md).

```text
src/cairntir/
├── memory/       # SQLite storage, embeddings, retrieval
├── mcp/          # stdio server and backend
├── reason/       # prediction, experiment, observation
├── recipes/      # composable workflows
└── cli.py        # cairntir setup | init | handoff | recover | recall | replay | hotfix | doctor | export | import
tests/            # unit, integration, contract, property, evaluation
docs/             # guides, architecture, recipes, release evidence
```

[Contributing](CONTRIBUTING.md) documents the locked development environment
and required checks. Tests enforce at least 80% coverage of the measured
surface; transport entrypoints are excluded and tested separately. The
LongMemEval subset is a regression gate, not a general benchmark claim.

## Documentation

- [Getting started](docs/how-to-use.md)
- [Concepts and data handling](docs/concept.md)
- [Multi-host architecture](docs/architecture/multi-host-continuity.md)
- [Recipes](docs/index.md#recipes): CodeGlass, Decision Replay, Signal Reader,
  Bounded Hotfix, and Finalization Mode
- [Roadmap](docs/roadmap.md)
- [Security policy](SECURITY.md) · [release policy](docs/release-cadence.md)
- [Design principles](ETHOS.md) · [lineage](docs/lineage/brainstormer.md)

Cairntir (*CAIRN-teer*) combines a cairn, a waypoint of stacked stones, with a
seeing-stone. Maintained by Patrick McGuire. [MIT licensed](LICENSE).
