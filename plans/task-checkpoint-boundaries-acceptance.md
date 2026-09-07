# Task checkpoint boundary acceptance

Independent tester: `/root/foundation_tester`. Scope: the reproducible input
validation defects in the combined 1.11.0 preparation under requests #1352 and
#1353. Runtime and the existing frozen 70 task-resume cases remain outside the
tester's write scope.

The existing `TaskBook.checkpoint`, CLI `checkpoint --input`, and MCP
`cairntir_remember(checkpoint=...)` interfaces are retained. An evidence ID that
cannot fit SQLite's signed 64-bit integer domain must produce a surfaced
`TaskError`/`CairntirError`, never a raw binding overflow. A representable but
unavailable positive ID must also fail cleanly. No new arbitrary integer limit
or identifier format is prescribed.

Unpaired high or low UTF-16 surrogate code points cannot be encoded as valid
UTF-8 and must be rejected before persistence. Apply the same boundary to
content, idempotency_key, task_id, completed/outstanding items, next_action and
the optional model string. Valid accented text, combining sequences, CJK and
non-BMP emoji must remain accepted verbatim; neither replacement nor Unicode
normalization is permitted. Generated task IDs remain the existing UUIDs.

Every rejected write preserves the complete logical store: schema and every
persisted table, including physical vector tables, access/provenance fields,
workflow failure receipts and task registry. Creation and updates are both
covered. Transport errors use the existing CLI `cairntir:` or MCP
`[cairntir error]` envelope, with nonzero exit/isError and no raw traceback,
overflow exception or encoding traceback text. After rejection the existing
task is still resumable, and an MCP peer remains usable.

The suite has 33 executable cases: 14 direct surrogate checks, two direct
integer overflows, one representable missing-ID control, two invalid-creation
checks, nine real CLI rejections, two real stdio MCP rejections, and three
valid-Unicode round-trip/idempotent-replay controls. Transport JSON encodes
surrogates as ASCII escapes for CLI input, so they reach application validation
rather than failing the test writer's UTF-8 encoder. The MCP SDK rejects those
unpaired surrogate escapes before tool dispatch; this contract does not impose
SDK/parser changes. Real MCP proofs cover representable JSON integers and valid
Unicode. Direct and CLI proofs cover the application's invalid-string boundary.

The existing frozen task-resume suite supplies only temporary-store snapshot
and bounded CLI/stdio transport helpers. The new stdio subclass changes JSON
wire escaping only. Runtime methods, SQLite operations and validation are not
mocked. Helpers use a deterministic Hash32 embedding provider, isolated homes,
documented notifier/registration opt-outs and no external networking. Real
embedding semantics are unrelated to this input-validation boundary.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_task_checkpoint_boundaries_acceptance.py --no-cov -q --tb=short
.\.venv\Scripts\python.exe -m pytest tests/unit/test_task_resume_acceptance.py tests/unit/test_task_resume_supporting.py tests/unit/test_task_resume_budget.py --no-cov -q
.\.venv\Scripts\python.exe -m ruff check tests/unit/test_task_checkpoint_boundaries_acceptance.py
.\.venv\Scripts\python.exe -m ruff format --check tests/unit/test_task_checkpoint_boundaries_acceptance.py
```

The companion baseline records exact counts, invocation, base HEAD, raw output
and runtime fingerprints. The freeze binds this suite, this contract, baseline
evidence, conftest and the unchanged original 70-case files. At most two official
repair rounds; reserve the final quarter for verification. All new artifacts
use UTF-8 with LF. No runtime, schema, dependency or historical acceptance edits.

Final preimplementation baseline: 17 failed, 16 passed in 20.28 seconds, with
zero collection/setup/transport infrastructure failures. Ruff and format pass.
The superseded 40-case authoring diagnostic is retained separately; its seven
MCP parser cases were removed before freeze with review approval. The final
33-case application contract is unchanged by that transport restriction.
The independent tester runs these 33 cases after the fix; `/root/resume_acceptance`
owns the unchanged 70-case regression and separate host-policy gate.
