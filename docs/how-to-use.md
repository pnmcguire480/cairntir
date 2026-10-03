# How to Use Cairntir

**Current release: 1.12.3.** [Publication and verification](release/v1.12.3.md).

## Install

You need Python 3.11+ and a shell. You do **not** need Claude Code
installed. Cursor, Codex, and Qwen Code are first-class hosts too.

```bash
pip install cairntir
cairntir setup
```

That one wizard initializes the store, wires every supported host it
can find at user scope, and prints the Cursor User Rule that Cursor
cannot install from a file. Missing CLIs are skipped, not fatal.

Then fully quit and reopen the host you use.

`uv tool install cairntir` and `pipx install cairntir` work the same
way. Contributors clone the repo and `pip install -e .` instead.

To wire a single host later:

```bash
cairntir init --host cursor --user    # or claude, codex, qwen, or all
```

Project-local Cursor setup (`cairntir init --host cursor`, no
`--user`) writes both the MCP config and the always-apply rule.
Cursor's **global** User Rule still has to be pasted into
**Cursor Settings → Rules → User Rules** — `setup` and
`init --host cursor --user` print the text to paste.

## Check it worked

The diagnostic changes described here are **unreleased**. Published 1.12.3 may
still run registration/update callbacks for doctor/status/version, and status
may open its store for writing. The read-only guarantees and new wording below
apply to the candidate in the [change record](CHANGE-STATUS.md), not to an
installation identified only by the unchanged version string.

```bash
cairntir version    # this CLI's version; current published release is 1.12.3
cairntir status     # where the store lives, drawer counts
cairntir doctor     # store and host wiring; see the installed-version note above
```

Open a task in your project and ask the agent to call
`cairntir_handoff(wing="myproject")`. It should return a tool receipt, not
merely describe Cairntir. Ask it to save a harmless, unique test task using
`cairntir_remember` with a checkpoint. Keep the actual save receipt, wing,
`task_id`, drawer ID and revision. Open a fresh chat and request
`cairntir_handoff(wing="myproject", resume=true, task_id="the saved ID")`.
Use `cairntir_get` for the acknowledged drawer ID to compare the exact saved
text, and check that the resumed task has the acknowledged current revision.
An offer to call a tool, an unsaved chat message, a stale task or an empty
result is not successful continuity. For ambiguity or unavailable memory,
check the task, intended store and access before writing a replacement.

`doctor` reports stored index/integrity and configuration observations. Its
`MCP=configured` means a matching configuration entry, while `live=unverified`
means this command has not contacted the host. Old receipts cannot prove a
current connection. Index metadata marked `verified` does not prove semantic
retrieval; test that separately through the actual client with a retrieved ID
and exact content. Setup's local write/read smoke check is likewise not a
host handshake or semantic recall test. Missing/skipped host setup and warmup
warnings still require attention even when the local store check passes.

`version`, `status` and `doctor` do not register hosts or run update checks.
They do not initialize a missing store. Status counts use a temporary read-only
snapshot and close it after inspection; this can take time on large stores.
Ordinary `doctor` exits 1 for a missing store. `doctor --gate` prints an explicit
SKIP and exits 0 there so pre-commit remains usable on fresh clones; that skip
is not a health pass. Damage or drift on a present gated store still exits 1.

For exact artifact identity, installation and rollback evidence, use the
[change and adoption record](CHANGE-STATUS.md). Keep separate intended personal
and work stores separate; a shared Git checkout is not database synchronization.

## Backups

These commands require Cairntir 1.12.1 or later.

Choose a backup directory, preferably on another drive:

```powershell
cairntir backup configure "E:\Cairntir\backups" --interval-hours 12
cairntir backup run
cairntir backup status
```

Configuration is stored beside the database and shared by hosts using that
database. Automatic backups are off until configured. Owner CLI, MCP, and capture
daemon stores check at writable startup and before an outer write transaction;
the snapshot contains committed state before that write. With Cairntir closed,
the next writable startup catches up. No scheduler or background service is
installed. Library callers opt in with `DrawerStore(..., automatic_backups=True)`.

Each snapshot is a complete SQLite database, including vectors, provenance and
task checkpoints. Cairntir verifies integrity and foreign keys before publishing
the database and checksum receipt. It keeps every managed snapshot from the last
seven days and the latest snapshot in each of four older ISO calendar weeks.
Pruning follows a successful backup and does not manage existing manual backups.

If the destination is unavailable, memory writes continue and a backup warning
is emitted. `backup status` reports the last successful snapshot, next due time,
active backup and last error. All backup commands return JSON; status does not
create files, load a model or trigger a backup. `backup run` requests an immediate
snapshot regardless of the interval. Concurrent automatic attempts share a lock;
an interrupted process releases it for a later attempt.

```bash
cairntir backup disable
```

Disabling preserves existing snapshots. Read-only and scoped sessions never
activate automatic backups. Existing mandatory migration and reindex backups
remain in place independently of this policy.

To recover, stop every client using the store, preserve the current database and
its sidecars separately, and verify the selected snapshot against its checksum
receipt. Restore the verified database to the path reported by `cairntir status`
with no stale WAL or journal files beside it. Reopen Cairntir and run
`cairntir doctor --gate`. A complete database snapshot needs no reindex.

## The four words

1. **Wing** — a project.
2. **Room** — a topic inside a project.
3. **Drawer** — one verbatim memory.
4. **Layer** — identity / essential / on_demand / deep. Default writes
   land on `on_demand`. That is why agents start with **handoff**, not
   `session_start`: handoff still returns recent default-layer
   memories; `session_start` does not unless you pass a query.

## What you type as a human

The installed policy asks agents to read and write memory. You can also
inspect and recover context directly:

```bash
cairntir recall "database decisions" --wing myapp
cairntir handoff myapp
cairntir handoff myapp --task "repair cache invalidation" --budget 8192
cairntir recover --host codex --wing myapp
cairntir cost myapp
```

Transcript recovery is opt-in. Use `recover`, or add `--recover-from codex`
to `handoff`, only when you want Cairntir to inspect the host's newest
non-live transcript tail. Qwen Code, Claude Code, and Codex are supported.
Cursor returns an unsupported receipt rather than guessing at undocumented
SQLite tables. Recovered text is untrusted evidence and is never stored unless
you explicitly pass `--write N` to `recover`.

With `--task`, handoff selects current relevant evidence and returns JSON with
provenance, exclusion and conflict receipts, and an explicit abstention when
nothing matches. The character ceiling covers the complete response, including
CLI and MCP result wrapping. Task selection uses cached local embeddings and
does not update access state or download models. Run transcript recovery as a
separate request when using task mode. `--candidate-limit N` bounds the initial
candidate scan and discloses incomplete scans in the result.

Try the [isolated continuity demo](context-demo.md) to inspect exact recalled
requests, excluded stale evidence, and measured payload sizes across store sessions.

## Bound a recall response

In 1.13.0, callers of the existing `cairntir_recall` MCP tool can request a
complete-response character ceiling. For example, send these tool arguments:

```json
{"query":"database decisions","wing":"myapp","limit":10,"full_content":3,"budget_chars":8192}
```

The response text is JSON with schema `cairntir.recall-budget.v1`. Each entry
in `evidence` contains the whole original `content`, UTF-8 `content_sha256`,
complete `provenance`, `drawer_id`, source location and `supersedes_id`.
Retrieved text has `instruction_authority: "none"`; importing or recalling
evidence does not make it an instruction. Existing access scope still applies.

`full_content` selects how many of the top search hits are eligible for whole
delivery. An oversized hit is omitted whole; a later eligible hit may still fit.
The default `full_content: 0` produces routing IDs without snippets. To request
usable evidence in the first call, set a positive `full_content` explicitly.
Ranking and the existing search provider are unchanged.

Read `status` and `omitted` before treating a response as complete:

| Field | Meaning |
| --- | --- |
| `status: "complete"` | Every returned search hit is included; also used for zero matches. |
| `status: "partial"` | Some whole evidence is included and some matched hits are omitted. |
| `status: "omitted"` | Matches exist, but no whole evidence is included. |
| `omitted.count` | Number of hits withheld from this search result, including routing-only hits. |
| `omitted.drawer_ids` | Source IDs retrievable with `cairntir_get` using `drawer_id`. |
| `omitted.ids_complete` | False when the ID list itself could not fit. The total count remains exact. |

The counts refer to the search result up to `limit`, not every matching drawer
in the database. To obtain omitted evidence, request selected IDs or repeat a
focused recall with a larger budget. A `cairntir_get` response has no inherited
recall budget. If the ID list is incomplete, narrow the query or increase the
budget rather than assuming unseen hits do not exist.

`budget_chars` must be an integer from **1,024 to 262,144**, inclusive. Null,
booleans, fractions, strings and out-of-range values are errors. Successful
bounded responses fit `len(CallToolResult.model_dump_json())`, including JSON
escaping, provenance, omission receipts and the MCP result envelope. The outer
JSON-RPC frame is excluded. Error responses are surfaced, not successful bounded
evidence. Characters are not tokens, wire bytes, latency or a billed-cost guarantee.

Bounded calls do not echo the query or append an update banner. They report
`notification_policy: "excluded"`; a later eligible legacy call can still show
the usual once-per-session notice. Omitting `budget_chars` retains the existing
text/snippet behavior. This option is an MCP feature; the CLI recall command
retains its existing interface.

## Recovering after compaction

The shared host policy asks agents to save each multi-step request before work,
then checkpoint after an implementation step, verification result, changed
decision or blocker, before starting the next work block. Corrections and new
constraints are captured as they arrive. Each checkpoint preserves completed
and outstanding work, the next action, changed files and verification evidence.

After compaction or lost continuity, the policy asks the agent to resume its
saved task and compare the checkpoint with current working state before further
task reasoning or actions. The saved wing and task ID select the same task
even when the checkout folder changes. Ambiguous tasks require selection;
terminal tasks stay closed, and unavailable tasks require checking identity
and access. Corrections belong in the same task's checkpoint content and
outstanding work. Missing progress must be investigated or clarified.
Other saved tasks do not authorize work outside the current conversation.

This is an instruction to the host agent, not a compaction detector or an
automatic transcript recorder. Recovery depends on acknowledged writes and the
agent following the policy. With an older server that lacks checkpoint/resume
arguments, agents save ordinary request and progress memories and disclose that
structured task resumption requires an upgrade. Version 1.10.0 has that older
surface; checkpoint/resume support and the policy ship in 1.11.0. Restart or
reconnect existing host sessions after upgrading so they load the new tool schema.
See [task resumption](task-resumption.md) for the complete workflow.

## Bounded hotfixes

Use `cairntir_hotfix` when a repair must follow an explicit, inspectable order:
open the observed failure, compare evidence-cited candidates, authorize one
exact candidate, record an independent preflight, let the host perform one
attempt, then record independent verification or an exact rollback. Follow the
`legal_actions` returned by every receipt.

```bash
cairntir hotfix status --wing myapp --case-id hf-abc123
```

Mutating actions also require `--idempotency-key` and an action-specific JSON
`--payload`. The MCP tool exposes the complete discriminated payload schema.
Cairntir does not run the repair, sign the authority, or prove that a caller's
identity is independent; it preserves those claims and rejects out-of-order or
binding-mismatched records. See the
[Bounded Hotfix recipe](recipes/bounded-hotfix/README.md).

## Day 30

You open a fresh chat in a project you have not touched in three
weeks. The installed policy tells the agent to call
`cairntir_handoff(wing)` first. It gets whole drawers under a budget:
the protocol, the last session deltas, open questions, and memory
anchored to the files in play. Then you ask your question.

That is the North Star. Details live in the repository README.

## Troubleshooting

- **Tools appear, agent never uses them.** The MCP server is wired
  but the policy is missing. Re-run `cairntir setup`, and if you are
  on Cursor at user scope, paste the printed User Rule.
- **`cairntir setup` warned that `claude` is not on PATH.** Expected
  on a Cursor-only machine. Cursor and Qwen still got wired.
- **Wrong Python / venv.** `cairntir init --user --force --host all`.

File a bug at
[github.com/pnmcguire480/cairntir/issues](https://github.com/pnmcguire480/cairntir/issues).

## Embedding identity and explicit rebuilds

The unpublished 1.14.0 candidate binds semantic indexes to model/tokenizer bytes
and runtime versions. Existing name-only indexes require an explicit backed-up
rebuild; raw recovery remains available. Read the [operator guide](embedding-artifacts.md)
before upgrading.
