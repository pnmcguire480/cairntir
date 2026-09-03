# Reason Loop Boundary Hardening

**Status:** implemented as part of the v1.9.0 release candidate and locally
verified on the isolated PR #84 branch; protected CI remains before merge.
Canonical `main` remains untouched.

## Evidence

- Drawer #118 defines the Karpathy-derived loop as prediction, experiment,
  observation, surprise, evidence-bound learning, and human-governed promotion.
- Drawer #342 proves that success and surprise are independent: a prediction can
  hold while the route differs, so `delta` must not be inferred from verdict.
- Drawer #1215 records the founder request to harden this loop before merge.

## Problem

`ReasonLoop.step()` trusts protocol type hints at runtime. A broken adapter can
return a blank claim, write into a different wing or room, attach an outcome to
a different hypothesis, omit the experiment or observation, or pass a non-bool
verdict. The loop also has no way to preserve a path-level surprise when the
prediction succeeds, and a caller can request idempotency from a gateway that
cannot provide durable replay.

Those are integrity failures at the loop boundary. They make the stored record
look more certain, scoped, or replay-safe than the actual run.

## Change

Keep the existing four ports and one-step orchestration. Add only boundary
validation and one additive value:

1. reject blank questions, claims, and predicted outcomes before a prediction
   drawer is written;
2. require the proposed hypothesis wing and room to equal the invocation scope;
3. require a positive `supersedes_id` when one is supplied;
4. require the runner's outcome to reference the exact proposed hypothesis,
   carry a non-empty experiment description and observation, and use a real
   boolean verdict;
5. add optional `Outcome.delta`, preserving explicit surprise independently of
   success while retaining the generated fallback for failed predictions;
6. persist the experiment description with the observation;
7. reject `idempotency_key` when the memory gateway cannot durably replay it;
8. expose optional delta through `NullRunner` and every shipped CLI path that
   drives it (`reason`, `replay`, and `recipe-run`);
9. admit only observation drawers bound to a matching Reason prediction into
   automatic discovery;
10. keep repeated-claim discovery scoped to the originating room instead of
    combining unlike contexts inside a wing;
11. count each prediction at most once so branched observations cannot
    manufacture independent episodes.

No inference, autonomous promotion, new dependency, schema migration, or public
root export is added. Existing valid callers remain source-compatible because
`Outcome.delta` defaults to the empty string.

## Frozen acceptance inventory

- A blank claim is rejected before any drawer or belief write.
- A proposer cannot redirect a step into another wing or room.
- A runner cannot settle a different hypothesis than the one committed.
- Blank experiment descriptions, blank observations, and non-bool verdicts fail
  loudly before observation or belief mutation.
- A successful prediction can retain a non-empty path-level delta without being
  weakened.
- A failed prediction with no explicit delta still receives the deterministic
  predicted-versus-observed fallback.
- The observation drawer preserves the experiment description.
- A non-durable gateway cannot silently ignore an idempotency key.
- Outcome-shaped or unbound drawers cannot manufacture learning candidates.
- Repeated claims in different rooms remain separate evidence populations.
- Multiple observations of one prediction do not count as multiple episodes.
- Existing public API names, store schema, and valid Reason/recipe flows remain
  green.

## Verification reserve

Write the regression tests before production changes. Run focused Reason and
durability tests, the complete non-slow suite with coverage, Ruff lint/format,
strict mypy, landed commitments, package build/install smoke, and the remote
GitHub matrix. At most two repair-and-verify rounds are allowed; an identical
retry against identical state is not progress.

```cairntir-commitments
symbol src/cairntir/reason/loop.py ReasonLoop
symbol src/cairntir/reason/model.py Outcome
symbol src/cairntir/learning.py propose_multi_episode_discoveries
test   tests/unit/test_reason_loop.py test_reason_loop_rejects_cross_scope_hypothesis_before_writing
test   tests/unit/test_reason_loop.py test_reason_loop_rejects_outcome_for_a_different_hypothesis
test   tests/unit/test_reason_loop.py test_reason_loop_rejects_outcome_without_an_experiment
test   tests/unit/test_reason_loop.py test_successful_step_preserves_explicit_surprise_delta
test   tests/unit/test_reason_loop.py test_non_durable_memory_rejects_idempotency_key
test   tests/unit/test_learning.py test_multi_episode_reflection_ignores_unbound_outcome_shaped_drawers
test   tests/unit/test_learning.py test_multi_episode_reflection_keeps_rooms_separate
test   tests/unit/test_learning.py test_multi_episode_reflection_counts_each_prediction_once
test   tests/unit/test_cli.py test_replay_extends_supersedes_chain
test   tests/unit/test_cli.py test_recipe_run_preserves_explicit_delta
```

## Finalization Mode

`COMPLETE` requires the frozen tests, full local gate, package smoke, remote CI,
clean pushed branch, open mergeable PR, and canonical `main` still clean at
`4e123a1f8a91f3867046a818490de63f4d8433e7`. GitHub Actions is the independent
execution environment; the pre-existing protocol, calibration, and durability
tests remain outside this slice and may not be weakened. `BLOCKED` names one
external dependency and its smallest unblock. `EXHAUSTED` stops after two repair
rounds. Merge and live-store mutation remain separate gates. Patrick explicitly
authorized the `v1.9.0` tag and trusted GitHub/PyPI publication after the exact
candidate finishes protected CI and merges.
