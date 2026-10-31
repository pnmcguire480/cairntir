# Explicit managed sessions

This development candidate adds a foreground worker for a producer that can
submit exact events and read receipts. It records requests and checkpoints,
requires a current acknowledged brief before a configured action, and retains
uncertain actions after interruption. Native editor hooks are not installed by
this command. A saved event is evidence of capture, not completion of the task.

## Configure and start

Create a trusted JSON configuration with schema `cairntir.managed-config.v1`:

| Field | Meaning |
| --- | --- |
| `wing`, `room` | The existing project scope selected by the operator. |
| `project_root` | An existing absolute project directory. |
| `brief_budget_chars` | An integer from 1024 through 262144. |
| `profiles` | A nonempty map of named, fixed commands. |

Each profile has `argv`, `cwd`, `timeout_seconds` and `output_limit_bytes`.
The first argv item is an existing absolute executable path; cwd is an existing
absolute directory inside project_root. Timeouts range from 1 to 300 seconds,
and output limits from 1 to 1048576 bytes. Choose the exact fixed arguments and
review the executable before starting. Profile configuration is operator input,
not instructions recovered from memory. Requests cannot substitute arguments.

The worker invokes the configured executable path, preserving environments such
as a Python virtual environment. It separately binds the resolved executable
target and its bytes; changing either requires a restart and fresh acknowledgement.

Run `cairntir managed --config managed.json --session-id SESSION_UUID`, optionally
adding `--task-id TASK_UUID` when selecting an existing task. Session and task IDs
use canonical UUID strings. The first stdout line is a fresh startup brief.
Ambiguous task discovery requires explicit selection; incomplete or stale briefs
cannot authorize dispatch.

## Use the receipt protocol

Send one JSON object per input line, with schema `cairntir.managed-command.v1`,
an `operation` and its `request`. The exact request shapes and examples are in
the preserved [runtime contract](https://github.com/pnmcguire480/cairntir/blob/22a291cd3868b568af1c5013519f14af53aff24f/plans/acceptance/v2-managed-runtime/CONTRACT.md).

1. `capture` submits an exact producer event, event UUID and sequence number.
   The first event supplies the original request. A successful receipt follows
   the committed event and TaskBook checkpoint. Preserve the exact request for
   retries; changing the payload while reusing its ID is refused.
2. `brief` returns current task evidence and a fresh brief identity. Read it,
   then `acknowledge` its exact ID and SHA256. Captures or changed evidence make
   previous readiness stale. Acknowledgement records receipt of the brief; it
   does not certify understanding or confer new permissions.
3. `dispatch` names an existing profile and binds its action UUID, current
   acknowledgement, prediction and captured event IDs. The worker records a
   durable prediction and intent before launching without a shell. Query
   `status` after interruption. An intent with no confirmed outcome stays
   uncertain and is never automatically launched again.
4. `close` supplies the producer's final sequence watermark. Missing sequences,
   failed captures and missing prior close records remain visible. EOF without
   a final watermark cannot claim complete capture. Closing does not mark the
   task complete.

Keep stdout receipts and surfaced errors. Any input error makes the final CLI
exit nonzero. If configuration or executable bytes change, explicitly restart
and obtain a new brief and acknowledgement. A zero child exit is an observed
command outcome, not proof that a user's entire request was satisfied.

## Rebuild Last Session explicitly

After committing capture and close, call
`cairntir.managed_projection.project_last_session(store, root=..., path=...,
wing=..., session_id=..., epoch=...)` with the recorded session and epoch.
The Python API rebuilds one generated block from authorized committed evidence
and the current task checkpoint. It returns a complete receipt or a surfaced
error. A filesystem error leaves committed memory intact; retrying projection
does not replay actions or append drawers.

Both paths must be absolute, root must exist, and the target must remain within
it. Existing human files need exactly one correctly ordered pair of
`<!-- cairntir:generated:begin -->` and `<!-- cairntir:generated:end -->` markers.
Human bytes outside that block are preserved. No implicit CLAUDE.md rewrite,
file watcher or projection on host startup is added.

## Authority and limits

Existing owner/scoped store authority still applies; revoked or unavailable
required evidence cannot be used as fresh action authority. The runtime does
not enroll accounts, create credentials, raise operating-system privileges or
sandbox arbitrary descendants. A configured process runs with the caller's
existing OS permissions. Exactly-once external effects are not guaranteed.

Receipt-producing methods and projection refuse a caller-owned transaction:
commit or roll back that transaction before retrying. A capture refused because
of its caller-owned transaction remains pending until the same event commits. Reads and
declared approvals do not replace operator authentication.

The current port has bounded public synthetic evidence only. Native host delivery,
connected human acceptance, exact installed qualification and full-product release
gates remain separate. No live activation or rollout is implied by these examples.
