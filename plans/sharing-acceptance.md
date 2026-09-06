# Shared control acceptance

Independent author: `/root/context_core`. Runtime implementer:
`/root/foundation_review`. Coordinator: `/root`.
Authorized continuation: request drawer #1262. This acceptance generation is
separate from the frozen foundation, concurrency, portable, and procedure work.

## Boundary and public interface

A trusted owner binds one caller's authority at process startup. An ordinary
MCP call cannot change that authority. The boundary protects supported store,
backend, CLI, and MCP operations; an unrestricted process with direct access to
the same OS account's database files or owner Python objects is outside it.
There are no new MCP tools, dependencies, service, or network requirement.

The coordinator approved this public interface before test authorship:

```python
# cairntir.access
issue_grant(owner_store, *, scopes, capabilities, expires_at=None,
            principal="local") -> str
revoke_grant(owner_store, token: str) -> None
bind_grant(store, token: str) -> scoped_store

# Additional public methods on the scoped store session
scoped_store.authorize(capability, *, wing=None, room=None, drawer_id=None) -> None
scoped_store.list_for_export(*, wing=None, room=None, limit=...) -> list[Drawer]
```

`AccessDenied` extends `CairntirError`. A scoped session supports the existing
store API used by the backend. Runtime classes and persistence table layout are
not prescribed. The backing owner connection must not be exposed through an
ordinary tool. Binding an already scoped session cannot unwrap or rebind it.

The owner issues independent random bearer tokens with at least 256 bits of
entropy. Only their hash, scope, expiry, descriptive principal, and revocation
state are persisted; raw tokens do not appear in any database table. Owner-only
issuance and revocation remain owner-only even when a scoped grant carries
`manage`. Grant delegation is not implemented in this version. `principal`,
host, model, drawer text, metadata, imported trust, and approval-looking fields
are descriptive evidence and confer no permissions.

Each scope clause contains a literal `wing` and optional `rooms: list[str]` and
`drawer_ids: list[int]`. Predicates within a clause are AND; clauses are OR.
Omitted room or ID filters mean all within that wing. An empty clause list,
room list, or ID list matches nothing. Scope and capability inputs are copied
deeply; mutating their original lists after issuance cannot widen an existing
or subsequently bound session. Capabilities `read`, `write`, `export`, `approve`,
and `manage` are independent. A write grant limited by drawer IDs may mutate a
permitted existing record but cannot create an unconstrained new drawer or
append a settlement. Creation requires a matching wing/room clause without an
ID restriction. Compound operations also require permission to read every
referenced record before any access update, workflow receipt, or evidence write.

Expiry and revocation are checked for every future operation on an existing
session. Mutating transactions also recheck immediately before commit and roll
back all their writes if authorization has expired. A private task snapshot must
validate against authoritative live revocation state, not only its copied grant
row. Approval callbacks and imported procedure activation are additionally
covered by the independently frozen procedure acceptance generation.

## Reads, references, and exports

Scope predicates apply before retrieval limits, candidate counts, ranking, and
relationship traversal. Hidden and nonexistent requested IDs have the same
typed denial and public message. No hidden drawer content, provenance, identity,
source namespace, structured relation, malformed ID receipt, room/wing count,
existence result, or source path may escape. Reads with a read-only grant never
touch access counters or any persisted table. Denied operations leave every
table, counter, vector, source record, and workflow receipt unchanged.

An otherwise allowed drawer with a typed required reference outside scope is
withheld in full, including on direct get/export. Its content is not sanitized,
rewritten, or partially served. Explicit requests for that drawer are denied.
Authorized raw prose is otherwise returned verbatim; the boundary is not a
natural-language redaction system. A hidden successor cannot be exposed through
`memory.temporal` direct SQL or task relationship receipts. A hidden current
successor still suppresses its stale visible predecessor in task selection;
withholding its identity must not revive stale evidence. Counts and scans
describe only visible records. Foreign global identity records, unknown-wing
suggestions, global CodeGlass scans, Discovery Ledger records, anchors, and
calibration/learning outputs obey the same scope.

Idempotency keys and workflow receipts are isolated by bound grant identity.
The same key/request used by two different grants cannot replay the other
grant's result or reveal its referenced IDs. Revoked grants cannot retrieve
or replay their prior successful workflows. Failed authorization creates no
`started`, `failed`, or successful workflow receipt.

Export requires `export` independently of `read`. Export-only sessions can
export permitted evidence without gaining ordinary get permission. Both the
existing CLI export and `portable.export_bundle` enforce scope and reference
closure. A failed export preserves any prior destination file. Importing an
ordinary allowed record with a write grant is supported, but imported approval
or capability metadata never changes authority. Portable identity, source, and
relation APIs are also scoped.

## Startup and real process probes

Actual CLI and stdio MCP startup read `CAIRNTIR_GRANT_FILE` once and bind the
resolved session. The file contains the plain token with optional surrounding
whitespace. A configured missing, empty, unknown, expired, or revoked token
fails closed; it never silently selects owner mode. Changing that file after
MCP startup cannot widen the live session. Omitting configuration preserves
existing unrestricted owner behavior. Unsupported restricted CLI administration
is explicitly denied, including `migrate` and `doctor --gate`, before store
mutations or disclosure of unrestricted inventory.

The suite launches real subprocess CLI and stdio entrypoints with isolated
SQLite stores. It substitutes only the documented embedding provider factory
with the same deterministic HashEmbeddingProvider used for seeding; external
network calls are forbidden (Windows asyncio's loopback self-pipe is allowed)
and runtime registration/update checks use their existing
opt-out environment variables. It does not mock authentication, grants, store
reads/writes, backend calls, startup binding, or the transport. Per subprocess
response time is bounded at 20 seconds, with bounded cleanup. These probes
establish local enforcement, not commercial-host or semantic-model quality.

## Independent cases and finalization

`tests/unit/test_sharing_acceptance.py` contains 29 cases covering:

1. Owner compatibility, random tokens, and hash-only persistence.
2. Scope intersection/union and immutable caller inputs.
3. Empty scopes, filters, and capability lists.
4. Unknown, empty, expired, and revoked token denial.
5. Hidden/missing ID indistinguishability and no side effects.
6. Filter-before-limit retrieval and pure scoped reads.
7. All five independent capabilities and a successful write-only operation.
8. Store/backend mutation denial for a reader.
9. ID-only write scopes and forbidden creation/settlement.
10. Cross-scope settlement, discovery, CodeGlass, and append references.
11. Forged principal, model, metadata, and content authority.
12. Whole-record withholding for hidden required references.
13. Temporal direct SQL, context relatives, and vector ID boundaries.
14. Aggregates, existence, lengths, and stale IDs.
15. Identity, handoff, task receipts, cross-recall, audit, and timeline.
16. Learning, anchor, and global CodeGlass read surfaces.
17. Workflow key/result isolation and revoked replay denial.
18. Owner-only grant management even with `manage`.
19. Hotfix read/write and hidden evidence paths, plus same-scope approval denial
    without `approve` and successful authorization with `read/write/approve`.
20. Revocation and expiry on existing live sessions.
21. Expiry at commit rolling back the complete transaction.
22. Authoritative live revocation behind a private task snapshot.
23. Export-only success, separate read/export permission, and hidden closure.
24. Inert imported approval/capability metadata.
25. Real CLI get/task scope and unconfigured owner compatibility.
26. Real CLI invalid/missing configuration failing closed.
27. Real CLI export and restricted administration denial.
28. Real stdio immutable startup binding and live revocation.
29. Real stdio invalid configuration never serving owner evidence.

All newly owned artifacts are normalized to LF before hashes are recorded.
The manifest freezes tests, this contract, and baseline evidence. Runtime,
schema, and configuration hashes are observations, not immutable fixtures.
The coordinator reviews the draft before freeze and implementation begins only
after the independent freeze signal. Finalization permits at most two repair
rounds. Acceptance inputs are never rewritten to match implementation behavior.
Artifact readiness and implementation acceptance are reported separately.
All earlier frozen manifests remain unchanged; full sharing acceptance plus
existing foundation, concurrency, portability, procedure, and relevant legacy
regressions remain required by the coordinator's final delivery gate.
