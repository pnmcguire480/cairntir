# Cairntir Modernization Session — Layman Report

**Date:** 2026-07-27
**Code version:** `1.2.0` release candidate (not tagged or published)
**Verification:** all 372 tests passing, 81.12% coverage

## The short version

Cairntir crossed an important line in this session. It is no longer only a
fast memory store with a visible learning ledger. Its important multi-step
thoughts are crash-safe, retries do not duplicate them, every new memory knows
which host/model/session produced it, and recalled memory is explicitly
treated as evidence rather than instructions.

The first functional-growth loop is also real: repeated Reason episodes can
propose a calibrated pattern, the human can inspect or reject it, CodeGlass can
measure whether an explanation was retained, and the resulting learning can
be projected into Anthropicer without surrendering SQLite as the source of
truth.

This is not yet proof that Cairntir improves indefinitely. It is the first
governable mechanism that can produce and measure that improvement.

## Changed and updated

- The database schema moved from v4 through v5 to **v6**.
- Every write now carries immutable provenance: host, model, session, capture
  path, trust, visibility, sensitivity, validity, client version, and tool
  version.
- The MCP surface grew from eight to **seventeen tools**.
- Reason, recipes, replay, imports, daemon capture, and CodeGlass use durable
  idempotent workflows.
- Codex, Cursor, and Claude Code adapters identify themselves while sharing
  one canonical memory store.
- Discovery candidates can be proposed automatically from repeated Reason
  episodes and inspected through a calibration report.
- CodeGlass is a real recipe and memory protocol with cited
  WHAT/HOW/WHERE/WHEN/WHY explanations, teach-back, and delayed retention.
- `cairntir obsidian-project` projects learning and CodeGlass notes into an
  Obsidian vault while preserving user-written text.

## Fixed

- A crash can no longer leave half of a production Reason/recipe workflow
  committed.
- Repeating an already-completed request no longer creates duplicate drawers.
  Reusing the same key for different work fails loudly.
- A memory that says “ignore previous instructions” cannot silently become
  policy; it is rendered as untrusted evidence and flagged.
- Legacy drawers no longer have ambiguous origin. Migration marks their
  provenance as legacy/untrusted rather than inventing certainty.
- Database migrations create a timestamped backup first, and doctor can report
  SQLite integrity, foreign-key failures, and stranded workflow receipts.
- The contradiction detector now compares meaningful observed/predicted
  anchors instead of accidentally anchoring on an empty outcome.
- Delayed CodeGlass teach-back now supersedes the immediate result, producing
  a coherent learning history rather than two disconnected branches.

## Removed

- No lineage artifact, user memory, three-skill behavior, or public v1 API was
  removed.
- Mandatory `sentence-transformers`/Torch remains removed from the hot path;
  it is still available through the legacy optional extra.
- Silent prompt authority, silent mixed embeddings, and silent partial
  workflow success were removed as accepted behaviors.

## Improved

- Semantic filters now run before nearest-neighbor limiting.
- Full drawers are exact-fetchable with length/hash/truncation receipts.
- The Discovery Ledger records confidence, observation count, baseline,
  counterexamples, evidence fingerprint, and the next falsifying test.
- Automatic discovery deliberately stops at **candidate**. Only reviewed
  evidence can move it toward corroborated or promoted.
- Calibration reports resolved/unresolved predictions, success rate, a 95%
  uncertainty interval, belief mass, contradictions, and room distribution.
- Obsidian projection excludes secret material, uses generated markers,
  refuses to overwrite unmarked user files, and preserves notes outside its
  generated block.

## Learning vocabulary

- **Transaction:** a group of database changes that either all happen or none
  happen.
- **Savepoint:** a safe checkpoint inside a larger transaction.
- **Idempotency key:** a receipt number that makes an exact retry return the
  first result instead of doing the work twice.
- **Provenance:** the origin receipt for a memory—who/what wrote it, where,
  when, and through which path.
- **Trust boundary:** the rule separating remembered evidence from commands an
  agent is allowed to obey.
- **Prompt injection:** text that tries to smuggle instructions through data
  or memory.
- **Calibration:** measuring whether predictions were right often enough to
  justify confidence in them.
- **Wilson interval:** a conservative uncertainty range for a success
  percentage, especially when the sample is small.
- **Teach-back:** asking the learner to explain the idea in their own words so
  apparent understanding can be tested.
- **Retention:** how much of that understanding remains after time passes.
- **Projection:** a one-way human-readable view generated from the
  authoritative database.
- **Candidate discovery:** a pattern worth testing, not a fact and not an
  automatically adopted strategy.

## Verification

- All 372 tests pass, including the opt-in LongMemEval-style semantic test.
- Coverage is 81.12% (required minimum: 80%).
- Ruff lint and mypy strict pass across 46 source files.
- Failure-injection, idempotent replay, prompt-poisoning, schema migration,
  CodeGlass retention, Obsidian safety, and automated three-host continuity
  all have regression tests.

## Next-steps presentation

### 1. Real-host release-candidate smoke

Run Codex, Cursor, and Claude Code as three independent clients against the
same temporary project. Write, exact-fetch, supersede, and inspect provenance
across all three. The adapter contract is automated; the live-client smoke
cannot be honestly claimed from one Codex session.

### 2. Rehearse the live data transition

Copy the real Cairntir database, run v6 migration/doctor/reindex against the
copy, and verify counts, provenance, semantic recall, and recovery artifacts
before touching the live store.

### 3. Earn the “Evolving Mind” claim

Add stronger independence checks across episodes/hosts, contextual usefulness
feedback, strategy holdouts, repeated-error reporting, and a longitudinal
scorecard that compares Cairntir with its own earlier baseline.

### 4. Complete CodeGlass automation

Build the deterministic host-side code evidence collector and run a real
learner holdout. Cairntir currently validates, stores, tests, and projects a
cited walkthrough; an agent still supplies the evidence and explanation.

### 5. Release deliberately

Inspect the wheel, test strict docs, reconcile version/tag/PyPI/release notes,
then cut v1.2. No version was bumped and nothing was committed during this
session.
