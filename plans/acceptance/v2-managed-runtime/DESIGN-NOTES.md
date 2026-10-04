# R06 / R07 / R09 / R10: managed local runtime

20 September 2026. Design only; no runtime, host configuration, application code or live store changed. This is a proposed implementation contract for independent freezing, not delivered acceptance evidence.

## Approved requirements recovered

The four complete source sections were compared: the approved snapshot and working register match exactly. Their action, dependency and closing criteria are quoted below. Their authority is the approved `v2-design-2026-09-20-r1` snapshot, not this design. All remain Week 1 obligations owned by the Continuity owner; narrowing a first implementation does not silently close the broader host-delivery obligation.

Source: [approved commitments](<C:/Dev/Cairntir/.cairntir/evolution-audit-20260920/approved-v2-baseline-r1/04-Cairntir Integration Commitments.md>), SHA256 `af14f0d28d951ce7c313368416ac97a988e84abb3e08fc999930e2be428ae245`; [approved roadmap](<C:/Dev/Cairntir/.cairntir/evolution-audit-20260920/approved-v2-baseline-r1/03-Cairntir Near-Term Integration Roadmap.md>), SHA256 `e576dc0b8327532f12709721a6e9c72b2ca3432cf16d67853e29c75056a985cc`.

**R06 — Unconditional session-start briefing agent. Historical disposition: Partial.**

> Run the existing briefing automatically when the supported host starts/resumes, with an acknowledgement receipt.
>
> Depends on: Host lifecycle adapter and current handoff API.
>
> Closes with: A fresh/restarted host receives the right project/task before its gated work; missing briefing is visible.

**R07 — Session-close agent captures deferred work even on abrupt exit. Historical disposition: Not implemented.**

> Persist incoming commitments incrementally; close reconciliation and next-start recovery collect unfinished work.
>
> Depends on: Acknowledged event intake; host integration cannot rely solely on shutdown hooks.
>
> Closes with: Forced termination preserves every acknowledged commitment; unacknowledged input gaps are reported. No promise of recovering bytes never captured.

**R09 — Mandatory read of previous promises before work proceeds. Historical disposition: Partial.**

> Require promise-brief acknowledgement before the supported adapter dispatches a new action.
>
> Depends on: R06 and controlled host dispatch boundary.
>
> Closes with: Bypass/absent acknowledgement blocks that dispatch; other unintegrated hosts are not falsely described as gated.

**R10 — Generate Last Session from a structured event log. Historical disposition: Partial.**

> Generate the Last Session view from recorded events/checkpoints with source links.
>
> Depends on: Structured event history and owned generated block.
>
> Closes with: Regeneration reproduces completed/outstanding work; retained human notes survive and missing events are visible.

The [working roadmap](<C:/Dev/Cairntir/vaults/Cairntir Coding Brain/Research/Cairntir Evolution Audit 2026-09-20/Cairntir Near-Term Integration Roadmap.md>) targets one supported coding host/project stack initially, and permits persistence/routing to operate without a thinking model. Its later scheduling amendment makes physical custody provisioning parallel work; it does not change these closing criteria.

## Existing mechanisms and actual gaps

Read-only discovery used active worktree HEAD `0428edda2eefa995fa8071dc194bd76bc7cbc556`, with E22 changes present separately. Task recovery drawer #2427 confirms the current scope; it is historical evidence, not execution authority.

| Mechanism | Reuse / gap |
| --- | --- |
| [TaskBook](C:/Users/pnmcg/.codex/worktrees/v2-foundation/Cairntir/src/cairntir/tasks.py:130) | Exact original request, complete replacement checkpoints, optimistic revision checking, scoped registry, durable replay, bounded raw resume. No automatic host event delivery. |
| [DrawerStore.execute_once](C:/Users/pnmcg/.codex/worktrees/v2-foundation/Cairntir/src/cairntir/memory/store.py:1240) | Request-bound committed receipts and atomic append. Suitable for database-only phases. Never put an external action inside its retriable action callback. |
| [ReasonLoop.step](C:/Users/pnmcg/.codex/worktrees/v2-foundation/Cairntir/src/cairntir/reason/loop.py:61), [StoreBackedMemory.atomic](C:/Users/pnmcg/.codex/worktrees/v2-foundation/Cairntir/src/cairntir/production/adapters.py:51) | Prediction is appended before runner invocation but remains in the enclosing transaction. Runner failure rolls it back. This is not durable pre-action commitment. Keep this API's existing semantics; introduce a separate managed dispatch path. |
| [Spool intake](C:/Users/pnmcg/.codex/worktrees/v2-foundation/Cairntir/src/cairntir/daemon/spool.py:50), [CaptureDaemon.tick](C:/Users/pnmcg/.codex/worktrees/v2-foundation/Cairntir/src/cairntir/daemon/capture.py:64) | Atomic queue-file replacement and filename/hash-bound replay after daemon processing. Producer gets a queue path, not a durable event receipt. Each producer retry creates another name. Not sufficient as the managed commitment acknowledgement. |
| [Host policy acceptance](C:/Users/pnmcg/.codex/worktrees/v2-foundation/Cairntir/plans/host-continuity-policy-acceptance.md:1) | Explicitly verifies distributed instructions, not model obedience or actual hook delivery. |

Generic Claude command/HTTP/MCP pre-tool hooks can time out without blocking the tool. SessionStart supplies context but cannot block. Agent SDK callbacks have a different timeout rule, but no SDK integration has been qualified here. Therefore this proposal does not use generic hooks as its authority boundary. [Official hook reference, checked 20 September 2026](https://code.claude.com/docs/en/hooks#timeouts), [decision-control table](https://code.claude.com/docs/en/hooks#decision-control).

Inspected file SHA256: `reason/loop.py` `862d489353e4d38282496686ee5199510e3d8035c9674df2d2a89cea60c6e1f0`; `tasks.py` `420b4b0fbb99625d3cecf4fe6c381d23a71ff6b60c1dfb31daed42c7197fcad8`; `daemon/capture.py` `45f0e919531550c08c24e864af8b8ceaf466283c7df80aa32fa0e5797a43b47e`; `daemon/spool.py` `f4d1f0c646d338539c583ebcfd272db4a9b7eac5b15da26830462eed90149d03`.

## One selected implementation

Add a foreground `cairntir managed` CLI worker with a bounded JSON-lines stdin/stdout protocol. The worker is the first supported runtime: it owns session start, event intake, acknowledgement checks, subprocess launch, result collection and session close. Its execution profiles initially cover explicitly configured local verification commands. No scheduler, model SDK, dependency, database table or MCP tool is added. Existing 21 tools continue supporting other clients unchanged.

The startup configuration fixes project root, wing, store, optional known task ID, generated-view target and named execution profiles. Requests cannot redirect those bindings. A profile fixes executable, argument template, working root, accepted parameters, environment names, timeout and output limit. Use argv and `shell=False`. No executable/shell text is extracted from a memory, prediction, transcript or model response. Only actions already authorized through that configured managed route may launch. Existing local/scoped store permissions are checked on every transition; receipt history never creates fresh permission.

This is a workflow boundary for the worker's own launches, not an OS security boundary. Same-user shell tools outside it remain outside it. Local models can propose jobs through the protocol later; they do not choose profile authority. Do not claim unattended Dream qualification or install any third-party host hook as part of this increment.

### Durable protocol and ordering

1. **Start/resume automatically briefs.** Generate a fresh runtime epoch, recover the selected task through TaskBook and collect scoped outstanding commitments, unresolved questions and uncertain prior dispatches. Do not silently select among ambiguous tasks. Return exact linked source records and a bounded brief with omissions/required size. Required promise evidence cannot be omitted and then acknowledged as complete. A new process always requires a fresh acknowledgement.
2. **Capture on receipt.** Input carries a stable event UUID, producer session UUID, monotonically increasing sequence, kind and exact UTF-8 content. Persist every submitted commitment/input event before acknowledging it; classification can be added later and cannot erase the original. Use dedicated request-bound workflow receipts and immutable structured drawers. In one database-only transaction append the event and update the TaskBook checkpoint with evidence links. Return event ID, payload hash, source identity/drawer ID, task ID/revision and committed status only after commit. Same event retry replays; changed payload or conflicting sequence rejects. A stale checkpoint surfaces a conflict and requires reconciliation rather than overwriting concurrent work. The client retains its event until acknowledged.
3. **Acknowledge the actual brief.** Record an acknowledgement bound to principal, runtime epoch, store/project/task, task revision, exact brief hash and commitment-state fingerprint. That fingerprint covers the served unresolved commitments/questions and pending dispatch state, not incidental access counters. A supplied hash alone is not an acknowledgement: validate the matching committed brief and acknowledgement records. Every newly captured commitment or relevant checkpoint change invalidates readiness. This proves protocol receipt, not human/model comprehension.
4. **Prepare and commit before action.** The action request names a stable action UUID, named profile, validated parameters, declared claim/predicted outcome and source commitment IDs. In a short transaction verify current grant/config/brief acknowledgement and absence of unresolved dispatches, then append the exact prediction, action envelope and dispatch-intent receipt. Bind profile/config and input hashes, task revision, acknowledgement and prediction ID. Commit before invoking the runner. No runner or model callback executes while this transaction is open.
5. **Launch once per committed intent.** Only the invocation receiving a fresh, non-replayed dispatch-intent receipt may enter `Popen`. A replayed intent never launches again. Distinguish an observed spawn failure from an intent whose outcome is unknown. The gap between commit and actual launch is intentionally conservative: a crash there leaves an uncertain action, even if it probably never ran. Do not requeue it automatically. Concurrent launch attempts must result in at most one fresh permit. Reconciliation requires explicit outcome evidence or separately authorized replacement action with a new ID; retain the uncertain original.
6. **Record outcome separately.** Persist actual process exit/timeout, bounded output with truncation indicators, artifact references/hashes, observation linked to the prediction, and a replacement checkpoint in a new transaction. The process result is the observed result of that profile, not proof that an unrelated user commitment is complete. Persist explicit completion/defer events with source links. If the outcome commit fails, retain the original committed prediction/intent and report outcome-recording failure. Do not repeat the subprocess.
7. **Close and recover.** Normal EOF/close records the final received sequence and session-close event, checkpoints outstanding work and regenerates Last Session. Closing a session does not make its task terminal. Abrupt termination needs no shutdown hook: next start lists every acknowledged open commitment and intent lacking an outcome. A missing close event yields interrupted/unclean status. Report detected sequence holes; without a producer's final watermark, the size of an undelivered tail is unknown, not zero.

All lifecycle decisions come from dedicated committed operation results bound to exact source IDs and hashes, not arbitrary `metadata.kind` objects. Reuse the store/scoped registry pattern with whole-group access checks. Ordinary remember/imported evidence cannot forge an acknowledgement, completion or launch permit. Events and checkpoints are immutable; generated views are rebuildable projections.

The first executor contract must record timeout/owned-process cleanup results. An unconfirmed descendant or lost process result remains uncertain and blocks another launch in that managed session; a timeout is never proof of rollback. Profile qualification and a real subprocess pilot precede claiming support for project commands that spawn children. No claim of arbitrary process-tree containment is needed to prove durable pre-action recording.

### Last Session projection

Own one clearly marked generated block in a configured `Last Session.md`, initially in a disposable vault/workspace. Render session/task identity, last acknowledged sequence, completed/outstanding exact descriptions, deferred items, uncertain actions, capture gaps and source links from the structured event/checkpoint records. Do not infer commitments or success from prose or exit code alone.

Preserve every byte outside the owned block, including human CRLF/Unicode. Reject duplicate/missing markers in an existing target rather than replacing human text. Database close/checkpoint commit precedes projection; file-write failure returns committed history plus projection failure, and an exact retry only regenerates the projection. Restart regeneration must produce identical generated bytes for the same event set. Do not rewrite CLAUDE.md or a human Last Session section implicitly.

## Independent acceptance to freeze before implementation

| Obligation | Required observable challenge |
| --- | --- |
| R06 | Real fresh/restarted worker emits the correctly bound brief before a synthetic external action marker; wrong project/task, ambiguity, unavailable store or omitted required promises prevent that marker. |
| R09 | Missing, forged, stale, swapped-project and prior-epoch acknowledgements prevent launch. Capturing another commitment invalidates the old acknowledgement. A clean current acknowledgement permits the configured action. |
| Pre-action durability | The child opens an independent database connection and sees the exact committed prediction/intent before writing its external marker. Kill the worker immediately before/after spawn and after the marker but before outcome persistence. Original commitment/prediction survives every case. |
| Retry/concurrency | Lost intake acknowledgement replays without another drawer; altered event conflicts. Two dispatcher processes racing the same action produce one launch at most. An outcome-less committed intent is never automatically rerun after restart. |
| R07 | Kill after each acknowledged Unicode/CRLF commitment and checkpoint, then recover exact outstanding items in a fresh process. Missing sequence, unacknowledged tail, absent close and failed capture are visibly distinguished. Revocation still denies replay/dispatch. |
| R10 | Regenerate exact completed/outstanding/uncertain state with source links; preserve human prefix/suffix byte-for-byte; malformed ownership markers reject. Projection failure after commit repairs on retry without duplicate events. |
| Authority/compatibility | Unknown profile, unsafe parameter/path redirection, forged memory lifecycle metadata, inaccessible source and changed config do not launch. Existing Reason rollback contract, task replay behavior, generic spool behavior and 21-tool inventory remain intact. |
| Real boundary | Installed worker runs outside the checkout, isolated store/cache/project, actual subprocess and forced termination—not only an in-process mock. No live project actions or host config changes for this proof. |

Do not implement a universal two-phase exactly-once executor. The concrete guarantee is durable intent plus at-most-one managed launch per action ID within its store/principal namespace, with explicit uncertainty after interruption. That trades automatic availability for preventing duplicate external effects. Initial durability proof covers forced process termination, not untested storage-device/power-loss behavior. A transaction containing the runner, or a restart that reruns every incomplete workflow, is the critical wrong control.

## Remaining delivery gap and next step

The local runtime can enforce and prove its own protocol without a host plugin. It cannot prove that every user message, assistant commitment or action from Codex/Claude/another host reaches it. An actual host adapter must forward stable input events, retain/retry until acknowledged, deliver the returned brief to the worker/model, obtain the protocol acknowledgement, and route supported actions exclusively through this dispatcher. Merely launching a host with a prompt or receiving a SessionStart callback does not establish that chain.

Freeze and build the managed worker slice first; then qualify one real event producer/action consumer end to end. Until that adapter has actual start/input/action/close/crash receipts, describe R06/R07/R09 as supported for managed sessions only and retain the named coding-host delivery gap. R10 may independently qualify for recorded managed events. Native host delivery, model comprehension and inaccessible/unsubmitted conversation bytes remain unverified.

Crucible preflight: [K strong] approved acceptance wording and existing transaction/spool behavior are directly inspected; [K strong] official generic-hook limitations prevent the proposed universal-hook claim; [A load-bearing] the new worker can expose a durable fresh-only launch permit and refuse replay, to be tested with real competing processes/crash witnesses; [U] actual coding-host event delivery and complete action mediation. Proceed with independent contract freezing for the bounded worker, not a claim that the host integration is already complete.
