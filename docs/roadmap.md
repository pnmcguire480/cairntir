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
The corrected feature is published in [1.12.1](release/v1.12.1.md).

## Current: complete recall-response budgeting

The 1.13.0 candidate exposes a caller-selected full MCP response ceiling on the
existing recall tool, with whole evidence and explicit bounded omissions. This
ports only the preserved E23 foundation; it does not activate the parked v2
program. See [usage](how-to-use.md#bound-a-recall-response) and the
[finite plan](https://github.com/pnmcguire480/cairntir/blob/main/plans/recall-response-budget.md).
Independent adversarial review passed. The current required CI result and
release readiness are tracked in [PR124](https://github.com/pnmcguire480/cairntir/pull/124);
this candidate is not yet published.

## Current: explicit Obsidian correction loop

The 1.15.0 candidate adds an explicit workspace and optional correction plugin,
stacked on reviewed PR125. It preserves originals and durable retry receipts;
ordinary vault edits are not commands. See [usage](obsidian-corrections.md) and
the [finite plan](https://github.com/pnmcguire480/cairntir/blob/feat/obsidian-correction-loop-20261003/plans/obsidian-correction-loop.md). Nothing is installed or
published by creating the candidate. Questions remain the next dependent feature.

## Current: opt-in practice ownership and review metadata

The trusted Python API can attach attributed ownership, explicit versions,
rationale and review dates to procedure families while retaining prior verbatim
records. See [governance and compatibility](procedure-governance.md). This does
not authenticate owners, schedule reviews or bypass evaluation and promotion.
Reviewed PR127 is being qualified together with PR126 in the unpublished 1.15.0
candidate. Upgrade all participating ProcedureBook clients before opt-in.

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
