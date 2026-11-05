# Codex managed sessions

`cairntir codex-managed` connects one foreground Cairntir task to a persistent
Codex conversation. Each new action starts a separate app-server, delivers the
whole current task brief, validates the actual model's structured acknowledgement
and closes the server before the existing managed dispatcher runs the configured
action. Later turns cold-resume the observed native thread and verify the prior
turn's stored acknowledgement.

Create a trusted JSON file with exactly `schema`, `runtime` and `host`.
Use schema `cairntir.codex-managed-cli.v1`. `runtime` is the existing
[managed configuration](managed-sessions.md). `host` has these exact fields:

| Field | Value |
| --- | --- |
| `schema` | `cairntir.codex-managed-config.v1` |
| `executable` | Absolute path to the reviewed Codex executable. |
| `codex_home` | Existing private home containing the operator's native configuration/authentication. |
| `cwd` | Existing absolute project directory. |
| `model` | Explicit model identifier. |
| `timeout_seconds` | Integer 1–120 for each owned native server. |
| `output_limit_bytes` | Integer 1–1048576 per native output stream. |
| `env` | Explicit string/string host environment. |

Prepare the private home and its authentication outside the adapter. It does not
copy credentials, install hooks or change production settings. Only the basic
OS process environment is inherited; provide private HOME/USERPROFILE,
APPDATA/LOCALAPPDATA, temporary/cache directories and required host settings in
`env`. CODEX_HOME is bound to `codex_home`. Keep native hooks, apps, MCP servers
and project instruction loading disabled for this text-only acknowledgement
profile. Do not share its private credentials, logs or native conversation files.

Start an explicitly selected existing task:

```text
cairntir codex-managed --config bridge.json --session-id SESSION_UUID --task-id TASK_UUID
```

The first JSON line is the normal kernel brief; startup performs no inference.
Then send strict JSONL objects with schema `cairntir.codex-managed-command.v1`,
an `operation` and `request`. Operations are `capture`, `turn`, `status` and
`close`. Capture/status/close use the existing managed request shapes.

A `turn` request has exactly schema `cairntir.codex-managed-action.v1`,
`action_id`, `profile`, `claim`, `predicted_outcome` and nonempty `event_ids`.
The adapter obtains the actual native ACK and supplies the committed kernel
`ack_id`; callers cannot provide a replacement ACK, command or per-turn model.
Missing/incomplete task evidence prevents inference. Invalid or stale native
responses cannot authorize an action. Capture or checkpoint changes require a
new current acknowledgement.

An exact same-controller completed retry uses the kernel's live historical
status without another model call or effect. Changed payloads under that action
ID fail. After a controller restart, inspect existing actions with `status`;
the new controller cannot invent their native binding. The current controller
retains its native thread identity; a new controller recovers Cairntir's task
through a fresh native conversation.

Receipts distinguish `native_codex` from an explicitly injected local-test
transport. They join the current brief, model ACK, committed kernel ACK and
actual action receipt. They prove protocol acknowledgement, not comprehension.
SDK/provider retries may cause multiple network or billable attempts inside one
logical turn; the adapter does not add automatic model retries.

This boundary gates its configured managed actions. Unexpected ordinary native
tool activity fails the text-only profile and triggers cleanup; detection does
not prove prevention or undo native reads. Native image capability is unqualified.
Private evaluator custody, other host integrations and release qualification
remain separate.
