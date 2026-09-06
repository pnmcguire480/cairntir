# Continuity candidate local gates

PASS for local verification of the 1.10.0 candidate. Remote CI, protected merge
and publication remain separate gates. [Canonical evidence](continuity-gates.json)
binds runtime hashes, independent results and raw regression/model logs.

Independent results: foundation and concurrent WAL reads accepted; portable 71,
procedures 161, sharing 193 and bulk boundaries 8 pass. The portable suite includes
the unchanged 100,003-record archive case. The real-store private migration
preserves 1,280 drawers/vectors and all 19 original tables without embedding calls.

Regression selected 986 tests: 983 passed, with three documentation checks failing
on CP1252 text in two newly written result reports. Those reports were converted
to UTF-8 LF; both affected test files then passed all 18 cases. Runtime and frozen
assertions did not change. Coverage is 83.37%; all seven offline model evaluations
pass. The first combined run's explicit OpenBLAS allocation failures are retained;
serial verification used one numerical-library thread per process.

Ruff, format, strict types, silent-exception, 157 commitments, nine seams, local
links, release tags, 134 dependency advisory checks and strict MkDocs all pass.
The fresh wheel installation passes version/help/recipes, v2 interchange,
task-aware CLI/stdio MCP parity, abstention, integrity and the isolated demo.
The wheel advertises 1.10.0 and exactly 21 MCP tools.

Source review and archive inventory pass. Production installation/configuration
remain unchanged. Claude's installed launcher connected but reported tools-fetch
failure; a private candidate project awaits Claude approval. Neither is claimed
as a passing candidate host test. Automated transport and adapter evidence is
recorded separately.
