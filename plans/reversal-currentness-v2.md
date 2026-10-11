# Decision reversal currentness — v2 acceptance boundary

The installed 1.12.4 baseline in disposable wing `reversal-test` saved Postgres
drawer `#2846` and a later SQLite reversal `#2847` through ordinary remember.
Neither has a `supersedes_id`. Task-aware handoff for setting up the datastore
returned Postgres first and SQLite second, with neither marked historical or
conflicted. This is a Tier-2 wrong-answer risk, not an inferred store mutation.

Current v2 work already has an explicit append-only correction path from
Obsidian. It binds source identity and content hash, rejects a stale source,
and writes a successor edge. That does not yet give an agent using MCP an
ordinary way to declare a correction: `cairntir_remember` still has no source
parameter. No shipped function should be renamed as a new v2 capability.

The next public contract is a dedicated agent-facing correction operation
over the same durable source-binding rules. The caller supplies the exact
source drawer, wing, source identity/hash, replacement text and retry key.
The operation returns a committed or replayed receipt naming both drawer IDs.
It preserves the original verbatim, refuses stale, hidden, cross-wing, secret
and structured lifecycle sources, and never infers a supersession edge merely
from contradictory prose. A normal unlinked remember remains historical
evidence, not an assertion of currentness.

All handoff and recall views that show a decision must carry its saved date,
source identity and current/historical/unresolved status. A task-aware brief
must never present a known superseded ancestor as current. If two valid
successors conflict, or if unlinked prose disagrees without a reliable
relationship, the brief must say currentness is unresolved instead of choosing
one by recency or embedding rank. Bounded/partial scans must disclose that
they cannot establish global currentness. `get` retains verbatim history.

Independent evaluation should first capture the installed failing baseline,
then freeze a public behavior contract and separately held-out cases before
builder implementation. The evaluator controls its own environment and source
of truth. Include stale/cross-wing/revoked access, replay, branched successors,
missing date, budget omission and old-client behavior; report the exact source
head and all failures. The builder must not edit evaluator cases or qualify its
own hidden oracle. Existing historical acceptance artifacts remain byte-for-byte
unchanged. Native fresh-agent and Obsidian round trips remain separate gates.

The 1.12.4 A/B baseline cannot be retrospectively called linked. A migration
may append a reviewed successor relation or mark the pair unresolved while
preserving both original drawers; it must not silently rewrite `#2846` or
`#2847`. No real wing migration is part of this plan.
