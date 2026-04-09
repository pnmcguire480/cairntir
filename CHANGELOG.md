# Changelog

All notable changes to Cairntir will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] — 2026-04-08

Library extraction. Cairntir graduates from "a tool" to "the thing other
tools store their memory in". The v1.0 contract is a curated protocol
surface re-exported from the package root; concrete implementations
move to `cairntir.impl.*` and reserve the right to change between
minor releases. Six versioned phases (v0.2 → v0.6) landed in the
pre-v1.0 arc — prediction-bound drawers, consolidation / forgetting /
contradiction, surprise + belief-as-distribution, portable signed
format, and the clean-ports Reason loop — and v1.0 locks the seam.

### Added — Public protocol surface (`cairntir.__init__`)
- `Store` protocol: `add`, `get`, `list_by`, `search`, `update_layer`,
  `reinforce`, `weaken`, `stale_ids`, `close`
- `EmbeddingProvider` protocol (re-export from the memory package)
- Reason-loop ports: `HypothesisProposer`, `ExperimentRunner`,
  `BeliefStore`, `MemoryGateway`
- Frozen value types: `Drawer`, `Layer`, `Hypothesis`, `Experiment`,
  `Outcome`, `BeliefUpdate`
- Typed exceptions: the full set from `cairntir.errors`, plus the new
  `CairntirDeprecationWarning`

### Added — `cairntir.impl` namespace
- `DrawerStore`, `HashEmbeddingProvider`, `SentenceTransformerProvider`,
  `Retriever`, `RetrievalResult`, `ReasonLoop`, `SCHEMA_VERSION`
- All concrete — reserved right to change. The public contract is the
  protocol surface above.

### Added — v1.0 contract test infrastructure
- `tests/contract/test_store_contract.py` — every `Store` impl must
  pass this suite; runs against `DrawerStore` via a parametrized
  factory fixture
- `tests/property/test_taxonomy_properties.py` — Hypothesis-driven
  property tests for taxonomy invariants (valid identifiers round
  trip, whitespace content rejected, belief mass preserved, layer
  preserved)
- `tests/unit/test_public_api.py` — snapshot of `dir(cairntir)` that
  fails on drift; separate assertions for `__all__` and `__version__`
- v1 → v2 → v3 schema migration fixtures exercised against
  `DrawerStore` (hand-built pre-v4 databases reopen and upgrade
  losslessly)

### Added — Deprecation policy
- `CairntirDeprecationWarning` subclass of `DeprecationWarning`. Public
  surfaces must emit this warning for at least two minor releases
  before removal. No silent removals.

### Changed
- `cairntir.__init__` is now a *curated* surface. Importing private
  concrete classes from `cairntir.memory.*` or `cairntir.reason.loop`
  still works for now, but the stable seam is the protocol re-exports.
- `hypothesis` added to dev dependencies.
- Version bumped `0.1.0 → 1.0.0`.

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
