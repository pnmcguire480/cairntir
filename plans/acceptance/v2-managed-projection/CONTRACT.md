# R10 public projection contract v1

Independent public acceptance before projection implementation. Authority is the
approved baseline `v2-design-2026-09-20-r1` and the user's `begin` instruction.
The approved R10 says: “Generate the Last Session view from recorded
events/checkpoints with source links.” Its closing criterion is: “Regeneration
reproduces completed/outstanding work; retained human notes survive and missing
events are visible.” Historical source S0033:223 requests generation from a
structured log instead of manually accurate CLAUDE.md. Managed DESIGN-NOTES
supplies proposed implementation detail, not a new source of approval.

This slice qualifies a rebuildable view of recorded managed events. It does not
install coding-host hooks, automatically rewrite CLAUDE.md, prove native Obsidian
interaction, recover never-submitted bytes or certify private evaluator custody.
Raw memory and dedicated committed lifecycle receipts remain authoritative.

## Minimal public seam

`cairntir.managed_projection.project_last_session(store, *, root: Path,
path: Path, wing: str, session_id: str, epoch: str) -> dict`.

Select an existing committed managed epoch and its task explicitly. The store
may be owner or scoped; enforce its current read access and whole required
evidence visibility. Wrong session/epoch/wing, unavailable or corrupt required
evidence fails visibly rather than inventing an empty or complete session.
Root and target are absolute; target is confined to the resolved root. Reject
symlink/reparse escapes. Rendering never starts a ManagedRuntime, creates a brief,
changes epoch, consumes an acknowledgement or writes any SQLite row/access
counter. It must work after closing and reopening the store without a runtime.

Return schema `cairntir.managed-projection.v1`, status `complete` or `error`.
Success includes `snapshot` and `generated_sha256`. Failure includes nonempty
`error`, preserves any existing target bytes, and cannot undo already committed
capture/checkpoint/close. A caller retries this function with the same selection;
only the filesystem projection is regenerated, no lifecycle operation repeated.
This is explicit close-then-project composition, not automatic CLI projection.

## Snapshot and authority

Snapshot schema `cairntir.managed-last-session.v1` includes:

- `wing`, `session_id`, `epoch`, `task_id`, current task `revision`, exact
  `original_request`, `completed`, `outstanding`, `next_action`.
- `last_received_sequence`, nullable `declared_last_sequence`, `gaps` (known
  absent sequence numbers), `capture_complete`, `unknown_tail`, `close_status`
  (`closed` or `missing`), `pending_captures` and `unclean_sessions`.
- `uncertain_actions` containing at least action_id and prediction_drawer_id,
  plus `sources` of `{drawer_id, source_identity, content_sha256}`.

Completed/outstanding descriptions retain exact UTF-8 strings and ordering from
the authoritative task checkpoint. Deferred items remain exact outstanding
descriptions; no heuristic parsing creates a new commitment or completion.
A successful process exit does not resolve an outstanding user commitment.
Use the current authorized checkpoint at rendering time; later checkpoint/event
changes may update the view. Identical recorded inputs produce identical bytes,
including across store restart; no wall clock or freshly generated identifier.

An absent durable close means `close_status=missing`, capture_complete=false and
unknown_tail=true. It is not proof of a crash. Close without final producer
watermark also leaves unknown_tail=true. Explicit matching watermark may make
unknown_tail=false while a known gap/pending failed claim keeps
capture_complete=false. Unknown tail must never be displayed as zero lost events.
Include all recorded pending capture SHA keys, and unclean epoch records in scope;
do not erase another epoch's missing close because this epoch closed cleanly.
Internal committed event epoch binding is legitimate evidence of its selected
task before the first ready brief; arbitrary metadata is not lifecycle authority.

Sources include the immutable original request, current checkpoint and selected
captured-event drawers, plus prediction drawers for uncertain actions. Bind each
source to its real portable UUID and SHA256 of exact UTF-8 content. Markdown must
display direct `[drawer #ID](cairntir://drawer/ID)` links and visible identity/hash
bindings; do not fabricate links to filesystem notes that do not exist. The
renderer must not call access-counting get to obtain them. Inert forged memory
metadata cannot hide missing events or resolve uncertain actions.

## Generated block and preservation

Use the existing owned delimiters `<!-- cairntir:generated:begin -->` and
`<!-- cairntir:generated:end -->`, exactly once each in that order. New targets
may be created. Existing targets without exactly that one pair reject unchanged.
Preserve every byte before the begin delimiter and after the end delimiter,
including BOM if present, Unicode, CRLF/LF mixtures and no trailing newline.
Only the owned block is replaced. UTF-8 source text containing delimiters remains
exact in snapshot/raw memory; escape it in Markdown so it cannot create another
owned block. Ordinary content must remain visibly faithful, including CRLF.
`generated_sha256` binds the exact UTF-8 bytes between the two delimiters.

File creation/replacement is atomic. A refused/unwritable target surfaces an
error; previous bytes survive. No database rollback or fake successful projection.
Existing `_upsert_generated` may be reused if all these constraints are met.

## Frozen proof and limits

Use disposable real HashEmbeddingProvider stores and actual TaskBook/managed
receipts. Cases cover checkpoint fidelity/deferred text/source binding, bytewise
human preservation, deterministic read-only restart regeneration, missing close
and unknown watermark, sequence holes and failed claims, uncertainty after a
committed dispatch intent, malformed ownership delimiters, reserved-marker source
text, confined target and wrong epoch/wing, and file failure after durable close
followed by regeneration with no appended records. A separately reported baseline
RED against absent projection module is expected, not product evidence.

Wrong controls to execute after implementation: a renderer that invokes brief()
must fail the read-only test; dropping human suffix bytes must fail preservation;
declaring an absent close complete must fail the unknown-tail witness. Frozen
assertions stay immutable. Maximum two product repair rounds, at least 25% effort
reserved for verification. Shared-workspace tests are public and tester-authored,
not hidden or protected holdouts. Actual installed rendering is a later gate.
