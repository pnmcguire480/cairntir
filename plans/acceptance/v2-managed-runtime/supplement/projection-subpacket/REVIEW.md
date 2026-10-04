# Public projection supplement review

PASS: four independently frozen supplemental cases, nine visibility/corruption subcases and the real checkpoint-advance/retry outcome. No skips, errors or product changes. Source remained SHA256 53fa5cc28d256a434d181a96d82b3a87534acc5eb6710236b6bcf6b44bad4df8.

Wrong-control PASS: an in-memory copy with the current-projectability refusal removed produced exactly three expected assertion failures (secret, expired, future source) and no harness errors. Actual source bytes remained unchanged. The successful original run is first-run.json/log; the deliberate failing candidate is wrong-control.json/log.

These assertions were frozen after the original full-suite coverage observation and before their first execution, not before product implementation. All earlier frozen tests remain unchanged. No coverage data was touched by these unittest executions; the combined maintainer will separately measure the unchanged-source union.

Maintained integration: load test_projection_supplement.py normally against canonical cairntir imports and collect only ProjectionSupplementAcceptance. It has no sibling-fixture dependencies. Preserve frozen bytes; treat this fixture like the existing immutable public acceptance files. A pre-freeze general Ruff invocation reported documentation/import-order conventions on this external fixture; no acceptance assertion was edited after freeze and no clean static claim is made for it.
