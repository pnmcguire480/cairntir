# Resource budgets proposed for review, not accepted thresholds

No performance measurements were run in this slice. These numerical candidates
are relative to a same-machine stable-release baseline; they are not estimates
of current Cairntir performance and cannot produce a PASS yet.

For each of Patrick's and Lou's machines, use the exact published 1.12.3 artifact
as baseline B and the exact candidate wheel as C, with matched isolated configs,
synthetic schema/history fixtures and local model/cache state. Record artifact,
dependency, OS, CPU/RAM, client and provider identities. Do not compare one
machine's candidate with the other's baseline. Do not change fan/power settings.

Proposed maximum regression allowances, requiring explicit pre-run acceptance:

| Metric | Candidate rule |
| --- | --- |
| Cold server initialization to handshake (model not warmed) | C p95 <= B p95 + max(10% of B p95, 50 ms) |
| First and warm acknowledged save, exact get and task resume | Each C p95 <= matched B p95 + max(10% of B p95, 20 ms) |
| Cold and warm semantic retrieval, with identical already-cached local model | Each C p95 <= matched B p95 + max(10% of B p95, 100 ms) |
| Idle CPU summed over owned server/worker processes | C mean <= B mean + 0.1 percentage point of one logical CPU |
| Idle working-set memory, owned process aggregate | C p95 <= B p95 + max(5% of B p95, 10 MiB) |
| Two-host aggregate idle CPU/memory | Same relative allowances against matched two-host B, not against a single-host baseline |

These are regression budgets, not sufficient absolute usability targets. Record
the actual B and C values for review; if B is already too slow or too large,
passing a relative allowance cannot establish a fast/lightweight product. Set
any absolute user-facing latency or machine resource ceilings in the same
dated pre-run amendment, before observing candidate results.

Proposed later method: five paired cold starts and twenty paired warm operations
per scenario, alternating B/C order; nearest-rank p95; identical synthetic
histories of 100 and 10,000 drawers, with task/history shape frozen beforehand.
Record first-use initialization separately from an existing-store startup.
Freeze embeddings and cache state; no model download is part of timed warm
results. Run a two-minute idle sample after settling, using one-second process
samples and including children, backups and update-check state. A sample small
enough to be unstable is inconclusive, not a reason to loosen the threshold.

Before measuring, agree on a thermally suitable window and a numeric sensor
stop rule based on fresh readings and Patrick's maintenance outcome. Today's
reported 93 C peak does not diagnose its cause. Do not launch these repeated
runs tonight under the current thermal restriction. No performance, token,
subscription-cost or whole-run savings are claimed by this proposal.
