# R10 — generated Last Session

Current port checkpoint (2026-10-03): isolated R08-based candidate; fresh full/installed qualification and native acceptance remain pending. The implementation and verification sections below describe preserved historical evidence, not qualification of this new candidate. The fresh port repairs caller-transaction receipts/projection and refuses close when the selected task evidence is unavailable. See [usage and limits](../docs/managed-sessions.md).

Generate a view of recorded managed-session events and the current authorized
task checkpoint. The raw memory and committed lifecycle receipts remain the
authority; this file can be rebuilt. This implements the approved R10 projection
slice alongside the [managed runtime](v2-managed-runtime.md).

## Explicit projection

`cairntir.managed_projection.project_last_session(store, *, root, path, wing,
session_id, epoch)` accepts an existing owner or scoped store and explicitly
selects a committed managed epoch. Both paths must be absolute, the root must
exist, and the target must remain inside that root. It does not start a runtime,
create a brief, change an epoch, consume an acknowledgement or update access
counters. It works after closing and reopening the store.

The returned `cairntir.managed-projection.v1` receipt has `status=complete` with a
structured snapshot and generated-block SHA256, or `status=error` with a surfaced
diagnostic. It displays exact original, completed, outstanding and next-action
text, sequence gaps, pending capture hashes, missing close records and uncertain
actions. Deferred descriptions remain outstanding until an explicit checkpoint
changes them. A successful command is not inferred to complete a user commitment.
Missing final producer watermarks leave the undelivered tail explicitly unknown.

Source links use `cairntir://drawer/ID` with visible portable UUID and exact
UTF-8 SHA256. Checkpoint metadata, committed session receipts, dispatch intents
and actual outcome evidence must agree; inconsistent required evidence refuses
projection. The current authorized checkpoint is read at render time. Identical
recorded inputs produce identical output across restart; later recorded changes
can update the view.

## Human notes and failure

The existing Cairntir generated-block markers delimit the only owned content.
Every human byte outside them survives, including Unicode and mixed line endings.
Existing files with missing, duplicated or reversed markers are refused unchanged.
Source text containing a reserved marker remains exact in raw memory/snapshot
and is escaped only for the Markdown view.

Commit capture/close first, then explicitly project. A filesystem failure cannot
roll back those committed records. Retrying projection regenerates the file
without replaying the lifecycle or appending more drawers. Automatic CLI/host
projection and implicit CLAUDE.md rewrites are not part of this API.

## Verification

The [public acceptance packet](acceptance/v2-managed-projection/README.md)
preserves eleven original cases and five separately frozen source-consistency
cases. The first candidate passes the initial runnable cases but fails three
new witnesses: inconsistent checkpoint metadata, altered close completeness and
an outcome assigned to the wrong action. One projection repair fixes those
bindings. All failures and original frozen bytes remain saved.

Fifteen cases pass; one Windows symlink fixture is explicitly skipped because
the test process lacks creation privilege. Deliberate brief-write, lost-human-note
and false-completeness controls fail their expected assertions. The maintained
wrapper verifies all 35 immutable package files and imports the unchanged tests
against canonical production modules; all 35 tampering controls are rejected.

A separate combined check repeats all sixteen cases and the maintained wrapper
against managed-runtime repair2 (`301eefc5`) and projection repair1 (`53fa5cc2`),
again yielding fifteen passed and one skipped. The earlier dependency receipt
remains historical evidence. The combined source, repository and installed gates pass; see
[the shared verification record](v2-managed-runtime.md#final-combined-verification). Native graphical Obsidian, coding-host event delivery and protected
evaluator custody are not certified by these public checks. At most two product
repairs and a 25% verification reserve apply; one projection repair was used.
