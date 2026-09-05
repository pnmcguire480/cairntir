# Shipping-hardening audit — 2026-09-05

Baseline: `ff25ea3` on `main`, after the published 1.9.0 release. This record
describes unreleased hardening, not a new package publication.

## Reproduced defects closed

| Boundary | Defect | Repair |
|---|---|---|
| Portable export | Interrupted streams truncated an existing backup | Same-directory temporary file, flush/fsync, atomic replacement, cleanup |
| Portable import | External data received user-asserted trust | Explicit untrusted write provenance |
| Imported relationships | Source-local ids could bind unrelated destination history | Reject unresolvable v1 supersession, evidence metadata, nested hotfix references, and local drawer URIs |
| Input validation | Malformed text/signatures escaped typed errors; import bypassed URL restrictions | Validate both directions, including escaped lone Unicode surrogates |
| Capture spool | Null/array/numeric fields became invented strings or blocked later captures | Reject invalid types and quarantine malformed Unicode before embedding |
| Obsidian | Output junctions escaped the vault; duplicate markers erased user text | Enforce resolved output containment and exactly one generated marker pair |
| Obsidian links | Shared evidence and ids such as 1/10 corrupted receipt links | Single-pass, exact-id replacement |

## Repository cleanup

Removed 42 obsolete files: closed execution plans, session narratives,
speculative product collateral, promotional drafts, duplicate setup material,
a placeholder example, and the unused Jekyll configuration. Git history retains
them at the baseline commit. No file under `lineage/` was changed.

All 157 executable commitments remain checked. The old front-door plan's
self-existence assertion now names the consolidated commitment registry;
runtime and regression-test assertions are unchanged. Release evidence and
legal attribution remain in the tree.

The shared agent brief is concise and describes the actual installed-package
development boundary. Documentation distinguishes implemented behavior from
experiments and documents recovery consent, trust, backup, and interchange limits.

## Dependency findings

PyPI reported active advisories for 14 of 134 locked registry packages:
Click, cryptography, idna, MCP, MkDocs Material, pydantic-settings, PyJWT,
PyMdown Extensions, python-multipart, setuptools, Starlette, PyTorch,
Transformers, and urllib3. The affected entries and required transitive versions
were updated. No direct dependency was added. MCP remains on patched 1.x APIs.

The resulting lock reports **zero active PyPI advisories or yanked releases**.
`scripts/check_dependency_advisories.py` now enforces that check in CI and
release verification, failing closed on an unavailable or malformed feed.
This checks known advisories for the lock, not exploitability or every possible
consumer environment. Package installation does not automatically enforce the
repository lockfile.

## Verification

- Complete local suite: **826 passed**, including all five model-backed evals;
  **85.04%** coverage of the configured surface.
- Independent frozen acceptance: **20/20 passed**, plus four supplementary
  escaped-surrogate checks and the shared-evidence link regression.
- Frozen artifact: `tests/unit/test_shipping_hardening.py`, SHA-256
  `d8d556ba94c0e893a49a76440f7c64d3d82c66f4f17c6a19dbe881c3796708fd`.
  Baseline: 19 failed, 1 passed. The coder did not modify this artifact.
- Ruff lint/format, strict mypy (54 source files), pre-commit, local store-health
  gate, 157 commitments, nine seams, local documentation links, and strict
  MkDocs build passed.
- Wheel rebuilt from the source distribution. Source package excludes host
  configuration and the historical lineage archive.
- Fresh isolated install with locked runtime dependencies: no broken package
  requirements; three skills and five recipes load; a stored request returns
  verbatim; a real stdio initialize/list-tools exchange reports the package
  version and all 21 tools. The model cache was initialized first, as setup
  normally does. No production installation or memory store was changed by
  these tests.

## Remaining boundaries

Native Dependabot alerts are disabled in repository settings. The new CI gate
does not enable continuous GitHub alerts. Existing CodeQL maintenance notes
(protocol stubs, import cycles, context-manager style) and deliberate exception
tests were inspected without a reproduced runtime/security failure; they were
not dismissed or hidden.

Cursor transcript recovery remains unsupported. Portable v1 cannot round-trip
linked history; use a database backup. Release publication requires explicit
maintainer authority. The protected pull request's checks are the authoritative
cross-platform delivery evidence; this local audit is not a release attestation.
