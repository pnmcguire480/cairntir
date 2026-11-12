# Claim tests

Available from **1.14.0**. `cairntir claim-test` turns a falsifiable claim into a
test that is actually run. Cairntir does not write the test. A different author
does, a person or another agent, and Cairntir makes sure the test that runs is
exactly the one that author froze.

A claim comes from a drawer that holds both a `claim` and a `predicted_outcome`.
A drawer without a prediction is refused.

## The four steps

**1. Export a packet.** The packet is a folder holding the claim, the
prediction and the name of the module the subject must provide. It never holds
the subject's source, so the author cannot copy answers from the thing under
test.

```bash
cairntir claim-test export ./packet --drawer 42 --interface pricing --claimant alice
```

**2. A different author writes the tests.** They add one or more files named
`tests/test_*.py` inside the packet, using only the Python standard library
`unittest` module.

**3. Freeze the tests.** This records each test file's SHA-256 in `FROZEN.json`.
The author name must differ from the claimant name given at export.

```bash
cairntir claim-test freeze ./packet --author bob
```

**4. Run them against a subject.** The subject is a folder that provides the
module named at export. The frozen bytes are checked again and then run in a
separate Python process.

```bash
cairntir claim-test run ./packet --subject ./candidate
```

## Verdicts

| Verdict | Meaning |
| --- | --- |
| `HELD` | Every executed case passed. |
| `FALSIFIED` | At least one case failed: the claim does not hold for this subject. |
| `NOT_EXECUTED` | No case ran. A packet with no test file, or only skipped cases, lands here. Prompt text alone is never reported as a test. |
| `INCONCLUSIVE` | The run could not finish, for example it timed out. |

## Qualifying the tests themselves

A test that passes against broken behavior proves nothing. `qualify` runs the
frozen tests against a subject known to be wrong and one known to be right:

```bash
cairntir claim-test qualify ./packet --known-bad ./broken --corrected ./fixed
```

It reports `QUALIFIED` only when the known-bad subject is `FALSIFIED` and the
corrected subject `HELD`. Anything else is `NOT_QUALIFIED`.

## Exit codes

| Code | When |
| --- | --- |
| 0 | `export` or `freeze` succeeded, `run` reported `HELD`, or `qualify` reported `QUALIFIED`. |
| 1 | `run` reported any other verdict, or `qualify` did not qualify. |
| 2 | The command was refused: for example changed test files, a changed claim, an author equal to the claimant, or a drawer with no prediction. |

`run` and `qualify` accept `--timeout` in seconds (default 120).

## Limits

- The author check compares the two names you supply. Cairntir cannot prove two
  names belong to different people or agents.
- Tests are limited to the standard library `unittest` module.
- No independent checker session has reviewed this feature yet.
