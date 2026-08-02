# Landed Commitments

A plan that promises something is making a claim. This is the check that
the claim came true.

## The defect it closes

It is the oldest defect in the lineage and the only one present in all
four generations. BrainStormer's 2026-04-03 harness audit named it:
*infrastructure without the enforcement layer.*

Then it recurred at the level of the recovery plan itself. The
2026-07-27 evolution audit correctly diagnosed that Cairntir had lost the
context-control discipline it inherited from BabyTIEROS, and wrote
*"restore explicit context budgets"* into the **v1.2 core** list. v1.2
was implemented, verified across three hosts, released to PyPI, and
attested — **without the fix.** Nobody noticed for five days, and it was
only found because someone went looking through the lineage.

The pattern is not "we build badly." It is:

> **We do not verify that a commitment landed.**

`scripts/check_release_tags.py` already solved one narrow instance: a
changelog header is a claim, and CI fails if the matching tag is missing.
That check exists because the same gap silently swallowed 1.0.1 and
1.1.3. This generalises the idea to plans.

## How to use it

Put a fenced `cairntir-commitments` block in any plan or doc. Every line
is an assertion about the codebase, verified by CI.

````markdown
```cairntir-commitments
# Finding 5 — the composed brief, and the budget v1.2 promised.
symbol src/cairntir/handoff.py compose
param  src/cairntir/handoff.py compose:budget_chars
test   tests/unit/test_handoff.py test_included_drawers_are_returned_whole
file   docs/release-cadence.md
```
````

Four kinds, deliberately few:

| Assertion | Verifies |
|---|---|
| `file <path>` | The path exists. |
| `symbol <path> <name>` | That Python file defines a function, method, or class of that name. |
| `param <path> <function>:<parameter>` | That function accepts that parameter — positional or keyword-only. |
| `test <path> <name>` | That test file defines a test of that name. |

`param` is the one that earns its place. **`session_start` existed the
whole time** the v1.2 budget was outstanding — it simply never grew the
argument. Only a parameter-level assertion catches that; a symbol check
would have passed happily.

## Rules

**A malformed block is a failure, never a skip.** An assertion nobody can
parse is an assertion nobody is checking. This is not hypothetical: the
four-segment version proposal (`1.2.0.0`) was rejected in drawer #177
precisely because `check_release_tags.py` would have *skipped* the header
rather than flagged it — re-creating the 1.1.3 failure inside the tool
built to prevent it.

**Write the assertion when you write the promise, not when you keep it.**
A block added after the work lands only documents the past. A block added
with the plan fails loudly the moment the plan ships incomplete, which is
the entire point.

**Do not delete an assertion to make CI green.** Either the commitment
landed, or the plan changed and the plan document should say so in prose
first.

## Running it

```bash
python scripts/check_landed_commitments.py
```

Exit code 1 if any commitment is declared but absent. Wired into the CI
lint job and the release verification gate, so an unlanded commitment
cannot reach `main` and cannot be published.
