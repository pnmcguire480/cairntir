# Embedding artifact identity

Available in the **unpublished 1.14.0 candidate**. This is an explicit index
compatibility change for FastEmbed users; plan the rebuild before upgrading.

Cairntir now binds a FastEmbed semantic index to the actual ONNX model,
tokenizer/configuration files, registry-declared additional files, dimension,
pipeline defaults and installed FastEmbed, ONNX Runtime, tokenizers and NumPy
versions. The identity is `fastembed/text-embedding-v2/sha256=...`.

Identical assets moved to another directory retain identity under the same
runtime versions. Equal-size changes are detected. A different runtime version
also changes identity, even when assets and dimensions match. The digest proves
byte/runtime consistency; it does not authenticate the model publisher, prove
untampered installed package code, discover undeclared ONNX external-data files,
or protect against an adversarial writer changing files during native loading.

## Inspect and recover

Use the same configured store and model cache as the intended MCP clients.

```sh
cairntir doctor
cairntir get 42
```

Doctor reports active/stored identity, index generation and detail without
loading inference, downloading a model or adopting metadata. A legacy
`fastembed/text-embedding-v1/...` store reports **unverified** and a nonzero exit
code. Today's cache cannot prove which bytes produced its historical vectors.
Raw `get` remains available, including when model assets are absent; it retains
ordinary access bookkeeping. Semantic reads and writes are refused until an
explicit successful rebuild. This applies to CLI and MCP clients. `status`
continues to count stored drawers without requiring model assets.

Before any real rebuild, stop all clients using that store, confirm its identity
and intended cache, and choose a new backup path. Then, when authorized:

```sh
cairntir reindex --yes --backup /absolute/path/to/new-backup.db
cairntir doctor
```

Use an appropriate absolute path on your platform; do not reuse an existing
backup. Reindex prewarms/validates the provider, preserves a database backup,
rebuilds every vector and atomically records the new identity and generation.
Acquisition or inference failure leaves the original logical database intact.
The backup preserves the previous index for the previous matching runtime;
restoring it is an explicit operator operation, not an automatic downgrade.
No candidate test or installation instruction authorizes changing a live store.

With `HF_HUB_OFFLINE=1`, missing assets cannot be fetched. Supply the complete
intended cache or use the existing explicit `cairntir setup` acquisition workflow
when network access is allowed. Do not edit index metadata to bypass a mismatch.
If a pinned asset changes or disappears, that provider fails visibly; it cannot
silently reacquire a replacement. Keep model assets stable while clients run.

## Inspect the manifest in Python

The concrete FastEmbed provider exposes the same offline identity used by doctor:

```python
import json
from cairntir.memory.embeddings import FastEmbedProvider

provider = FastEmbedProvider()
print(provider.embedding_space_id)
print(json.dumps(provider.artifact_manifest(), indent=2, ensure_ascii=False))
```

This requires existing readable assets and runtime package-version evidence.
It raises `EmbeddingError` for missing or invalid evidence, rather than creating
a cache. Returned dictionaries are detached; modifying them cannot alter the
provider's identity. Normal and read-only model construction rehash the pinned
assets and use their exact directory with local-only loading. Hashing occurs at
identity resolution and before construction, not on every vector. No measured
startup-performance or token/cost improvement is claimed.
