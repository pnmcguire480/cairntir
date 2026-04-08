# Changelog

All notable changes to Cairntir will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] — 2026-04-08

The memory-first reasoning layer ships. Five phases from bootstrap to the
one-loop daemon, tying together verbatim memory, three skills, and a
six-tool MCP surface that Claude Code can talk to directly.

### Added — Phase 0 · Bootstrap
- Professional scaffolding: `pyproject.toml`, `ruff`, `mypy --strict`,
  `pytest`, `pre-commit`
- GitHub Actions CI: lint + test matrix
- Core documentation, community files, lineage material from
  BrainStormer preserved read-only
- Ban on silent `except: pass` enforced by CI

### Added — Phase 1 · Memory Spike
- `cairntir.memory.taxonomy` — frozen pydantic `Drawer` + `Layer` enum
  with strict identifier validation
- `cairntir.memory.embeddings` — `EmbeddingProvider` protocol,
  deterministic `HashEmbeddingProvider` for tests, lazy-loading
  `SentenceTransformerProvider` for production
- `cairntir.memory.store` — sqlite-vec backed `DrawerStore` with a
  `vec0` virtual table and typed error surface
- `cairntir.memory.retrieval` — 4-layer `Retriever`
  (identity / essential / on_demand / deep)
- LongMemEval R@5 eval skeleton

### Added — Phase 2 · MCP Server
- `cairntir.config` — `CAIRNTIR_HOME` + platformdirs-based path resolution
- `cairntir.mcp.backend.CairntirBackend` — transport-free implementation
  of `remember`, `recall`, `session_start`, `timeline`, `audit`, `crucible`
- `cairntir.mcp.server` — stdio adapter, runnable as
  `python -m cairntir.mcp.server`

### Added — Phase 3 · Skills
- `src/cairntir/skills/crucible.md` — 4-phase epistemic forge distilled
  from BrainStormer lineage
- `src/cairntir/skills/quality.md` — two-stage ship gate with
  Evidence-Before-Claims and the Cairntir-native T6 Memory Discipline tier
- `src/cairntir/skills/reason.md` — new memory-backed thinking loop
- `cairntir.skills.load_skill` — bundled markdown via
  `importlib.resources`, wired into the Crucible and Quality tools

### Added — Phase 4 · Daemon
- `cairntir.daemon.spool` — atomic `write_capture`, arrival-ordered
  `pending_files`, strict `parse_capture`, quarantine-on-failure
- `cairntir.daemon.capture.CaptureDaemon` — `tick()` for one-shot
  processing, `run()` for the asyncio poll loop, graceful `request_stop`
- `python -m cairntir.daemon` — production entry point
- Retires the init/wrapup ceremony: spool → daemon → store → session_start

### Quality
- 54 tests, 85% coverage
- `ruff check`, `ruff format`, `mypy --strict` clean
- Every exception typed; no silent `except: pass`

[Unreleased]: https://github.com/pnmcguire480/cairntir/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/pnmcguire480/cairntir/releases/tag/v0.1.0
