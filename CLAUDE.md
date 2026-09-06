# Cairntir — project brief

Host-neutral, local-first memory and reasoning through MCP. Owner:
Patrick McGuire (@pnmcguire480). License: MIT. Python 3.11–3.13.

## Current state

Published version: **1.9.0**. The release record is
[docs/release/v1.9.0.md](docs/release/v1.9.0.md); pending changes belong under
[Unreleased](CHANGELOG.md#unreleased), not an invented release header.

The core has verbatim SQLite drawers, explicit provenance, budgeted handoff,
semantic and anchored recall, prediction settlements, discovery review, three
skills, recipes, and 21 MCP tools. Transcript recovery supports Claude Code,
Codex, and Qwen Code; Cursor returns an unsupported receipt.

The continuity foundation and demo are independently accepted. Request #1262
extends that work through concurrent CLI reads, portable evidence, evaluated
procedures, scoped sharing and release delivery. The current additive candidate
is **1.10.0**, with published version still 1.9.0. Follow the
[delivery plan](plans/continuity-delivery.md), tracked by
[issue #88](https://github.com/pnmcguire480/cairntir/issues/88).

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
site-packages installation, not this checkout (verified 2026-09-05).
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

Request #1262: remove false CLI busy errors with other SQLite clients open, then
finish the remaining continuity milestones and delivery. Work is on
`codex/v2-foundation`; candidate version 1.10.0 follows the additive release policy.
Local acceptance is complete. Patrick explicitly approved public branch push,
PR/CI, merge and release in request #1295. The candidate branch is now pushed;
protected CI and publication remain in progress.

Foundation and demo acceptance is preserved in the
[historical result](plans/v2-foundation-result.md). The subsequent
[concurrency result](plans/context-concurrency-result.md) passes 210 tests with
zero repair rounds: cold filesystem purity and coherent live WAL snapshots.
The CLI uses a bounded private snapshot while other clients remain open.

Portable v2, evaluated procedures and scoped sharing are implemented against
separate independent freezes. Integration review added frozen reproductions for
nested-reference mapping, bulk-cache invalidation and private registry/anchor
access. Those assertions remain unchanged during repairs. The unchanged
100,003-record archive case passed in 70.5 seconds after bulk-write optimization;
complete-candidate independent acceptance is PASS: portable71, procedures161,
sharing193 and bulk8. All seven offline model evaluations pass. Regression
covered986cases with83.37% coverage; three report-encoding failures were fixed
and both affected test files reran18/18 green. [Gate evidence](plans/continuity-gates.md)
retains the failed runs, infrastructure retry and exact scope. Runtime commit3fe5e6f.

[Release acceptance](docs/release/v1.10.0.md) records the remaining PR, native CI,
private migration rehearsal, package and publication gates. The
[support change record](plans/continuity-support-changes.md) distinguishes
historical 1.9.0 frozen inputs from schema 7 and the candidate version.
No new dependencies, production installation changes, live reindex, license
changes or published tags have been made. The production MCP server continues
to use installed 1.9.0; development commands use this checkout's `.venv`.

Delivery checkpoint: runtime `3fe5e6f`, independent evidence `01e12f4`.
Final wheel/sdist rebuilt after documentation changes; the final wheel package
payload exactly matches the installed/tested wheel. Two earlier automatic
approval rejections were resolved by Patrick's explicit approval (#1295).
`codex/v2-foundation` is pushed to the verified public repository. Complete
native CI, merge the exact accepted PR head, publish 1.10.0, verify provenance
and a fresh public-package installation, then settle the release record.

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
