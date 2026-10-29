# Editable calendar candidate

The unpublished calendar SDK turns source-bound channel material and explicit planning constraints into 30 dated days. It schedules formats and calls to action, retains flex and blackout days, links repurposed entries to their originals, and reports collisions. It does not publish content.

SQLite holds the authoritative context and immutable revisions. An optional Obsidian projection makes a selected version readable alongside human notes. This is a planning SDK; it does not add a calendar command or publishing integration.

## Inputs

`generate_calendar` accepts either a validated [experimental ideation status](../ALPHA.md#experimental-and-unfinished-work) reference, `{ "kind": "i03", "ref": ... }`, or a separately labelled historical context using `cairntir.i04.historical-context.v1`.

Historical context contains project and attribution, source files with original IDs, safe relative paths, full hashes and byte lengths, uniquely anchored exact excerpts and excerpt hashes, and ideas with source-linked hooks, channels and formats. Source files are read only beneath the supplied root. Original absolute paths are retained as inert provenance. A source mismatch refuses generation; it does not repair or reinterpret the evidence.

An accepted channel graph verifies its recorded generation and dependencies. It does not confirm its selection, factual claims or effectiveness. Both inlets retain their provisional attribution and `human_confirmation=false`. Historical source text is evidence, not instructions or a current product promise.

The `cairntir.i04.policy.v1` policy explicitly supplies:

- `start_date`, `days: 30`, `timezone` and positive `daily_capacity`;
- `weekly_slots`, each with an ID, weekday, hook cycle or an explicit repurposing source/map, and titles/CTAs keyed by hook ID;
- `flex_weekdays`, dated `blackouts`, and dated `existing_commitments` with capacity units;
- `collision_policy: "retain_and_report"`, repurposing constraints, planning-only publication policy and attributed operator assumptions.

Weekdays use Monday 0 through Sunday 6. UTC needs no external timezone data. A named zone requires available system or installed ZoneInfo data; missing data causes a typed refusal. No timezone package is downloaded and no UTC fallback is inferred. An unsatisfiable repurposing rule, including a missing source before the planning horizon, refuses the plan.

For a modern channel graph, hook IDs equal its adaptation channel IDs and idea IDs come from the original validated selection. Historical channels remain literal; they are not converted into modern profiles.

## Generate, edit and reopen

Prepare source-bound `context.json` and `policy.json` with the fields above, then use an explicitly selected database:

```python
import json
from pathlib import Path

from cairntir.ideation_calendar import (
    generate_calendar,
    get_calendar,
    project_calendar,
    revise_calendar,
)
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore

context = json.loads(Path("context.json").read_text(encoding="utf-8"))
policy = json.loads(Path("policy.json").read_text(encoding="utf-8"))
source_root = Path("calendar-input")
database = Path("calendar-demo.db")

with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
    original = generate_calendar(
        store, wing="calendar-demo", context=context, policy=policy,
        source_root=source_root, idempotency_key="first-plan",
    )
    entry = next(item for day in original["days"] for item in day["entries"])
    revised = revise_calendar(
        store, original["ref"], expected_revision=original["revision"],
        changes=[{"entry_id": entry["entry_id"], "notes": "Review this topic before writing."}],
        idempotency_key="first-edit", source_root=source_root,
    )

with DrawerStore(database, HashEmbeddingProvider(dimension=32), read_only=True) as reader:
    saved = get_calendar(reader, revised["ref"], source_root=source_root)
    projection = project_calendar(
        reader, revised["ref"], vault_path=Path("existing-vault"),
        source_root=source_root,
    )
```

Hash embeddings make this example deterministic; they are not semantic retrieval qualification. The vault must already exist. Keep the returned references to reopen either immutable version.

Each day exposes its date, kind and entries. Each entry identifies its source idea and hook, channel, format, title, CTA, notes and optional `repurpose_of` entry. `collisions` names the date, affected entries and existing commitments, capacity and load. Moving an entry onto a blackout, flex day or overbooked day keeps it visible with a diagnostic. A move that invalidates required repurposing chronology refuses the edit.

Edits accept only `entry_id` and one or more of date, CTA or notes. They append a new version with its exact predecessor; they do not overwrite prior content. Stale edits refuse even when a successor is hidden or expired. Concurrent edits to one predecessor can create one successor. Identical idempotent retries return the same reference; conflicting key reuse refuses. `get_calendar(ref)` returns the requested immutable version and does not claim it is the global latest plan.

## Vault and access boundaries

Projection writes under `cairntir-sync/<wing>/calendars/<initial-calendar-hash>/`. It creates immutable source and version notes plus a stable selected-version note. Generated origin, idea, hook, repurposing and revision links resolve inside the vault. Raw historical text is fenced so its old wiki text remains inert evidence.

Only the block between `<!-- cairntir:calendar:begin -->` and `<!-- cairntir:calendar:end -->` is generated. Surrounding bytes belong to the human and survive later projections. Changed generated content, ambiguous markers, modified immutable notes and projected revision downgrades cause a typed conflict before file writes. Other runtime filesystem failures are surfaced; inspect `projection_status` and `projection_error` before treating a projection as ready.

Generation and revision need live read/write authority. Projection needs read/export authority for the whole dependency graph, including upstream channel records. An authorized read-only database may project; a read-only grant without export cannot. Calendar operations do not unwrap a scoped store or expand its grant. Generation, revision and projection refuse caller-owned active transactions.

`CalendarError.code` exposes typed input, constraint, conflict and artifact failures; access and store errors remain surfaced. No calendar call authorizes publication or turns provisional evidence into an active practice.
