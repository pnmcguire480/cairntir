# Cairntir ethos

## 1. Comprehension before code

Understand the request, existing implementation, and evidence before changing
them. Use Crucible for load-bearing assumptions. Prefer the smallest mechanism
that closes a demonstrated gap.

## 2. Preserve the evidence

Keep drawer content verbatim. Append predictions, observations, and corrections
with provenance; do not rewrite history to make an earlier claim look right.
Distinguish a verdict from the surprise encountered along the way.

## 3. Make failure visible

Use typed, surfaced errors. A skipped check, unsupported adapter, exhausted
budget, or missing receipt must remain visible. Never substitute an optimistic
claim for a result.

## 4. Keep the user in control

Local storage is authoritative. Recovery is opt-in and untrusted; storage
requires an explicit write. Importing evidence does not grant authority.
No new dependency, expanded execution authority, or irreversible operation
without the required approval.

## 5. Verify the finish

Bind work to tests, verify component boundaries together, and use independent
acceptance for finalization. Stop after bounded repair rounds. Publish only
through the release gate; a changelog entry is not a release.

These principles descend from the
[BrainStormer design lineage](docs/lineage/brainstormer.md). Cairntir implements
its own memory-first architecture, not BrainStormer's kernel or agent runtime.
