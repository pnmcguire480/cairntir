# E22 bounded acceptance freeze, 2026-10-03

This packet independently freezes the already planned artifact identity increment,
stacked on PR124 head `65126e49faf49f542ddc4ee8d3361a2402e2838b`, tree
`0a12665`. `ORIGINAL-CONTRACT.md` is the governing complete semantic contract,
copied without edits from the preserved 2026-09-20 public packet. That original
document's historical baseline and preparation statements describe that earlier
freeze, not the present implementation or baseline.

The acceptance authority is public synthetic shared-workspace testing. There is
no private holdout, model qualification, production adoption, real cache/store,
two-machine proof, API spend, or model download. The author read the governing
contract, public tests, reviewed base project guidance/dependency declarations and
CLI command surface. The author did not inspect parked prototype runtime
`artifacts.py`, `embeddings.py`, or `store.py`.

## Exact bounded behavior

`artifact_manifest()` provides detached canonical JSON with exactly schema/model/
positive integer dimension/POSIX registry model_file/sorted unique full-byte
required and additional asset hashes/pipeline/exact nonempty installed versions
of fastembed, onnxruntime, tokenizers and numpy. Identity is the SHA256 of the
original contract's canonical JSON, prefixed `fastembed/text-embedding-v2/sha256=`.
No inference, bootstrap, filesystem writes, or missing-version substitution may
occur during offline identity/inspection. Invalid dimensions, unsafe paths,
unsupported additional-asset forms/schemes and non-file assets fail as typed
actionable EmbeddingError. Duplicate declared paths deduplicate.

First successful identity pins immutable manifest, absolute configured cache and
resolved snapshot. Returned JSON, changed environment/cwd or moving refs cannot
redirect it. Rehash all pinned bytes before each inference-model construction;
use exact specific_model_path and local_files_only=True. Missing pinned bytes
never reacquire. Once the model is loaded, its retained identity stays pinned;
this acceptance does not require per-vector rehashes or concurrent-native-load
custody. Relative cache paths are resolved against cwd at first resolution and
stay absolute. The existing explicit bootstrap routes alone may acquire, then
validate and construct a pinned local inference model before accepted vectors.

Reject asset symlinks escaping the model root; a recognized Hub snapshot permits
only its own repository's blobs root in addition. Other repository blobs remain
forbidden. These real symlink controls honestly skip when the platform denies
symlink creation; a skip is incomplete containment evidence, never a pass claim.
Arbitrary ONNX external-data discovery is outside this increment.

Nonempty old name-only FastEmbed indexes remain unverified without inference,
metadata adoption or semantic writes/search. Ordinary raw drawer retrieval works
with absent cache and retains normal access bookkeeping. Empty indexes may adopt
only after pinned model validation. Existing custom/hash provider behavior stays
supported. Real CLI doctor reports unverified/disabled for legacy metadata; raw
get returns exact JSON content; refused recall changes no logical evidence;
explicit reindex --yes --backup creates an intact pre-rebuild backup, preserves
drawers, replaces vectors and installs new identity/generation, after which doctor
reports verified and actual recall returns the existing drawer. Constructor,
hashing or batch inference failure preserves original drawers, vectors and
metadata, including multi-drawer failure and its backup.

No new project dependencies or unrelated features are accepted. This is one
existing planned foundational feature; it does not authorize merge, publish,
installation or live data migration.

## Frozen executable scope and reserve

35 serial cases: original 25 unchanged, existing relative-cache v2's 2 cases
unchanged, and 8 supplementary controls as listed in the runner.
The supplementary names are 26 actual full CLI workflow, 27 absent-cache CLI raw,
28 multi-drawer rebuild rollback, 29 missing/empty runtime evidence, 30 changed
runtime evidence with immutable pin, 31 pinned asset loss/no reacquisition,
33 invalid dimension/unsupported scheme, and 35 other-repository symlink
containment. All fixtures and diagnostic user homes are beneath packet/runs.
Network socket connect and Hub acquisition APIs are blocked by the public base
fixture; the one explicit synthetic bootstrap creates bytes locally.

The original dependency baseline is unchanged and matches the reviewed PR124
project declarations, so no portability adapter is needed. Existing 25 synthetic
cases are preserved byte-for-byte. `FREEZE.json` records SHA256 custody of every
contract, test, runner and dependency file. Runner validates hashes before use.
Reports and runs are appended evidence and excluded from freeze hashes.

Baseline uses the clean exact PR124 candidate before runtime implementation. The
missing interface is expected structural baseline evidence, not proof that all
new requirements were individually violated. Follow frozen tests unchanged for
candidate verification; any fixture repair or acceptance addition requires a
separate explained versioned freeze before the associated product repair.
Independent post-implementation adversarial review and wrong-control reserve
remain available; review has not been spent during preparation. At most two
product repair rounds remain governed by the parent finalization plan.

Requested author routing: gpt-6.1-sol, high effort. Actual serving variant and
actual effort are not exposed by execution metadata; cost is unavailable.

Run in PowerShell with the existing dev interpreter (no environment sync):

```powershell
& 'C:\Users\pnmcg\.codex\worktrees\v2-foundation\Cairntir\.venv\Scripts\python.exe' 'C:\Users\pnmcg\Documents\Codex\2026-09-30\task\cairntir-embedding-feature-20261003\acceptance\run_acceptance.py' --source-root 'C:\Users\pnmcg\AppData\Local\Temp\cairntir-embedding-work-20261003' --report 'C:\Users\pnmcg\Documents\Codex\2026-09-30\task\cairntir-embedding-feature-20261003\acceptance\baseline.json'
```
