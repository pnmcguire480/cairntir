# Claim test packet

You are the independent test author for one falsifiable claim. You have not
seen the subject's source and must not ask for it.

## Claim

reading_minutes(text) rounds the reading time up to whole minutes at 200 words per minute, and any text with at least one word takes at least one minute.

## Predicted outcome (what must be observed if the claim is true)

reading_minutes('') == 0; one word gives 1; exactly 200 words gives 1; 201 words gives 2; 400 words gives 2; 401 words gives 3. Words are separated by any whitespace.

## Interface

The subject is importable as `readtime`.

## What to write

- One or more files named `tests/test_*.py`, using only the Python standard
  library `unittest` module.
- Each test must fail if the predicted outcome does not hold.
- Derive every expected value from the claim and prediction above. Never
  compute an expected value by calling the subject, and never compare the
  subject's answer with itself.
- Do not skip tests and do not use `expectedFailure`.

When you are done, the claimant freezes your files with
`cairntir claim-test freeze PACKET --author YOUR_ID`. Your identity must differ
from the claimant's.
