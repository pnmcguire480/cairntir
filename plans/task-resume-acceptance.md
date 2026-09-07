# Task resume acceptance

Independent author: `/root/resume_acceptance`. Coordinator: `/root`.
Status: FROZEN; implementation acceptance is expected RED before implementation.

## Recognizable outcome

The user asks: "start work in one host, interrupt it, and resume in another
without rebriefing."

After host A receives an acknowledged checkpoint, its MCP process is killed.
A fresh host B MCP process receives only a project wing and task identifier.
It retrieves the exact original request, latest complete checkpoint, durable
completed and outstanding work, and source evidence. A completed task cannot
silently become active again. Reading a checkpoint is not a claim that an agent
executed the next action.

## Independent scenarios

1. Exact Unicode, whitespace, and multiline request persistence; stable task
   identity; more than one task in a project and the same identifier in another
   project cannot mix evidence.
2. Complete acknowledged checkpoint survives abrupt process termination and a
   fresh connection. The receiver supplies no task text, reconstructed context,
   cached response, or transcript recovery input.
3. Append-only revisions retain earlier evidence. Atomic compare-and-swap
   admits one writer for a shared expected revision and rejects stale updates
   without losing acknowledged work. Different processes exercise the race.
4. Exact retries are idempotent before and after restart; changed payloads with
   the same request key fail visibly. A stale retry cannot replace newer work.
5. Missing task, wrong wing, missing checkpoint, and completed task return
   explicit outcomes. Terminal task completion persists across restart and
   cannot be reopened. Completed/outstanding lists are full checkpoint snapshots;
   this milestone introduces no individual-obligation transition model.
6. Invalid field types, blank identities, broken references, and rejected
   transitions produce typed errors without partial drawers, vectors, workflow
   receipts, or checkpoint state.
7. Origin host/session/model provenance accompanies the original request and
   every checkpoint. Host B must not replace host A's provenance. Approval-like
   source content is preserved as inert evidence and confers no execution or
   access authority.
8. Grants apply to task state and every referenced drawer before disclosure.
   Hidden and nonexistent tasks are indistinguishable. Read-only and revoked
   grants cannot create/update/replay checkpoints or leak prior results.
9. Resume is read-only, including access counts and workflow records. A
   read-only SQLite connection can resume an existing task.
10. The complete serialized MCP result respects the caller's budget. An
    oversized checkpoint is omitted whole with an explicit retrievable receipt;
    a partial checkpoint must never masquerade as complete context.
11. Existing ordinary remember/handoff behavior remains and the MCP surface
    remains exactly 21 tools. The new operation is advertised through existing
    tool schemas and is exercised through actual JSON-RPC stdio transport.
12. Every advertised MCP tool schema has root `type: "object"`, including the
    existing hotfix schema. Destination-host tool discovery cannot depend on a
    permissive client accepting a missing root type.

## Evidence boundary

Tests use temporary SQLite stores and a deterministic local hash embedder.
Actual subprocesses run the existing MCP server entrypoint with distinct host
identities; only the embedding factory is substituted. Network use is denied
apart from the Windows event-loop loopback socket. Production memory,
registration, updates, paid models, and commercial host automation are outside
the test boundary. This proves interruption-safe MCP continuity; it does not
prove Claude/Codex model behavior, automatic checkpoint capture, billing
savings, or elimination of host context compaction.

## Frozen contract and reproduction

The coordinator's [public contract](task-resume.md) fixes the existing
`remember(checkpoint=...)` and `handoff(resume=True, task_id=...)` APIs, response
fields, whole-chain visibility, idempotency namespaces, and CLI syntax.
`tests/unit/test_task_resume_acceptance.py` contains 66 executable cases.
The scalar validation matrix is independent input-boundary coverage; the
transport cases use actual separate MCP server subprocesses.

Run with the existing development interpreter:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_task_resume_acceptance.py --no-cov -q --tb=short
.\.venv\Scripts\python.exe -m ruff check tests/unit/test_task_resume_acceptance.py
.\.venv\Scripts\python.exe -m ruff format --check tests/unit/test_task_resume_acceptance.py
```

The [freeze manifest](task-resume-acceptance-freeze.json) records SHA-256 hashes
for this inventory, the public contract, executable tests, and baseline records.
Those input hashes must remain unchanged; implementation agents may read but
not edit them. Separately labeled later supporting probes cannot replace this
suite or alter its expected results.

The three-hour delivery budget reserves its final hour for independent
verification and landing, with at most two repair-and-verification rounds.
Implementation acceptance requires PASS for all frozen cases, required repository
gates, and actual isolated Claude tool-list health verification. No paid model
call or production installation is part of this authorization. Missing external
evidence is INCONCLUSIVE, not PASS. Final dispositions are COMPLETE, BLOCKED,
or EXHAUSTED as defined by the Finalization Mode recipe.

Pre-freeze schema probe: **FAIL**, 1 failed in 1.19 seconds. Exactly
`cairntir_hotfix` lacks an object root. The runtime was unchanged for this probe.

The final pre-implementation baseline is independently recorded in
[baseline JSON](task-resume-acceptance-baseline.json) and its full
[pytest output](task-resume-acceptance-baseline.txt). All 66 cases are expected
to fail because task checkpoint/resume APIs and their schemas are absent and
the hotfix input schema lacks a root object type. No skipped or xfailed cases
substitute for these failures. Ruff and formatting must pass at freeze.
