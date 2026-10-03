# Correct a Cairntir memory from Obsidian

This optional workflow is part of the **unpublished 1.15.0 candidate**. SQLite
remains authoritative. A correction adds a new memory that supersedes an earlier
one; it does not rewrite or delete the original. A committed receipt means stored
evidence, not authenticated authorship or proof that a claim is true.

## Refresh the workspace

First rehearse with an explicitly selected disposable Cairntir home and an
existing disposable Obsidian desktop vault. Preserve the work/personal boundary.
Use the intended Python environment, store and wing consistently.

```sh
cairntir obsidian-sync /absolute/path/to/vault --wing example-project
```

The vault must contain its `.obsidian` directory. The command generates a
`cairntir-sync` workspace for that wing with current and historical memory notes,
source identities, exact machine-readable content and linked correction history.
Secret records are excluded. Existing human notes outside Cairntir's generated
blocks survive refresh. Unmarked files and unsupported linked paths are refused.
Ordinary vault notes and direct edits to generated content are never commands.

The trusted Python API can receive an existing owner or scoped store; its grants
still apply. Correction and sync refuse a caller-owned outer transaction so a
receipt cannot claim a save that the caller could later roll back. The CLI remains
an administrative operation denied to restricted
sessions. Nothing in a vault file or owner label expands access rights. Exported
files are local copies: use a vault appropriate for that data and its recipients.

## Submit and retry a correction

The [optional desktop plugin](https://github.com/pnmcguire480/cairntir/blob/feat/obsidian-correction-loop-20261003/addons/cairntir_obsidian/README.md) provides
**Refresh workspace** and **Correct current memory**. Configure the Python
executable, Cairntir home and wing explicitly. Loading the plugin runs no sync.
The correction form starts from exact manifest text; Cancel submits nothing.
Submit creates a retained UUID-named request in `cairntir-sync/outbox`, checks the
source again and invokes the backend without a shell.

Confirmation requires a matching committed receipt. Starting Python or writing
an outbox file is not confirmation. A committed correction can still have a
failed acknowledgement file or projection; the form reports that distinction
and retains the same request for retry. Retry/refresh repairs the view without
duplicating the memory. Changed payloads under an old UUID and stale sources are
rejected. Refresh and open the current successor to submit a new correction.
Structured task/prediction/workflow records require their own lifecycle commands.

CLI stdout is one JSON report. Exit zero requires successful processing,
acknowledgements and projection; exit one can contain a valid partial-commit
report. Individual malformed requests do not hide successes for other requests.
Keep queued requests intact while diagnosing failures.

## Adoption and limits

This feature adds no database schema migration. It retains PR125's separate
[FastEmbed compatibility change](embedding-artifacts.md): a legacy/unverified
index needs an explicitly authorized backed-up rebuild before semantic writes,
including corrections, can succeed. Raw original memories remain available.
All clients sharing a store need compatible model assets and runtime versions.
Do not edit metadata to bypass refusal or merge work and personal stores.

Automated tests use synthetic vaults/identities and mock Obsidian UI, with actual
CLI/process checks where documented. They do not certify a native graphical
session, live operator adoption, private evaluator custody or token/cost savings.
Installation/enabling, any real rebuild and publication require separate authority.
