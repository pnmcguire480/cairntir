# Independent schema migration rehearsal

PASS: a private readonly snapshot migrated from schema 6 to 7. All 19 original tables retained their exact original row and schema hashes, including 1280 complete drawers with provenance/access fields, all physical vector tables, workflow receipts and existing metadata.

Only the documented portable identity metadata row and three new portable/procedure tables were added. Portable records cover every original drawer; both privileged procedure registries remain empty. The automatic pre-v7 backup matches the original snapshot exactly. SQLite integrity checks pass; embedding calls: **0**.

The live source was accessed only by a separate-process readonly snapshot helper. DrawerStore opened only the private copy. Existing live SHM bookkeeping is within the documented SQLite boundary. No source migration or reindex occurred. Public evidence contains counts and hashes only.

[Canonical evidence](continuity-migration-result.json) records all comparisons, source fingerprints and test provenance. JSON SHA-256: `5ad40f99b0bfb550b7eb99e996416d9630519d17e1c93b9cdd289b2ef56df320`.
