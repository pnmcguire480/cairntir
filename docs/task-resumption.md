# Resume interrupted work

Task checkpoints let another host recover the exact request and the latest
saved progress from the same Cairntir store. This capability is under
development for the next release; it is not part of published 1.10.0.

Both hosts must use the same store and wing. A wing is your shared project
identity; different host checkout paths do not automatically identify a project.
No transcript import is needed.

## Start and checkpoint

Before starting work, call the existing `cairntir_remember` tool:

```json
{
  "wing": "myapp",
  "room": "tasks",
  "content": "Fix cache invalidation without changing the public API.",
  "checkpoint": {
    "expected_revision": 0,
    "idempotency_key": "cache-fix-start-1",
    "status": "active",
    "completed": [],
    "outstanding": ["Reproduce the defect", "Implement and verify the fix"],
    "next_action": "Reproduce the stale cache response",
    "evidence_ids": []
  }
}
```

Pass your own model ID when known. Save the returned task_id and revision.
To checkpoint progress, call remember again with that task_id and revision as
expected_revision. Supply a new idempotency_key, a progress summary as content,
and the complete replacement completed/outstanding/next_action/evidence_ids.
The original request is preserved unchanged.

Checkpoint after meaningful progress, before switching hosts, and before work
that may outlast the session. If the response is lost, retry the identical call
with its original idempotency key. A changed request needs a new key. A stale
revision is rejected; read the current task before reconciling concurrent work.

For the CLI, put the content/checkpoint object and optional model in a UTF-8
JSON file, then run:

```bash
cairntir checkpoint myapp --room tasks --input checkpoint.json
```

## Resume in another host

Call `cairntir_handoff(wing="myapp", resume=true)`. If there is exactly one
visible active task, it returns the original request and latest checkpoint.
For multiple tasks, select the appropriate returned ID; Cairntir does not guess
from recency. You can also resume directly:

```bash
cairntir handoff myapp --resume --task-id TASK_ID --budget 8192
```

No request text needs to be supplied again. The receipt preserves the source
host, session, and model of the original request and progress. Evidence IDs are
references for deliberate retrieval. Check current code and external state
before continuing: a checkpoint reports what was saved, not what was freshly
verified in the destination host.

If the whole checkpoint exceeds the response budget, status is omitted and the
receipt supplies required_chars. Repeat with that budget to obtain the full
checkpoint. The budget includes the serialized MCP tool result. No partial
checkpoint is presented as complete.

## Finish and trust

Write a final checkpoint with status completed or cancelled, empty outstanding,
and an empty next_action. Terminal tasks stay closed and disappear from active
discovery. Reading or resuming a task never changes its state or claims ownership.

Scoped grants must cover the entire checkpoint chain and its evidence. Partial
visibility withholds the task; it never exposes an older visible checkpoint as
current. Imported checkpoint metadata does not activate a task. Checkpoint text,
including saved approval statements, is historical evidence and grants no
execution authority.

Capture still requires an acknowledged write. Generated host instructions ask
agents to checkpoint; they are not an automatic conversation watcher. A process
interruption can lose work performed after its last acknowledged checkpoint.
Protocol tests use separate host connections; they do not measure autonomous
model behavior or billed token savings.
