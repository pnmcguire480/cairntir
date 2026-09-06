# Continuity support changes

The portable milestone migrates schema 6 to schema 7. The independent migration
fixture and all frozen foundation test inputs remain unchanged.

The unfrozen legacy migration test in `tests/unit/test_store.py` now locates its
backup using the imported `SCHEMA_VERSION`, matching its existing assertion on
the migrated database version. Its previous literal `pre-v6` filename was stale
for schema 7. It still requires exactly one backup; the runtime backup policy
is unchanged. No frozen manifest binds this test file.

The additive release candidate is 1.10.0, following the release policy's minor
version rule. `pyproject.toml`, `uv.lock`, the package version and plugin version
advance together. No dependency selection changes. Historical foundation
manifests retain their original 1.9.0 support-input hashes and recorded commits;
new milestone manifests record release configuration without freezing it.

The independent portable author recorded one separate harness correction in
[amendment 1](portable-v2-amendment1.json): supply the existing mandatory empty
Hotfix command payload before testing rejection of imported authority. The
original suite and freeze are archived byte for byte; acceptance assertions and
scope remain unchanged.
