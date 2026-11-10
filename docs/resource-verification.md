# Prepared resource verification

Status: unpublished candidate, verified locally for the declared Q05 workflow.

`PaladinResourcesRun` executes declared performance, bundle and security stages
through an existing authorized managed runtime. The controller supplies an
immutable contract, disjoint prepared source/producer/output directories, exact
tool inventories, environment and matching configured command profiles.

```python
from cairntir.paladin_resources import PaladinResourcesRun

run = PaladinResourcesRun(runtime, contract=contract)
receipt = run.execute(stage_id, acknowledged_action)
report = run.report()
```

The stage IDs are `performance`, `bundle` and `security`. Obtain a current managed
brief and acknowledgement for each new stage action. Construction validates and
detaches the contract without writing or dispatching. The adapter installs no
tools. The repository's `plans/resources-q05-r1.md` and frozen acceptance packet
record the concrete contract and qualification evidence.

## Measurements

The prospective Q05 fixture reads a declared SQLite note workload with 100 and
1,000 database rows and 256 requested IDs per invocation. Its independent pinned
producer measures 20 complete child processes per size after two warmups.
Process creation, imports, opening the prepared disk database, reads and returned
values are included; database seeding is excluded. Separate cProfile and Python
allocation runs must return the same complete values. Expected output digests
come from the typed `policy.expected_outputs` manifest; descriptive oracle text
is inert.

| Check | Frozen budget or policy |
| --- | --- |
| Nearest-rank wall p95 | At most 250,000,000 ns per declared size |
| Python allocation peak | At most 8,388,608 bytes per declared size |
| Profiled SQLite execute calls | At most 512 per declared size |
| Compressed wheel | At most 65,536 bytes, including archive overhead |
| Uncompressed regular wheel members | At most 131,072 bytes |
| Ruff S307 | Zero findings with configuration and noqa suppression disabled |

These limits belong to the prepared `q05-notes` representative project.
Each project must declare its own workload and budgets. The separate full
Cairntir package check verifies source, wheel and installed-module identity;
it does not apply these fixture wheel-size limits to Cairntir.

The adapter recomputes wall p95, hashes actual returned lists and reads raw
profiles to count SQLite calls. Allocation peaks describe Python allocations;
they are not RSS or model-memory measurements. Bundle verification checks the
actual offline-built wheel's paths, CRC, RECORD hashes and declared Python source
bytes. Security parses the actual pinned Ruff JSON and reconciles exit 0 with
zero findings or exit 1 with findings. Other scanner exits are inconclusive.

The frozen prepared tools are Python 3.11.9, uv 0.11.2 and Ruff 0.15.9. Their
inventoried existing payloads and version observations are bound to the run.
This finite local workload does not establish arbitrary-project, full-OS,
browser, model-resource or protected-evaluator qualification. The tests are
independently authored public tests on the same shared machine.

## Durable evidence and recovery

A plan and stage preparation commit before dispatch. The stage retains the
actual managed prediction/outcome and captured event bindings. Repeating the
same complete action recovers its original receipt without another launch.
Another action or changed contract cannot replace the prepared stage. If the
controller loses its reply after the outcome commits, the exact original action
can reconstruct a receipt from that outcome and surviving artifacts. Preparation
without a committed outcome remains pending and cannot relaunch.

Receipts expose `status`, `metrics`, `diagnostics`, `managed_result`, `artifacts`,
`evidence_ids` and `replayed`. An observed budget or functional violation fails;
missing, malformed, timed-out, truncated or uncertain evidence is inconclusive.
Every completed stage binds all regular files beneath its output directory,
including raw profiles, child output, launch records and databases.

`report()` is read-only, including on a reopened runtime that has not been
started. Historical receipts retain their original statuses. Current
qualification separately checks source, producer, tools, profiles, environment,
access and the entire saved artifact closure. `disposition` is `COMPLETE` only
when all three receipts pass and `qualification.status` is `CURRENT`; otherwise
it is `BLOCKED`. An external finite finalization budget determines exhaustion.

Scoped history requires a currently valid complete-wing read grant. A grant for
only a room or drawer IDs is insufficient. Revocation, conflicting registry
namespaces, altered source evidence or inconsistent managed action bindings
refuse the history projection. Surviving source drawers alone cannot replace
missing committed registry rows.

Wheel member bodies stream in fixed chunks. Metadata headers remain buffered;
these budgets measure the declared project workload.
