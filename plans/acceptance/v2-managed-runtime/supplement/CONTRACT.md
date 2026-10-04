# Managed runtime missing-outcome supplement

This additive public acceptance is frozen after the first combined suite exposed a coverage gap, before these cases execute. It tests obligations already present in CONTRACT.md and PROCESS-CONTRACT.md against the unchanged repair-2 candidate. It does not alter earlier assertions, exclusions, the 92% floor, or product code. The original failing full-suite coverage and its three independently diagnosed environment-contaminated embedding failures remain separate evidence.

Eleven cases require these observable outcomes:

1. Invalid schema, configuration roots, profile mappings, unsafe arguments and numeric limits reject before source/workflow changes or launch. A valid configuration still starts.
2. Unsupported action schemas, noncanonical UUIDs, unconfigured profiles, malformed/duplicate/unknown event references and absent acknowledgements reject without writes or launch. The original valid action then launches once.
3. A second start, unknown action status and invalid JSONL envelopes reject without writes. The published status envelope returns the actual completed action.
4. A real child exits 7 with independently specified stdout/stderr. Its receipt reports failure, keeps exact CRLF output and the outstanding original request, and exact replay produces no second marker or additional database write.
5. A real child writes and fsyncs a marker then exceeds a one-second timeout. Without process-tree cleanup proof, the result remains uncertain with timeout true and null outcome/exit. Exact replay never launches, and a new action cannot bypass unresolved uncertainty.
6. A real child emits 8192 ASCII bytes against a 128-byte per-stream cap. The returned prefix is exactly 128 bytes, truncation is truthful, unconfirmed cleanup remains uncertain, and replay cannot repeat the marker.
7. A witnessed OSError at the real child's stdout read boundary leaves an uncertain observation even when the process can exit normally. No successful outcome or invented exit code is returned; exact replay remains non-launching. This fault does not replace the actual child effect.
8. Raw captured source corruption after an acknowledged brief cannot authorize a process. Refusal neither rewrites the source nor appends lifecycle records.
9. Removing only the matching committed brief record prevents acknowledgement even when the runtime retains its exact public brief in memory.
10. A completed action cannot be replayed under a changed configured output limit after restart. Its exact profile binding remains authoritative and the external marker remains single.
11. A grant revoked after successful dispatch cannot read the completed protected result or replay it. Revocation does not erase history or repeat the effect.

Fixtures use disposable stores with HashEmbeddingProvider(32), fixed local Python profiles, no network, no production state, and a fsynced independent marker. Raw SQLite updates/deletion are deliberate corruption controls inside the owned fixture; snapshots are taken after corruption to prove refusal performs no repair/write. Comparison with a prior observed success alone is not the outcome oracle: expected exit values, output bytes, original request and single marker are specified independently.

The output-cap wrong control copies the candidate package into an owned directory and disables only the branch that sets truncation/terminates oversized output. Running the unchanged frozen output case must fail; the real child and fixed 128-byte expectation remain. The source candidate and original assertions remain unchanged. A separate reviewer owns projection-subpacket's independent whole-evidence and raw-binding refusal cases.

Run with the reviewed interpreter and PYTHONPATH set to reviewed source, isolated CAIRNTIR_HOME, automatic registration/update checks disabled and PYTHONUTF8=1. Record source, contract and test hashes before and after. Passing this supplement is scoped to managed local processes and generated projection; it does not establish native host capture, arbitrary descendant containment, protected evaluator custody or private holdout qualification. Coverage may be combined only on copied artifacts and reported separately; the original failed full-suite result cannot be relabeled passing.
