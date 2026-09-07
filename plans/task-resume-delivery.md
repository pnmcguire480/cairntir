# Interrupted task resumption delivery

The implementation satisfies the [frozen task contract](task-resume.md).
[Issue #92](https://github.com/pnmcguire480/cairntir/issues/92) tracks landing.
The feature remains unreleased; production installation stays on 1.10.0.

## Implemented behavior

The existing remember tool accepts durable checkpoints. The existing handoff
tool resumes by task ID or unambiguous wing without a new request brief. The
CLI exposes the same operations. Original requests remain verbatim; complete
progress revisions append atomically with idempotency and stale-write checks.
Completed/cancelled tasks stay terminal. Scoped reads withhold incomplete chains,
and imported metadata cannot activate a task. No schema bump or dependency.

Generated host instructions use checkpoints when the connected server advertises
them, retaining ordinary memory behavior with older servers. The hotfix schema
now supplies the required object root and passes actual Claude Code validation.

## Evidence

- [Independent final acceptance](task-resume-acceptance-final.json): 70 PASS,
  with exact frozen and runtime hashes. The original 66 cases were frozen red
  before runtime implementation; two transaction and two budget probes are
  separately identified supplements.
- Real stdio tests kill the originating server after an acknowledged write and
  start a distinct host process. The receiving connection supplies only wing and
  task ID. Concurrent MCP writers, read-only CLI/MCP parity, rejected-write
  rollback, terminal discovery, access revocation and whole-response budgets pass.
- Full local regression: 1,056 PASS, 8 slow deselected; 83.62% branch-inclusive
  coverage. All seven registered model evaluations PASS separately with cached
  models and an isolated synthetic corpus.
- Ruff, format, strict mypy, documentation build/links, commitments, seams,
  silent-exception scan, release-tag gate, dependency advisories and package build
  pass. The advisory scan checked 134 locked packages with zero findings.
- [Actual Claude health](task-resume-host-health.json): Claude Code 2.1.197
  accepts the isolated development server and all 21 object-root schemas.
  Production settings remain unchanged; no model prompts or downloads.

The exact-budget retry bug found in development was fixed before independent
acceptance. Supplemental harness defects (a reserved pytest parameter and a
Windows environment-variable limit caused by a generated test ID) were corrected
without changing inputs or assertions. Original sources/manifests and the
inconclusive run remain archived; the original 66 tests were never edited.
See [budget supplement history](task-resume-acceptance-budget.md).

The first broad local run was blocked by sandbox access to host settings/PyPI
and the supplemental harness setup. The complete suite passed after the documented
harness correction and rerun with required host-read/network permissions.

## Limits

These results establish durable acknowledged checkpoints and transport continuity.
They do not establish automatic conversation capture, autonomous model task
success, actual token savings, remote synchronization, or publication of 2.0.
Unsaved work still depends on the originating host. Stored approvals remain
historical evidence, not current execution authority.
