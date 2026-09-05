# Retrieval preflight experiment

Status: proposed evaluation; no implementation authorized by this plan alone.

Test whether receipt-visible retrieval preflight improves outcomes over explicit
handoff and recall. Pre-register a holdout before implementation. Include
relevant, irrelevant, stale, contradicted, untrusted, and malicious memories.

A candidate may abstain. It must show provenance and preserve scope, trust,
freshness, and authority boundaries. It must not rewrite the user's prompt,
promote imported evidence, modify model weights, or silently change source code.

Measure full-evidence recall, unsafe retrieval, stale-memory rejection, task
success, and cost against the existing baseline. More memories or more frequent
retrieval do not count as improvement. Reject the idea if the holdout does not
show a useful gain without weakening safety.

The shipped foundation remains prediction-bound reasoning, discovery candidates,
human review, and calibration. Stronger adaptation requires evidence, not a
claim that the system has become an autonomous learning agent.

## Finalization Mode

Before coding, register the exact holdout, success thresholds, baseline,
non-goals, and independent tester. Freeze tester-authored acceptance artifacts
outside the coder's write scope. Reserve the final phase for holdout verification.

Allow at most two repair-and-verification rounds; unchanged state is not
progress. Terminate COMPLETE only after independent PASS and all registered
thresholds, BLOCKED for an external prerequisite, or EXHAUSTED when the repair
budget is spent. No automatic promotion or release publication.
