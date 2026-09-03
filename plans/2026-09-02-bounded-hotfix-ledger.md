# Bounded Hotfix Ledger

**Status:** authorized for implementation on an isolated clone of `main` at
`4e123a1f8a91f3867046a818490de63f4d8433e7`. The live Cairntir store stays
closed until the implementation, pull request, and verification are complete.

## Problem

Hotfix work currently arrives as scattered errors, authority messages, command
outputs, and human answers. An agent can remember each fragment and still lose
the ordering law between them: compare earlier evidence first, bind authority
to one candidate, prove the real environment, attempt once, independently
verify, and stop when no relevant state changed.

The result is avoidable repetition. A failed protected check can be retried
against identical state, a later authorization can be mistaken for broader
permission, and a green component test can be mistaken for terminal evidence.

## Outcome

One deep `HotfixCoordinator.run(command)` interface turns those fragments into
an append-only, hash-chained case ledger. Through the same interface a host can:

1. open and classify a failure;
2. compare candidate paths against cited memory and completed precedents;
3. seal one exact authority envelope;
4. record an evidence-cited preflight of the real target;
5. record one bounded host execution without giving Cairntir execution power;
6. record independent acceptance or an exact rollback;
7. settle as `COMPLETE`, `BLOCKED`, or `EXHAUSTED`; and
8. render the next legal action as an operator hotfix card.

The host executes commands. Cairntir only validates ordering, preserves
evidence, and returns receipts. This keeps the memory-first layer
host-neutral and does not turn it into an agent or build orchestrator.

## Interface and seam

`HotfixCoordinator.run(HotfixCommand) -> HotfixReceipt` is the module's only
behavioral interface. `HotfixCommand.action` selects `open`, `recommend`,
`authorize`, `preflight`, `record_attempt`, `rollback`, `verify`, `settle`, or
`status`; action-specific data stays inside one JSON-compatible payload.

The interface owns these invariants:

- every mutating command is idempotent;
- every cited drawer exists in the same wing;
- event drawers form a verified hash and `supersedes_id` chain;
- candidate ranking is deterministic and explains its precedent/evidence,
  reversibility, and risk ordering;
- authority binds exact candidate, plan, toolchain, target, sequence,
  capabilities, required preflight checks, and acceptance inventory;
- preflight must match every binding and cite fresh evidence for every check;
- one authority permits at most one attempt;
- a failed attempt cannot be repeated from its unchanged resulting state;
- verification covers the frozen acceptance inventory and uses a verifier
  distinct from the executor;
- rollback is accepted only when the observed hash equals the pre-attempt hash;
- only independently verified acceptance can settle `COMPLETE`;
- attempt or repair exhaustion terminates instead of reopening itself.

The MCP and CLI layers are adapters over this interface. MCP adds one tool,
`cairntir_hotfix`; the CLI adds one command, `cairntir hotfix`. Neither contains
workflow rules.

## Persistence

Hotfix events use ordinary drawers in the affected wing and the reserved
`hotfix-ledger` room. Structured metadata is namespaced with
`cairntir.hotfix.v1`; human-readable content remains useful through normal
recall. Each drawer supersedes the prior event in its case. No schema migration,
destructive rewrite, or new dependency is required.

Completed settlements retain the resolution and evidence needed by later
recommendations. Conflicting or tampered chains fail closed with a typed
`HotfixError` rather than silently choosing a winner.

## Delivery slices

1. Domain values, deterministic classification/fingerprinting, open/status,
   and chain validation.
2. Evidence- and precedent-based recommendation with stable tie-breaking.
3. Immutable authority and binding-aware preflight.
4. Bounded attempt, no-progress guard, exact rollback, independent verify,
   and terminal settlement.
5. One MCP adapter, one CLI adapter, and the bundled operator recipe.
6. Mutation-check the ordering guards, run the complete local gate, build the
   wheel, inspect it, open the PR, and wait for CI.

## Acceptance inventory

- A replayed command writes no duplicate event.
- Same failure facts always produce the same fingerprint and classification.
- A recommendation prefers a matching completed precedent, explains the
  ranking, and never accepts missing or cross-wing evidence.
- Any authority-binding mismatch blocks preflight before an attempt.
- An authority cannot be reused and an unchanged failed state cannot be
  attempted again under a later envelope.
- Verification fails closed for an omitted acceptance item, stale state hash,
  or verifier/executor identity collision.
- Exact rollback and `COMPLETE`, `BLOCKED`, and `EXHAUSTED` dispositions are
  independently observable through `status`.
- A damaged event hash or forked supersession chain is detected on read.
- MCP and CLI adapters exercise the same coordinator seam and surface typed
  errors without corrupting the store.
- Existing behavior remains green; public root exports and schema stay fixed.
- The wheel contains the hotfix recipe and imports in a clean environment.

## Explicit non-goals

- Cairntir does not run shell commands, mutate repositories, acquire
  privileges, sign authority, or claim that caller-supplied observations are
  independent.
- No fourth skill, autonomous agent loop, database migration, live-store
  mutation during development, release tag, publication, or merge to `main`.
- No test deletion, weakening, selective substitution, or expectation
  rebaselining to manufacture a pass.

## Verification reserve

Reserve the final third of the run for focused tests, the complete non-optional
suite, ruff, formatting, strict mypy, repository guard scripts, package build,
wheel-content inspection, clean-install smoke, and remote PR checks. At most
two repair-and-verify rounds follow the first full verification. Repeating an
identical check against identical state is not progress.

The unchanged-clone baseline on 2026-09-02 was 745 passing tests at 84.42%
coverage. One optional legacy-embedding eval failed because the isolated clone
did not install `cairntir[legacy-embeddings]`; it is not a regression signal.

## Finalization Mode

The implementation terminates as:

- `COMPLETE` only when every acceptance item has fresh evidence, the branch is
  committed and pushed, the pull request exists, required checks pass, and the
  original `main` checkout remains clean at its frozen SHA;
- `BLOCKED` when one named external dependency or authority is the smallest
  remaining unblocker; or
- `EXHAUSTED` when the verification reserve or two repair rounds are spent.

The acceptance inventory above is frozen before implementation. Production
code may not special-case its fixtures, and any change to an acceptance test
after its first green result must be justified as a new discovered requirement,
not silently rebaselined.

```cairntir-commitments
symbol src/cairntir/hotfix.py HotfixCoordinator
symbol src/cairntir/hotfix.py HotfixCommand
symbol src/cairntir/hotfix.py HotfixReceipt
symbol src/cairntir/mcp/backend.py hotfix
symbol src/cairntir/cli.py hotfix_cmd
file   docs/recipes/bounded-hotfix/recipe.toml
test   tests/unit/test_hotfix.py test_same_failure_produces_one_stable_fingerprint
test   tests/unit/test_hotfix.py test_authority_preflight_attempt_and_independent_verification_complete
test   tests/unit/test_hotfix.py test_unchanged_failed_state_cannot_be_attempted_again
test   tests/integration/test_seams.py test_hotfix_mcp_and_coordinator_enforce_the_same_ordering
```
