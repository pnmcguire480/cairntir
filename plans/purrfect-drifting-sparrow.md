# Plan: Cairntir — Professional Repo Bootstrap

> **Cairn** (stacked waypoint stones) + **Palantir** (seeing-stone across time).
> A stack of stones that sees across time. Memory-first reasoning for Claude Code.
>
> **Mission:** Kill cross-chat AI amnesia. Step one on a longer road toward
> AI + grand-scale 3D printing + post-scarcity tooling. If we can model it,
> we can make it. If we can remember it, we can build it again. Cairntir is the memory.

---

## Context

BrainStormer was built to solve cross-chat amnesia and doesn't. MemPalace solves memory (96.6% recall on LongMemEval) but has no reasoning layer. Patrick is done bolting — he wants a **clean professional repo** at `c:\Dev\Cairntir\` that distills the best of both into something simpler, opinionated, and open-source from day one.

This is not a weekend hack. This is **serious-time repo**. It needs to stand up to public scrutiny on GitHub, be installable by strangers, and be extensible by contributors. It needs CI, tests, docs, conventional commits, and a clear governance model — because it's the foundation of a larger vision (AI + 3D printing + post-scarcity manufacturing), and foundations carry the weight of everything built on them.

**North star for v1:** A fresh Claude Code chat in `c:\Dev\Cairntir\` on day 30 should feel like walking into a lit room. No re-briefing. No lost decisions. No "what were we doing?"

## Decisions Locked In

| Decision | Value |
|---|---|
| **Name** | `Cairntir` |
| **License** | MIT |
| **Language** | Python 3.11+ |
| **Vector store** | `sqlite-vec` (embedded, zero-dep, one file) |
| **Package manager** | `uv` (fast, modern, locks reproducibly) |
| **Linter/formatter** | `ruff` (one tool, replaces black+isort+flake8) |
| **Type checker** | `mypy` strict mode |
| **Test framework** | `pytest` + `pytest-cov` |
| **Pre-commit** | `pre-commit` hooks for ruff, mypy, tests |
| **CI** | GitHub Actions (test matrix: 3.11, 3.12, 3.13 on Linux/macOS/Windows) |
| **Versioning** | Semantic Versioning (`0.1.0` start) |
| **Commits** | Conventional Commits (`feat:`, `fix:`, `docs:`, etc.) |
| **Changelog** | `keep-a-changelog` format, auto-generated from conventional commits |
| **Docs** | `mkdocs-material` (hosted on GitHub Pages) |
| **Distribution at launch** | `pip` package + Claude Code plugin |

## Core Concept (The Three Ingredients)

1. **Verbatim persistent memory** — sqlite-vec backend, nothing summarized away.
2. **Minimal skill dispatch** — 3 skills total: `crucible` (epistemic stress test), `quality` (audit), `reason` (memory-backed thinking).
3. **One loop, not two commands** — daemon + MCP server auto-capture/restore. No init/wrapup ceremony.

**Taxonomy:** Wings (projects) → Rooms (topics) → Drawers (verbatim entries). Four retrieval layers: identity / essential / on-demand / deep.

## Professional Repo Structure

```
c:\Dev\Cairntir\
│
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                  # Test matrix + lint + type-check on every push/PR
│   │   ├── release.yml             # Tag → build → publish to PyPI + GitHub Release
│   │   ├── docs.yml                # Build mkdocs → deploy to GitHub Pages
│   │   └── codeql.yml              # GitHub security scanning
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.yml
│   │   ├── feature_request.yml
│   │   └── config.yml
│   ├── PULL_REQUEST_TEMPLATE.md
│   ├── CODEOWNERS                  # @pnmcguire480 owns everything v1
│   ├── dependabot.yml              # Auto-PR for dep updates
│   └── FUNDING.yml                 # Optional: GitHub Sponsors
│
├── .vscode/
│   ├── settings.json               # Ruff, mypy, pytest config
│   └── extensions.json             # Recommended extensions
│
├── docs/
│   ├── index.md                    # Landing (mkdocs home)
│   ├── manifesto.md                # WHY Cairntir — amnesia + post-scarcity mythos
│   ├── concept.md                  # The three ingredients
│   ├── quickstart.md               # 5-minute install + first recall
│   ├── taxonomy.md                 # Wings / rooms / drawers / layers
│   ├── mcp-tools.md                # The 6 MCP tools reference
│   ├── skills/
│   │   ├── crucible.md
│   │   ├── quality.md
│   │   └── reason.md
│   ├── architecture.md             # How it's built + why
│   ├── contributing.md             # Points to CONTRIBUTING.md
│   ├── lineage/
│   │   ├── brainstormer.md         # What we kept, what we dropped
│   │   └── mempalace.md            # Same for MemPalace
│   └── roadmap.md                  # Post-v1 vision (3D print bridge, etc.)
│
├── src/
│   └── cairntir/
│       ├── __init__.py             # Version, public API
│       ├── __main__.py             # `python -m cairntir`
│       ├── py.typed                # PEP 561 type marker
│       ├── config.py               # Config loading (XDG-compliant paths)
│       ├── cli.py                  # Typer CLI: 2 commands (`cairntir`, `cairntir recall`)
│       ├── memory/
│       │   ├── __init__.py
│       │   ├── store.py            # sqlite-vec backend
│       │   ├── taxonomy.py         # Wing/Room/Drawer dataclasses
│       │   ├── retrieval.py        # 4-layer loader
│       │   └── embeddings.py       # Embedding provider (start: local sentence-transformers)
│       ├── skills/
│       │   ├── __init__.py
│       │   ├── crucible.md         # Skill prompt (markdown)
│       │   ├── quality.md
│       │   └── reason.md
│       ├── mcp/
│       │   ├── __init__.py
│       │   └── server.py           # 6 MCP tools via stdio
│       ├── daemon/
│       │   ├── __init__.py
│       │   └── capture.py          # Auto-capture loop
│       └── errors.py               # Typed exceptions (NO silent `except: pass`)
│
├── commands/                       # Claude Code slash commands
│   ├── remember.md                 # /cairntir:remember
│   ├── recall.md                   # /cairntir:recall
│   └── reason.md                   # /cairntir:reason
│
├── tests/
│   ├── conftest.py                 # Shared fixtures (tmp db, sample drawers)
│   ├── unit/
│   │   ├── test_store.py
│   │   ├── test_taxonomy.py
│   │   ├── test_retrieval.py
│   │   └── test_embeddings.py
│   ├── integration/
│   │   ├── test_mcp_server.py
│   │   ├── test_cli.py
│   │   └── test_daemon_capture.py
│   └── eval/
│       └── test_longmemeval_subset.py   # 80% R@5 target
│
├── lineage/                        # Read-only historical material
│   ├── brainstormer/               # 10 source files from BrainStormer
│   └── mempalace/                  # Design notes only (no code)
│
├── scripts/
│   ├── bootstrap.py                # One-shot dev env setup
│   └── release.py                  # Cut a release
│
├── .claude-plugin/
│   └── plugin.json                 # Claude Code plugin manifest
│
├── .mcp.json                       # MCP server registration
├── .gitignore                      # Python + VSCode + OS noise
├── .gitattributes                  # Line endings, binary markers
├── .editorconfig                   # Cross-editor consistency
├── .pre-commit-config.yaml         # Ruff, mypy, pytest-fast, trailing whitespace
├── pyproject.toml                  # PEP 621 project metadata, ruff + mypy + pytest config
├── uv.lock                         # Reproducible dep lock
│
├── README.md                       # Mythos + badges + 30-sec quickstart
├── LICENSE                         # MIT
├── CHANGELOG.md                    # keep-a-changelog format
├── CONTRIBUTING.md                 # How to contribute, commit format, PR flow
├── CODE_OF_CONDUCT.md              # Contributor Covenant 2.1
├── SECURITY.md                     # How to report vulns
├── GOVERNANCE.md                   # Who decides what, how decisions are made
├── ETHOS.md                        # 5 principles (imported from BrainStormer)
├── CLAUDE.md                       # AI-agent north star + current state
│
└── plans/
    └── purrfect-drifting-sparrow.md  # This plan, copied in
```

## The 6 MCP Tools

1. `cairntir_remember(wing, room, content, metadata?)` — store a drawer
2. `cairntir_recall(query, wing?, room?, limit=10)` — semantic + metadata search
3. `cairntir_session_start(wing)` — 4-layer context bootstrap (THE amnesia killer)
4. `cairntir_timeline(wing, entity)` — chronological view of a topic
5. `cairntir_audit(wing)` — Quality skill on demand
6. `cairntir_crucible(claim)` — Crucible skill on demand

## Files to Transfer from BrainStormer (Read-Only Lineage)

Copy into `lineage/brainstormer/`, never modified after import:

| Source Path | Purpose |
|---|---|
| `crucible/SKILL.md` | Port → `src/cairntir/skills/crucible.md` |
| `quality/SKILL.md` | Port → `src/cairntir/skills/quality.md` |
| `quality/references/severity-model.md` | P0–P3 language reference |
| `kernel/references/agent-species.md` | Taxonomy vocabulary |
| `ETHOS.md` | Copy → repo root `ETHOS.md` |
| `docs/oracle-round-table-transcript.md` | Historical critique |
| `HARNESS_AUDIT.md` | Gap analysis justifying the rebuild |
| `memory/project_v1_realization.md` | "The Big Realization" |
| `memory/user_tsc_ethos.md` | Sociocybernetic framing |
| `CLAUDE.md` (KNOWN ISSUE section only) | North star problem statement |

## Concepts from MemPalace (No Code Copy, Reference Only)

Write into `lineage/mempalace/notes.md` (our words, their ideas):
- Wing/room/drawer taxonomy
- 4-layer retrieval model
- LongMemEval benchmark (our v1 bar: **80% R@5**)
- MCP tool surface shape (we distill 19 → 6)

## Explicitly Dropped

- BrainStormer's 571 agents (re-curate on demand post-v1)
- License system (dead code, contradicts MIT)
- Obsidian sync (optional render target, not v1)
- 20+ CLI commands (collapse to 2)
- AAAK compression (cargo cult at our scale)
- ChromaDB (version churn)
- init/wrapup ceremony (daemon replaces both)
- **224 silent `except: pass` blocks** — every exception in Cairntir is typed, logged, and surfaced

## Quality Gates (Non-Negotiable)

These are CI-enforced from commit #1:

- ✅ `ruff check` — zero warnings
- ✅ `ruff format --check` — consistent formatting
- ✅ `mypy --strict` — zero type errors
- ✅ `pytest` — all tests pass
- ✅ `pytest --cov=cairntir --cov-fail-under=80` — 80% coverage minimum
- ✅ Conventional commit message validation
- ✅ No `except: pass` — grep check in CI
- ✅ No hardcoded paths — grep check in CI
- ✅ All public functions have docstrings + type hints

## Phased Execution (After Approval)

### Phase 0 — Professional Bootstrap (~1 hour, this session)

1. Create `c:\Dev\Cairntir\` and full folder tree
2. Copy 10 BrainStormer lineage files → `lineage/brainstormer/`
3. Write from scratch (Patrick's voice, HumanFlow ethos):
   - `README.md` — mythos-forward, badges, quickstart
   - `CLAUDE.md` — AI agent north star
   - `docs/manifesto.md` — the post-scarcity mission
   - `docs/concept.md` — three ingredients
   - `docs/quickstart.md` — 5-minute install
   - `docs/architecture.md` — how + why
   - `docs/lineage/brainstormer.md` — what we kept, what we dropped
   - `docs/lineage/mempalace.md` — same
   - `docs/roadmap.md` — post-v1 vision (3D printing bridge)
   - `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `GOVERNANCE.md`
4. Copy `ETHOS.md` and `HARNESS_AUDIT.md`
5. Bootstrap toolchain:
   - `pyproject.toml` (PEP 621, ruff, mypy strict, pytest config)
   - `.pre-commit-config.yaml`
   - `.editorconfig`, `.gitignore`, `.gitattributes`
   - `uv init`, `uv lock`
6. Write `.github/workflows/ci.yml`, `release.yml`, `docs.yml`, `codeql.yml`
7. Issue + PR templates, CODEOWNERS, dependabot
8. `.claude-plugin/plugin.json`, `.mcp.json`
9. `git init`, conventional first commit: `chore: initial repo bootstrap`
10. Create GitHub repo, push, enable Pages, enable CI
11. Copy this plan into `plans/`

**Exit criteria:** `uv sync && pre-commit run --all-files && pytest` all green on empty skeleton. Fresh Claude chat in folder immediately understands project from CLAUDE.md + manifesto.

### Phase 1 — Memory Spike (1–2 sessions)
- `src/cairntir/memory/store.py` — sqlite-vec backend
- `src/cairntir/memory/taxonomy.py` — dataclasses
- `src/cairntir/memory/retrieval.py` — 4-layer loader
- `src/cairntir/memory/embeddings.py` — local sentence-transformers provider
- Unit tests for all of the above
- First LongMemEval subset eval (skeleton OK)

### Phase 2 — MCP Server (1 session)
- `src/cairntir/mcp/server.py` — 6 tools over stdio
- `.mcp.json` wiring
- `commands/*.md` slash commands
- Integration tests

### Phase 3 — Skills Port (1 session)
- Trim and port `crucible.md`, `quality.md`
- Write new `reason.md` (memory-backed loop)

### Phase 4 — Daemon (1 session)
- `src/cairntir/daemon/capture.py` — auto-capture loop
- Retire init/wrapup fully in favor of daemon + `cairntir_session_start`

### Phase 5 — v0.1.0 Release
- Cut first tag
- PyPI publish
- GitHub Release with notes
- Landing page live at `pnmcguire480.github.io/cairntir/`

## Verification (How We'll Know Phase 0 Worked)

End-to-end checklist for Phase 0 sign-off:

- [ ] `cd c:\Dev\Cairntir && git log` → conventional first commit present
- [ ] `uv sync` → clean install, lockfile stable
- [ ] `pre-commit run --all-files` → all hooks pass
- [ ] `ruff check src tests` → zero warnings
- [ ] `mypy --strict src` → zero errors
- [ ] `pytest` → passes (skeletons OK)
- [ ] `python -m cairntir --help` → shows CLI
- [ ] GitHub Actions CI → green on first push
- [ ] GitHub Pages → docs site live
- [ ] **The sniff test:** fresh Claude Code chat in `c:\Dev\Cairntir\` asked *"what is this project and why does it exist?"* answers in terms of memory-first reasoning, the amnesia problem, the post-scarcity mission, and lineage from BrainStormer + MemPalace — **without re-briefing**
- [ ] **The mythos test:** README.md first paragraph makes a stranger understand that Cairntir is step one toward AI + 3D printing + post-scarcity, not just another memory tool

## Open Questions (None Blocking Phase 0)

- GitHub org: personal `pnmcguire480/cairntir` or new org? (Default: personal for v1)
- Embedding model: which sentence-transformers default? (Decide Phase 1)
- Daemon transport: stdio only, or also WebSocket? (Decide Phase 4)
- 3D printing bridge: when does Phase 5+ begin? (Post-v0.1.0, separate plan)
