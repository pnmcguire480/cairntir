# Automatic store backups

Status: publication verification exposed a worker-ownership race; corrective 1.12.1 acceptance and delivery in progress.

## Problem and goal

Verified manual snapshots exist, but the store has no recurring recovery point.
Provide opt-in backups every 12 hours when Cairntir next opens the writable store
or begins a write. Keep complete SQLite snapshots that can be restored without
rebuilding embeddings or reconstructing task history.

## Scope and acceptance

- Persist configuration beside the database; all hosts using that store share it.
  The destination is user-configured, with a 12-hour default interval.
- Check on writable startup and before an outer write transaction. Do not back up
  uncommitted state, wait indefinitely, or require a model download.
- Create a consistent online SQLite snapshot, verify integrity and foreign keys,
  and publish a timestamped database plus a checksum receipt only after success.
- Coordinate processes. A crash releases ownership; interrupted files are never
  mistaken for a verified backup. Repeated opens inside the interval do not copy.
- An unavailable destination or failed backup surfaces a typed warning while
  ordinary memory writes remain usable. A later attempt can recover.
- Retain all managed snapshots from the last seven days and four older weekly
  recovery points. Prune only verified, owned snapshots after a new verified
  snapshot succeeds. Preserve manual snapshots and unrelated files.
- Provide CLI configuration, explicit backup, status, and disable operations.
  Status is read-only. Read-only store use never activates backup side effects.
- Preserve existing mandatory backup-first migration and reindex safeguards.

## Non-goals and boundaries

No Windows scheduler, Codex automation, transcript capture, cloud upload, new
dependency, schema migration, automatic restore, or change to published 1.11.0.
No production data repair or reindex: the completed independent audit found none
necessary. Existing manual recovery baselines remain outside automatic retention.

The local destination is authorized by the user. Production publication is a
separate release gate after a concrete reviewed candidate exists.

## Verification and budget

An independent tester owns the acceptance specification and tests and freezes
their hashes before runtime implementation. The coder cannot edit these files.
Verify real WAL data, restore fidelity, persisted cadence, concurrent processes,
interrupted/failed snapshots, retention, configuration, and read-only boundaries.
Run the existing project gates after focused acceptance passes.

Budget: one implementation pass, at most two repair-and-verify rounds, with at
least 25% of work reserved for verification. Stop with COMPLETE, BLOCKED, or
EXHAUSTED; do not weaken tests or reopen settled release work.

## Assumptions

Known: Python's SQLite backup API already serves migration/reindex snapshots;
the store centralizes ordinary writes in outer transactions. Known: shared
configuration can use the existing platform-derived home. To verify: backup
latency under lock contention, operating-system lock release after interruption,
and safe publication/pruning with multiple hosts and an unavailable destination.

## Delivery evidence

Issue [#101](https://github.com/pnmcguire480/cairntir/issues/101).
The [independent freeze](automatic-backups-acceptance-freeze.json) binds 29 cases,
the contract and baseline, and mandatory legacy store tests. Baseline: 29 expected
failures because the backup API is absent; zero infrastructure failures. Runtime
implementation began after the freeze. [Independent round 0](automatic-backups-result.md)
passed all 29 cases and 39 mandatory legacy store regressions, with zero repair
rounds and unchanged artifacts/runtime. Three additional independent failure
boundary cases passed. Full local regression: 1,142 passed, eight deselected,
82.42% coverage. Complete offline model evaluation: seven passed.

Ruff, strict typing, strict documentation, links, commitments, seams, exception
handling, immutable release tags and all 134 locked dependency advisories passed.
The authorized machine policy is configured and its first managed snapshot is
verified. The published and installed package remains 1.11.0; automatic policy
activation is tracked in the corrective [1.12.1 release](../docs/release/v1.12.1.md).
The first tagged candidate failed crash-replacement verification before publication;
its tag and all frozen evidence remain unchanged. New independent acceptance
reproduces the worker-ownership race before the runtime repair.
PR [#102](https://github.com/pnmcguire480/cairntir/pull/102) merged at `e27fe04`
with all 14 checks passing. The user explicitly approved the 1.12.0 publication
and installation gate on 2026-09-07.

```cairntir-commitments
file   src/cairntir/backups.py
symbol src/cairntir/backups.py configure
symbol src/cairntir/backups.py run
param  src/cairntir/memory/store.py __init__:automatic_backups
test   tests/acceptance/test_automatic_backups.py test_due_outer_write_backs_up_committed_state_before_nested_work
test   tests/acceptance/test_automatic_backups.py test_contention_is_bounded_and_crashed_owner_can_be_replaced
test   tests/acceptance/test_automatic_backups.py test_retention_keeps_recent_and_four_weekly_points_and_unmanaged_files
test   tests/acceptance/test_backup_worker_ownership.py test_orphan_worker_never_removes_a_live_replacement_attempt
```
