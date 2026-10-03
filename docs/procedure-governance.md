# Versioned procedure governance

The trusted Python `ProcedureBook` API accepts optional `PracticeGovernance`
on a `ProcedureSpec`. It records the practice's attributed owner, explicit version,
rationale and review date alongside the existing steps and evidence.

```python
from dataclasses import replace
from cairntir.procedures import PracticeGovernance

# book and spec are existing explicitly configured ProcedureBook/ProcedureSpec values.
governed = replace(spec, governance=PracticeGovernance(
    owner="project maintainer",
    version="1",
    rationale="Retain the observed ordering fix and its evidence.",
    review_due="2026-11-01",
))
first = book.propose(wing="example-project", spec=governed)
second = book.revise(first.drawer_id, spec=replace(
    governed,
    governance=replace(governed.governance, version="2", rationale="Refined applicability."),
    applicability="Use for the reviewed list-processing case.",
))
history = book.history(second.drawer_id)
```

Run against an explicitly chosen store only. These operations persist records;
the example was tested only with synthetic isolated stores and grants no access.
Existing applications need not opt in: an omitted governance field retains the
legacy payload, content and revision identity without migration or backfill.

Owner/version/rationale must be nonblank primitive strings; version has no outer
whitespace. Review date is a valid exact `YYYY-MM-DD`; a past date remains valid
and visible. Owner and rationale are preserved verbatim. Revision hashing includes
every governance field. The owner is an attribution label, never authenticated
identity, consent or promotion permission.

Once a family opts in, a content revision must retain governance and use a version
not previously used in that family. Reusing a version in a different family is
allowed. Versions are exact labels, not automatically incremented or semantically
ordered. Owner changes also require an explicit new family version. Revisions
append new records; prior drawer bytes and metadata remain
available through history, including after reopening the store. Stale revisions,
invalid metadata and stripped/reused versions fail without appending records.

Evaluation, corroboration, promotion and withdrawal retain the current version.
Promotion still requires the unchanged independent evaluation and trusted operator
approval. This API does not schedule reviews, resolve guidance conflicts, implement
retirement/restoration policy, expose a new MCP tool or authenticate an operator.
Those connected R17/R18-R20 and release qualification requirements remain tracked.

## Compatibility and adoption

The increment uses the existing procedure registry; no schema change, backfill or
live migration is needed. Legacy records are reconstructed with `governance=None`,
while newly opted-in records persist a complete nested governance object. An
explicit `governance=None` on a new spec omits that object entirely.

Upgrade every participating client to a governance-aware application before any
family opts in. This is a persistent format compatibility change even though it
requires no SQL schema migration. An older `ProcedureBook` cannot reconstruct the
added nested object: `list(active_only=False)` can fail the entire listing when
it encounters a governed record, including otherwise readable legacy records in
that listing. Raw drawer reads and history for unrelated legacy families remain
readable. No downgrade conversion or metadata stripping is provided. Keep any
existing store backup when changing application versions.

This finite capability is available through trusted Python startup code and the
existing `propose`, `revise`, `history` and `list` APIs. A review date is stored
intent: it neither expires a practice nor triggers a callback. The repository's
`plans/practice-governance-r17.md` records qualification and the reserved connected
governance work.
