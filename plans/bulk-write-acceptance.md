# Bulk-write performance and integrity acceptance

Independent tester `/root/foundation_tester`; root implements. A measured
4,000-add profile found repeated full-vector counts consuming 40.3% of runtime;
the unchanged 100,003-record portable acceptance was still running after about
15 minutes before this optimization. That original slow test stays unchanged.

Six real-store cases in `tests/unit/test_bulk_write_boundaries.py` require:

1. Fifty public `add` calls inside one public `transaction` perform between one
   and three full-vector COUNT statements, observed through SQLite trace.
2. Public `embedding_status` immediately reports injected vector corruption;
   the next add fails with a typed error and adds no partial drawer/vector.
3. Changing persisted embedding identity between additions causes typed failure.
4. A schema change causes a fresh integrity recount before the next valid add.
5. Rollback/new transactions and an external writer invalidate prior verification.
6. Cached verification cannot bypass validation of each returned vector length.

Only verified results following known paired writes may be reused within an
outer transaction. Any intervening data/schema/provider change invalidates
reuse. Doctor/public integrity status remains a fresh complete inspection.
Tests prescribe no private cache layout and mock no runtime functions. Private
connection access is limited to real SQLite tracing and explicit corruption,
schema and external-writer fixtures. All stores are temporary Hash32 stores.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_bulk_write_boundaries.py --no-cov -q --tb=short
.\.venv\Scripts\python.exe -m ruff check tests/unit/test_bulk_write_boundaries.py
.\.venv\Scripts\python.exe -m ruff format --check tests/unit/test_bulk_write_boundaries.py
```

Baseline and freeze JSON record source fingerprints, counts and exact artifact
hashes. Existing frozen artifacts remain immutable. This six-case optimization
gate augments the complete 100,003-record portable test and existing integrity
regressions; it cannot substitute for them. No runtime or dependency edits are
authorized to the tester. All new evidence uses LF. At most two repair rounds;
the final quarter remains reserved for verification.
