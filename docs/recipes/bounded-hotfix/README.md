# Bounded Hotfix

Bounded Hotfix prepares a repair contract and then records its execution as an
append-only evidence chain. It is a recipe over Cairntir's existing Quality and
Crucible skills, not a fourth skill and not an autonomous repair agent.

## Boundary

The host reads files, runs commands, changes the isolated target, and gathers
evidence. Cairntir does none of those things. `cairntir_hotfix` validates the
order and bindings of caller-supplied records and returns a durable receipt.
Caller identities and observed hashes are assertions. The event hash chain
detects local corruption and forks; it is not a signature and its drawer IDs
are local to one store.

## Prepare the contract

```bash
cairntir recipe-run bounded-hotfix \
  --input failure="A4 protected smoke failed after ACL preparation" \
  --input acceptance="ACL exact; zero-capability worker; smoke passes" \
  --input candidate_paths="rebuild protected broker from cited failure evidence" \
  --input authority_boundary="cache-only target; no live mutation; independent verifier" \
  --input max_attempts=1
```

Quality checks whether the repository and evidence can support the claim.
Crucible attacks the proposed finish line and authority boundary. Freeze the
result before the first attempt.

## Record the run

Call one action at a time and follow `legal_actions` from the returned receipt:

| Action | Required proof |
|---|---|
| `open` | failure, frozen acceptance, non-goals, attempt budget, cited evidence |
| `recommend` | host-proposed candidates, same-wing evidence, state change, reversibility, risk, optional completed precedents |
| `authorize` | selected candidate plus exact candidate/plan/toolchain hashes, target, executor, capabilities, action boundary, checks, sequence |
| `preflight` | a different inspector, exact observed bindings and capabilities, state hash, fresh evidence for every required check |
| `record_attempt` | the authorized executor, allowed actions only, before/after hashes, outcome, evidence, artifact digests, rollback reference |
| `verify` | a different verifier, exact post-attempt hash, and one evidence-cited result for every frozen acceptance item |
| `rollback` | authorized rollback executor, different verifier, bound rollback reference, and exact pre-attempt state hash |
| `settle` | reusable resolution for `complete`, blocker and smallest unblock for `blocked`, or consumed attempt budget for `exhausted` |
| `status` | case ID only; performs no write |

Every mutating action needs a unique stable idempotency key. Replaying the same
key with the same request returns the original receipt; changing its request is
rejected. One authority envelope permits one attempt. A failed attempt cannot
be retried when the next preflight observes the same failed state. Changed
failed state must be rolled back before a terminal `blocked` or `exhausted`
settlement.

Candidate ranking is deterministic: strongest completed precedent, actual
state change, more cited evidence, reversibility, lower risk, then candidate ID.
Exact fingerprint matches outrank same-stage/failure-class and class-only
precedents. The returned precedent includes its recorded resolution and outcome.

## Stop conditions

- `COMPLETE` requires a passing attempt, complete independent acceptance, and a
  reusable resolution.
- `BLOCKED` names the blocker and smallest external unblock after any changed
  failed state has been rolled back.
- `EXHAUSTED` requires the recorded attempt budget to be consumed and the same
  rollback rule to hold.

Terminal cases advertise no legal actions and cannot be reopened. Further work
starts a new case with new explicit authority; it never silently extends the
old attempt budget.
