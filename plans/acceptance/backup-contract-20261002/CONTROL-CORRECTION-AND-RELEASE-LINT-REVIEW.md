# Independent control correction and release lint-scope review

Reviewed 2026-10-02, static only. No candidate files, original frozen artifacts, runtime or tests were executed/changed by this reviewer.

## Backup control correction

The coordinator's first bounded run reported two passes (the unchanged original CLI case through its explicit amended probe, and the new due-status purity case) and one failure in the newly authored owner-get control, at `assert legacy._state(db) == before`. Its full snapshot fidelity assertions had already passed.

This assertion was an independent-test authoring error, not a product defect. `DrawerStore.get` at src/cairntir/memory/store.py:1665 explicitly documents access_count and last_accessed_at updates and invokes `_touch` after a successful read. The backup governing plan requires a snapshot of prior committed state on writable startup, while the original frozen startup test compares that snapshot against pre-startup complete state. It does not require the subsequent ordinary writable operation to leave source metadata untouched.

The additive v2 control deletes exactly that one invalid new assertion. Every other control byte remains unchanged, including full snapshot state equality, checksum/standalone verification, exactly one snapshot, actual get result and repeat-get cadence. The status test retains whole-tree bytes/mtime and policy equality. The original test, adapter, conftest and all historical assertions remain byte-identical. `CONTROL-CORRECTION-V2.json` pins the corrected control and wrapper; the latter changes only control filename and hash. Original v1 artifacts and failed outcome remain evidence. This amendment supersedes only the v1 README's assertion that owner get itself leaves source state unchanged. It does not weaken the separate read-only status guarantee.

## Release lint-scope reconciliation

The release workflow currently runs `uv run ruff check .` and `uv run ruff format --check .`. Existing CI and CONTRIBUTING both use `src tests scripts addons`. The wider release commands also traverse preserved Python acceptance artifacts under plans, whose exact bytes are separately bound and executed through normal pytest wrappers. The coordinator reports that this real broader invocation produces 393 findings in those preserved artifacts; this reviewer verified the command mismatch statically, not by rerunning lint.

Recommendation: change only those two release workflow command arguments to `src tests scripts addons`, matching current CI and canonical contributor checks. This keeps all active application code, test wrappers, scripts and addons in the same strict lint/format scope already required by CI. Do not add global Ruff ignores/exclusions, rewrite frozen evidence for style, alter hashes, change pytest collection or coverage, or relax the preservation gate. Frozen controls must continue executing through their reviewed wrappers, with their original bytes and hash assertions intact.

This is a justified narrow reconciliation of existing release/CI scope, not authorization to skip a failed substantive test or lower runtime verification. Full required CI and the release workflow still need to pass on the resulting exact head. No new host, performance, pilot or architectural gate is introduced.
