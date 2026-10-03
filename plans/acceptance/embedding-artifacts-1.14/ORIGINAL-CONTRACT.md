# E22 artifact identity contract v1

Prepared independently before product implementation on 2026-09-20. This is public synthetic acceptance, not protected evaluation or two-machine proof. Drawer 2408 and the read-only discovery packet supply the current-state evidence. No live cache or database is a fixture.

## Interface and identity

`FastEmbedProvider.artifact_manifest()` returns a detached JSON-compatible dict. It resolves only existing assets through `model_cache_dir(create=False)`, without constructing an inference model, creating directories, writing metadata or downloading. Missing/unusable assets raise an actionable `EmbeddingError`; failure must not create or stamp an index. `embedding_space_id` uses this same offline resolution and returns `fastembed/text-embedding-v2/sha256=<digest>`.

The canonical manifest has exactly these fields:

- `schema`: `cairntir.embedding-artifacts.v1`.
- `model`: the selected registry model name.
- `dimension`: the registry's positive integer dimension.
- `model_file`: validated POSIX-relative registry ONNX path.
- `files`: sorted by path, unique entries with exactly `path`, `size_bytes`, `sha256`. Include the model, `config.json`, `tokenizer.json`, `tokenizer_config.json`, `special_tokens_map.json`, and every registry `additional_files` asset. Each hash covers the entire file's bytes. Unrelated files do not affect identity.
- `pipeline`: `fastembed.TextEmbedding/defaults-v1`. This denotes unmodified TextEmbedding preprocessing/postprocessing defaults under the exact runtime versions below. A future adapter override needs a different pipeline tag and acceptance.
- `runtime`: exact installed versions under keys `fastembed`, `onnxruntime`, `tokenizers`, `numpy`. Missing version evidence fails closed. Package versions identify behavior, while file hashes identify assets; this does not prove unmodified installed package code.

Digest bytes are `json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")`, without a trailing newline. Absolute directories, host identity, mtimes, mutable refs and repository commit labels are excluded. Repository/revision may be reported separately as provenance; neither substitutes for local byte hashes.

Reject empty, absolute, drive/UNC, backslash, `.`/`..` segment or escaping asset paths before hashing. Resolve symlinks/junctions and reject assets outside approved roots. A plain model directory permits targets only beneath itself. A recognized Hugging Face repository snapshot additionally permits targets beneath that same repository cache's `blobs` directory: this is the normal Hub symlink layout, not permission to read arbitrary sibling/cache files. Required files must resolve to ordinary readable files. Duplicate valid registry paths may be deduplicated. This increment supports the registry-declared complete asset set; it must not claim to discover arbitrary ONNX external-data references. The production registry currently declares no additional files. Unknown unsupported asset schemes must fail rather than imply complete provenance.

## Pinning and acquisition

The first successful offline resolution pins the provider to one resolved model directory and immutable canonical manifest. Returned dicts cannot mutate this internal identity. Rehash the pinned assets immediately before each inference-model construction, rejecting changed or missing bytes. Both `_load` and `embed_query_readonly` construct with that exact `specific_model_path` and `local_files_only=True`; moving `refs/main` after identity resolution must not redirect the load. A fresh provider may resolve the new ref and compute a different identity.

A loaded in-memory model retains its pinned identity. This contract does not demand hashing a large ONNX file for every vector or claim protection against an adversarial concurrent writer during native model loading. Stronger custody/immutable-file guarantees are a separate boundary.

Offline identity/inspection and read-only embedding never bootstrap. Preserve existing explicit setup/reindex prewarm routes (`embed(...)` / `dimension`) for first-time acquisition: acquire assets under the configured cache, then fingerprint and construct the pinned local runtime before producing vectors or stamping an index. A temporary unpinned acquisition object cannot supply accepted vectors. The synthetic harness permits acquisition only in its explicit bootstrap case; it performs no actual network access. Do not convert a missing-file failure in a previously pinned snapshot into an implicit reacquisition.

## Index policy

Existing nonempty FastEmbed indexes with the old name-only identity are `unverified`, even if today's cached assets look correct. Opening them or inspecting them never upgrades their metadata. Semantic add/search rejects them before inference or durable mutation; ordinary raw drawer retrieval must still work, including when the cache is absent. This means ordinary existing-store opening plus `get`, which retains its existing access bookkeeping; it does not promise that the current `read_only=True` semantic-snapshot constructor accepts an unverified index. Existing hash/custom provider identities remain supported.

Brand-new/empty indexes can be stamped only after pinned model validation, including an empty v1 store whose old metadata exists but which has no vectors or drawers. An explicit existing `reindex --yes --backup ...` can recover a legacy index: preserve a backup, rebuild every vector through the pinned provider, then atomically install the new identity/generation. Failed acquisition, hashing or rebuilding preserves the original logical database. No automatic reindex, legacy adoption, or production migration is authorized by this preparation.

## Verification and scope

The harness creates synthetic local snapshots and SQLite stores under this packet's `runs` directory, substitutes only FastEmbed/Hub model loading, and uses the real Cairntir provider/store/CLI code. Cases cover canonical hashes, every required file, equal-size mutations, additional files, missing/path escape, relocation, configured cache precedence, immutable returned values, moving refs, exact local loading, pre-load mutation, unavailable offline behavior, bootstrap separation, legacy/raw reads, refusal without metadata/vector changes, explicit backed-up rebuild, rebuild failure and no new project dependencies.

No product implementation exists for this contract at freeze time. The baseline is expected to fail at the missing `artifact_manifest` interface. Preserve this freeze and any failures. A fixture repair needs a new version with explanation; acceptance changes need a separately frozen contract before the associated product repair. This packet is prepared for root review; implementation remains unstarted.
