# Changelog

All notable changes to Cairntir will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.1.2] — 2026-05-03

**Architectural follow-up to 1.1.1.** 1.1.1 silenced the stdout
corruption that was wedging `cairntir_session_start`; 1.1.2 makes
sure the call can never trigger the slow path in the first place.

### Fixed — `cairntir_session_start` is now pure SQL

Removed the `query` parameter from the `cairntir_session_start` MCP
tool spec. The retriever's optional `query` argument was the only
path through `session_start` that triggered the embedder, and on
cold MCP servers the sentence-transformers cold load took up to
~2.5 minutes — long enough that Claude Code's MCP-call timeout
fired well before the response arrived, even when the server
ultimately produced a valid 3,625-char answer (observed
2026-05-03).

With `query` removed from the tool spec, Claude Code stops passing
it. `session_start` becomes two `list_by` SQL queries plus a string
format — sub-second on every cold MCP server boot, no embedder
cold-load on the critical path. Semantic search has its own home:
`cairntir_recall`.

The backend method `CairntirBackend.session_start(wing, query)`
still accepts `query` for direct library callers; only the
MCP-advertised tool surface drops it.

Diagnostic plumbing added during the chase stays in place:
- `cairntir_home() / mcp.log` — per-process timestamped log of
  server startup, every tool dispatch, every embedder load step
- `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` are set as
  defaults at MCP startup so the embedder never tries to phone
  home

### Process

- New regression test pins the `cairntir_session_start` tool spec
  to never advertise a `query` parameter
- 240 → 241 tests passing, ruff/format/mypy --strict/silent-except
  all clean
- Bumped 1.1.1 → 1.1.2 in pyproject.toml, __init__.py, plugin.json

## [1.1.1] — 2026-04-25

**Critical hotfix.** `cairntir_session_start` was wedging Claude Code
sessions for 20+ minutes (sometimes indefinitely) on real user
machines. Two independent bugs were stacked on top of each other; both
are fixed in this release.

### Fixed — MCP stdio stream corruption

`sentence-transformers`, `transformers`, and `torch` write progress
bars (`Loading weights: ...`) and architecture-mismatch tables
(`BertModel LOAD REPORT`) directly to **stdout** during model
construction. When `SentenceTransformerProvider` runs inside the MCP
stdio server, those bytes interleave with the JSON-RPC responses
Claude Code is reading. The JSON parse breaks, Claude Code waits
forever for a valid response that never comes, and the user sees
"Pontificating..." for hours.

`SentenceTransformerProvider._load()` and `.embed()` now wrap their
work in a `_silence_io()` context manager that:

- Dups fds 1 and 2 to `/dev/null` at the OS level (so even direct C
  extension writes vanish).
- Swaps `sys.stdout` and `sys.stderr` for `io.StringIO()` instances
  (so Python-level writes also vanish).
- Restores both via `try/finally` so a load failure can't silence
  the rest of the process.

### Fixed — Warmup race

The `warm_embedder_in_background` daemon thread (added in 91a8350)
loaded the sentence-transformers model in parallel with the asyncio
stdio loop. When a `cairntir_session_start` call arrived with a
query, the main thread also tried to load the model — both went
through `SentenceTransformer.__init__` simultaneously, and on real
user boxes this combination of (race + stdout corruption) is what
produced the 20-minute hangs.

The warmup is now **opt-in** via `CAIRNTIR_ENABLE_EMBEDDER_WARMUP=1`.
Default behavior is the pre-91a8350 lazy first-call load on the main
thread. The ~25s first-write latency is the price; reliability comes
first. Re-enable the warmup once a process-wide model-load mutex is
in place to serialize the warmup and synchronous paths.

### Process

- `_WARMUP_DISABLE_ENV_VAR` → `_WARMUP_ENABLE_ENV_VAR`. Same
  vocabulary (`1`/`true`/`yes`/`on`), inverted semantics.
- `tests/unit/test_mcp_warmup.py` rewritten for the opt-in shape.
- 240 tests passing, ruff/mypy/silent-except all clean.

### Diagnostics that surfaced this

Three orphaned Python processes (250 MB each, sentence-transformers
fully loaded) were sitting in `tasklist` after multiple Claude Code
sessions had spawned and wedged their MCP servers. The user's
"Pontificating..." Claude Code session showed `cairntir [cairntir_session_start]`
at the top of the active tool stack, blocked indefinitely. Reproducing
the cold load against the real `SentenceTransformerProvider` showed
`Loading weights: 100%|##########|` and a `BertModel LOAD REPORT`
table on stdout — the smoking gun.

## [1.1.0] — 2026-04-18

v1.1 Synergy Stack — the three-upgrade bundle. Pulls forward v1.2
(Production Reason Loop), v1.3-partial (Cross-Wing Recall + Temporal),
and v1.5 (Recipe Runtime) from the Road to 2.0, and ships them
together because the value compounds when they land in the same
release. Plus the cold-start handshake fix and the embedder warmup
from the unreleased hotfix branch; 1.1.0 is the first PyPI release
that carries both halves of the install hardening *and* the synergy
stack.

### Added — Cross-Wing Recall + Temporal Walk

- **`cairntir_cross_recall` MCP tool.** Where `cairntir_recall` scopes
  to one wing, `cairntir_cross_recall` searches every wing the user
  has ever written to, annotating each hit with its wing-of-origin.
  A question asked in one project now finds its answer in another.
- **`cairntir cross-recall "<query>"` CLI.** Same reach at the
  terminal.
- **`cairntir.memory.temporal` module.** Two pure query functions
  over the existing supersedes chain: `walk_supersedes(store, id)`
  returns the full chain root→leaf, and `as_of(store, id, when)`
  returns the chain member that was the live leaf at `when`. No
  schema change — every relation was already present in v0.2.

### Added — Production Reason Loop (stdlib-only, zero network)

Cairntir does not call LLMs. The Reason loop is a *discipline* for
committing falsifiable predictions; the hypothesis comes from the
caller — a human at a terminal, or the Claude Code session already
driving the CLI. Cairntir stays the memory layer, not a second
inference provider that would double-bill the user.

- **`cairntir.production` package.** Four stdlib-only adapters:
  - `StoreBackedMemory(store)` — `MemoryGateway` over any `Store`.
  - `StoreBackedBeliefs(store)` — `BeliefStore` over any `Store`.
  - `NullRunner` — `ExperimentRunner` that records a caller-supplied
    verdict.
  - `ManualProposer` — `HypothesisProposer` that returns a
    caller-supplied hypothesis. Accepts either a prebuilt
    `Hypothesis` or raw `claim` + `predicted_outcome` strings.
- **`cairntir reason "<question>" --wing X` CLI.** Runs one full
  Reason loop step. `--claim`, `--predicted`, `--observed`, and
  `--success`/`--fail` can be supplied as flags for non-interactive
  use, or collected via `typer.prompt` one by one. Writes the
  prediction + observation drawer pair, adjusts belief mass. Zero
  network calls, zero paid tokens.
- **Future: local-AI proposer.** A Gemma 4 (via llama.cpp or
  similar) proposer can drop in by implementing
  `HypothesisProposer` — no API costs, still local-first. Planned
  as a separate phase once the synergy stack has been exercised in
  the field.

### Added — Recipe Runtime

- **`cairntir.recipes` package.** Declarative protocols that chain
  the three core skills into repeatable disciplines. The three
  skills stay locked — recipes are the escape valve.
  - `RecipeContract` dataclass loaded from `recipe.toml`: `name`,
    `description`, `version`, `output_wing`, ordered `skills` list
    (`crucible` / `quality` / `reason`), typed `input` table.
  - `load_recipe(path)` validates the TOML and rejects malformed
    recipes with a typed `RecipeError`.
  - `discover_recipes()` walks `docs/recipes/**/recipe.toml` in the
    project and `~/.claude/recipes/**/recipe.toml` for the user;
    project recipes shadow user recipes when names collide.
  - `RecipeRunner(memory, beliefs, proposer, runner)` executes a
    contract end-to-end. Writes a seed drawer capturing the
    invocation + inputs, then one drawer per skill step. When the
    chain includes `reason`, runs a full `ReasonLoop.step` with
    the caller-supplied `ManualProposer` — the prediction-bound
    drawer pair is the recipe's load-bearing output.
- **`docs/recipes/signal-reader/recipe.toml`.** Ships the Signal
  Reader protocol as an executable recipe. Input slots: `summary`
  (required), `url` (optional), `horizon_months` (optional).
- **`cairntir recipe-list` + `cairntir recipe-run`.** Discover and
  execute recipes from the terminal. Recipes that chain `reason`
  collect claim / predicted / observed / verdict via `--claim` /
  `--predicted` / `--observed` / `--success`/`--fail` flags or
  interactive prompts — never via a network call.

### Changed

- `src/cairntir/__init__.py` and `pyproject.toml` bumped to
  `1.1.0`. `.claude-plugin/plugin.json` matches.
- `src/cairntir/mcp/server.py` and `src/cairntir/cli.py` gain the
  new tools and commands above. The stable v1.0 public API
  (`cairntir.__init__` re-exports) is unchanged — every new surface
  is under `cairntir.impl` / `cairntir.production` / `cairntir.recipes`
  or the CLI/MCP adapters.

### Fixed (carried over from the unreleased hotfix branch)

- **Cold-start MCP handshake timeout** — `DrawerStore.__init__` no
  longer eagerly touches `embedder.dimension`; the model loads only
  when the `vec_drawers` virtual table must be created (first-time
  DBs). Brought startup from ~28 s to ~1 s on cold cache, so Claude
  Code's ~10 s `initialize` timeout stops firing.
- **Embedder background warmup.** A daemon thread kicks off a
  throwaway `embed()` call after the handshake returns, so the
  first `cairntir_remember` / `cairntir_recall` is also instant
  instead of blocking ~25 s on the model load.
- **Pydantic `ValidationError` in MCP tool calls.** The stdio
  server's `_call` adapter now catches `ValidationError` alongside
  `CairntirError` and surfaces it as a one-line `[cairntir error]
  <field>: <message>` so an invalid wing/room/content argument
  doesn't crash the tool response.

## [1.0.1] — 2026-04-17

Install hardening. The 1.0.0 install model pinned the MCP registration
to `sys.executable`, which silently broke whenever a venv moved, was
recreated, or got upgraded. This release switches the registration to
a stable console-script shim, adds silent self-heal on every CLI run,
and surfaces a one-line update banner when a newer Cairntir is on
PyPI. Once installed, Cairntir stays on until the user uninstalls — no
re-running setup, no "tools not loaded" surprises.

### Added — Stable install seam
- **`cairntir-mcp` console script.** New entry point declared in
  `[project.scripts]`. Pip's launcher hard-pins the right interpreter
  on install, so the registered MCP command is one stable name that
  survives venv changes, shell restarts, cwd shifts, and Python
  upgrades. `pip uninstall cairntir` removes the launcher; that
  vanish is the user-visible signal that Cairntir is gone.
- **`cairntir.register` module.** Silent self-heal that runs on every
  CLI invocation: checks `claude mcp list` for the cairntir entry,
  re-registers via `claude mcp add -s user cairntir -- cairntir-mcp`
  if missing, writes a checkpoint to `cairntir_home() / .registered`
  for fast-path no-ops on subsequent runs. Opt-out via the
  `CAIRNTIR_DISABLE_AUTOREGISTER` environment variable.
- **`cairntir.update` module.** Non-blocking update notifier. Hits
  `https://pypi.org/pypi/cairntir/json` once per 24 hours in a daemon
  thread (2s timeout, fail-silent on network errors). When a newer
  release exists, the next CLI command and the next MCP tool response
  prepend a one-line banner: `[cairntir update available: X → Y —
  run \`pip install -U cairntir\`]`. Banner appears at most once per
  process. Opt-out via `CAIRNTIR_DISABLE_UPDATE_CHECK`.
- 22 new tests covering the self-heal helper and the update notifier.

### Changed
- `cairntir.cli._mcp_spec` now returns `{"command": "cairntir-mcp",
  "args": []}` — no more `sys.executable` pinning. Both `cairntir
  init` (project scope) and `cairntir init --user` (user scope) use
  the new shim.
- `.claude-plugin/plugin.json` updated to register the same shim.
- The CLI root callback now triggers the silent self-heal and the
  background PyPI check on every invocation. Both side effects are
  fail-silent and opt-out by env var.
- The MCP server kicks off the PyPI check on startup and prepends
  the update banner to the first tool response per process.

### Fixed
- `cairntir_audit` and `cairntir_crucible` MCP tool descriptions no
  longer claim "(Phase-2 stub)" — both tools fully shipped in 1.0.0
  and the label was a documentation bug.
- Tests: `tests/conftest.py` autouse fixture sets both opt-out env
  vars during test runs so the self-heal and PyPI check never touch
  the developer's real home directory or the network.

### Added — Pre-1.0.1 (the prior "Unreleased" block, now historical)
- **PyPI release (2026-04-15):** `pip install cairntir` now works
  worldwide at https://pypi.org/project/cairntir/1.0.0/. First public
  install path; the git-clone + editable-install route is now the
  contributor path, not the user path.
- README badges for PyPI version and monthly downloads.
- `docs/cairntir-for-dummies.md` Step 1 rewritten around `pip install
  cairntir`; uv / pipx alternatives called out; editable-install path
  moved to a "for contributors" aside.
- `docs/publish-checklist.md` Phase 4 marked complete with the two
  gotchas we hit (PowerShell hiding token prompts, never paste a
  token in a shared context).

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

[Unreleased]: https://github.com/pnmcguire480/cairntir/compare/v1.0.1...HEAD
[1.0.1]: https://github.com/pnmcguire480/cairntir/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/pnmcguire480/cairntir/compare/v0.1.0...v1.0.0
[0.1.0]: https://github.com/pnmcguire480/cairntir/releases/tag/v0.1.0
