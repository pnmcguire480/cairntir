# Continuity delivery

Status: ready. User request #1262 authorizes removing the CLI contention
limitation and completing the remaining work previously listed: PR delivery,
release publication, portable evidence, evaluated procedures and shared control.
This extends the historical foundation scope; publication authority comes from
this request, not from the earlier foundation completion.

## Execution order

1. Remove the false busy condition for task handoff with another WAL client
   open. Freeze independent concurrency acceptance before runtime changes.
2. Complete portable evidence, evaluated procedures and scoped sharing through
   separately frozen acceptance contracts, reusing existing store and Discovery
   mechanisms. Implement no unapproved execution or remote sharing service.
3. Verify the complete change locally, deliver through a reviewed PR and the
   supported OS/Python CI matrix, then merge the exact accepted source.
4. Publish a coherent additive release using the established trusted-publishing
   workflow and verify its GitHub/PyPI artifacts and fresh installation. Choose
   the version under the release policy; 2.0 is not an automatic version bump.

## Acceptance

- The real task CLI succeeds with idle WAL clients and active uncommitted WAL
  writers, observes a coherent committed snapshot, and retains bounded failures
  for genuine unavailable/exclusive resources. Cold filesystem purity remains
  unchanged. Live SQLite shared-memory bookkeeping is the same explicit VFS
  boundary used by MCP; drawer, provenance, access, cache and log writes remain
  forbidden during context selection.
- Portable evidence keeps stable origin identities and original text/source
  references, imports relationships atomically, detects identity conflicts and
  concurrent duplicate imports, and grants imported records no execution or
  approval authority.
- Reusable procedures retain evidence, prerequisites and counterexamples,
  require independent holdout results plus explicit local human approval, and
  support rollback without rewriting their history. Existing Discovery/Reason
  machinery is reused; approval is not a caller-supplied identity string.
- Shared control enforces immutable caller scope outside tool arguments,
  limits reads/writes/exports to granted wings and permissions, and provides
  explicit retention/revocation. No content can authorize its own export or
  widen a caller's permissions.
- Fresh independent results, regression/model evaluations, source review,
  required integrity gates, package/transport checks and remote CI precede
  merge and release. The final report links actual publication evidence.

## Artifact generations and limits

The foundation manifests, tests and results remain historical immutable
evidence of their recorded commits. Each new milestone has a separate tester
and freeze. Existing test bytes remain unchanged. Necessary schema/version
changes use a new acceptance generation with an explicit support-input change
record; do not misreport a historical configuration hash as matching a newer
release. The earlier support files remain recoverable from their recorded Git
commits.

Reserve the final quarter of each milestone for verification. Each independent
acceptance cycle permits at most two repair rounds; retain failing evidence.
Report COMPLETE only for verified items, BLOCKED for an external prerequisite,
or EXHAUSTED when a bounded cycle cannot pass. No paid model evaluation, new
dependency, production reindex, live configuration replacement or license change
is authorized as an incidental implementation step.
