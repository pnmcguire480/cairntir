# Managed runtime — durable intake and configured dispatch

Current port checkpoint (2026-10-03): isolated R08-based candidate; fresh full/installed qualification and native acceptance remain pending. The implementation and verification sections below describe preserved historical evidence, not qualification of this new candidate. The fresh port repairs caller-transaction receipts/projection and refuses close when the selected task evidence is unavailable. See [usage and limits](../docs/managed-sessions.md).

Status: public local implementation COMPLETE. This verifies the explicit
managed-session slice of R06/R07/R09 and the companion R10 projection API.
Automatic coding-host delivery and action routing remain separate owed work.

## Behavior

A foreground worker receives exact producer events, atomically commits each
event with its TaskBook checkpoint, then returns a durable receipt. The first
event supplies the original request; the worker never guesses it. Later events
preserve that original and every outstanding commitment. Event UUID, payload and
session sequence bind exact retries; changed payloads, occupied sequences and
stale revisions reject without partial writes.

Startup emits a task brief with a fresh runtime epoch. Ambiguous tasks require
an explicit task ID. A complete current brief needs an exact acknowledgement
before configured dispatch. Captures and changed state invalidate readiness.
Known failed captures remain pending until the identical payload commits;
unrelated successful events cannot erase them. Prior epochs lacking durable
close records remain visible, without claiming that the old process crashed.

The dispatcher binds a trusted fixed executable/argv/cwd profile, executable
hash, timeout and output limits. It commits a prediction and intent before
launching the process without a shell. A caller's outer transaction prevents
dispatch because a nested savepoint cannot establish physical durability.
Outcome and checkpoint are a separate transaction. A committed intent without
an outcome stays uncertain and never launches again, even after restart.
Concurrent calls permit at most one launch per store/principal/action ID.
This is not a guarantee of exactly-once external effects.

Explicit close reports the producer watermark, sequence gaps and pending claims.
EOF without a final watermark cannot claim complete capture. Closing a worker
does not finish its task. A timeout, output cap or unconfirmed cleanup remains
uncertain; arbitrary descendant containment is outside this process boundary.

## Protocol and authority

```bash
cairntir managed --config managed.json --session-id SESSION_UUID
cairntir managed --config managed.json --session-id SESSION_UUID --task-id TASK_UUID
```

The first stdout line is the startup brief. Each stdin JSONL command contains
schema `cairntir.managed-command.v1`, an operation, and its request object.
Operations are capture, brief, acknowledge, dispatch, status and close. Each
produces a JSON receipt or a structured error; any input error makes final exit
nonzero. The worker performs no hook installation or host registration.

Trusted configuration selects a wing, room, absolute project root, brief budget
and named profiles with fixed argv, contained cwd, timeout and output limit.
Caller requests cannot substitute executable arguments. CLI configuration bytes
are checked again before every command; changes require an explicit restart.
Executable bytes and resolved paths are rechecked before launch. Existing scoped
read/write grants still apply, including revocation and whole evidence access.
Configuration and stored memory do not confer additional operating-system rights.

The [frozen protocol](acceptance/v2-managed-runtime/CONTRACT.md) defines exact
module, configuration, event, brief, acknowledgement and receipt shapes.
[Close/restart](acceptance/v2-managed-runtime/CLOSE-CONTRACT.md) and
[configuration replacement](acceptance/v2-managed-runtime/CONFIG-CONTRACT.md)
supplements make the failure boundaries explicit. The database schema,
dependencies and 21 MCP tools remain unchanged.

## Verification and disposition

The original 12 core and 10 real-process cases passed on the first candidate.
Independent review then reproduced false capture completeness, missing unclosed
epochs, and stale CLI configuration. One product repair passed all 27 frozen
cases with zero skips. A later startup race exposed session telemetry in the
readiness hash. A separately frozen deterministic case reproduced it; the final
repair separates that telemetry from readiness while preserving it in the whole
brief. All 28 cases pass, including the original race and new two-runtime
acknowledgement case. Original failures remain in the
[acceptance packet](acceptance/v2-managed-runtime/README.md).

A real child opens an independent SQLite connection and verifies committed
prediction/intent before writing its external marker. Tests kill the managed
driver before spawn and after the effect, restart it, race two authorized
drivers, inject a witnessed outcome-write fault, and verify owner/scoped outer
transaction denial. The actual CLI cases use copied qualified model assets
offline. An uncommitted-writer control is rejected before its marker. Removing
only the replay guard in a disposable copy creates a second child marker and
fails the unchanged assertion, both before and after repair.

The maintained wrapper verifies immutable bytes. Its default run executes 26
cache-free cases and explicitly skips the two production-model CLI cases unless
MANAGED_ACCEPTANCE_MODEL_CACHE points to a qualified local cache. The independent
final run passes 28. The [state followup](acceptance/v2-managed-runtime/STATE-FOLLOWUP-NOTES.md)
retains the later race, deterministic red, final repair and independent review. This is public local evidence,
not independent evaluator custody or native host-event delivery certification.

At least 25% of effort was reserved for verification; both allowed repair
rounds were used. Source, repository and installed evidence remain separately bound. No live installation, store, publication or host changes
are part of this increment.

## Final combined verification

The corrected complete source run finishes with 1,932 passed, 4 Windows symlink-privilege skips, at 92.252901% coverage.
The unchanged coverage floor remains 92%. The original run is retained: 1,914
passed, three embedding-fixture failures and four skips at 91.826994%. Independent
old/new-source controls trace those three failures to the runner's global cache
override; removing it requires no product or existing-test changes. The second
run is also retained: 1,925 passed, seven OpenBLAS allocation failures and four
skips at 92.252901%. Independent controls reproduce all seven failures, then
pass the same seven cases with only `OPENBLAS_NUM_THREADS=1`. The final run uses
that process-local verification setting, retaining the original assertions and
application concurrency. Separately frozen outcome cases are included in the
corrected complete run. Neither runner correction changes the product.

All 17 other repository gates pass: static/build/documentation/preservation,
six model-backed evaluations with one explicit no-live-corpus skip, one slow
case, five historical pairs, 15 mutation pairs and installed CLI/MCP checks.
The exact wheel contains 83 source-matched runtime members and 61 locked
dependencies. Its managed proof passes 28 cases and three normal CLI sessions;
the Last Session proof uses five processes, preserving database state and human
bytes, reproducing the view after restart, and refusing forged records.
