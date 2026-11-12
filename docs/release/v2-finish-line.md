# November 6 release finish line

Scope frozen on 2026-10-30 from ALPHA.md and docs/alpha-roadmap.json.
The 23 completed component commitments stay complete. E22 was the one
open November commitment and is now complete (see the table row below); the 11 dated follow-ups remain assigned to their
existing dates. They are not new prerequisites for November 6.
Q08, one of those follow-ups, is complete as of 11 November 2026: an
independently written test, frozen by hash, fails against known-bad behavior
and passes against the fix, and a packet with no executed case is reported
`NOT_EXECUTED` (see ALPHA.md).

Decision, 4 November 2026: the maintainer set an 85% floor for alpha releases, in their words "lets make it 85% for release and we can go back on another date and kill tokens getting to 90% another day." 90% stays owed and remains the stable 2.0 target; this table's requirement is unchanged and earlier failures stay failures.

Decision, 9 November 2026: the maintainer chose to publish this work now as 1.13.0, under an 87% floor, in their words "87% is all we need, thats my compromise, ill go back at another date and 90% everything after." 2.0.0 stays reserved for the finished roadmap. See the [1.13.0 record](v1.13.0.md). This table's 90% requirement is unchanged and earlier failures stay failures.

No merge, tag, PyPI publication or production adoption without final approval.
Preserve failures and the 90% overall coverage floor. No percentage-only tests.
Two repairs without measured progress or three unsuccessful rounds require a
different approach; non-blocking improvements stay on the follow-up roadmap.

| Agreed requirement | Current working evidence | Remaining work | Acceptance / blocker |
| --- | --- | --- | --- |
| Combined source suite and 90% coverage | Complete 5fe8945a matrix: all nine assertion suites pass, Windows 2,707 each and POSIX 2,705/two skips. Coverage 85.528949–86.506810%. Lint/types/docs, CodeQL and three OS mutation jobs pass. | Measure published 5015aa9d; meaningful behavioral coverage of measured missing paths; fix actual failures only. | Same full matrix reaches 90%; current complete matrix FAIL on coverage alone. |
| Actual PALADIN Python workflow | Local three original scenarios/five deliberate-defect subtests PASS; portable preparation and original cases pass on all nine hosted jobs at 5fe8945a. Original failure retained. | None for this exercised workflow. | Clean five-stage workflow, rejected broken implementations and preserved repair evidence pass; 95% subject floor, 60-second stages and 1 MiB output limits unchanged. |
| Promised memory workflows | Component evidence exists for origin/currentness, Obsidian corrections, managed acknowledgement/resume, practices, calendar and Blender. R06 and other completed commitments remain closed. | Reuse valid receipts; demonstrate release candidate through documented workflows where integrated evidence is missing. | Exact candidate end-to-end evidence; no claim of automatic text-based supersession or cross-store SQLite sync. |
| E22 second supported machine | COMPLETE, 10 November 2026. Home baseline receipt (sha256 30651673…d07) and work-PC receipt (sha256 45dbab53…045, 18 of 18 checks) show the same five model-file hashes and identity `fastembed/text-embedding-v2/sha256=ec062705…5372`, different machine fingerprints. The work PC refused a one-byte model change (search and write refused, raw read exact, count unchanged). On 1.13.0 code the mismatch tests pass and a deliberate break fails three of them. The same work PC then re-ran all 18 checks on the 1.13.0 release commit 3b02538f (receipt sha256 660c5fb2…854, 10 November 2026): overall PASS, same five file hashes and identity, one-byte change refused. | None. | Original criterion met: "Two supported machines verify the same bytes; a mismatch is refused or requires explicit migration, never silently reused." The work PC belongs to Lou; receipts claim only a different physical machine. |
| Protected independent evaluator | Public regression/mutation checks pass; protected custody remains unqualified. | Use independently controlled evaluation environment. | Builder cannot access private tests; administrator-controlled local account alone is insufficient. |
| Installed package, upgrade, restore and rollback | Local Windows wheel passes CLI/MCP, cold resume, all-table backup/restore, semantic recall and failed-write rollback/retry. Composite retained evidence verifies actual 1.12.4 upgrade/reindex to schema8 and backup restoration under1.12.4. Three runner failures and the fixture-encoding limitation remain visible. | Obtain remaining hosted platform evidence after the coverage gate. | Exact seeded fields, identities and semantic recall verified before/after; no production-store experiments. |
| Public alpha | GitHub pre-release `alpha-2.0.0a1` carries the wheel and states that the coverage gate fails. It is not on PyPI and is not merged to main. | Ship remaining features in batches of 2-4 as later alphas. | Each alpha names its commit, wheel hash and failing gates. |
| Reviewed delivery | Draft PR140, 41 curated commits/393 paths at 5015aa9d. | Include only qualified changes, current evidence and usable delivery instructions; identify exact candidate commit/artifacts. | Final review and explicit merge/publication approval; not yet release-ready. |

## Existing local work

- paladin_python_real_unit: three original scenarios and five defect subtests
  pass after import-path repair; prepared inputs unchanged. Focused outer
  application coverage remains FAIL at 14.119872%; it is not a combined result.
- managed_cli_unit: 15 original CLI behavior cases PASS in 20.54 seconds,
  including real SQLite request preservation and EOF/close behavior.
- humanflow_unit: 25 original cases PASS in 85.64 seconds, covering existing
  narration/evidence/publication boundaries. R12 feature delivery stays November
  12; these checks cover code already included in the global coverage surface.

Portable seven-tool preparation succeeds locally and on all nine hosted jobs.
Its original copy/digest/runtime guards remain; all nine full assertion suites pass.
Focused outer coverage fails remain visible (Python 14.119872%, managed CLI
10.493706%, HumanFlow 15.268186%); none is a combined application result.

Current CI: run 41155243753 at 5fe8945a. The previous complete matrix,
41002352488 at 81ed7897, passed all assertions and failed coverage alone.
The older calibration and timing failures retain their original status in
v2-alpha-ci.md; newer results do not rewrite them.
