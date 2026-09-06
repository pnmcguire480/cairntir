# Portable v2 independent acceptance

PASS — round 0, 71 passed, zero skipped/failed/error cases.

The complete 25-case suite, the separately frozen nested-supersedes boundary, and all 45 legacy portable/shipping cases ran. The unchanged 100,003-record completeness case and the genuine schema-v6 migration fixture were included. All frozen generation-1 inputs, archived generation-0 inputs and Python runtime source/configuration hashes matched before and after. Ruff and formatting checks passed.

PASS: immutable original envelopes and explicit numeric UUID mappings preserved; portable lookups/replacements/supersession updates use scoped-store hooks, export uses independent export capability, and only original top-level /supersedes_id activates a local lifecycle edge. No additional actionable portable correctness finding in bounded review.

Raw commands, output, durations, source/config hashes and limits are retained in [portable-v2-result.json](portable-v2-result.json) and the adjacent JUnit XML/logs. Isolated local fixture stores, including genuine schema-v6 migration fixture, 100003 records and separate-process import race. No production writes or network sharing. Public release/host/native-OS validation remains separate.
