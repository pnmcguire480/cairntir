# Concurrent task handoff acceptance

Independent tester: `/root/foundation_tester`. User request #1262 asks to remove
the practical CLI busy limitation while another SQLite client holds the store
open. This is a new acceptance generation; every foundation artifact remains
immutable and its earlier busy-source probe remains historical evidence.

The public interface stays `cairntir handoff WING --task TASK --budget N`.
Normal WAL ownership and an active uncommitted WAL write must permit successful
handoff of a coherent committed snapshot. No new runtime API is prescribed.

| Acceptance item | Executable proof |
| --- | --- |
| Idle WAL owner permits real CLI handoff | `test_cli_reads_committed_wal_without_mutating_owner_state[idle-wal-owner]`; repeated CLI subprocesses deliver exact existing and newly committed WAL-only evidence. |
| Active uncommitted WAL writer permits committed-only handoff | Same test `[uncommitted-wal-writer]`; another process holds `BEGIN IMMEDIATE` with a dirty update throughout retrieval. Original committed text is returned; the uncommitted canary is absent. |
| Commits/checkpoints cannot produce mixed or stale snapshots | `test_cli_snapshot_is_coherent_during_atomic_commits_and_checkpoints`; real background SQLite transactions atomically update two multipage records while alternating PASSIVE/TRUNCATE checkpoints. Four real CLI results each contain a complete matching generation bounded by observed commits before/after the call. |
| Owner closure preserves newly committed evidence | `test_cli_retains_committed_evidence_when_wal_owner_closes[0.0/0.05]`; close occurs immediately or 50 ms after the imported CLI signals dispatch. Exact records survive closure; subsequent open-owner handoff also succeeds without application-state writes. These are bounded race schedules, not proof of every OS interleaving. |
| Genuine exclusive contention terminates safely | `test_genuine_exclusive_rollback_lock_fails_with_bounded_cleanup`; a separate rollback-journal `BEGIN EXCLUSIVE` blocks all SQLite readers. CLI must surface explanatory lock/busy/timeout error and clean up within 15 seconds after dispatch. Ordinary WAL ownership cannot use this exception. |

Six collected cases. No skips, xfails, conditional expectation changes or
fixture-specific implementation branches are permitted. At most two
postimplementation repair-and-verification rounds are available.

## Purity boundary

With a live owner but no deliberate committing test writer, hash every SQLite
table, schema and user version before/after repeated task reads, including
provenance, access counters, belief state, workflow state and vector backing
tables. Compare source DB/WAL, cache/log files, all other files and directory
timestamps exactly. Only the already-existing `cairntir.db-shm` bytes/timestamp
are excluded as SQLite VFS bookkeeping; creation/removal of source paths remains
detectable through the directory timestamps. No private snapshot may remain.

During continuous writer commits/checkpoints, the two designated drawer-content
columns and DB/WAL/root-directory timestamps can change due to that writer.
Every other persisted field/table and every non-SQLite source file is compared
exactly once the writer stops. The race test requires actual commit/checkpoint
progress and coherent responses; it does not claim the writer's own effects are
reader mutations. Owner-close schedules likewise allow the owner's checkpoint
and sidecar cleanup. The original frozen 51 foundation cases retain their cold
whole-tree purity, secret filtering, real cached embeddings and full-budget
requirements unchanged.

Helpers and the actual Typer CLI run as separate Python processes against
temporary stores. The only CLI substitution is a deterministic Hash embedder;
snapshot logic, SQLite locks, backup/copy operations and transport rendering
remain real. Socket connections, registration/update hooks and pending banners
are explicitly trapped. Profiles and private temporary roots are isolated and
must be empty after each CLI finishes. No production database/cache or new
dependency is used. Imports have a separate 15-second harness deadline; each
dispatched CLI must terminate within 15 seconds.

## Evidence and reproduction

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_context_concurrency_acceptance.py --no-cov -q --tb=short
.\.venv\Scripts\python.exe -m ruff check tests/unit/test_context_concurrency_acceptance.py
.\.venv\Scripts\python.exe -m ruff format --check tests/unit/test_context_concurrency_acceptance.py
.\.venv\Scripts\python.exe -c "import hashlib,json; from pathlib import Path; m=json.loads(Path('plans/context-concurrency-freeze.json').read_text()); assert all(hashlib.sha256(Path(a['path']).read_bytes()).hexdigest()==a['sha256'] for a in m['artifacts']); print(len(m['artifacts']), 'unchanged bound artifacts')"
```

The original complete foundation suite, boundary supplement (including actual
cached embeddings), and five full mandatory legacy files remain regression
gates: 41 + 10 + 153 cases. Set `CAIRNTIR_ACCEPTANCE_MODEL_CACHE` to an explicitly
provisioned local cache for those existing model tests; no download is allowed.
The concurrency suite itself needs no model cache.

[Baseline JSON](context-concurrency-baseline.json) records the exact source HEAD,
source hashes, invocation, counts and harness classification.
[Raw baseline](context-concurrency-baseline.txt) retains the behavioral red.
The tester-owned freeze manifest binds this contract, suite, baseline and
existing regression inputs. Any changed bound hash invalidates acceptance;
runtime code may change, and each official result records its exact fingerprints.
The manifest's own hash is supplied externally to avoid circularity.

After implementation, the independent result must be PASS, FAIL or
INCONCLUSIVE with complete six-case and 204-case regression evidence, hashes
before/after, tested runtime fingerprints and the used repair count. Preserve
the preimplementation baseline and each failed/interrupted official attempt.
Native platform executions are distinct evidence; a Windows PASS does not claim
Linux/macOS execution. Publication and later continuity milestones are separate.
