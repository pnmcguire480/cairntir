# Origin-qualified references and derived memory

These additions belong to the 2.0.0a1 experimental preview. Existing portable identities, bundle interchange and append-only corrections supply their foundations.

## Moving a reference between stores

Independently created work and home SQLite stores can both contain drawer `123` with unrelated content. Numeric IDs and `cairntir://drawer/123` identify records within the connected store. Carry the complete origin descriptor when a reference travels:

```python
from cairntir.origin import origin_reference, resolve_reference
from cairntir.portable import export_bundle, import_bundle

reference = origin_reference(work, work_id)
export_bundle(work, bundle_path, drawer_ids=[work_id])
import_bundle(home, bundle_path)
resolved = resolve_reference(home, reference)
```

Here `work` and `home` are existing authorized stores, and `bundle_path` is a selected local file. The descriptor contains `source_store_id`, `source_drawer_id`, `identity` and `content_sha256`. Origin store/number come from the immutable original record; the digest covers the exact authorized body. Store identity travels with a copied database.

Resolution uses the existing portable UUID mapping and verifies every descriptor field. A successful result supplies the mapped home `drawer_id`. Malformed, absent, hidden or mismatched references return only `{"status":"unresolved"}`. There is no numeric fallback or content disclosure through an unresolved result. These SDK reads preserve retrieval counters.

MCP `cairntir_get` accepts the mapped local ID with explicit expectations:

```python
cairntir_get(
    drawer_id=resolved["drawer_id"],
    expected_identity=reference["identity"],
    expected_source_store_id=reference["source_store_id"],
    expected_content_sha256=reference["content_sha256"],
)
```

Call this only after a `resolved` result. A mismatch fails before body disclosure or retrieval-counter changes. Successful get returns the original body alongside `origin_reference` and `derivation`. Current handoff/recall evidence also carries origin descriptors. Keep those fields when transferring the reference.

For an ordinary captured handoff, declare its originating store:

```python
cairntir_remember(
    wing="my-project",
    room="handoff",
    content=foreign_text,
    reference_origin=reference["source_store_id"],
)
```

When that declaration differs from the connected store and submitted fields contain numeric drawer URIs, capture refuses before writing and directs the caller to portable bundle import. The guard checks submitted content, metadata, claim, prediction, anchors and checkpoint fields. It requires `reference_origin`; it does not infer origins from English prose or detect every unannotated paste. Import preserves original text and untrusted provenance. Native correction of imported evidence still requires an explicit supported adoption into a locally authored decision; import itself performs no adoption or approval.

## Corrections and derived notes

`derivation_status(store, drawer_id)` follows only explicit portable `/metadata/derived_from/<index>` dependencies, including transitive dependencies. Imported dependencies resolve through UUID mappings. Ordinary `evidence_ids`, citations and other source relations do not create derivation dependencies.

The read-only result contains `status`, `reasons` and authorized source descriptors:

| Status | Meaning |
| --- | --- |
| `not_derived` | No explicit derivation dependencies. |
| `current` | The dependency chain is available and has no observed replacement or conflict. |
| `needs_review` | An explicit source was superseded or has competing successors. |
| `unknown` | A source is unavailable, expired, protected, unresolved, cyclic, or cannot be assessed under the caller's authority. |

Plain/task-aware handoff and legacy/bounded recall withhold `needs_review` and `unknown` derived bodies, replacing them with labelled receipts. Explicit historical get retains the original body and its status. Source and derived content remain unchanged.

Owned Obsidian workspace refresh marks the generated note `Derivation: needs_review` and `Status: Historical or inactive`, links available sources/replacements, and sets its workspace entry `current:false`. Historical content remains inspectable. Human text outside the owned generated block is preserved. These statuses identify review work; they do not automatically rewrite advice or establish causal truth.
