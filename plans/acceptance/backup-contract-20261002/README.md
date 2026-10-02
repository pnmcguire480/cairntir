# Independent backup/diagnostic contract reconciliation

Decision: TEST PROBE AMENDMENT; no runtime repair or weakened backup requirement.

The original plan requires opt-in backup on writable store startup and before an outer write, and explicitly forbids backup side effects on read-only use. The frozen contract repeats production owner store startup opt-in and read-only/scoped exclusion. CLI `_open_store` still opts owner writable startup into backups; `get 1` still reaches that path. The approved diagnostic repair makes `status` a metadata-only read-only snapshot inspection. Restoring a status-triggered backup would violate that new diagnostic boundary and the original read-only exclusion.

The observed original CLI test failure is valid evidence of incompatible historical probe selection. Preserve it and the original freeze. Do not mark it expected, skip it, change its snapshot/state assertions, or disable a gate. The explicit adapter changes only the genuine command used by the exact original CLI startup case, from `_cli("status")` to `_cli("get", "1")`. The frozen test's complete snapshot count/state assertions execute unchanged. Its MCP parameter and every other test remain untouched. The original source therefore still visibly contains the historical status probe: this amendment documents the runtime test adapter rather than hiding that discrepancy.

The adapter is an autouse fixture, not a generic collection hook. It matches the exact node ID and source module, verifies the frozen original hash, and permits exactly one argument-free legacy status call. Unexpected calls or repeated/missing calls fail assertions. The wrapper validates original and adapter bytes at import. Thus a missing or changed historical source fails before execution; selecting unrelated tests remains supported without requiring the amended node to be selected. No global tool redirection, product special case, xfail, deselection, coverage exemption, or preservation-checker edit is authorized.

Two independent controls exercise actual synthetic CLI subprocesses and existing snapshot/backup code. Due configured backups must not make status alter any source/configuration/backup file bytes or mtimes; counts must still be visible. Real owner get must return drawer 1, produce exactly one checksum-verified standalone snapshot preserving complete preexisting state, leave source state unchanged, and preserve cadence on repeat. These detect both a return to mutating status and a blanket removal of owner startup backup activation. Existing outer-write, read-only, scope, MCP, race, retention and crash controls remain unchanged.

## Integration map

- Copy this packet's frozen evidence under `plans/acceptance/backup-contract-20261002/`, preserving bytes and hashes.
- Copy `acceptance_conftest.py` exactly to the previously absent `tests/acceptance/conftest.py`.
- Copy `acceptance_test_wrapper.py` exactly to `tests/acceptance/test_backup_contract_amendment.py`.
- Preserve `tests/acceptance/test_automatic_backups.py`, its original manifests and preservation checker exactly. The archival original here is byte-identical.
- Keep original failure evidence and the new run receipt separate. If formatting changes a wrapper, record a separately reviewed amendment rather than silently altering frozen bytes.

## Bounded validation plan

Run serially in the existing isolated synthetic environment, no installs, downloads, model inference or private stores. Set TYPER_USE_RICH=0 plus the existing autoregister/update disable and offline flags. Use existing Hash32 provider substitution and actual subprocess helper. Run the amended original `[cli]` case and the two new controls with `--no-cov`; retain original `[mcp]` and the complete unchanged suite in hosted CI. A bounded targeted readonly/scoped/outer-write regression group is appropriate if thermal budget permits. The existing preservation gate must still pass unmodified.

Known baseline: required CI at head `6e9590ac12dcce4216bf0c2499f4c2f9e08049fd`, run 36957564392, failed the original `[cli]` startup assertion because snapshot count was zero. The coordinator's serial reproduction records one corresponding failure in 2.453 seconds with no collection/infrastructure error (`baseline-backup-check.json` and `.log`). The new controls and adapter are frozen before execution; this reviewer ran no tests or product code.
