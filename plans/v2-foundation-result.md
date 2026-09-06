# Independent foundation verification

Tester: `/root/foundation_tester`. Final independent foundation verdict: **PASS**
after one repair round. All 204 required cases and four additional WAL safety
scenarios pass. Both manifests and all 13 bound artifacts remain unchanged.

| Gate | Final repair 1 evidence |
| --- | --- |
| Original complete frozen suite, including cached real embeddings | 41 passed in 3.05s. |
| Separately frozen boundary supplement, including cold cached reads | 10 passed in 4.56s. |
| Complete mandatory legacy regression files | 153 passed in 12.81s. |
| Original manifest and 12 bound artifacts | Unchanged before, after and at finalization. |
| Supplementary manifest and one bound artifact | Unchanged before, after and at finalization. |
| Runtime source | Every Python file under `src` and `scripts` remained identical. |

Detailed invocations, timestamps, exact source fingerprints and evidence hashes
are in [v2-foundation-result.json](v2-foundation-result.json). Final raw outputs:
[original](v2-foundation-round1-original.txt),
[boundary](v2-foundation-round1-boundary.txt), and
[legacy](v2-foundation-round1-legacy.txt). The cached production model was
available locally; no skip, xfail or infrastructure inconclusive remains.

Tests ran against uncommitted runtime bytes based on Git HEAD
`ad3ccee95d6d4c0bc5cb5b57e1ec76d799d23c3e`. Subsequent coordinator commits
`e19ba8e` and `ac89c20` preserve those bytes; source hashes, rather than the
later commit metadata, identify the tested implementation.

## Source purity and committed WAL

The independent [probe output](v2-foundation-round1-wal-probe.json) and
[reproducible script](v2-foundation-round1-wal-probe.py) verify:

- Cold quiescent reads expose exact evidence without changing source files or
  directory/file timestamps.
- Idle live WAL connections and active write transactions produce typed busy
  failures while preserving the source tree.
- Orphan committed WAL evidence, proven absent from the main database and
  present in WAL, is visible through the read-only store without source changes.
- Every private snapshot and the owned probe workspace is removed.

The active-transaction observer uses read-only mmap to hash SHM bytes under
Windows byte locks. This standalone observation adjustment preserved complete
hash/timestamp equality assertions. No frozen tests or runtime source changed.
The existing MCP connection's SQLite VFS bookkeeping sidecars remain outside
the cold-source filesystem boundary; persisted application-state purity is
covered by the original acceptance suite.

## Preserved round history

[Round 0](v2-foundation-round0-result.json) was **FAIL**: original 40 passed / 1
failed, supplement 9 passed / 1 failed, and legacy 153 passed. Its two behavioral
failures were:

1. `test_real_cached_embeddings_retrieve_paraphrase_and_reject_noise` returned
   the relevant cache-policy drawer and an unrelated orchid-greenhouse drawer.
   A matching semantic candidate must not automatically make unrelated evidence
   relevant.
2. `test_task_cli_preserves_home_and_skips_registration_updates_and_pending_banner[True]`
   created SQLite `-shm` and `-wal` files and changed the memory-home directory
   timestamp. The test uses the real CLI/store path and checks complete stdout,
   hooks and the whole isolated filesystem tree.

A separate [WAL diagnostic](v2-foundation-round0-wal-diagnostic.json) confirmed
the files survived explicit reader closure. Repair 1 applies a generic cosine
threshold of 0.75 and obtains a private snapshot under exclusive source locks.
Busy sources surface a typed retryable failure; quiescent committed WAL remains
visible. Final acceptance and the probes above verify both repairs.

An [initial repair-1 attempt](v2-foundation-round1-interrupted-result.json) is
preserved as **INTERRUPTED_BY_SOURCE_CHANGE** because the implementer corrected
snapshot error reporting during that run. The complete three gates were rerun
after the final stable-source signal. This used one repair round, not two.

## Supporting semantic evidence

The independent tester chose three additional calibration topics and three
separate holdout topics, each with relevant paraphrases and unrelated controls.
All measurements used the existing cached production FastEmbed model with
networking forbidden. These are small synthetic local-model checks, not
commercial-host, billed-savings or general task-success evidence.

[Calibration](v2-foundation-semantic-calibration.json) produced three positive
cosines of 0.812127, 0.780064 and 0.775350; the largest of fifteen unrelated
comparisons was 0.718913. The implementer fixed the generic threshold at 0.75
before the tester revealed the separate holdout results.

The [holdout](v2-foundation-semantic-holdout.json) achieved 18/18 correct
classifications at that fixed threshold: three relevant and fifteen unrelated
pairs, with positive minimum 0.769490 and unrelated maximum 0.735214. Its
pre-reveal bytes were verified against SHA-256
`52e3636e8c5a59186cefe01ae126fb0b0e91afb64b5e8374afbbc553574d31c0`.
This supports the proposed repair without replacing any frozen acceptance case.

The verdict covers the foundation contract only. Coordinator-wide regression,
package, visual-demo and release checks are separate evidence.
