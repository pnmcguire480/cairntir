# R18 and managed-session integration candidate — 2026-10-10

This local candidate combines PR131 head `1acec03793a5c5c2975cc389fd18c92f06e45d4b`
with PR130 head `1c628966321d3c94abd7dd5fd1704ccd226f51e8`, both descending from
PR128 head `9e65c37c9a734f88d54935933047bda598e03146`. It is an integration
review artifact, not a release or installed-host qualification.

The only merge conflicts were the two pull-request target lists in
`.github/workflows/ci.yml` and `.github/workflows/codeql.yml`. The PR131 lists
already contained every PR130 target plus the later question branch, so the
superset was retained. The later draft integration PR adds its PR131 base branch
to both trigger lists so that hosted CI and CodeQL can run on this stacked
candidate. `src/cairntir/access.py` merged automatically; its
complete-wing authorization addition coexists with the managed and question
visibility methods. PR130's `src/cairntir/procedures.py` bytes were retained
unchanged in this candidate (SHA256
`e20d3dfcbffa56fae4eaeccf922c982ef50ff37011c38b37f74c1b8938855fd7`).

Local verification with Python 3.11.9 and the repository development environment:

- R18 frozen, scope, and red-team archive wrappers: 172 passed.
- Adjacent procedure, managed runtime/hardening, and question wrappers: 162
  passed, 3 skipped, 51 subtests passed, 1 failed.
- `ruff check` and `ruff format --check` on the six changed Python files: pass.
- `mypy --strict src`: pass for 65 source files.
- `git diff --check HEAD`: pass.
- Full local `pytest -m 'not slow' -q --no-cov`: 2,356 passed, 9 skipped,
  8 deselected, 11 failed, 150 subtests passed in 480 seconds. Six doctor
  failures stop at a `PermissionError` while probing host configuration in
  this restricted Windows process. Three verification failures stop when
  `taskkill /T /F` receives `Access denied` for fixture-owned child processes.
  The release-tag check fails closed because this process cannot reach PyPI
  (`WinError 10013`). The remaining failure is the installed-proof source pin
  below. These are unqualified gates, not passes or observed product behavior.

Draft PR132's first hosted head `d78eba5` reached lint, type and docs checks,
then the unchanged dependency advisory gate reported one finding:
`fsspec==2026.3.0` / `GHSA-27vj-qcqg-25rc`; downstream jobs were skipped.
The lock now changes only `fsspec` to advisory-patched `2026.6.0`. Offline lock
consistency passed, and the unchanged advisory script checked 134 locked
registry packages with zero findings. Hosted checks on the refreshed head are
still required; the first run is preserved as a failed result.

The sole adjacent failure is
`test_installed_identity_rejects_wrong_binding_before_case_import[none]`.
Its historical installed-proof capsule pins `src/cairntir/access.py` to SHA256
`5553a29df68c6e77701654fb5f75c943f95a7decc01d24da4526082ff29d81ad`.
PR130 legitimately changes that file, so the positive fixture fails its
identity assertion before case import. This is an expected historical binding
failure on the combined source, not evidence that the new runtime behavior was
executed or verified. The frozen capsule and assertion remain unchanged. A
separately authored and frozen combined-head installed qualification is needed.

PR130's README names `f3797a36...` as its final procedures source digest,
while the fetched PR130 head and this candidate contain SHA256
`e20d3dfcbffa56fae4eaeccf922c982ef50ff37011c38b37f74c1b8938855fd7`
after its later `1c62896` repair. The earlier digest matches `011aa6f`.
That repair also adds 22 lines to `src/cairntir/access.py`, outside the README's
stated procedures-only runtime ownership. All 20 hosted PR130 checks, including
its source matrix, package builds, mutation evidence and CodeQL, completed
successfully at the exact `1c62896` head. Those checks do not amend the older
ownership statement or independently qualify the combined head. Parent review
should reconcile the scope and source binding before promotion.

The installed Obsidian app has a `obsidian-1.13.7.asar` and the registered
`Cairntir Coding Brain` vault contains the older `cairntir-vault-refresh`
plugin, not the draft `cairntir-workspace` plugin. No v2 plugin was installed
or activated in that real vault during this review.

Open gates: independent combined-head acceptance, native installed-host proof,
Ubuntu protected evaluator custody, and an explicit maintainer merge/release
decision. The existing 35-commitment v2 plan remains larger than this integration.
