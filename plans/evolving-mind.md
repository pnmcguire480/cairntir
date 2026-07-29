# Evolving Mind — Functional Growth Through Use

**Status:** North Star accepted; first measurable growth loop implemented
**Recorded:** 2026-07-27
**Memory source:** Cairntir drawer #117
**Ancestry:** BabyTIEROS learning gates → BrainStormer Auto-Research/CodeGlass
→ Cairntir prediction, surprise, consolidation, belief, Reason, and recipes

## Product definition

Cairntir is not a searchable notebook and it is not “RAG with a mythology.”
It is a transparent, local, user-shaped learning system.

The more it is used, the more capable it should become at:

- recalling the right evidence immediately;
- predicting what will happen;
- detecting when it was wrong;
- turning repeated experience into reusable strategies;
- avoiding errors it has already paid for;
- explaining systems at the reader's actual level;
- strengthening the human's understanding alongside the agents'.

The black-suit metaphor means a fitted, adaptive exoskeleton: capability grows
around the user. It must remain inspectable, removable, exportable, and under
human control.

## Karpathy-derived operating principles already in Cairntir's lineage

This plan uses the principles the project has already attributed to the
Karpathy round table; it does not invent a new external doctrine:

- small details and tight experimental loops;
- prediction-bound work instead of untestable reflection;
- surprise/delta as the gradient when no model weights are trained;
- evidence from repeated use rather than architecture by proclamation;
- simple mechanisms that can be measured, replaced, and compounded.

## What “functional growth” means

Cairntir grows along five explicit memory systems:

1. **Episodic:** what happened, in what context, through which host/agent, and
   with what outcome.
2. **Semantic:** derived concepts and relationships, always cited back to
   verbatim evidence.
3. **Procedural:** candidate and verified strategies—what tends to work for
   this user, task, project, tool, and constraint.
4. **Metacognitive:** calibration, recurring errors, contradiction patterns,
   uncertainty, and the conditions under which Cairntir itself is unreliable.
5. **Pedagogical:** what Patrick understands, what remains confusing, which
   explanations worked, and what should be revisited.

The underlying model's weights do not need to change for the system to learn.
The evolving state is the versioned memory graph, retrieval policy, validated
strategy library, calibration record, and user-learning model.

## The recursive learning loop

```text
capture evidence
    → make a falsifiable prediction
    → act / observe
    → record surprise (delta)
    → reflect and consolidate
    → propose a scoped strategy or concept
    → test against replay and holdouts
    → human approves, rejects, or limits
    → retrieval and future work use the verified result
    → measure whether it actually helped
```

Every pass leaves linked receipts. A later pass can supersede an earlier
conclusion, but never erase its evidence.

## Growth invariants

- Verbatim evidence is immutable.
- Derived learning cites its source drawers, runs, files, and observations.
- Every learned artifact has scope, confidence, validity window, provenance,
  and supersession.
- “Used often” is not the same as “true” or “useful.”
- Contradictions are surfaced, never averaged away.
- Imported or agent-generated memory begins untrusted.
- Promotion to a reusable strategy requires outcome evidence and, for
  high-impact behavior, human approval.
- Adaptation is reversible. The user can inspect, disable, export, or retire
  any learned strategy.
- Hosts and models contribute evidence to one mind; they do not create
  separate minds.

## What this is not

- autonomous self-modifying source code;
- silent prompt rewriting;
- a global personality score;
- reinforcement of whatever the user or model repeats most;
- model fine-tuning disguised as memory;
- an agent runtime inside the memory layer;
- dependence on a single vendor, model, cloud, or chat history.

## Falsifiable measures of growth

A release may claim functional growth only when longitudinal evaluation shows
improvement over its own earlier baseline:

- recall precision and full-evidence retrieval improve;
- stale or contradicted memory is rejected more often;
- prediction calibration improves;
- repeated-error rate falls;
- task success rises or cost/latency falls for comparable work;
- accepted strategies outperform their unadapted baseline;
- CodeGlass teach-back accuracy and later retention improve;
- the user spends less time re-explaining settled context;
- cross-host continuity remains exact while adaptations compound.

“Drawer count increased” is not a growth metric.

## Discovery Ledger and Human Learning Log

Growth must be visible to the human. Cairntir should proactively surface:

- recurring patterns across independent episodes;
- a strategy that outperforms the user's or project's normal baseline;
- a surprising contradiction or constraint that changes the working model;
- a newly reliable capability that emerged from combined memories/recipes;
- a concept the user has demonstrably learned or still misunderstands;
- a useful method that differs from the project's standard approach.

Every discovery follows a visible lifecycle:

```text
signal → candidate → corroborated → promoted
                         ↘ rejected
                         ↘ expired
```

A discovery entry contains:

- plain-language title and explanation;
- whether it is new to Patrick, new to Cairntir, or potentially novel in
  general;
- evidence and linked source drawers/runs;
- scope and counterexamples;
- confidence and number of independent observations;
- baseline/standard method and measured difference;
- first seen, last seen, and validity window;
- next falsifying test;
- user verdict and later outcome.

“Potentially novel in general” is never claimed from local repetition alone;
it requires explicit external research. Notifications fire only when a
candidate crosses an evidence threshold or materially changes a decision, so
the system does not turn coincidences into applause.

The foundation-hardening implementation now provides:

- active discovery notices at `cairntir_session_start`;
- `cairntir discoveries` for candidates and promoted findings;
- `cairntir learning-log` for the chronological human/AI co-learning record;
- MCP tools to record, transition, list, scan, calibrate, and read learning;
- append-only lifecycle transitions with evidence drawer references;
- a hard guard against promoting "general novelty" without a note that names
  external research;
- automatic candidate proposals after at least three repeated Reason episodes,
  with confidence, observation count, baseline, counterexamples, evidence
  fingerprint, and next falsifying test;
- a read-only prediction calibration report with uncertainty bounds and
  contradiction counts;
- one-way Anthropicer/Obsidian projection that preserves user notes and keeps
  SQLite authoritative.

This is a real emergence detector, but not a finished evolving mind. It
intentionally stops at proposing candidates. Still planned: stronger
independence tests across episodes/hosts, contextual usefulness feedback,
dismissible notification receipts, structured MCP resources, strategy
holdouts, and longitudinal proof that accepted learning improves outcomes.

## Crucible result

**Decision:** proceed with the direction; investigate before automating
promotion.

Load-bearing assumptions and their tests:

- **Assumption:** memory-level adaptation can improve outcomes without weight
  training.
  **Test:** replay comparable tasks with and without learned strategies.
- **Assumption:** usefulness feedback will not merely reinforce popularity.
  **Test:** scoped feedback, counterfactual retrieval, stale-memory, and
  poisoning holdouts.
- **Assumption:** CodeGlass can strengthen human understanding.
  **Test:** teach-back immediately and delayed recall on real code changes.
- **Assumption:** signals from different hosts/models are comparable.
  **Test:** normalized provenance plus cross-host task fixtures.
- **Assumption:** derived strategies remain understandable enough to govern.
  **Test:** every promotion must render its evidence, scope, confidence, and
  rollback in one inspection view.

## Sequence

Foundation hardening comes first. Functional growth cannot be trusted while
embeddings can mix, retrieval can omit scoped evidence, workflows can
half-commit, provenance is incomplete, or host adapters can diverge.

After those gates:

1. ~~typed episode/failure/teaching receipts and immutable provenance~~;
2. contextual retrieval feedback rather than global popularity alone;
3. reflection and consolidation runs with derived-from citations;
4. candidate strategy lifecycle: propose → evaluate → promote → retire;
5. ~~initial prediction calibration dashboard~~; next add repeated-error and
   longitudinal comparison views;
6. ~~CodeGlass teach-back, delayed retention, and user-learning memory~~;
7. ~~Discovery Ledger, Human Learning Log, automatic evidence thresholds, and
   Anthropicer projection foundation~~;
8. longitudinal “is Cairntir actually getting better?” evaluation.
