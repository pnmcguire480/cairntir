# Host continuity policy acceptance

Independent tester: `/root/resume_acceptance`. Request: #1352 consolidated
1.11.0 preparation. Runtime ownership remains with the coordinator and core
implementer. Prior task-resume acceptance and its history are immutable.

## Frozen user-visible contract

1. Reuse the known wing and task ID after a host, checkout-folder, or context
   change; carry wing, task ID, and acknowledged revision in generated summaries.
   Derive a wing from the current folder only when project identity is unknown.
2. Save exact corrections and constraints into the same task's replacement
   checkpoint content and outstanding work before further dependent work.
3. An explicit terminal or unavailable task requires stopping, reporting, or
   checking identity. It does not select another task. Open requests remain
   within the selected, authorized scope.
4. One creation checkpoint performs capture-on-arrival. Ordinary memory is the
   explicit fallback for an older tool surface; do not duplicate the creation
   write or send unsupported arguments.
5. Keep compaction recovery, current-state checks, complete checkpoints,
   idempotent retry fields, acknowledged-write/failure honesty, opt-in transcript
   recovery, and the distinction between stored evidence and execution authority.
6. Consolidate overlapping instructions into fewer than the reviewed draft's
   775 words. No exact replacement text, paragraph count, or writing style is
   prescribed.
7. All seven file-backed project host configurations receive the same current
   policy, preserve surrounding user text, and are idempotent. Cursor/Cline
   manual user rules remain explicitly manual. Repository mirrors stay aligned.

`tests/unit/test_host_continuity_policy_acceptance.py` checks essential nearby
semantic terms and real isolated host-configuration outputs. These are static
contract and distribution checks, not proof of a model following instructions
after compaction. An independent reading of the final policy remains required.
No paid model experiment, production configuration, or live memory is touched.

The original 70 task-resume cases remain the behavioral acceptance for runtime
simplifications. These policy tests cannot replace crash, concurrency, scope,
idempotency, or budget proof. They add only the newly agreed policy contract.

## Reproduction and freeze

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_host_continuity_policy_acceptance.py --no-cov -q --tb=short
.\.venv\Scripts\python.exe -m ruff check tests/unit/test_host_continuity_policy_acceptance.py
.\.venv\Scripts\python.exe -m ruff format --check tests/unit/test_host_continuity_policy_acceptance.py
```

The separate `host-continuity-policy-freeze.json` records the executable and
contract hashes plus pre-edit baseline evidence. Existing freezes are not
changed. Implementation may consume these tests but may not edit their frozen
inputs. Final evidence requires unchanged hashes, all cases passing, and the
coordinator's full consolidated verification gates.
