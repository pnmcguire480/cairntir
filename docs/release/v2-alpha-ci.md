# Alpha CI evidence — 29 October 2026

This records actual results for draft [PR140](https://github.com/pnmcguire480/cairntir/pull/140). It does not approve stable release or production adoption.

| Run / head | Result |
| --- | --- |
| [Initial CI](https://github.com/pnmcguire480/cairntir/actions/runs/40827340947), `09175f6b` | FAIL: 17 Windows-only API type errors on Linux. |
| [First complete matrix](https://github.com/pnmcguire480/cairntir/actions/runs/40828934684), `2427101b` | Lint and CodeQL passed. Test samples: 27–29 failures, 1,753–1,755 passes; 37.98–38.05% coverage against the then-92% override. All three mutation jobs rejected a stale omitted-memory fault at an unrelated foreign-key guard. |
| [Second complete matrix](https://github.com/pnmcguire480/cairntir/actions/runs/40834698849), `744ff9f8` | Lint, CodeQL and all three OS regression/mutation jobs passed. All nine test jobs: 1,941–1,942 passes, no failed assertions, two backup fixture setup errors; 44.32–44.41% coverage against 90%, FAIL. Installed-package and evaluation checks remained blocked downstream. |
| [Documentation follow-up](https://github.com/pnmcguire480/cairntir/actions/runs/40966490355), `572124df` | Ruff, formatting, types and CodeQL passed. Strict documentation failed on two repository evidence links outside the site; subsequent checks were skipped. The links were corrected to repository URLs and the strict local build passed. |
| [Restored-test matrix](https://github.com/pnmcguire480/cairntir/actions/runs/40966952683), `72bd8c0e` | Lint, CodeQL and all three OS regression/mutation jobs passed. Six Linux/macOS jobs each had 25 failures, 2,067 passes and two skips; coverage 59.224586% against 90%, FAIL. The new PALADIN fixture recorded a virtual-environment alias while binding the resolved executable. All three Windows jobs passed 2,088 tests with no assertion failures and 62.410821% coverage; the 90% gate still failed. Installed-package/evaluation jobs remained blocked downstream. |

Historical failures retain their original criteria. The approved prospective floor is 90%; aligning the stale CI override does not turn either measured coverage failure into a pass. No coverage surface or exclusions changed.

The real scoped-handoff timeout came from repeatedly starting an authority subprocess. The repaired scoped reader reuses an isolated helper, taking a fresh WAL-aware authority snapshot for every lookup. Seven independently authored security/lifecycle tests and the two original CLI cases passed locally under unchanged deadlines. All three hosted mutation/regression jobs then passed.

Five versioned v2 test contracts preserve their original public source under [the exact amendment](https://github.com/pnmcguire480/cairntir/blob/codex/v2-alpha-preview/plans/acceptance/alpha-ci-contracts-20261029/AMENDMENT.json). Its metadata and each original/successor hash are checked; council preservation and coverage scope remain enforced. The remaining backup setup errors came from the separate historical control collector expecting the old fixture hash. The ordinary collector now validates that exact amendment before loading successor helpers; both original independent control functions remain unchanged.

Focused verification of that collector and restored practice conflict/lifecycle cases: **25 passed**. Restored PALADIN controlled Python and synthetic UI cases: **35 passed, 12 subtests passed**. These test state, integrity, replay, cancellation and refusal behavior; controlled stage reports and synthetic images do not establish actual static-tool efficacy or live-browser/visual qualification. Existing Windows-only containment boundaries remain explicit.

The managed/question/recall/angle batch initially passed 84 cases and 120 subtests, with one symlink capability skip and one failure: a historical recall test expected a 105,000-character query to succeed despite the existing 6,000-character input limit. The updated case checks a 5,600-character query against the complete 1,024-character response ceiling, then separately requires the original oversized query to be refused. Its targeted rerun passed one case and six subtests. The original failure and the intermediate oversized-query failure remain retained. Across the new focused groups: **145 unique cases passed, one capability skip, 138 passing subtests**; this is not a full-suite result.

Further restored contract/artifact/lifecycle controls pass **30 cases and 40 subtests**; iteration-artifact/human-review controls pass **26 cases**. Nine additional controlled Codex wire cases pass with byte-identical pinned helpers; this proves fake-peer wire behavior, not actual-host acknowledgement. Total focused verification across these groups is **210 unique passing cases, one capability skip and 178 passing subtests**. The full hosted gate is measured separately.

Portable test source is included as ordinary tests, with [source hashes and explicit adaptations](https://github.com/pnmcguire480/cairntir/blob/codex/v2-alpha-preview/plans/acceptance/alpha-portable-tests-20261029/SOURCES.json). Private qualification manifests, historical project records, machine configuration, raw local receipts and archived controls remain excluded. Existing feature tests are being restored to normal collection; their presence alone does not establish 90% overall coverage.

The POSIX fixture mismatch is corrected by observing, recording, binding and hashing the same resolved Python executable. The runtime identity guard is unchanged. All 68 cases sharing the corrected fixture pass locally, including 52 subtests; this rerun is not counted as additional unique cases. Fresh POSIX CI remains required.

The patched dependency lock passed the unchanged advisory checker: zero findings across 134 registry packages, down from the preserved 82 findings. Default-branch alerts remain separate until reviewed changes land.

Full coverage, installed upgrade/restore/rollback, protected evaluator custody and second supported-machine readiness remain open. The [35-item roadmap](../alpha-roadmap.json) and dated follow-ups remain assigned. No merge, tag, PyPI release or production installation has occurred.
