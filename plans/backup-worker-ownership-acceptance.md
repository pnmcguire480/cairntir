# Backup worker ownership supplement

Independent tester `/root/foundation_tester`. This is a new supplement to the
immutable automatic-backup and 1.12.0 release contracts. Release run 34152318223
failed before build/publication: an orphan worker removed a replacement attempt's
staging directory and its `pending.json` marker. A repeated green stress run does
not resolve this reproducible ownership defect.

The single deterministic regression uses public `backups.run` coordinators and
their actual worker subprocesses. Test-only `sitecustomize` wrappers pause the
original `_publish_snapshot` and `_prepare_snapshot` functions; they neither
replace backup/cleanup/locking behavior nor fabricate success. The old worker
pauses before snapshot publication begins, its coordinator is killed, and a new
coordinator starts. If the replacement reaches its initialized staging directory,
the old worker is resumed while the replacement remains paused. The replacement's
directory and exact marker bytes must survive; it must subsequently publish a
valid standalone snapshot preserving complete source state.

A repair may instead retain genuine worker ownership after coordinator death.
In that case the replacement must return the existing bounded `busy` receipt;
after the orphan exits, a bounded retry must publish successfully. The test does
not prescribe deleting, fencing or locking as the implementation strategy.
Manual baseline bytes and source application state remain unchanged. Every
barrier, process and retry is bounded, with unconditional barrier release and
owned-process cleanup. Existing unmanaged-file/retention/deadline coverage remains
in the original frozen suite and is not weakened or duplicated here.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/acceptance/test_backup_worker_ownership.py --no-cov -q --tb=short
```

Freeze this supplement and its failing baseline before runtime repair. Preserve
the original 29+39 acceptance, three prior supporting cases and all historical
release artifact hashes. A repaired source requires a new release-verification
generation; do not change the old verifier's expected hashes. At most two bounded
repair rounds and at least 25% verification reserve remain in force. No production
store, memory writes, package installation or publication actions occur here.
