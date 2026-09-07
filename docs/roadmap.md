# Roadmap

## Shipped foundation

Cairntir provides verbatim local memory, provenance, whole-drawer handoff,
semantic and structural recall, prediction settlements, calibration, discovery
review, and recipes over a 21-tool MCP surface.

[1.8.0](release/v1.8.0.md) added bounded, opt-in transcript recovery for
Claude Code, Codex, and Qwen Code, with an honest unsupported receipt for Cursor.
[1.9.0](release/v1.9.0.md) added the bounded hotfix ledger and hardened the
bindings between hypotheses, experiments, observations, and learning evidence.
[1.10.0](release/v1.10.0.md) added task-aware context selection, portable evidence,
evaluated procedures, and scoped local sharing.

Release records describe tested versions and limits. The
[landed-commitment registry](landed-commitments.md) preserves their regression
contracts independently of retired execution plans.

## Current: interrupted task resumption

Persist acknowledged task checkpoints and recover them from another host with
only a shared wing or task ID. Freeze independent acceptance for interruption,
concurrent updates, scoped visibility, terminal states and exact evidence.
See the [active plan](https://github.com/pnmcguire480/cairntir/blob/main/plans/task-resume.md)
and [task resumption guide](task-resumption.md). Actual autonomous host behavior
and billed token savings require separate evaluations.

## Current: automatic store backups

Provide opt-in verified SQLite snapshots on writable startup and the next write
after a default 12-hour interval. Retain recent and weekly recovery points,
preserve manual baselines, and report failures while memory writes remain usable.
See the [backup plan](https://github.com/pnmcguire480/cairntir/blob/main/plans/automatic-backups.md).
The accepted feature is included in the [1.12.0 release candidate](release/v1.12.0.md).

## Next: retrieval preflight evaluation

Pre-register a holdout before building an automatic retrieval path. A candidate
must improve on explicit handoff and recall while retaining provenance, scope,
trust, freshness, and the ability to abstain. No prompt rewriting or automatic
authority promotion.

The [experiment plan](https://github.com/pnmcguire480/cairntir/blob/main/plans/evolving-mind.md)
defines this boundary; it is not a claim that the feature exists.

## Deliberate boundaries

The core stays local-first, MIT, and host-neutral. Crucible, Quality, and Reason
remain the three primitive skills; repeatable workflows become recipes.
Cairntir records evidence and execution receipts, but does not execute repairs
or cryptographically prove caller identity.

No model-training system, commercial product family, or unrelated application
is part of this build. Major version 2 remains reserved for a revolutionary
change in the project's purpose; see [release policy](release-cadence.md).

## Finalization Mode

Every active roadmap must freeze acceptance criteria, required evidence,
non-goals, dependencies, and verification reserve before coding. An independent
tester owns and hashes the acceptance artifacts; the coder cannot edit,
weaken, or rebaseline them.

Allow at most two repair-and-verification rounds. A repeated unchanged failure
without new evidence is not progress. COMPLETE requires an independent PASS
and every acceptance item; BLOCKED names the external prerequisite; EXHAUSTED
records the repair budget reached. Do not hide unresolved items in a completion
claim or treat completed code as permission to publish.

Apply the [Finalization Mode recipe](recipes/finalization-mode/README.md).
