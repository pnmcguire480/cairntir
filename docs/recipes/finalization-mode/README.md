# Finalization Mode — Bounded Roadmap Closure Recipe

> **Recipe, not skill.** Cairntir keeps its three-skill core. Finalization Mode
> combines Quality evidence with a Crucible stress-test and a hard stop budget.

## When to use this

Run Finalization Mode when drafting a roadmap and again when its implementation
enters the final phase. The roadmap is not executable until its ending is clear.

## Contract

Extract and freeze:

1. the outcome the user or business will recognize, not an activity proxy;
2. atomic acceptance items and the fresh evidence that proves each one;
3. explicit non-goals and forbidden shortcuts, including weakening tests;
4. dependencies, authority boundaries, and known external blockers;
5. a total work budget, a protected verification reserve, and a maximum of two
   repair-and-verify rounds; externally billed or protected gates get one;
6. one of three terminal dispositions: `COMPLETE`, `BLOCKED`, or `EXHAUSTED`.

Send only the thesis, issue, and test parameters to an impartial tester before
coding. The tester authors the acceptance tests and freezes their hashes. The
coder may consume tests and failure evidence, but test paths remain outside the
coder's write scope. A changed test hash invalidates the run instead of becoming
a repair attempt.

The independent result vocabulary is `PASS`, `FAIL`, or `INCONCLUSIVE`. Honest
red is useful: it identifies a gap the coder can repair. False green is a
contract breach. Test deletion, selective-suite substitution, weakened
assertions, expectation rebaselining, and fixture-specific production logic all
invalidate the run and remain visible in the terminal evidence.

## Execution loop

For each round:

1. choose the highest-value unmet acceptance item;
2. make the smallest change that can close it;
3. run the narrow proof, then the broader proof only when the roadmap requires
   it;
4. update the acceptance inventory with evidence and remaining gaps;
5. continue only if the round changed relevant state, produced new evidence, or
   falsified a named hypothesis.

Do not repeat an identical check against identical state. Do not invent work
after every acceptance item passes. Do not spend the verification reserve on
implementation.

## Terminal report

- `COMPLETE`: the independent tester returns `PASS`, every acceptance item has
  fresh evidence, and all non-goals held.
- `BLOCKED`: name the unmet item, retained evidence, and smallest external
  action that can unblock it.
- `EXHAUSTED`: name the round or resource limit reached and preserve the last
  reproducible state. Further work requires a new roadmap or explicit amendment.

Before reporting `COMPLETE`, use Quality to audit the evidence and Crucible to
ask whether the passing condition represents the requested outcome or merely a
score the agent learned to game.
