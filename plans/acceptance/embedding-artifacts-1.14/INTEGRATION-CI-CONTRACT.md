# Normal-CI loader formatting and frozen 35-case wrapper

This separately frozen amendment preserves INTEGRATION-ADAPTER-FREEZE.json and
its original loader. The new e22_fixture_loader_v2.py is formatted for the normal
tests lint scope and verifies INTEGRATION-CI-FREEZE.json, including the new pytest
wrapper. The exact original fixture adapter remains byte-identical v2. Late
plugin registration supplies default=None for its optional report argument; the
pytest Config._processopt implementation supplies that default, and normal CI
requires no special argument or alternate test filter.

Copy e22_fixture_loader_v2.py into tests/, copy
test_embedding_artifact_acceptance.py into tests/unit/, and copy this manifest,
the frozen plugin and referenced explanatory artifacts into
plans/acceptance/embedding-artifacts-1.14. Append only
`pytest_plugins = ("e22_fixture_loader_v2",)` to root tests/conftest.py after its
byte-identical original prefix. The older loader/integration freeze are preserved
as evidence and are not loaded. No original outcome/assertion file changes.

The wrapper verifies every FIXTURE-V3-FREEZE.json file hash before loading the
original 25 cases, the two explicitly selected relative-cache cases and the eight
explicit supplementary cases. It uses distinct import names and temporarily
binds the supplement's base-module dependency, restoring the previous module
binding immediately. Both base SOURCE_ROOT variables refer to the normal test
checkout. It does not collect inherited tests from the relative or supplementary
classes, so exactly 35 parameterized pytest cases execute once each. unittest
failures, subtest failures and cleanup errors become pytest failures; actual
platform skips become pytest skips. There is no unconditional acceptance bypass,
source exclusion, copied assertion rewrite, or special normal-CI invocation.

No pytest/model tests were run while another agent owned the serial slot. Only
syntax/count static checks and Ruff check/format verification of the new loader
and wrapper are authorized during this preparation. Runtime candidate evidence
remains the parent's 35-case subprocess result (32 passed/3 Windows privilege
skips). Candidate integrated execution and Linux symlink evidence remain pending.
Independent review reserve remains untouched by this fixture integration work.
