# E22 independent review: FAIL pending one bounded repair

Reviewed the exact runtime SHA256 values in `REVIEW-FREEZE.json` against candidate AGENTS/CLAUDE, `plans/pinned-embedding-artifacts.md`, and the independent original and current acceptance contracts. PR124 behavior was treated as accepted; this review covers E22 artifact resolution, construction and store identity seams only.

## P2: Missing-asset classification permits acquisition before invalid evidence is rejected

`src/cairntir/memory/embeddings.py:222-227` treats every `MissingArtifactsError` from initial pinning as authority to construct an unpinned acquisition object. The upstream resolution can emit this class before validating all evidence:

- `embeddings.py:446-452` checks only `is_file()` when finding fallback roots. An existing `model.onnx` directory is consequently treated as absent, and acquisition is attempted. The contract requires non-file assets to fail closed.
- `artifacts.py:93-100` reports missing cache/model before runtime versions are checked at `artifacts.py:105-113`. A missing model combined with unavailable installed-version evidence therefore attempts acquisition, although acquisition cannot repair that invalid runtime evidence.
- `artifacts.py:119` hashes files in sorted order, stopping at the first missing asset. An absent `config.json` masks an existing non-file `tokenizer.json`, again enabling acquisition before invalid evidence is rejected.

All three were reproduced on the exact candidate with synthetic local files and a constructor blocker. Each refusal assertion received `EmbeddingError`, but each no-acquisition assertion failed because the constructor had already been called with only `model_name` and `cache_dir`; neither `specific_model_path` nor `local_files_only` was supplied. Actual download was blocked. This is an acquisition-policy violation, not evidence that invalid vectors were stored or that data was lost.

Smallest repair: distinguish genuinely absent assets from invalid present files/roots, validate runtime evidence before any missing-only decision, and inspect the declared asset set for invalid evidence before allowing a missing-only result to initiate acquisition. Preserve the genuine first-use/bootstrap route. Apply that rule consistently to recognized Hub snapshots and fallback cache layouts without adding a general acquisition framework.

## Evidence

- `adversarial_controls.py` and `REVIEW-CONTRACT.md` were frozen in `REVIEW-FREEZE.json` before execution and product repair.
- Eight serial synthetic cases: five pass, three fail, zero errors, 0.133 seconds suite time. Complete observations and tracebacks: `review-results.json`; console evidence: `review-results.log`.
- Passing controls cover pinned/local-only valid construction, genuinely missing model acquisition followed by a separate pinned constructor, typed permission/stat and resolution-loop errors without acquisition, and refusal of an equal-size pinned mutation before construction.
- One deliberate in-memory wrong control disables pre-load verification. The unchanged pinned-mutation assertion fails because no `EmbeddingError` is raised, demonstrating sensitivity. No runtime source was mutated.
- Runtime hashes matched the parent's supplied candidate. Inherited acceptance FREEZE and fixture-v3 freeze hashes are recorded in the review freeze.

No separate E22 store/reindex defect was found in the scoped static review. That statement does not replace the independent acceptance and CI gates. Parent-reported acceptance evidence is 32 passes and three Windows privilege-dependent symlink skips; this reviewer did not rerun it. Real symlink containment on a capable platform remains a qualification gap, not a pass.

This is public shared-workspace testing with synthetic files, no real models, network, credentials or stores. Requested routing was gpt-6-astra/high; actual serving model, effort and cost are not exposed. Runtime remained read-only. This initial failure record must remain preserved after repair.
