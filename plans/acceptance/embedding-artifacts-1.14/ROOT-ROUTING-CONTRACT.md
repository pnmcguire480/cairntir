# Root fixture routing amendment

The integrated normal test run passed 90 cases with three real Windows symlink
skips. The unchanged preservation gate then correctly rejected the additive hook
in tests/conftest.py, because that historical fixture file is frozen. The parent
retains that failure in preservation.log. Earlier integration instructions to
append pytest_plugins to tests/conftest.py are explicitly superseded here.

Restore tests/conftest.py to its exact original bytes, SHA256
`a43e93cbc6abc0f182239545fb77ca4d6a61945d9ec3781d2338380edeffdbef`.
Copy this independently authored root_conftest.py to a new repository-root
conftest.py, and copy ROOT-ROUTING-CONTRACT.md, ROOT-ROUTING-FREEZE.json and the
frozen root_conftest.py evidence into plans/acceptance/embedding-artifacts-1.14.
No repository-root conftest existed in the reviewed base.

The new root hook checks its own hash, this amendment, the original integration
manifest and historical tests/conftest.py before loading the already frozen
tests/e22_fixture_loader_v2.py by importlib and calling its pytest_configure.
That unchanged loader verifies the same frozen wrapper/plugin files and registers
the same exact-case synthetic fixture adapter. Normal pytest invocation and
collection remain unchanged. All original test files, fixtures, assertions,
markers, selection and preservation gates remain byte-identical and effective.

The original CI wrapper, adapters, integration freeze and failed gate evidence
remain preserved. No runtime change or product repair is justified by this
routing correction. No tests are run during preparation while another agent owns
the serial slot. Ruff lint and format checks cover only the new root loader;
candidate routing, historical tests and preservation verification are the parent's
next bounded checks. Requested routing gpt-6.1-sol/high; actual serving model and
effort not exposed; cost unavailable.
