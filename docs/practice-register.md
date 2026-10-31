# CodeGlass practice register

Publish the practices for one wing into an existing Obsidian vault:

```sh
cairntir obsidian-project /path/to/vault --wing my-project --practice-register
```

The command prints the register path. Open that note in Obsidian. Its rows show
the current practice, attributed owner, version, change rationale, next review
date, review evidence and linked original versions. The snapshot date determines
whether a review is due. A deadline does not mean a review happened.

Only a promoted current revision is active. A proposed replacement appears as
pending until it passes the existing evaluation and operator approval process.
Its predecessor remains in the linked history with its original content and
fingerprints. Rejected and expired families appear as withdrawn.

Older active practices without governance remain visibly incomplete. Add their
owner, distinct version, rationale and review date through `ProcedureBook.revise`,
then evaluate and approve promotion. The register never invents those fields.
Complete a review through the existing assessment and receipt APIs; only a
receipt for the current revision can advance its effective review date.

SQLite remains authoritative. Refreshing the register does not change practices
or complete reviews. Markdown edits do not approve anything. Personal text
outside Cairntir's generated markers survives refreshes.

The explicit register mode publishes its register, revision notes and review
receipts. It requires complete read authority for the wing. If sources become
unavailable, refreshing invalidates the owned generated evidence and reports
that the register is unavailable. Broken markers, unsafe paths and receipt
ownership collisions produce a failure instead of overwriting unrelated notes.

Running `obsidian-project` without `--practice-register` retains the existing
learning-log projection. This increment adds no automatic refresh schedule,
practice editing UI, model, dependency or MCP tool.

Implementation status: independently verified in a disposable installed workflow.
Eight new behavior checks and 209 existing regressions pass. Combined release
qualification and real-user adoption remain pending. This is an unreleased feature.
