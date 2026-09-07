# Interrupted task resumption

Status: ready. Execution gate: allowed by the maintainer's request:
"start work in one host, interrupt it, and resume in another without rebriefing."

## Goal and scope

An acknowledged checkpoint survives termination of its originating process.
A fresh host connection needs only the wing (when unambiguous) or task ID to
recover the exact original request and latest complete progress record.
Implement this through the existing remember/handoff tools and CLI, preserving
the 21-tool surface. Repair the demonstrated hotfix schema defect preventing
Claude Code from accepting the tool list. No production installation or release.

## Public contract

`remember(wing, room, content, checkpoint={...}, model=...)` returns JSON when
checkpoint is supplied; ordinary remember remains unchanged. The checkpoint
object accepts exactly `task_id` (optional on creation), `expected_revision`,
`idempotency_key`, `status`, `completed`, `outstanding`, `next_action`, and
`evidence_ids`. Revision is a nonnegative integer (not bool); keys are nonempty
strings; completed/outstanding are lists of nonempty strings; evidence IDs are
unique positive integers. All fields other than task_id are required.

Creation uses expected_revision=0, no task_id, and status="active". Content is
the immutable original request. The server generates a UUID task_id and revision
1. Later calls require the task_id and current expected_revision. Their content
is the latest progress summary; the other fields replace the checkpoint in full.
Status is active/completed/cancelled. Active checkpoints require a nonempty next
action. Terminal checkpoints require empty outstanding and next_action. A
terminal task cannot be reopened. Empty original requests or progress are invalid.
Checkpoint mode rejects metadata, anchors, claim, and predicted_outcome arguments;
use ordinary evidence drawers and evidence_ids for supporting material.

Creation uses one drawer: original_drawer_id equals checkpoint_drawer_id and
summary equals the exact original request. Idempotency keys are store-wide for
owner sessions and grant-namespaced for restricted sessions, matching existing
workflow behavior. Identical replay never authorizes access across either scope.

Write receipt: schema="cairntir.task-checkpoint.v1", task_id, revision, status,
original_drawer_id, checkpoint_drawer_id, replayed. An identical retry returns
the original receipt even after later revisions; a changed payload with the same
key conflicts. Validation, denied access, stale updates and terminal transitions
leave the database unchanged. Typed CairntirError subclasses surface as MCP
isError=true or CLI nonzero exit.

`handoff(wing, resume=True, task_id=None, budget_chars=8192)` returns JSON with
schema="cairntir.task-resume.v1", status, task_id, revision, checkpoint,
candidates, instruction_authority="none", and budget. An explicit task_id also
selects resume mode. Resume cannot combine with task search, files, candidate_limit
or transcript recovery. No embedding call, transcript access or database write.

For status="ready", checkpoint contains original_request, summary, completed,
outstanding, next_action, evidence_ids, original_drawer_id, checkpoint_drawer_id,
and provenance={original:..., checkpoint:...}; source text is exact quoted evidence.
Evidence IDs remain explicit retrieval references, not a claim their contents or
anchored files were revalidated. No saved text grants instruction or execution
authority. Whole mandatory state must fit in both JSON text (plus CLI newline)
and serialized MCP CallToolResult; otherwise status="omitted", checkpoint=null,
and required_chars plus both drawer IDs identify how to retrieve the complete
state. budget contains limit_chars and rendered_chars. Minimum budget is 1024.
required_chars and the two drawer IDs are top-level omission fields;
required_chars is the maximum size of the full ready JSON plus newline and its
serialized MCP CallToolResult. rendered_chars is the returned JSON text length.

Discovery returns none if no visible active tasks, ready for exactly one, or
ambiguous with only visible {task_id, revision} candidates and no checkpoint.
An explicit terminal task returns terminal with no checkpoint/next action.
Unknown, wrong-wing and inaccessible explicit IDs return unavailable identically.
Unavailable responses never echo the requested ID: task_id and revision are null.
Candidate lists also obey the budget; omitted candidates are disclosed by count,
as omitted_candidates, never silently resolved by recency. Resume never claims
or advances a task. Whole-chain visibility includes prior checkpoints' evidence,
even when references were removed from the latest replacement.

## Storage and authority

Use existing committed workflow receipts as the local task registry, with
operation="task.checkpoint.v1". Append verbatim drawers for request/progress.
No schema bump or new dependency. A task's wing/room and original request never
change. An outer transaction encloses idempotency, authorization, revision check,
checkpoint append and receipt commit. Imported/ordinary metadata cannot activate
or alter task state. Partial visibility of a task chain or required evidence
withholds the entire task; never resume an older visible revision. Grants must
permit read of the task and evidence, plus write for checkpoints. Retry access
is checked against current grants. Stored approvals never become current consent.

## CLI and host policy

`cairntir checkpoint WING --room ROOM --input FILE` reads a UTF-8 JSON object
with content, checkpoint and optional model, using the same backend validation.
`cairntir handoff WING --resume [--task-id ID] --budget N` is read-only, including
when another MCP process holds the store. Generated policy discovers resumable
tasks first, captures a new request before work, checkpoints meaningful progress,
and closes completed tasks. It uses task-aware evidence retrieval when needed.
Multiple active tasks require selection; no transcript collection is introduced.

## Independent acceptance and finish

The independent tester owns tests/unit/test_task_resume_acceptance.py and
plans/task-resume-acceptance*; implementation agents may not edit frozen inputs.
Tests cover exact Unicode requests, abrupt process death after acknowledgement,
fresh distinct host identities, CAS races, retry conflicts, rollback, terminal
states, ambiguity, budgets, scoped visibility/revocation, forged metadata,
read-only CLI/MCP parity and all tool schemas. Existing frozen suites stay intact.

Three-hour delivery budget, with the final hour reserved for verification and
landing. At most two repair-and-verification rounds. Required repository checks
and independent PASS precede completion. Use a green PR to land on main.
Actual Claude tool-list health is tested with isolated development configuration;
separate MCP clients prove transport continuity, not autonomous model performance.
No paid model calls, actual token-saving claims, automatic capture hooks, remote
sync, production migration, or 2.0 version bump in this milestone.

Terminal status is COMPLETE only for proven registered scope; BLOCKED names an
external dependency, and EXHAUSTED preserves the last evidence after the budget.
