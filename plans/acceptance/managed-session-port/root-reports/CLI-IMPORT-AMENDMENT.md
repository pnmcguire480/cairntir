# Bounded port-integration correction

The two independently frozen runtime/projection behavioral repair rounds are
used. A subsequent retained-integration check found a separate mechanical port
omission: the copied historical managed CLI signature references `Annotated`,
but the port script did not copy that symbol from the historical typing import.
Ruff F821 and the unchanged frozen R08 CLI callback test independently reproduce
the error. The retained run is 47 PASS, 1 FAIL and 51 passing subtests; this is
a real CLI regression, not a fixture failure or full candidate PASS.

This explicit finite follow-up restores only `Annotated` to the existing
`from typing import Any, cast` statement, matching the historical CLI's import.
It adds no feature and changes no runtime/projection algorithm, test assertion,
historical evidence, dependency, grant or setting. The existing task authorizes
necessary isolated fixes; no new user access or release approval is implicated.

Acceptance is the same frozen failing R08 CLI check and unchanged remaining
R08 controls, plus focused Ruff lint/format. No new repair loop or third managed
behavioral repair is authorized by this amendment. Keep both original failures
and source bindings; bind the import-corrected candidate separately before
packaging. Report this correction in addition to the two behavioral repairs.
