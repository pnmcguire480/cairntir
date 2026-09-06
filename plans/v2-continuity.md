# 2.0 preparation: economical, portable working context

Current continuation: [delivery plan](continuity-delivery.md) implemented live CLI
concurrency, portable evidence, evaluated procedures and scoped sharing. Reviewed
source was published as 1.10.0 with verified artifacts, attestations and fresh
public-package smoke; delivery is **COMPLETE**. The foundation evidence below
remains the historical accepted base and has not been rewritten.

Status: foundation implementation and demo are **COMPLETE** locally on
`codex/v2-foundation`; independent acceptance is PASS after one repair round.
The user accepted the researched improvement directions and authorized
implementation on 2026-09-05 (request drawer #1237), then resumed the test-freeze
step in drawer #1241. This is not release publication authority.

## Foundation completion — 2026-09-06

User resumed implementation with "continue?" (drawer #1244). Task-aware handoff,
whole-evidence selection, complete-response budgeting, safe abstention and the
isolated HTML demo are implemented. The 21-tool MCP surface and no-task handoff
remain compatible.

[Independent acceptance](v2-foundation-result.md): 41 original cases, 10 frozen
boundary cases and all 153 legacy gates PASS. Original and supplementary hashes
remain unchanged. Round 0 failures are preserved; one repair round corrected
semantic noise and cold SQLite sidecar creation. A separate fixed holdout passed
18/18 at the generic cosine threshold. Source review and independent cold/busy/
orphan-WAL probes PASS.

[Local gate evidence](v2-foundation-gates.md): 870 regression tests with 83.56%
coverage, seven offline model evaluations, lint/format/types, all integrity,
commitment, seam, link, dependency and release-tag checks, strict docs build,
package build and built-wheel CLI/stdio-MCP/doctor smoke PASS. Windows is
executed; POSIX is source-reviewed pending native CI before landing.

The repeatable synthetic demo reduces measured payload from 7,720 to 2,899
characters (62.45%). Final HTML matches the inspected preview byte for byte.
Run it using [these instructions](../docs/context-demo.md). No commercial-host,
billed-token or general task-success claim follows from this measurement.

Cold task CLI reads a locked private snapshot; active or idle WAL clients can
cause an explicit busy error. Existing MCP task reads preserve persisted
evidence/access/log state; SQLite shared-memory bookkeeping is scoped separately.

Disposition: **COMPLETE — foundation implementation and local acceptance**.
Branch delivery through a green PR is the next gate. Portable evidence,
evaluated procedures and shared control retain separate plans and freezes.
No dependency, production installation, database migration, license, version,
tag or publication changes were made. This is not 2.0 release completion.

## Problem

The original purpose is affordable continuity: avoid repeatedly paying to
reconstruct context when changing chats, hosts, or models. Current handoff
prioritizes historical layers without knowing the task, and its content budget
does not include rendered overhead. Durable memory must remain available
without loading the entire archive into each context window.

## Goal

Make a reproducible, isolated demonstration of economical cross-session
continuity, then earn 2.0 through evaluated context selection, portable evidence,
and human-controlled procedural learning. More stored text is not learning.

## Scope and milestones

1. **Foundation (this implementation):** additive task-aware handoff with a
   total rendered character ceiling, relevance/abstention receipts, validity and
   supersession handling, unchanged originals, CLI/MCP parity, and a reproducible
   isolated demo with measured payload sizes and an inspectable HTML report.
   Preserve the existing 21-tool surface and legacy handoff behavior.
2. **Portable evidence:** stable identities, atomic relationship-preserving
   interchange, conflict/idempotency handling, and source references. Freeze a
   separate import/migration acceptance suite before implementation.
3. **Evaluated procedures:** evidence-linked candidate methods, prerequisites,
   counterexamples, independent holdout evaluation, human approval and rollback.
   Reuse the existing Reason/Discovery foundations; no automatic promotion.
4. **Shared control:** permission enforcement outside model prompts, scoped
   sharing and explicit retention. Optional encrypted transport is a separate
   security design, not a prerequisite for the local demonstration.

## Foundation acceptance criteria

- A task-specific request returns relevant whole original evidence and excludes
  unrelated, expired, future-valid, superseded, secret, or suspicious candidates
  from automatic selection. Conflicting current claims remain visible as
  conflicts, not silently resolved facts. All delivered evidence has no
  instruction authority and includes source provenance.
- No matching evidence produces an explicit abstention. Any candidate-scan
  limit is disclosed. Exclusion and omission receipts contain no secret text.
- The complete task-mode response fits the requested character budget,
  including JSON structure and provenance. Too-small/invalid budgets produce
  a typed error. Token figures are labeled estimates, never billing savings.
- Selection is read-only: no drawer, provenance, access-counter, belief, or
  transcript writes. No new network call or model service dependency is added.
- Existing handoff without a task remains compatible. CLI and the existing MCP
  handoff expose task mode; no additional MCP tool is required.
- An isolated repeatable demo closes one store/session, opens another, returns
  the exact request, retrieves relevant evidence, excludes stale/noisy evidence,
  shows abstention, and reports measured full-history versus selected payload.
  It labels synthetic fixtures and transport tests separately from actual
  commercial-host or model evaluations. HTML must escape untrusted content,
  load no remote assets, and execute no recovered instructions.
- Existing Claude/Codex/Qwen interrupted-request recovery tests remain green;
  Cursor remains explicitly unsupported. Recovery stays opt-in with a separate
  budget and no automatic storage. Task mode must not silently ignore requested
  recovery or claim a combined ceiling it does not enforce.

## Non-goals

No claim that host compaction disappears, every host is supported, model weights
improve, or synthetic payload reduction proves real-world task/billing gains.
No license/governance changes, new dependencies, execution orchestrator, paid
services, telemetry, production-store experimentation, live installation
changes, or 2.0 version bump/tag. No unrelated tree cleanup.

## Dependencies and execution gate

Target: local development environment and isolated temporary stores. The
existing user-approved continuity/selection/authority acceptance directions
are refined above into a foundation contract; later milestones require their
own frozen tests and do not inherit a completion claim from this milestone.

Execution gate: implementation against the [frozen contract](v2-foundation-acceptance.md)
is complete and independently accepted; preserve all frozen inputs during review.
GitHub issue tracks this plan; PR publication/merge and package release are
separate delivery gates. External billed model evaluations require explicit
approval and cannot be replaced by invented results.

## Historical foundation test freeze — 2026-09-05

User: "Resume by authoring and freezing the independent foundation acceptance tests"
(drawer #1241). This requested step is **COMPLETE**; foundation implementation is
not complete. Freeze timestamp: 2026-09-06T00:55:11Z.

Independent tester `/root/foundation_tester` authored
`tests/unit/test_context_acceptance.py`; `/root/foundation_review` returned PASS
for contract coverage. [The manifest](v2-foundation-freeze.json) binds 12 artifacts
including the contract, baseline, unchanged legacy gates and supporting inputs.
Manifest SHA-256:
`21a836728fad91f3a98cb1325a6ac08d91d421def183628c9acff8935a3a85c1`.
Mutable checkpoint documents are deliberately outside that inventory.

[Baseline evidence](v2-foundation-baseline.json): 39 expected failures and one
legacy pass in deterministic acceptance; the required real-embedding gate is
INCONCLUSIVE because its explicit local-cache prerequisite is unset. All 153
legacy regression tests, Ruff/format and isolation harness probes pass. No
collection errors, skips or xfails. The frozen contract specifies the actual MCP
response envelope, recovery combination handling, and a demo tied to observed
store reopening and backend calls; synthetic results cannot claim commercial-host
or model evaluation.

Next: implement against these artifacts without changing them, then verify all
foundation items including real embeddings and the demo. No runtime implementation,
dependency, production installation, license, version or release changed in this
step. Main remains `ad3ccee`; the acceptance and checkpoint files are uncommitted.

## Historical restart checkpoint — 2026-09-05

User: "find a good stopping point. i need to restart codex."

Tracking issue: <https://github.com/pnmcguire480/cairntir/issues/88>.
Main remains at `ad3ccee`; only planning/checkpoint documents changed locally.
No runtime implementation, tests, dependency changes, license changes, release,
or production installation changes have occurred for this request. The issue
contains the initial plan; this local checkpoint is the newer resume state.

Next action at that checkpoint: independently author and freeze foundation acceptance tests before
coding. Use the existing handoff with an optional task parameter rather than
adding a 22nd MCP tool. Preserve no-task behavior. Then implement pure candidate
selection and complete-response budgeting, integrate CLI/MCP, build the isolated
demo, and verify against the frozen suite and existing regressions.

Read-only architecture findings to carry forward:

- `DrawerStore.search()` and `get()` mutate access counters/timestamps. Add
  backward-compatible pure read options or dedicated methods; checking only
  drawer count is insufficient to prove a read-only path.
- `list_by()` and search filter expiry but not provenance `valid_from`. Both
  validity bounds belong in the context contract. Query actual same-wing
  successors independently of relevance so an unmatched correction is not lost.
- Existing temporal traversal touches access state, selects one branch, and can
  return a future root for an earlier as-of query. Do not use it to certify
  current evidence or resolve conflicts implicitly.
- Anchor parsing/path predicates are reusable; bounded scanning must disclose
  incompleteness. Stored source hashes are not automatically checked for freshness.
- Existing safety JSON quotes evidence but omits validity timestamps. Include
  validity and selection reasons in the new receipt. Regex checks and visibility
  labels are not authenticated permissions or proof of safety.
- `cost.py` already measures payloads; extend it rather than create a second
  dashboard. Its session-start path can touch discovery access state despite
  claiming purity. Real token counts vary by tokenizer; chars/4 is an estimate.
- Reason/Discovery already has evidence, candidates, confidence, baseline,
  counterexamples, next-test fields, and human-controlled lifecycle. Extend with
  withheld evaluation later, not a duplicate learning engine. Context reads must
  not call discovery generation.
- Semantic tests need actual embeddings as well as deterministic plumbing
  fixtures. Synthetic demo savings are not held-out task success or billed savings.
- Portable v2 is a later milestone: local IDs also occur inside verbatim text,
  CodeGlass fingerprints, and hotfix hash chains. Generic ID rewriting corrupts
  evidence. Prefer stable origin identities/reference maps and explicit unsupported
  receipt rehydration; never silently activate imported execution history.
- V1 content hashes include mutable layer/belief fields, so are not permanent
  identities. Import concurrency needs a dedicated same-key test and uniqueness
  checks inside the transaction; sequential idempotency alone is insufficient.

## Finalization Mode

Independent tester owns the artifacts bound in `v2-foundation-freeze.json`;
implementations must not alter them. Their SHA-256 values are registered before
coding; verify the complete inventory before acceptance. Reserve the
final quarter of the milestone for focused acceptance, full regression, lint,
types, package/CLI/MCP smoke, docs, and inspection of the demo report.

At most two repair-and-verification rounds after implementation enters
acceptance. COMPLETE requires independent PASS and every foundation item;
BLOCKED names an external prerequisite; EXHAUSTED preserves failing evidence
and the remaining work. Foundation completion does not mean 2.0 completion.
