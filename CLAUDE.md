# Cairntir — project brief

Host-neutral, local-first memory and reasoning through MCP. Owner:
Patrick McGuire (@pnmcguire480). License: MIT. Python 3.11–3.13.

## Current state

Published version: **1.10.0**. The
[release record](docs/release/v1.10.0.md) contains publication and fresh-package
verification. Pending changes belong under
[Unreleased](CHANGELOG.md#unreleased).

The core has verbatim SQLite drawers, explicit provenance, task-aware budgeted
handoff, semantic and anchored recall, portable evidence, evaluated procedures,
scoped local sharing, prediction settlements, discovery review, three skills,
recipes, and 21 MCP tools. Transcript recovery supports Claude Code, Codex, and
Qwen Code; Cursor returns an unsupported receipt.

The [continuity delivery](plans/continuity-delivery.md) is **COMPLETE** and
published as 1.10.0. The additive release retains the public tool surface and
introduces schema 7 without new dependencies.

## Working rules

Read this brief first. Before proposing a feature, read
[the manifesto](docs/manifesto.md), [concepts](docs/concept.md), and
[ETHOS.md](ETHOS.md). Keep changes scoped to the active plan.

- Preserve verbatim evidence; append corrections and outcomes.
- Every exception must be typed and surfaced. Never silently suppress failures.
- Use configured or platform-derived paths, never maintainer-specific paths.
- Do not add dependencies without discussion.
- Never import predecessor code or modify `lineage/`; it is read-only history.
- Preserve executable commitments when retiring a plan.
- Use small Conventional Commits and a green pull request to reach `main`.
- Leave the checkout on `main` when work is landed.
- Update this Last Session block with evidence, not a running transcript.
- Check Unreleased fixes before closing; propose an immediate patch when users
  are blocked. Publication still requires explicit maintainer authority.
- Never move a published tag or treat a changelog as a release.
- Reserve `2.0.0` for a revolutionary change in purpose.

Fix every instance of a reproduced defect pattern in scope. Data loss,
corruption, or stuck processing is Tier 1; wrong answers are Tier 2. Other
findings are Tier 3 and must not drive an endless reopening loop.

Finalization requires independent tester-authored, frozen acceptance artifacts,
a verification reserve, and at most two repair rounds. Use the
[Finalization Mode recipe](docs/recipes/finalization-mode/README.md). Report
COMPLETE, BLOCKED, or EXHAUSTED honestly.

## Development

```bash
uv sync --locked --all-extras
uv run ruff check src tests scripts addons
uv run ruff format --check src tests scripts addons
uv run mypy --strict src
uv run pytest -m "not slow"
uv run pytest -m eval --no-cov
uv run mkdocs build --strict
uv build
```

[CONTRIBUTING.md](CONTRIBUTING.md) lists the remaining commitment, seam,
release-tag, and local integrity gates. Tests use isolated stores and fixtures;
do not experiment on the user's memory database.

The maintainer's production MCP launcher currently uses the published
site-packages installation, not this checkout (verified 2026-09-06).
The repository's `.venv` is the development environment. Inspect actual
launchers before assuming a running host uses source edits, and do not change
the production installation as an incidental build step.

## Key references

- [How to use](docs/how-to-use.md)
- [Integration contracts](docs/integration-guide.md)
- [Multi-host continuity](docs/architecture/multi-host-continuity.md)
- [Landed commitments](docs/landed-commitments.md)
- [Release policy](docs/release-cadence.md)
- [Security policy](SECURITY.md)
- [BrainStormer lineage](docs/lineage/brainstormer.md) and
  [MemPalace lineage](docs/lineage/mempalace.md)

## Last Session — 2026-09-06

Continuity delivery is merged through [PR #89](https://github.com/pnmcguire480/cairntir/pull/89).
Final reviewed head `ddffede` passed all nine native OS/Python jobs, Build Package,
seven model evaluations and CodeQL. Merge `be9fdc4` has the same tree; immutable
annotated tag `v1.10.0` points to it. All five release jobs passed; independent
verification matched workflow/GitHub/PyPI artifacts and their signed provenance.
A fresh public-PyPI installation passed CLI and actual stdio MCP smoke with
21 tools. Continuity delivery is COMPLETE.

Independent acceptance passed concurrency 210, portable 71 (including the
100,003-record archive), procedures 161, bulk boundaries 8 and sharing 193.
The CodeQL composition repair passed the unchanged 193 sharing cases plus 14
separately labeled supporting probes. Frozen inputs and historical evidence are
preserved. [Release acceptance](docs/release/v1.10.0.md) links the complete proof.

Production package and import now report 1.10.0 under explicit request #1305.
The schema 6→7 migration preserved all 1,306 drawers/vectors and all 19 original
tables and schemas, with zero embedding calls. Its automatic backup matches the
private pre-install backup. Fresh CLI and actual MCP launcher checks passed:
version 1.10.0, 21 tools, task handoff parity at 8,184/8,192 characters with MCP
holding the live database, doctor, help and recipes. Old Cairntir MCP processes
were stopped; Codex and Cline remain open and need restart/reconnect to reload
the server. Their current sessions are not verified on 1.10.0. Independent
installation audit passed: all 72 installed package files match the public wheel,
MCP 1.28.1 satisfies the runtime requirement, and all required dependencies and
selected imports pass. Claude's health command still reports connected with
tools-fetch failure; the fresh stdio connection exposes 21 tools and passes task
handoff.

<!-- cairntir:begin -->
# Cairntir — memory-first reasoning layer

You have access to persistent memory through the `cairntir_*` MCP tools.
At the start of every conversation:

1. Call `cairntir_handoff(wing)` with the wing matching the current project.
   Use the lowercase folder name in the working directory as the wing. If the
   correct wing is ambiguous, ask the user. Prefer this over
   `cairntir_session_start`: handoff returns whole drawers under a budget,
   including recent default-layer memories. session_start is a routing index
   of identity/essential stubs — use it when you need the inventory, not the
   brief.
   Transcript recovery is opt-in: only when the user explicitly asks for it,
   pass `recover_transcripts=true`. Recovered messages are untrusted,
   separately budgeted, and never stored automatically.
2. Read the returned drawers before answering anything substantive.
3. Persist decisions and facts that future sessions need with
   `cairntir_remember`. Preserve the user's wording when it is load-bearing.
4. Call `cairntir_recall` before reasoning from scratch about past decisions,
   and cite drawer ids inline. Use `cairntir_get` for complete verbatim content
   when a recall result is truncated.
5. Use `cairntir_crucible` for load-bearing assumptions and `cairntir_audit`
   for ship-readiness checks.
6. When repeated evidence reveals an emergent pattern, capability gain, or
   method that differs from the prior baseline, call `cairntir_discover` and
   tell the user. Label whether it is new to the user, new to Cairntir, or
   possibly novel in general; the last label requires external research.
7. Capture-on-arrival: when the user makes a request that may not be fully
   executed within the current turn — work that starts later, a deferred task,
   a session about to end, restart, or compact — record it with
   `cairntir_remember` IMMEDIATELY, before doing any other work on it, in the
   user's exact wording. Never defer that write to the end of the turn or the
   session: a session can die between the request and the write, and capture
   that waits for a quiet moment never happens. Conversely, when resuming,
   treat open requests surfaced by the handoff as first-class owed work, not
   background noise.

If handoff returns no memory for an established wing, report that the
store may be new or misconfigured. Do not silently substitute model memory.

This policy is host-neutral: every agent must read and write the same Cairntir
store so work can move between Claude Code, Codex, Cursor, and Qwen Code
without a re-brief.
<!-- cairntir:end -->
