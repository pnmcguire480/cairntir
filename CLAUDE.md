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

The user authorized token-economical 2.0 preparation and a sales demo. The
foundation runtime and isolated demo are **COMPLETE**, with independent acceptance
PASS after one repair round. Resume from [the 2.0 plan](plans/v2-continuity.md) and
[frozen acceptance contract](plans/v2-foundation-acceptance.md), tracked by
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

Resumed implementation on "continue?" (drawer #1244), following the independent
41-case test freeze (#1243). Task-aware handoff, complete-response budgets,
current-evidence selection, read-only cached queries and an isolated HTML demo
are implemented on `codex/v2-foundation`. Published version remains 1.9.0.
Local commits: `e19ba8e` freezes acceptance; `ac89c20` implements the foundation.

Independent round 0 found unrelated semantic evidence and cold CLI SQLite
sidecar writes. Repair 1 fixes both: 41 original acceptance tests, 10 separately
frozen boundary tests and 153 legacy gates PASS. [The independent record](plans/v2-foundation-result.md)
preserves the failures and passing rerun. All frozen inputs remain unchanged.
Source review and cold/busy/orphan-WAL source-purity probes also PASS.

Local gates: 870 regression tests (83.56% coverage), seven offline model evaluations,
Ruff/format, strict types, integrity/commitment/seam/link/advisory gates, docs
build, wheel build and isolated wheel CLI/MCP/doctor smoke all pass. The demo
measures 7,720 history characters versus 2,899 selected (62.45% synthetic payload
reduction); it makes no billed-savings or commercial-host claim. Detailed
[gate evidence](plans/v2-foundation-gates.md) and [demo instructions](docs/context-demo.md)
are saved. The local preview is `.cairntir/context-demo-final/report.html`.

Cold task CLI uses a locked private snapshot and reports busy while another WAL
client is open. Already-open MCP task reads preserve persisted data/access/log
state; SQLite shared-memory bookkeeping is outside that byte-purity claim.
Windows execution is verified; POSIX received source review only.

Next delivery gate: review the local `codex/v2-foundation` commits, then run a
green cross-platform PR before landing. Later 2.0 milestones remain separate;
portable evidence needs its own frozen acceptance. The broader request is
#1237. No dependencies, production installation, version, license, tags or
publication changed.

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
