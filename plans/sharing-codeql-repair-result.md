# Sharing CodeQL repair — PASS

Independent repair round 1: **193 frozen acceptance/regression cases passed**, plus **14 supporting context-manager and unsupported raw/admin probes**. All frozen hashes and 61 runtime source hashes remained unchanged during verification. Original round 0 evidence is preserved.

The new probes were authored independently after implementation edits had begun; they are supporting evidence, not a new preimplementation freeze. Both normal and exceptional context exits close the owner, the body exception propagates, and unsupported raw/admin attributes deny without table, schema or counter changes.

Bounded source review passed: ScopedStore uses composition without base initialization or a second connection, context methods preserve ownership, and the two startup casts affect typing only.

Runs used OPENBLAS_NUM_THREADS=1, OMP_NUM_THREADS=1, and MKL_NUM_THREADS=1. Commands, hashes and raw results are recorded in [sharing-codeql-repair-result.json](sharing-codeql-repair-result.json). Working helpers and probe source remain private under `.cairntir/release-candidate/sharing-codeql`.
