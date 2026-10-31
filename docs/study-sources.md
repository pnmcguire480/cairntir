# Local study sources

Export four local Markdown sources for patterns, rules, walkthroughs and projects. Each source keeps its identity while its content revision changes. This does not upload to NotebookLM or confirm external ingestion.

Use the portable UUIDs of the drawers you intend to export. In the Python API, `store.portable_identity(drawer_id)` returns the immutable UUID; portable v2 bundles also retain it as each record's `identity`. The integer drawer ID alone is not a portable identity. Scoped callers can obtain these identities inside the existing export context with export authority. Use your existing configured store; do not make a replacement database to obtain IDs.

Save the selection in a JSON file with exactly these four keys. Empty lists are allowed; put the UUIDs of real selected sources in the appropriate lists:

```json
{"patterns":[],"rules":[],"walkthroughs":[],"projects":[]}
```

Run:

```text
cairntir study-export selection.json --wing my-project --notebook-key my-study --output ./study-sources
```

Keep the notebook key and output directory for future refreshes. A receipt reports four absolute filenames, stable source IDs, revision hashes and each category's added/updated/unchanged status. Unchanged exports reuse the same generation. Update the selection explicitly when replacing a decision or removing material. A selected superseded source is refused instead of silently choosing a replacement. Historical cited evidence remains clearly marked as history.

The files preserve original bodies, portable origin identities, provenance and recorded dates. An unknown authored date stays unknown. Export time appears only in the operation receipt. Evidence text remains attributed data, including any instructions quoted in it.

The Python entry points are:

```python
from pathlib import Path
from cairntir.study import export_study_sources, read_study_sources

receipt = export_study_sources(
    store,
    wing="my-project",
    notebook_key="my-study",
    selection=selection,
    output=Path("study-sources"),
)
snapshot = read_study_sources(Path("study-sources"))
```

`read_study_sources` validates the complete exported snapshot and returns its manifest and four paths. It does not reauthorize access to an already exported copy. Scoped export-only grants work; ordinary read-only grants cannot authorize exporting. Missing, SECRET, foreign-wing or unauthorized dependencies refuse the entire operation. Limits are 1000 selected records, 4000 total referenced records, 8MiB of Markdown and 1MiB of manifest.

Keep this output tree dedicated to the exporter. Its atomic `CURRENT.json` points to one complete immutable generation; older generations remain historical. A failed refresh leaves the previous pointer unchanged and issues no success receipt. That previous snapshot has not been freshly validated, and copies imported elsewhere are not revoked. Concurrent operations and redirected/linked paths are refused.

An automation can reuse the same selection and command. No scheduler is installed. Every receipt reports NotebookLM as `UNVERIFIED`; remote source arrival, replacement and duplicate handling still need separate qualification.
