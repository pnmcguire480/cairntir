# Complete recall-response budgeting (1.13.0 candidate)

One foundational feature from the preserved E23 recall-budget plan, ported onto
published 1.12.4 without importing the parked v2 tree. The previous backend
budget counted full content only; it did not expose a complete MCP result ceiling.
Clients can now request predictable whole-evidence context using the existing
recall tool. See [usage and limits](../docs/how-to-use.md#bound-a-recall-response).

## Acceptance and boundaries

The [independent finite contract](acceptance/recall-budget-1.13/FINITE-CONTRACT.md)
and [original acceptance](acceptance/recall-budget-1.13/ACCEPTANCE.md) require
strict 1024..262144 integer budgets, exact content/provenance/hash/ancestry,
whole records, complete omission accounting with bounded IDs, real MCP transport,
scope retention, legacy compatibility and deliberate wrong controls. The frozen
manifest binds 21 tests before this port. It is public shared-workspace evidence,
not a private holdout or a human usability evaluation.

Only successful serialized MCP CallToolResult characters are bounded. No model
token, cost, speed or wire-byte guarantee. No new tool, dependency, migration,
automatic ingestion, provider routing or execution authority. No live store,
credential, client registration or installed-package changes. No second feature.

## Finalization

Reserve at least 25 percent of effort for verification, with at most two repair
rounds. Preserve frozen assertions, negative controls and failed outcomes.
Run targeted serial synthetic checks locally; heavy repository-required tests
run through the existing hosted CI. COMPLETE requires independent adversarial
PASS and all repository-required checks at the exact candidate head. Publication,
merge, tag and live installation remain separate authority gates.

Current state: implementation candidate; independent review and hosted checks
pending. Historical E23 qualification is not reused as proof for this port.
