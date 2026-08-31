# Phone-to-PC Continuity Bridge

**Status:** Proposed. Documentation only; no implementation or release is
authorized by this plan.

**Field case:** A guitar-research conversation began on a phone, where the
original intent and source material remained available. A reduced handoff then
reached PC Codex. Work continued from that derivative account, the user noticed
drift, and the complete phone conversation had to be pasted over as a repair.
Useful PC work may still exist, so repair must distinguish unsupported additions
from independently sourced ones rather than discarding either side wholesale.

This plan preserves the product decisions and failure evidence from that
conversation. It is not a public dump of private chat or incidental personal
details.

## Decision in one sentence

Keep the PC-side Cairntir store as the single writer; use the phone as a control
surface; move exact, bounded intake records instead of synchronizing the live
SQLite file; and reconcile those records with project artifacts through an
inspectable, approval-gated diff.

## Requirements preserved from the conversation

- The bridge must feel simple, cohesive, and coordinated across phone and PC.
- The original source controls intent. A handoff or summary is derivative and
  must not silently override it.
- Routine output must be tiny. The user can provide long input, but should not
  pay repeatedly for the system to narrate the entire project back.
- A fresh PC session must continue without the user rebuilding context by hand.
- Cairntir may coordinate research and code work without becoming a second
  project manager or scattering its memory through source files.
- Drift, uncertainty, and contradictions must be exposed rather than repaired
  with invented connective material.
- Matt Pocock and Andrej Karpathy are design influences only where the repository
  has recorded lineage. Their useful habits should appear as behavior, not
  decoration or uncredited copying.

## What Cairntir already does

Cairntir already gives Claude Code, Codex, Cursor, and Qwen Code one canonical
local database, index, taxonomy, and MCP contract. Its deterministic handoff
loads whole drawers within a budget. Transcript recovery returns bounded,
untrusted evidence and never stores it automatically.

That solves continuity among supported hosts which can reach the same PC-side
store. It does not solve a ChatGPT phone conversation created outside that
boundary.

Cairntir also supports verified file anchors and read-only recall around a
changed path. It does **not** currently write arbitrary research trees or code
trees. Obsidian projection/import is a special, explicit boundary, not a general
repository adapter.

## Authority and ownership

| Material | Authority |
|---|---|
| Exact user input | Controlling evidence for the user's intent, constraints, preferences, and decisions |
| Verified primary/external source | Evidence for factual claims within its actual scope |
| Assistant-written research | Derived and untrusted until its claims are traced to checked sources |
| Cairntir drawer | Verbatim memory and provenance; new phone intake begins as proposed/untrusted |
| Handoff or summary | Derived navigation aid; never overrides its source |
| Research tree | Canonical accepted claims, sources, contradictions, and research decisions |
| Code repository | Canonical code, tests, specifications, decisions, and repo-local instructions |
| Git history | Reviewable mutation record, attribution, and rollback |
| Code comment | A local invariant needed to understand the code; never a hidden conversation log |

Do not give the same fact competing canonical authority in SQLite and a project
tree. Cairntir keeps the verbatim intake, source pointers, file anchors, hashes,
and receipts. The tree keeps the accepted project artifact. A repository must
remain understandable and usable when Cairntir is absent.

## Two transport lanes

### Lane A: live remote control

Prefer an existing remote-control path when the phone can drive the same
PC-hosted Codex workspace. OpenAI documents [Codex remote
connections](https://learn.chatgpt.com/docs/remote-connections) and a
[remote engineering workflow](https://developers.openai.com/blog/mastering-codex-remote-for-engineering).
In that path, the PC host performs normal Cairntir capture; the phone does not
open or copy the database.

Remote control is transport, not authority or memory. The exact request still
needs a successful PC-side capture receipt. Availability on the user's actual
phone, account, and PC must be tested before this lane is treated as solved.

### Lane B: disconnected intake

When a shared live session is unavailable, exchange one bounded, idempotent
intake envelope. GitHub is a reasonable first transport to test because this PR
demonstrates that a phone conversation can produce a reviewable repository
artifact. The protocol must remain transport-neutral and local-first; GitHub
cannot become a required Cairntir service, and raw private transcripts must not
be committed to a public repository by default.

The existing portable JSONL format is useful precedent, not an assumed drop-in
bridge. Its safety rules intentionally reject URL-bearing drawers, while
source-heavy research commonly contains URLs. Phone intake needs a separately
specified contract or a separately justified format change.

Never synchronize an active SQLite file through Drive, Dropbox, Git, or another
generic cloud-sync folder. The one PC-local Cairntir store is the sole
cross-device write authority, even when several supported local hosts reach it.
Transports carry records, not the database.

## Candidate host-protocol record

This is vocabulary for an experiment, not a Cairntir core command, MCP tool,
state machine, repository workflow, or persistence commitment:

```yaml
schema_version: 1
intake_id: immutable-id
wing: cairntir
room: phone-pc-continuity
operation: capture        # capture | reconcile | apply
authority: proposed       # proposed | accepted
base_revision: git-sha-or-null
source:
  kind: phone-conversation
  locator: local-or-opaque-reference
  sha256: optional-source-hash
body: |
  exact user delta (whole or omitted; never model-summarized)
```

`intake_id` supplies an idempotency key; it does not make retries safe by itself.
Safety also requires durable uniqueness, a retained receipt, defined replay
behavior, and a pre-registered retry test. `base_revision` exposes stale writes.
The body preserves the user's complete delta instead of asking a model to
regenerate it. Routine follow-ups may carry only the exact user request needed
for continuation, whole or omitted.

First reconciliation after a failed handoff needs more than the latest delta.
It requires the exact conversation or a bounded manifest which points to the
complete retained evidence:

```yaml
evidence_bundle:
  conversation:
    locator: local-private-reference
    sha256: source-hash
  items:
    - role: user          # user | assistant | external-source | artifact
      kind: decision     # intent | decision | claim | citation | artifact
      locator: source-location
      sha256: item-hash
```

The bundle may point to a full locally retained source instead of placing it in
Git or loading it into every prompt. Bounds limit the number and size of items
loaded at once; they never slice or model-summarize an evidence item. User turns
control intent. Assistant research remains derived. Cited factual claims become
usable only after the cited source is checked.

Cairntir's current core boundary remains verbatim memory, provenance, retrieval,
and recall. The labels below are candidate records at the seam between the user,
the host, Cairntir memory, and project artifacts. They are not built-in Cairntir
commands or a project workflow. An external host/repository bridge, such as
Codex, owns project-file inspection, diffs, checks, and Git operations. Cairntir
may remember the exact intake and resulting receipt without managing the work.

The three candidate operations are deliberately different:

- **CAPTURE** asks Cairntir to preserve a proposed intake and provenance. It
  changes no canonical project artifact.
- **RECONCILE** asks the external bridge to compare the role-aware evidence
  bundle with current project state, classify material as matched, missing,
  conflicting, independently sourced, or unsupported, and return a receipt for
  memory.
- **APPLY** asks the external bridge to prepare a bounded branch diff against a
  known revision, run the relevant checks, and require explicit user approval
  before accepted artifacts change. The resulting receipt may be remembered.

No proposed material may promote itself to accepted. Conflicting sources or base
revisions block `APPLY` rather than inviting an agent to guess.

## Low-token receipt

On a routine success, return the change, not another handoff dossier:

```text
Captured: 1 proposal
Target: guitar-research / roadmap
Base: 7c41a9e
Conflict: none
Next: review
```

The experiment should target at most 80 output tokens for a successful routine
receipt. A blocking conflict may use more, but only to identify the conflict and
the choice required. Detail stays on demand.

## Research-tree behavior

A future host-side bridge may update a project's existing research artifacts,
but only as an explicit projection into that project's authority model. It is
not a Cairntir-owned wiki or graph. The accepted [next-map
boundary](next-map.md) currently rejects Tier 3 wiki behavior;
reopening that boundary requires a separate accepted plan. A bridge should:

- preserve source identity and distinguish verbatim evidence from synthesis;
- separate user decisions, sourced claims, hypotheses, and agent suggestions;
- attach provenance to factual claims;
- mark contradictions and missing support instead of filling gaps;
- update only affected pages and links; and
- show a proposed diff before ambiguous material becomes canonical.

## Code-tree behavior

A future host-side repository bridge must first obey the repo's existing
instructions, tests, plans, and decision records. It should add the smallest
missing structure only after approval. The host creates repository changes on a
branch, with a diff and checks; Cairntir retains the intake ID and compact
receipt.

Cairntir should not put conversation history, model prompts, developer names, or
general development philosophy into unrelated code comments. A useful comment
states a local invariant, for example:

```ts
// Stable ordering is required because this output is hashed downstream.
```

Coordination belongs in repo-local instructions, plans, decisions, tests, or
research artifacts—not in decorative comments.

## Guitar-research reconciliation

The current guitar research is the first field test:

1. Record the current PC branch, commit, research tree, and roadmap without
   changing them.
2. Preserve the exact phone conversation or its complete role-aware evidence
   manifest; user turns control intent, while assistant findings remain derived
   until their cited sources are checked.
3. Compare requirements, exclusions, claims, citations, checked sources, and
   roadmap decisions.
4. Classify every material difference as matched, missing, conflicting,
   independently sourced, or unsupported.
5. Produce a review report and proposed patch. Do not overwrite the tree.
6. Let the user settle conflicts and accept or reject PC additions.
7. Have the host apply accepted corrections on a branch, run project checks,
   and open a PR.
8. Store the verbatim intake, accepted revision, provenance, conflict state, and
   compact receipt in Cairntir.
9. Resume the research roadmap only from that accepted baseline.

This procedure preserves valuable PC research while preventing a plausible
agent-written bridge from being mistaken for original intent.

## Design influences and attribution

The existing [Matt Pocock lineage
note](../docs/lineage/mattpocock-skills.md) credits a shared vocabulary and
scopes a possible glossary drawer. Progressive disclosure and other Pocock
workflow ideas raised in the conversation are new source-assessment candidates,
not covered by that lineage note. Adopting them requires an attribution update
before implementation.

The accepted [evolving-mind plan](evolving-mind.md) already records
the repository's Karpathy-derived principles: small details and tight
experimental loops, prediction-bound work, surprise/delta, evidence from
repeated use, and simple measurable mechanisms. AutoResearch-shaped
single-target keep/reject loops raised in the conversation would be a new source
assessment, not an existing Cairntir lineage claim.

If later implementation imports another person's named concept, benchmark,
prompt, or code, its lineage document must land before the code.

## Pre-registered acceptance bar

Before implementation, test both transport lanes against the actual phone and
PC setup. Accept a bridge only if:

- a fresh PC session recovers the exact requested delta without a manual
  re-brief;
- the phone never writes or synchronizes the live SQLite database;
- retrying the same intake does not duplicate drawers or project mutations;
- every applied change traces back to an intake ID and controlling source;
- unsupported and conflicting material is blocked, not smoothed over;
- repository changes are bounded, reviewable, checked, and reversible;
- the repository remains usable without Cairntir;
- a routine success returns a compact delta receipt; and
- a weaker or cheaper model can continue from the accepted state without
  reconstructing hidden context.

Reject a design that requires a cloud subscription for core Cairntir operation,
copies the live database, makes a summary authoritative, silently edits project
trees, stores memory in source comments, or costs more output than the handoff it
replaces.

## Implementation order

1. Run a read-only audit of the actual guitar research and current Cairntir
   interfaces.
2. Test the documented remote-control lane on the user's phone/account/PC.
3. If that lane is unavailable or insufficient, specify the transport-neutral
   intake and receipt schemas without changing persistence.
4. Add capture-only ingestion, then let an external host bridge perform dry-run
   reconciliation behind explicit user action.
5. Run the guitar field test and settle its conflicts.
6. Consider host-owned, branch-based `APPLY` only after the capture/reconcile
   evidence is good enough.

There are no `cairntir-commitments` in this proposal. Implementation requires a
ratified plan, attribution review, and pre-registered tests first.
