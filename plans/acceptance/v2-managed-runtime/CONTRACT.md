# Managed runtime public contract v1

Independent public acceptance before implementation. This first slice implements acknowledged intake, task resumption, brief acknowledgement and managed local dispatch. R10 generated Last Session and actual coding-host event delivery remain separately owed. No universal host gate, protected evaluator custody, scheduler, production installation, new dependency, new database table or additional MCP tool is claimed.

## Python and CLI boundary

Module `cairntir.managed` exports `ManagedRuntimeError(CairntirError)` and `ManagedRuntime(store, *, config)` accepting the existing owner or ScopedStore. Public methods:

* `start(session_id, *, task_id=None) -> dict`
* `capture(event) -> dict`
* `brief() -> dict`
* `acknowledge(request) -> dict`
* `dispatch(request) -> dict`
* `status(action_id) -> dict`
* `close(*, last_sequence=None) -> dict`

Calls before start or after close fail with ManagedRuntimeError. The caller supplies a canonical UUID logical session ID; every start creates an internally generated fresh UUID epoch. Restart may reuse the logical session ID, never the old epoch or acknowledgement. A runtime instance starts once. All text is valid UTF-8 and retained exactly, including leading/trailing whitespace and CRLF. All UUIDs are canonical; all numeric revisions/sequence/limits reject bool. Unknown fields reject.

CLI: `cairntir managed --config PATH --session-id UUID [--task-id UUID]`. It reads the trusted JSON config, creates the normal configured/scoped store and emits `start`'s brief as the first JSON stdout line before reading input. Later lines are exactly `{schema:"cairntir.managed-command.v1", operation, request}`. Operations map to methods: capture/acknowledge/dispatch pass the request object; brief requires `{}`; status requires `{action_id}`; close requires `{last_sequence}`. Explicit close ends the stream. EOF invokes close with last_sequence=null and emits its receipt unless already closed. Each input yields one JSON reply. Errors yield `{schema:"cairntir.managed-error.v1",status:"error",operation,error}`; no traceback or non-JSON stdout. Errors never launch an action, and the stream may continue. Exit nonzero if any input failed, otherwise zero. No daemon or hook installation.

## Config and authority

Config has exactly schema=`cairntir.managed-config.v1`, wing, room, project_root, brief_budget_chars, profiles. Wing/room use existing identifier validation. project_root is an existing absolute directory. brief_budget_chars is an integer 1024..262144. profiles is a nonempty mapping of existing-valid identifiers to objects with exactly argv, cwd, timeout_seconds, output_limit_bytes.

argv is a nonempty list of strings, executable is an existing absolute regular file; cwd is an existing absolute directory contained in the configured project root after resolution. timeout_seconds is integer 1..300; output_limit_bytes integer 1..1048576 per stream. Profiles contain fixed arguments; the first slice accepts no caller parameters, argv substitution or shell strings. Use shell=False. Capture the resolved profile, executable SHA256 and config identity; replacing the executable/config invalidates readiness before another launch. Profile authority comes from trusted startup configuration, not memory/event text. Do not expose environment secrets in any receipt. Same-user actions outside this worker remain outside its workflow boundary.

Every operation checks current store capability/scope. Revoked/expired grants cannot capture, acknowledge, dispatch or replay protected results. Whole required evidence groups must be visible; arbitrary remember/import metadata is not lifecycle authority. Existing grant-specific idempotency namespaces remain. The at-most-one launch guarantee is within a store/principal/action-ID namespace.

## Intake and automatic TaskBook checkpoint

Capture event has exactly schema=`cairntir.managed-event.v1`, event_id, session_id, sequence, task_id, expected_revision, content. event_id/session_id are UUIDs, sequence is positive, content is nonblank, task_id is null or canonical UUID, expected_revision nonnegative. Session must match the active logical session. A new task requires task_id=null, expected_revision=0 and start discovery status none. Its immutable original request is the exact event content; never invent a request. Existing tasks require the selected task ID and exact current revision. Ambiguous task discovery requires explicit selection in a fresh start; never choose from recency. Terminal or unavailable selections cannot proceed.

The event and TaskBook checkpoint commit atomically using existing execute_once/transactions. First capture may use TaskBook's original drawer as the event source; do not require duplicate source drawers. Later captures preserve the original and all prior outstanding commitments, append this exact content to outstanding, retain completed work and source evidence links, and advance the task revision once. Request UUID/payload and logical session sequence are durably bound: exact retry replays, changed payload or another event at that sequence conflicts. Sequence gaps may be captured but remain explicitly reported; dispatch is denied until reconciled. Stale validation or write failure leaves no partial event/checkpoint. Never acknowledge a queue path as committed capture.

Capture receipt fields: schema=`cairntir.managed-event-receipt.v1`, status=`committed`, wing, event_id, session_id, sequence, content_sha256, task_id, revision, drawer_id, source_identity, replayed (bool). drawer_id names the exact captured content; source_identity is its immutable portable UUID. Identical replay after close/reopen returns the same receipt except replayed=true, including after later revisions; temporal history does not change the request binding. A capture invalidates previous brief acknowledgement.

## Brief and acknowledgement

start and brief return fields: schema=`cairntir.managed-brief.v1`, session_id, epoch, brief_id (new UUID), wing, task_id (nullable), revision (nullable), status, task, uncertain_actions, gaps, complete, state_sha256, brief_sha256. task is the existing structured TaskBook resume object for that selection. status is its ready/none/ambiguous/terminal/unavailable/omitted status. Retain exact original request and completed/outstanding state with source links; do not change drawer access state. uncertain_actions lists durable intents lacking committed outcomes, with action_id and prediction_drawer_id. gaps names known absent producer sequence numbers; lack of a final producer watermark does not imply a complete tail.

complete=false if required task/promise evidence is omitted, inaccessible, unavailable or ambiguous. A ready complete brief is required for acknowledgement/dispatch. Budget the whole brief, using existing omission/required-size behavior rather than silently trimming source text. brief_sha256 is SHA256 of the full brief object with that one field removed, canonical UTF-8 JSON (ensure_ascii=false, sorted keys, compact separators). state_sha256 binds selected task/checkpoint and required commitment/uncertain-action state, excluding epoch/brief IDs, clocks and access counters. Brief records themselves do not invalidate state. Persist the brief identity and binding as a dedicated committed workflow record.

Acknowledgement request has exactly schema=`cairntir.managed-ack.v1`, brief_id, brief_sha256. It must match the latest complete ready brief, current epoch/scope/config and current state. Return schema=`cairntir.managed-ack-receipt.v1`, status=`committed`, ack_id (UUID), brief_id, brief_sha256, epoch, session_id, task_id, revision, replayed. Repeating this exact acknowledgement in its current valid state returns the same ID. A supplied hash without the committed matching brief/ack is insufficient. Receipt proves protocol acknowledgement, not comprehension. Old-epoch, stale, swapped or forged acknowledgements reject.

## Dispatch, durable prediction and uncertain effects

Action request has exactly schema=`cairntir.managed-action.v1`, action_id (UUID), ack_id (UUID), profile (configured name), claim (nonblank exact text), predicted_outcome (nonblank exact text), event_ids (nonempty unique UUID list). Referenced events must be committed, accessible and belong to the selected task. No request field can replace configured argv/cwd/limits.

Before an external process exists, atomically validate current acknowledgement, state, profile and authority, then commit a prediction drawer plus dedicated `managed.dispatch.v1` workflow result. The prediction drawer's content and claim equal the exact claim, predicted_outcome is exact, and metadata has a nonempty structured kind so generic correction cannot edit it. The committed workflow result is an inspectable public receipt: schema=`cairntir.managed-dispatch-intent.v1`, status=`committed`, action_id, task_id, epoch, ack_id, profile_sha256, prediction_drawer_id, and request equal to the complete submitted action object. Existing workflow_runs.state must be committed before Popen. Store profile binding and source references durably. Never execute the runner inside a transaction/execute_once action callback.

Only the caller receiving a fresh, non-replayed intent may launch. A matching committed intent without an outcome returns uncertain, never reruns; crash before spawn may conservatively leave an uncertain action. Changed payload with the same action ID conflicts. Concurrent attempts yield at most one launch. A pending uncertain action blocks new action IDs in that managed session/task until explicit reconciliation in a later separately authorized interface; do not infer rollback or manufacture an observation.

Record actual output/exit/timeout and an observation drawer linked by supersedes_id to the prediction in a separate committed `managed.outcome.v1` result. Append a TaskBook checkpoint while preserving every still-outstanding captured commitment; a successful verification command does not automatically complete the user's request. Never overwrite concurrent checkpoint work. If outcome persistence fails after an external effect, keep intent/prediction and report uncertainty; no automatic repeat. Timeouts/output-limit termination are surfaced and output is bounded per configured stream limit with truthful truncation. Unconfirmed child-process cleanup remains uncertain.

dispatch/status return schema=`cairntir.managed-action-receipt.v1`, status=`completed` (exit0), `failed` (observed nonzero/confirmed timeout), or `uncertain` (no committed outcome); action_id, task_id, prediction_drawer_id, outcome_drawer_id (nullable), exit_code (nullable), stdout, stderr, timed_out (bool), output_truncated (bool), replayed (bool). Unknown action IDs reject. Repeated completed dispatch returns the original IDs/result with replayed=true. For uncertain results outcome_drawer_id/exit_code are null and no success is invented. Current scope and immutable request bindings remain checked even for replay. This is durable intent and at-most-one managed launch, not exactly-once external effects.

## Close and scope still owed

close returns schema=`cairntir.managed-close.v1`, status=`closed`, session_id, epoch, task_id, revision, last_received_sequence, declared_last_sequence (nullable), gaps, capture_complete (bool), uncertain_actions. Commit a dedicated close record. Do not make an active task terminal merely because its session closes. capture_complete requires an explicit matching final sequence, no known gaps and no failed/unacknowledged claimed events; EOF without a producer watermark reports false. A restarted worker preserves acknowledged commitments and identifies prior unclean sessions/outcome-less intents without relying on shutdown hooks.

Initial public proof covers forced process termination, not untested power-loss/storage-device behavior. R10 human-preserving generated views and actual native host event delivery/action mediation require their own later contract and evidence. Keep R06/R07/R09 coverage explicitly limited to the managed runtime until then.

## Freeze phases

Core freeze covers intake/TaskBook fidelity, restart replay/conflicts, checkpoint rollback, explicit task selection, exact brief binding, stale/forged/old-epoch acknowledgement denial, scoped revocation and immutable source access state. The separately frozen process supplement must prove actual child observation of committed prediction before external marker; abrupt kill before/after marker and restart; lost result persistence; concurrent same-ID dispatch; profile safety and real CLI JSONL routing. It must reject a wrong control that runs the child inside the prediction transaction or replays an outcome-less intent. No product source or frozen assertions may be changed by this acceptance author.
