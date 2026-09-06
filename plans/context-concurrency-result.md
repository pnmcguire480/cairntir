# Independent concurrency verification

Tester `/root/foundation_tester`: **PASS**, official round 0; no repair round
used. The six new cases, original 51 foundation/boundary cases including real
cached embeddings, and full 153 mandatory legacy cases all pass: **210 total**.

| Gate | Fresh evidence |
| --- | --- |
| Frozen concurrency suite | 6 passed in 35.88s |
| Complete original foundation and boundary suites | 51 passed in 6.12s |
| Five complete mandatory legacy files | 153 passed in 5.26s |
| Freeze integrity | All 19 bound artifacts unchanged before and after |
| Runtime integrity | Every source Python file unchanged during acceptance |

Real CLI processes read exact committed evidence with idle and active
uncommitted WAL owners, retained coherent generations during commits and
checkpoints, and preserved evidence across owner-close schedules. Genuine
exclusive rollback contention terminated with an explanatory failure and
complete temporary cleanup. Live source purity permits existing SHM VFS
bookkeeping only; original cold whole-tree checks still pass.

[Result JSON](context-concurrency-result.json) records the tested Git HEAD,
source hashes, invocations, timestamps and raw-output hashes. Tested
`src/cairntir/memory/store.py` SHA256:
`535f6fafd79214d74d08f7aeeec7f680bfe45ed9b074a4d1e9350996f2ab1bcc`.
Raw outputs: [concurrency](context-concurrency-round0-concurrency.txt),
[foundation](context-concurrency-round0-foundation.txt), and
[legacy](context-concurrency-round0-legacy.txt).

[Preimplementation baseline](context-concurrency-baseline.json) remains
unchanged: five behavioral failures and one pass. The older foundation probe
expecting busy remains historical evidence. This result supersedes that
limitation for the newly authorized concurrency scope, with no changes to its
frozen artifacts. Native Windows execution is verified here; cross-platform
CI and publication are separate coordinator gates.
