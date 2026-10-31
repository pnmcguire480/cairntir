# November 6 release finish line

Scope frozen on 2026-10-30 from ALPHA.md and docs/alpha-roadmap.json.
The 23 completed component commitments stay complete. E22 remains the one
open November commitment; the 11 dated follow-ups remain assigned to their
existing dates. They are not new prerequisites for November 6.

No merge, tag, PyPI publication or production adoption without final approval.
Preserve failures and the 90% overall coverage floor. No percentage-only tests.
Two repairs without measured progress or three unsuccessful rounds require a
different approach; non-blocking improvements stay on the follow-up roadmap.

| Agreed requirement | Current working evidence | Remaining work | Acceptance / blocker |
| --- | --- | --- | --- |
| Combined source suite and 90% coverage | PR140 head 81ed7897: all nine assertion suites pass; Windows 2,664 passes, POSIX 2,662 passes/two skips. Coverage 84.131543–85.109404%. Lint/types/docs, CodeQL and three OS mutation jobs pass. | Meaningful behavioral coverage of measured missing paths; fix actual failures only. | Same full matrix reaches 90%; currently FAIL on coverage alone. |
| Actual PALADIN Python workflow | Windows import-path repair: three original scenarios and five deliberate-defect subtests PASS in 539.04 seconds; input preservation PASS. Original failure retained. | Qualify portable preparation and hosted execution. | Clean five-stage workflow, rejected broken implementations and preserved repair evidence pass locally; 95% subject floor, 60-second stages and 1 MiB output limits unchanged. |
| Promised memory workflows | Component evidence exists for origin/currentness, Obsidian corrections, managed acknowledgement/resume, practices, calendar and Blender. R06 and other completed commitments remain closed. | Reuse valid receipts; demonstrate release candidate through documented workflows where integrated evidence is missing. | Exact candidate end-to-end evidence; no claim of automatic text-based supersession or cross-store SQLite sync. |
| E22 second supported machine | Artifact identity implementation exists; roadmap still OPEN. | Verify exact model bytes and supported workflow on a second supported machine. | Real second-machine receipt; access/setup is an external dependency. |
| Protected independent evaluator | Public regression/mutation checks pass; protected custody remains unqualified. | Use independently controlled evaluation environment. | Builder cannot access private tests; administrator-controlled local account alone is insufficient. |
| Installed package, upgrade, restore and rollback | Packaging smoke exists; hosted installed/eval jobs skipped behind source coverage. | Complete disposable installed candidate and migration/backup/restore/rollback workflows. | Original data and supported version behavior verified before/after; no production-store experiments. |
| Reviewed delivery | Draft PR140, 37 curated commits/358 paths at 81ed7897. | Include only qualified changes, current evidence and usable delivery instructions; identify exact candidate commit/artifacts. | Final review and explicit merge/publication approval; not yet release-ready. |

## Existing local work

- paladin_python_real_unit: three original scenarios and five defect subtests
  pass after import-path repair; prepared inputs unchanged. Focused outer
  application coverage remains FAIL at 14.119872%; it is not a combined result.
- managed_cli_unit: 15 original CLI behavior cases PASS in 20.54 seconds,
  including real SQLite request preservation and EOF/close behavior.
- humanflow_unit: 25 original cases PASS in 85.64 seconds, covering existing
  narration/evidence/publication boundaries. R12 feature delivery stays November
  12; these checks cover code already included in the global coverage surface.

Portable seven-tool preparation succeeds in a fresh local directory. Its
original copy/digest/runtime guards remain; hosted execution is still pending.
Focused outer coverage fails remain visible (Python 14.119872%, managed CLI
10.493706%, HumanFlow 15.268186%); none is a combined application result.

Full current CI: run 41002352488. No assertion failures remain on published
81ed7897. The older calibration and timing failures retain their original status
in v2-alpha-ci.md; this result does not rewrite them.
