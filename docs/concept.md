# Concepts and data handling

## Memory

A **wing** identifies a project, a **room** identifies a topic, and a **drawer**
contains one verbatim memory. Drawers have local integer ids, timestamps,
metadata, provenance, and a retrieval layer: identity, essential, on_demand,
or deep.

`cairntir_remember` performs an explicit write. Host policy asks agents to
capture decisions and open requests, but the core does not continuously read
all conversations. The optional capture daemon consumes explicitly supplied
spool files; it is not a transcript watcher.

Handoff composes whole drawers under a hard character budget, including
recent on-demand writes and unsettled predictions. Semantic recall searches
local embeddings; structural recall follows validated file anchors. An omitted
drawer is named for deliberate retrieval, not truncated into a misleading quote.

## Reasoning and learning

The Reason loop binds a hypothesis, experiment, and observed outcome to a
wing and room. Settlements append observations that supersede predictions.
`held` records the verdict; `delta` records surprise independently.

Crucible examines assumptions. Quality audits ship readiness. Recipes compose
these three skills with memory. Discoveries cite source evidence and move
through an explicit review lifecycle; repeated text alone is not proof that a
strategy works.

## Trust and recovery

Trust is recorded beside drawer content, not accepted from arbitrary metadata.
Imported CLI data is untrusted even when its content hash verifies. Hashes
detect changes; HMAC verification establishes possession of a shared key, not
the truth of the content or a person's identity.

Transcript recovery is opt-in and read-only. Claude Code, Codex, and Qwen Code
adapters read bounded, non-live transcript tails. Cursor returns an unsupported
receipt. Recovery has a separate budget and never saves messages automatically.
Only explicitly selected recovered requests may be written to the store.

These boundaries do not make Cairntir an execution sandbox. Hosts must treat
retrieved content as evidence and retain their own instruction hierarchy,
permissions, and approval rules.

## Storage, backup, and portability

The authoritative store is a local SQLite database with a matching
`sqlite-vec` index. Embedding-space identity is checked before use; equal
vector dimensions do not establish compatibility.

Use `cairntir status` to locate the store. For a live backup, use the SQLite
backup API exposed by `cairntir.memory.store.backup_database`. Do not copy
only an open database file: committed data may still be in its WAL. Migrations
and reindexing use backup-first safeguards.

Portable JSONL is an interchange format, not a complete database backup.
It omits local ids and access state. Version 1 cannot map linked history into
another store, so imports with source-local supersession, evidence references,
or drawer URIs are rejected. Use a database backup when preserving that history.

The portable format rejects external URLs in content and metadata at export
and import. Whole-store export can therefore reject ordinary memories that
contain links; it is not a substitute for backup. Exports atomically replace
their destination only after the complete stream is written.

## Network and optional projections

Embeddings execute locally; first use may download model weights. Optional
update checks contact PyPI. Explicitly selected LLM adapters may contact a
provider. There is no product telemetry pipeline.

Obsidian projection is optional and one-way. SQLite remains authoritative.
Cairntir updates only a uniquely marked generated block inside its owned
`cairntir-sync` tree, preserving surrounding user notes. Ambiguous markers and
paths escaping that tree are rejected. Secret-classified drawers are excluded.

See the [integration guide](integration-guide.md) for APIs and the
[multi-host contract](architecture/multi-host-continuity.md) for adapter details.
