# Independent routing amendment, frozen before candidate execution

Version 1 remains unchanged under history/v1; baseline.txt and baseline.xml
retain its exact-head baseline run (18 failures, 22 errors). Twelve core setup
errors and other missing-module/plugin failures are missing-surface baseline
evidence. Ten additive integration fixture errors were an independent harness
problem: pytest 9 removed the private fixture marker used for dynamic routing.

Version 2 explicitly exports the named flow fixture and introduces a small
maintained normal-pytest wrapper. Formatting changes affect only newly authored
integration/routing files. Original 35 artifacts remain byte-identical.
Assertions are retained. Current fixture count is 28 original Python methods,
13 additive integration cases and two Node cases: 43 pytest cases total, with
46 plugin-v3 cases / 401 assertions inside its mandatory Node case.
The original CONTRACT's core count 13 was a clerical error; its unchanged source
actually has 12 core methods, as ORIGINALS-FREEZE/INTEGRATION-FREEZE record.

Before candidate execution, the finite controls additionally specify exact
legacy FastEmbed identity refusal, mismatched pinned synthetic identity refusal,
and outer-transaction sync refusal before acknowledgement/projection writes.
These extend the frozen transaction/compatibility contract; no result or failed
expectation is rebaselined. No candidate runtime tests preceded this amendment.
