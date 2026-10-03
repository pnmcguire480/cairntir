# Managed foreground runtime and explicit Last Session port

Freeze the whole existing managed-session protocol plus its explicit projection,
independent of the active R18 lane. The qualified R08 source is the platform base;
fresh candidate/source bindings precede any execution. No product implementation
or tests execute during this preparation phase.

The authoritative historical runtime input is the preserved pre-native-capture
`managed.py` SHA256 `301eefc5c2593f3fa466c06d84b0384dfd92294aee2e015ac68b967d82585f30`.
The projection input is SHA256
`53fa5cc28d256a434d181a96d82b3a87534acc5eb6710236b6bcf6b44bad4df8`.
The later native Codex source branch is separate work.

Port the complete runtime: start, capture, brief, acknowledge, dispatch, status,
close, and the existing fixed-profile JSONL CLI. Preserve exact committed event
and checkpoint content, request-bound replay, selected task/current epoch,
configuration identity, pre-action durable intent, at-most-one managed launch,
bounded output, uncertain lost outcomes, failed captures, close watermarks and
prior unclosed epochs. Explicit Last Session projection reconstructs committed
history/current authorized checkpoints while preserving every external human
byte, exposing incomplete capture and refusing inconsistent evidence.

Keep unchanged all historical core12/process10/close4/config1/state1 controls,
runtime outcome11 and projection11/corruption4/outcome1/supplement4 controls.
Their archives, freezes, failures, repairs, wrong controls and source receipts
remain byte-identical history. The combined outcome wrapper currently imports
projection tests; fresh maintained routing must preserve all 15 cases. Two original
production-cache CLI tests retain their explicit prerequisite and are qualified
through existing hosted infrastructure; no local model construction or installation.

The platform already has TaskBook, workflow transactions, owner/scoped authority,
`transaction_active`, and human-preserving generated-block support. Runtime needs
only its dedicated authenticated `_managed_records` owner/scoped readers, module
and explicit CLI. Projection adds its module. No dependency, schema, MCP tool,
live hook, scheduler, native host capture or automatic file rewrite is added.

## Fresh durable boundary controls

Twenty cases cover owner/scoped facade, explicit/raw caller transaction, and each
database-writing boundary: start, capture, brief, acknowledgement and close.
They must refuse with `ManagedRuntimeError` before lifecycle writes or durable
receipt, leave the caller's transaction/work intact, keep an independent full-schema
SQLite observer unchanged, and roll back exactly. The same prepared operation
must succeed after caller rollback and be immediately visible to that observer.
This also detects prematurely consumed start/close state. Dispatch's existing
owner/scoped outer-transaction controls remain unchanged.

Four cases cover owner/scoped projection inside explicit/raw caller transactions.
A valid public TaskBook checkpoint is appended within caller-owned work. Projection
must return its existing error receipt before publishing uncommitted state, leave
the prior human-preserving view and every database row intact, and omit success
snapshot/hash fields. Caller rollback restores the exact independently visible
baseline; a stable projection retry reconstructs identical bytes without writes.

Observers load sqlite_vec solely to read the complete existing physical schema.
These fixtures use HashEmbeddingProvider, isolated homes/caches, deny external
process/network calls, and never invoke the inert configured profile. Bounded
serial groups are coordinated with root; no full coverage/suite/model run locally.

## Deliberate controls and qualification limits

Replay the existing independent pre-action oracle's uncommitted denial/committed
positive and outcome-less replay-guard negative control after fresh source binding.
Its forbidden second external marker must fail the unchanged assertion. Retain
the original output-limit and human-byte/false-completeness projection controls.
The new inert ambient-guard control temporarily reports `transaction_active=False`
only during a guarded method invocation in an isolated interpreter; it must fail
an unchanged new receipt/refusal assertion, with no original source/test edits.

These are public synthetic managed-process and file contracts. They do not close
automatic supported-host delivery, prove comprehension, certify private evaluator
custody, contain arbitrary descendants, or prove exactly-once external effects.
Existing fresh hosted/installed qualification remains required. Reserve 25% for
verification and at most two product repair rounds for this new port; historical
repairs are preserved, never relabelled. No new review gate is introduced.
