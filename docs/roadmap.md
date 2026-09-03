# Roadmap

Cairntir's shipped foundation is the memory-first reasoning layer: verbatim
drawers, wing/room taxonomy, local embeddings, bounded whole-drawer handoff,
prediction and discovery ledgers, structural recall, three skills, recipes,
four first-class host adapters, and a 21-tool MCP server.

The original v0.1 → v1.7 build plans are retained under `plans/` as history.
They are not current status. The live plan map is
[`plans/README.md`](https://github.com/pnmcguire480/cairntir/blob/main/plans/README.md).

## v1.7.1 — New-user front door and truth pass ✅

Published 2026-08-25. Patch release for failures in the first five minutes:

- `cairntir setup` works without the Claude Code CLI and configures installed
  hosts while reporting unavailable ones;
- installed host policy starts with `cairntir_handoff`, so default
  `on_demand` writes return on the documented resume path;
- Cursor user-scope setup prints the paste-ready User Rule;
- first-run documentation, status, plan-map, MCP inventory, and release memory
  agree with the shipped product;
- the full local gate, remote operating-system/Python matrix, package build,
  trusted publication, provenance attestations, and fresh Windows install all
  passed.

No schema migration or reindex is required.

## v1.8.0 — Bounded transcript recovery ✅

Prepared as a release candidate on 2026-08-25. Capture-on-arrival narrows
memory loss but cannot close the interval between a user request and the
agent's first tool call. v1.8.0 implements the opt-in recovery contract in
[`plans/2026-08-05-transcript-recovery.md`](https://github.com/pnmcguire480/cairntir/blob/main/plans/2026-08-05-transcript-recovery.md):

1. bounded, whole-message tail readers for Qwen Code, Claude Code, and Codex;
2. a truthful unsupported receipt for Cursor until Cursor exposes a stable
   local transcript surface;
3. untrusted, provenance-visible recovery output that can abstain and never
   silently becomes authoritative memory;
4. acceptance by killing a session immediately after a request, opening a
   fresh session, and recovering the request verbatim.

The transcript adapters are host-specific. The recovery result and trust
boundary remain host-neutral.

## v1.9.0 — Bounded repair and evidence-bound learning 🚧

Prepared as a release candidate on 2026-09-03. The additive hotfix protocol
records one append-only case from failure through terminal settlement. It
compares cited candidate paths with completed precedents, binds one attempt to
exact authority and preflight observations, rejects retries from unchanged
failed state, requires independent acceptance or exact rollback, and stops as
`COMPLETE`, `BLOCKED`, or `EXHAUSTED`.

Cairntir remains the evidence and ordering layer. The host performs the actual
repair; caller identities and observed state are asserted evidence, not
cryptographic proof. The implementation contract is
[`plans/2026-09-02-bounded-hotfix-ledger.md`](https://github.com/pnmcguire480/cairntir/blob/main/plans/2026-09-02-bounded-hotfix-ledger.md).

The same candidate hardens the Karpathy-derived learning loop. Hypotheses,
experiments, and outcomes must bind to one non-empty wing/room scope; verdict
and surprise remain independent; non-durable gateways cannot advertise
idempotency; and discovery counts only unique predict-observe pairs from the
same room. Automatic promotion remains prohibited: repeated evidence produces
a human-reviewed candidate only. The hardening contract is
[`plans/2026-09-03-reason-loop-hardening.md`](https://github.com/pnmcguire480/cairntir/blob/main/plans/2026-09-03-reason-loop-hardening.md).

This release candidate does not displace the retrieval preflight experiment
below.

## Retrieval preflight — experiment before feature

After transcript recovery, Cairntir will pre-register a holdout evaluation for
a receipt-visible retrieval preflight. The candidate may retrieve only when
relevance, trust, freshness, and authority thresholds pass; it may abstain; it
must show provenance; it must not rewrite the user's prompt or expand stored
content's authority.

It ships only if the holdout shows a measured gain over explicit handoff and
recall without hiding misses or increasing unsafe retrieval. Otherwise the
idea is rejected with the evidence preserved.

## Completion rule

Cairntir is complete for the current arc only when:

- no Tier 1 or Tier 2 finding remains;
- `main` is clean and synchronized with `origin/main`;
- status, roadmap, plan map, MCP surface, changelog, release notes, and memory
  ledger agree;
- published GitHub and PyPI artifacts carry provenance and pass a fresh
  Windows installation;
- every other item is shipped, rejected with evidence, externally blocked, or
  explicitly Tier 3.

## Deliberate boundaries

- The three-skill core remains Crucible, Quality, and Reason. New repeatable
  behavior is a recipe, not a fourth skill.
- Cairntir remains local-first, MIT, host-neutral, and append-only at the
  evidence layer.
- Local Qwen3.8 is a private asynchronous shadow worker/evaluator, never an
  interactive or authority-path dependency.
- Model-weight revision pinning remains externally blocked until the production
  FastEmbed path exposes a usable revision contract.
- `2.0.0` remains reserved for a revolutionary change in what Cairntir is, not
  routine breaking changes.

## Horizon

Cairntir is still pointed at memory that compounds beyond software: AI,
grand-scale 3D printing, and post-scarcity tooling. That horizon guides the
local-first, open, substrate-neutral design; it is not a release commitment.

## Finalization Mode

Every roadmap ends here. Before execution starts, turn its finish line into a
fixed acceptance inventory: required outcomes, explicit non-goals, the evidence
that proves each outcome, and the authority or dependency each outcome needs.

An impartial tester receives the thesis, issue, and test parameters before the
coder starts. The tester authors and freezes the acceptance tests independently.
The coder may read the tests and their failure evidence but may not author,
edit, delete, weaken, or rebaseline them. Test artifacts are hash-bound outside
the coder's write scope; changing them invalidates the run.

`FAIL` and `INCONCLUSIVE` are honest evidence, not agent failure. Deleting a
test, narrowing the selected suite, loosening an assertion, blessing changed
output, or special-casing a fixture to manufacture `PASS` is false-green
tampering. It terminates the run without a completion claim and records the
producer as the source of the invalidation.

Finalization is bounded:

- reserve verification budget before implementation spends the rest;
- allow at most two repair-and-verify rounds unless the roadmap names a lower
  limit; protected or externally billed gates default to one attempt;
- repeat a check only after a relevant state change or to reproduce a declared
  flaky result; an identical check against identical state is not progress;
- stop when the next action cannot close a named acceptance gap.

The roadmap must terminate as `COMPLETE`, `BLOCKED`, or `EXHAUSTED`.
`COMPLETE` requires an independent `PASS` plus fresh evidence for every
acceptance item. `BLOCKED` names the unmet item and the smallest external
decision, authority, or dependency that can unblock it. `EXHAUSTED` preserves
the best evidence, names the budget
or round limit reached, and does not silently reopen the loop. New work becomes
a new roadmap or an explicitly authorized amendment; it is never smuggled into
finalization.

Use the [Finalization Mode recipe](recipes/finalization-mode/README.md) to apply
this contract to a specific roadmap.
