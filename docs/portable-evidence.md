# Portable evidence

Version 2 bundles move complete original records and their relationships between
local stores. Each record has a stable UUID. Importing it again reuses the local
copy; receiving different original evidence under that UUID raises a conflict.

```bash
cairntir export archive.json --format 2
cairntir import archive.json --format 2
```

Set `CAIRNTIR_HOME` to select the destination store before importing. A complete
export includes expired history. `--wing` and `--room` restrict the selection;
if a required relationship points outside that scope, export fails and preserves
the previous output file.

The default `--format 1` retains the older JSONL envelope behavior. Its URL and
source-local-reference restrictions still apply.

## Original records and local references

Schema 7 assigns UUIDs to existing drawers during a backup-first migration.
Original text, provenance, vectors, access state and workflow receipts remain
unchanged. Later changes to local layers, belief weights or anchors do not change
the portable original. Corrections belong in new drawers that supersede the old
ones.

A bundle preserves the original drawer projection, provenance, origin store UUID
and source drawer ID. Its typed reference map connects original numeric IDs to
portable UUIDs. Import maps relationships to local IDs while retaining the exact
original text and specialized source metadata. Two competing corrections remain
two branches.

```python
from cairntir.portable import export_bundle, import_bundle

export_bundle(source, path, drawer_ids=[selected_id])
receipt = import_bundle(destination, path)
local_id = receipt["identity_map"][source.portable_identity(selected_id)]
original = destination.portable_source(local_id)
relationships = destination.portable_relations(local_id)
```

An explicit selection includes its required reference closure. Relationship
records provide `kind`, `path`, `source_target_id`, `target_identity` and the
resolved `target_drawer_id`. Numeric IDs in original text continue to identify
their source namespace; use this map to navigate after import.

## Integrity and authority

The bundle hash covers canonical JSON containing version 2 and records sorted
by UUID. It binds original evidence, provenance and relationship mappings.
Optional `signing_key` and `verify_key` arguments apply HMAC-SHA256 to the same
payload. Requested verification rejects unsigned or incorrectly signed input.

Import validates the whole graph and commits drawers, vectors, mappings and its
durable receipt atomically. Interrupted attempts can be retried with the same
`idempotency_key`; the key cannot be reused for a different bundle. Different
bundles containing an existing UUID also deduplicate it.

Imported records are private, untrusted evidence. They retain source sensitivity
and validity bounds. Foreign Discovery promotions, hotfix approvals and execution
metadata remain in the original record and do not activate local workflows.
HMAC establishes shared-key possession, not personal identity or approval.
External URLs are preserved as quoted evidence and are never fetched.

[Independent acceptance](https://github.com/pnmcguire480/cairntir/blob/main/plans/portable-v2-acceptance.md) covers migration,
three-store relay, failures, concurrent imports, preserved authority boundaries
and an archive exceeding 100,000 drawers.
