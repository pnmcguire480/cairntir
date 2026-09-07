# Automatic SQLite backup acceptance

Independent tester `/root/foundation_tester`; issue #101. This generation adds
opt-in automatic local recovery points. It does not alter previous frozen tests,
runtime schema, package version, dependencies, or the 21-tool MCP surface.

The agreed public Python interface is `cairntir.backups.configure(database,
destination, *, interval_hours=12)`, `status(database)`, `run(database,
*, force=True)` and `disable(database)`. Paths are `Path` arguments and results
are JSON-compatible dictionaries. `BackupError` derives from `CairntirError`;
`BackupWarning` derives from `UserWarning`. A UTC-aware `utc_now()` clock seam
permits deterministic time in acceptance; no copy, lock or verification logic
is mocked. `DrawerStore(..., automatic_backups=False)` is an additive opt-in.
Production owner CLI/MCP store startup opts in; scoped and read-only startup do
not. Passing both `read_only=True` and `automatic_backups=True` remains pure.

Status exposes `enabled`, `destination`, `interval_hours`, `last_success_at`,
`next_due_at`, `last_error`, `in_progress` and `snapshots`. Snapshot records expose
`path`, `created_at`, `sha256`, `size_bytes`; paths name complete standalone SQLite
files. Empty success/due/error/destination values may be null. Run receipts have
`status`: `created`, `not_due`, `disabled`, or `busy`; a created receipt contains
`snapshot` with the same fields. Timestamps are ISO-8601 UTC strings. A checksum
receipt must also be persisted beside each published database. Storage layout
and lock/receipt filenames are otherwise implementation choices.

CLI commands are `cairntir backup configure DEST [--interval-hours HOURS]`,
`backup status`, `backup run`, and `backup disable`; successful output is JSON.
Commands use the configured Cairntir database. Status never creates missing
homes, databases, configuration, lock files, or backup files. Configure is
opt-in persistence, not an implicit snapshot. Disable retains existing recovery
points. Configuration/state is per source database; scratch and reindex paths
must not inherit another database's automatic policy. Invalid intervals
(nonfinite, nonpositive, boolean) and the database itself as destination raise
typed errors without changing existing configuration or evidence.
Changing the destination makes the new destination immediately due; a successful
snapshot at the old destination cannot satisfy the new destination's cadence.

A configured store is immediately due until its first success. Check before
writable startup returns and before the first outer write transaction at or
after `last_success_at + interval_hours`; nested writes do not trigger a second
copy. The pre-write snapshot contains only prior committed data. Due state
survives process restarts. Forced runs always create a new timestamped snapshot.
Only verified publication advances success/due time. A concurrent backup claim
returns `busy` promptly; a process crash releases ownership and a later run
recovers without treating incomplete files as snapshots. Individual operations
finish within 20 seconds, including contention. No periodic worker is required.

Snapshots preserve all source tables, rows, schema objects, provenance, access
state, workflow/task receipts, and physical vector tables without re-embedding.
They include committed WAL data and exclude an active writer's uncommitted
changes. Verification includes SQLite integrity and foreign-key checks. A
published file restores independently after all source connections disappear;
recovery never depends on adjacent copied WAL/SHM/journal files. Snapshot work
does not change source application state. Existing migration/reindex backup-first
safeguards remain mandatory regression gates.

An unavailable destination or verification failure raises `BackupError` for
explicit runs; automatic attempts emit visible `BackupWarning` and record
`status.last_error` while ordinary writes continue. Failed attempts cannot
advance successful cadence, publish a verified receipt, or trigger retention.
A later successful attempt clears the current error. Stderr warnings are
sufficient for CLI/MCP; existing budgeted response envelopes remain unchanged.

After publishing a new verified snapshot, retain every managed snapshot aged
at most seven days and the latest snapshot in each of the four newest older
ISO calendar weeks. Ownership is per source database. Manual baselines,
unrecognized files, other stores' snapshots, and snapshots whose recorded
checksum no longer matches must never be deleted by retention. Temporary
incomplete snapshots are excluded from status and cleaned on recovery without
deleting unrelated files. No source database is a retention candidate.

Tests use only temporary stores and destinations, real SQLite locks/WAL, real
subprocesses and real CLI/stdio MCP entry points. Only time and deterministic
embedding providers are substituted. The machine-specific authorized destination
is runtime configuration supplied by the coordinator, never a test path.

Run the complete new suite with:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/acceptance/test_automatic_backups.py --no-cov -q --tb=short
.\.venv\Scripts\python.exe -m pytest tests/unit/test_store.py --no-cov -q
.\.venv\Scripts\python.exe -m ruff check tests/acceptance/test_automatic_backups.py
.\.venv\Scripts\python.exe -m ruff format --check tests/acceptance/test_automatic_backups.py
```

Baseline and freeze receipts bind exact UTF-8 LF artifact bytes and preserve raw
failures. Missing implementation fails per case, never as collection failure or
skip. One initial implementation pass, at most two official repair rounds, and
at least 25% verification reserve. Independent verdicts are PASS, FAIL or
INCONCLUSIVE; milestone dispositions are COMPLETE, BLOCKED or EXHAUSTED.
