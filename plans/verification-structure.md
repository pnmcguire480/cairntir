# Verification that detects incorrect behavior

Status: **IN PROGRESS**. Tracking: [issue #107](https://github.com/pnmcguire480/cairntir/issues/107).
Base: `dc2607f2146b931e4fa9243fc847583d6bf99ebb`. Implementation is authorized;
publication, production installation, application restarts and subagents are not.
The preceding publication run completed before this work began.

## Historical audit

These are actual runtime fixes. `scripts/verify_history.py` extracts the exact
parent and fixing Git trees into disposable directories, copies the same tests
into both, and requires a specific behavioral assertion to fail on the parent
and pass on the fix. Collection errors, missing imports, fixture errors, skips,
timeouts and unrelated failures cannot satisfy the gate. Dependencies are the
current locked environment, not reconstructed historical dependency environments.

| Bug and fix | User outcome | Gap in the earlier verification | Reproducer |
| --- | --- | --- | --- |
| MCP reports the SDK version, `60ccbbf` | Identify the Cairntir version answering the host | The earlier MCP tests checked tools and error formatting, without asserting initialization version | `test_handshake_identifies_cairntir` |
| Failed export overwrites the previous file, `a67c000` | A failed export leaves the previous complete export usable | The earlier portable tests exercised completed streams; they did not interrupt iteration after writing the first record | `test_interrupted_export_preserves_previous_file` |
| Malformed checkpoint text escapes as an untyped error, `d88beab` | Reject invalid input cleanly and keep the previous task resumable | Task acceptance did not exercise lone surrogate idempotency keys; the later boundary baseline records real Unicode and integer overflow failures | `test_invalid_checkpoint_preserves_resumable_task` |
| Opening a current store rewrites its header, `e27fe04` | Opening without a write preserves database bytes | Migration tests asserted the resulting schema version and rows, not byte preservation on a second current-schema open | `test_reopening_current_store_preserves_database_bytes` |
| Orphan backup worker removes a live replacement, `5584ff7` | An interrupted coordinator cannot destroy another worker's backup attempt | Earlier process tests covered lock release and crashed coordinators, without synchronizing a surviving helper against a replacement's active staging directory | Existing frozen `test_orphan_worker_never_removes_a_live_replacement_attempt` |

The gap descriptions are conclusions from the earlier test surfaces and fixing
diffs, not claims about what reviewers thought. The original automatic-backup
baseline's missing-module failures prove an unimplemented feature; they are
explicitly **not** counted as failing-before-fix behavioral regression evidence.

First execution: all five broken revisions failed the required assertions and
all five fixes passed. Logs and JUnit results are under the private
`.cairntir/verification-structure/history/` directory. Final evidence will record
the tested hashes after implementation finishes.

## Required verification

1. Restore a managed SQLite snapshot to a new location; compare all tables,
   including physical vectors, provenance and checkpoint history. Resume the
   restored task and exercise restored retrieval. Check committed WAL data and
   exclusion of uncommitted writes.
2. Exercise real process locks, mid-write database failures, nested rollback,
   unavailable backup destination, interrupted backup and damaged snapshots.
   Assert the surfaced failure and surviving data, then demonstrate recovery.
3. Deliberately omit backup records and break other critical operations in
   disposable copies. Require behavioral test failures and passing unmodified
   controls. A killed process or broken harness is not a detected mutation.
4. Build and temporarily install the wheel; drive actual console scripts and
   MCP stdio from outside the source checkout. Check version, tool schemas,
   writes, task resumption, backup and restoration.
5. Measure subprocesses as well as parent tests. Use the existing combined
   statement-and-branch metric, reporting its components separately. Raise the
   enforced floor from 80% to 92% only after meaningful tests reach 92%. Add no
   omissions, exclusions or empty assertions to achieve the number.
6. Preserve every existing frozen acceptance artifact. Keep production data
   outside all fixtures, fault injection, mutation and package experiments.

New work is authored and verified by one agent, per the maintainer's explicit
constraint. No independent review is claimed. Existing independently authored
frozen tests remain immutable. Reserve at least 25% of finalization effort for
verification; at most two final repair rounds.

## Candidate evidence

The five historical comparisons and seven deliberate mutations passed with
clean controls. The result judge also has 15 tests proving that skips, missing
reports, setup errors and unrelated failures cannot count as success.
The installed wheel passed version/tool checks, abrupt MCP interruption,
resumption by another host without rebriefing, concurrent CLI checkpoint writes,
idempotent retry, complete table restoration and restored semantic retrieval.
The wheel contains 74 verified package files and exposes 21 MCP tools.

Outcome tests reproduced and minimally repaired these additional defects:

- Invalid embedding batches and nonfinite, zero, overflowing or underflowing
  float32 values could be stored or used for misleading matches.
- Rejected anchor updates and no-op repairs changed access history; legacy
  receipt reads could expose raw SQLite errors.
- Invalid workflow result types committed writes before reporting failure;
  a failed committed-receipt write could expose a raw SQLite error.
- Codex header decoding lost valid requests when later bytes were malformed;
  non-object headers crashed filtering.
- Transcript extraction trimmed original whitespace. Five behavioral failures
  cover Claude strings/blocks, Codex events/blocks and Qwen's first user part.
  Qwen's existing exclusion of subsequent hook context remains intact.

Private before/after source copies and JUnit receipts are retained under
`.cairntir/verification-structure/`. The same corrected whitespace tests also
failed in an isolated copy of the actual previous source. Harness mistakes and
invalid fixture assumptions are not included as evidence of product defects.

The current preservation gate passes 24 manifests and 115 protected artifacts.
Static/type, commitment/seam, documentation-link, release-tag and dependency
advisory checks pass (134 locked registry packages; no advisory findings).
All seven model evaluation tests pass against a provisioned disposable corpus.
The live production corpus is outside this work's authority.

The fresh CI selection passed **1,655 tests** with eight slow tests deselected.
Coverage is **92.16% combined**: 8,012/8,571 statements (93.48%) and 2,259/2,574
branches (87.76%). The enforced combined floor is now **92%** in pytest and CI;
`coverage report --fail-under=92` passes. No exclusions or frozen artifacts changed.
These are clean-run numbers; earlier appended development figures are not used
as final evidence. The separate provisioned model evaluation passed all seven tests, and the remaining
slow acceptance check passed. Together the selections cover all 1,663 tests with
no skips or omissions.

Finalization uses the remaining verification reserve, with at most two repair
rounds. New work is solo-authored and no independent review is claimed. The [verification receipt](verification-evidence.json) binds the tested source,
new tests, scripts and behavioral results. Cross-platform CI remains pending. Publication and
production installation remain outside this follow-up.

Limitations: targeted mutations are seven deliberate faults, not an exhaustive
mutation score. Destination loss is a disappearing disposable mount directory,
not a physical E: unplug; interruption kills owned test processes, not machine
power. Tests prove the exercised recovery paths and surviving data.

## Continuation

The maintainer clarified: "i dont care about the automation. i need the
implantations and features we discussed." Then: "implementations, yes. typo.
do we need the automation. yes or no". The answer is no; implementation continues
directly in this task. Do not restart the historical audit or spend implementation
time on automation management.

Persistent task: `01a07423-448f-7e11-bb22-7b36d4dabbb2`.
Memory task `c73d30d4-f6e3-4436-8e48-163f97e89741`, wing `cairntir`, room
`requests`, was acknowledged at revision 1 (drawer #1443). A fresh MCP startup
was blocked by automatic approval review because it may write the production
database. Progress is preserved in this workspace; no later memory revision is
claimed. Pause the heartbeat only when the implementation is complete.
