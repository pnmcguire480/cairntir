# Core release acceptance basis

Status: PRE-IMPLEMENTATION BASIS; NOT EXECUTED; NOT RELEASE QUALIFIED. Prepared 2026-10-01 by independent static reviewer for the explicitly revised release plan. This document defines evidence for an existing core release; it introduces no runtime API, schema, automatic capture service, or orchestration contract.

## Release boundary

Deliver dependable, lightweight local cross-chat memory first for Patrick and Lou. Use explicit acknowledged saves, exact retrieval, and task continuity through the existing interfaces. After this core proves dependable, introduce one or two features per measured release. The full 35-item roadmap remains preserved for later releases; it is not the first core release gate. Ten users are not required for this first pilot. Existing released core commitments remain regression obligations.

Starting branch: `codex/core-reliability-20261001`, isolated at `C:/Users/pnmcg/AppData/Local/Temp/cairntir-core-release-20261001`, based on commit `29c62abbd46f2d5e1b7ca0aec813bd2b4818cf43`, tree `dbbc71b5425b1089f46e79561330e3f195b5bb8e`. These are starting identities, not future release identities. Reviewed maintenance changes from pinned PR122 may enter only with their own exact source/artifact qualification. The broad `a70564526fab58e2b91f0fee9d0e88846403a29a` candidate remains parked and preserved; no wholesale import is presumed.

A version string in source, package metadata, registration file, or earlier report alone is not proof of the loaded runtime. Do not presume the currently installed package is this candidate. No publication, installation into live environments, live configuration change, host restart, or production migration is authorized by this acceptance document.

## Evidence and freeze rules

Freeze this basis and the independently authored executable controls before significant implementation. Record their hashes outside the frozen files. Any clarification or resource-budget decision must be an explicit dated, hash-pinned amendment that preserves the original basis and controls. If a control is defective, retain its original outcome and prove the amendment changes only that defect; do not silently weaken the user outcome. Freeze expected negative-control failures before running them. Preserve reproducible behavioral failure before repairing a reproduced product defect.

Each result records PASS, FAIL, BLOCKED, NOT RUN, or DEFERRED, its exact subject, command or native-client action, source/package/test identity, timestamp, outcome, and evidence reference. A skipped case, fixture/import failure, timeout, stale receipt, successful registration, or SDK-only test cannot count as native-host success. Preserve incomplete and unsuccessful runs. Redact credentials and private conversation content without erasing identity distinctions or test evidence. Use unique synthetic canaries and disposable stores for destructive failure cases; do not use the users' real memories as test fixtures.

These eight checks are the core acceptance boundary:

## C1. Loaded runtime, store, and authority identity

For every participating actual host session, bind the observed host/client version and session to the actual server process, absolute executable/interpreter, loaded Cairntir module/package location, exact installed artifact version and byte identity, resolved database identity/location, schema version, and effective owner or scoped access context. Retain evidence that ties those facts to the process handling the observed tool calls. A shell's interpreter or package listing is insufficient if the host loads another process. Do not expose grant tokens.

Negative controls, in isolated configuration/processes, cover a wrong launcher, an older still-running process, a different store, missing registration, and insufficient access. The evidence must distinguish configured, observed running, and currently unverified states. Each wrong identity must be visible and must not be counted as the intended target. Do not silently create a replacement store or report empty memory as successful continuity.

`doctor` currently maps configuration presence to `MCP=ready`; that result proves wiring inspection, not a handshake or current connection. Qualify it accordingly. Unknown or aged observations must not appear as fresh health. Failure/unavailability must be visible where a user depends on a save or retrieval. This requires truthful evidence and wording, not a new always-on monitoring service.

## C2. Explicit attributed save, exact retrieval, and correction

Through the selected real native client, explicitly save a unique synthetic request with the existing task/checkpoint interface, retain the acknowledged task/drawer/revision receipt, retrieve the exact saved content, and verify the stored provenance corresponds to the observed host and access context. Then append a uniquely identifiable correction to the same task, retaining the original request and prior constraints. Resume must show the acknowledged current revision and next action while the original evidence remains retrievable.

Prove exact content and attribution from the durable records and native-client result, not only from the agent's statement that it remembers. No unsaved message, automatic transcript capture, or synthesized recap may be represented as an acknowledged save. Existing semantic recall also needs at least one bounded real local-provider retrieval check; deterministic Hash32 tests establish plumbing only. Anchored/direct retrieval and exact resume remain separately identifiable from semantic search.

## C3. Restart, interrupted process, and uncertain acknowledgement

After an acknowledged save and correction, close/restart the actual selected host/server path and recover the same task and exact acknowledged content from the same intended store. In a disposable equivalent setup, forcibly terminate only the owned actual worker after its acknowledgement and before clean shutdown; retain worker identity, acknowledgement, termination, fresh-process identity, and recovered bytes. Killing a launcher without proving worker termination is insufficient.

Exercise a lost acknowledgement using the existing exact retry identity/payload. The retry must return the existing committed result without duplicate checkpoint revisions or evidence. Conflicting reuse must fail without overwriting prior evidence. An uncertain result must remain uncertain until reconciled; no invented success receipt. These are checks of existing persistence/retry semantics, not a new replay protocol.

## C4. Second host and scoped continuity

Use a second actual supported native host/client, in a new conversation, connected to the same intended local continuity store. Resume the specific task and retrieve its original request, corrected current state, constraints, and next action without re-entering them. Confirm the same database identity and current committed revision. Test ambiguous task discovery, a stale update, wrong task/store selection, and a denied scope through the existing interfaces; each must be visible and preserve committed content without unauthorized disclosure or fallback to another task.

A real SDK subprocess demonstrates transport behavior but does not replace a native client's delivery, permissions, process selection, or user-visible result. The present agent has no callable Cairntir native-client tool or GUI capability; until a real authorized operator/client supplies this evidence, the native-host check is BLOCKED or NOT RUN. No fabricated host attribution or inferred pass from registration.

## C5. Patrick and Lou: same package, separate intended stores

Qualify both machines with the same immutable built package bytes and matching installation receipts. Each user's selected host paths must point to their own intended store and access context; cross-host continuity within a user's environment is not permission to share Patrick's private store with Lou or vice versa. Repeat the finite identity, save/correction, restart, and handoff checks on both machines and record machine/runtime differences.

Maintain a portable evidence ledger containing artifact hash, source identity, host/runtime and schema observations, synthetic task identities, test outcomes, resource results, remaining blockers, and evidence hashes/relative links. Do not make the proof depend on one reviewer's absolute workspace paths or ship secrets/private stores in the ledger. This is an evidence index, not a new product data format. No ten-user prerequisite.

## C6. Disposable installation, backup, recovery, and rollback compatibility

Install the exact built artifact into a disposable environment and exercise it outside the source checkout. On disposable representative stores, verify fresh initialization and the supported upgrade path, backup, restore, usable original content/task history, and rollback behavior. A backup file's existence is insufficient. Record old/new schema and package identities and prove restored content can be opened and resumed.

If the old package cannot open the new schema safely, rollback instructions must preserve new evidence and restore a compatible backup; do not claim package downgrade alone is safe. Rehearse the stated path without destructive operations on live stores. The rollout/rollback operator approves a concrete package, verified backup/recovery procedure, target hosts/stores, and rollback limitations before live deployment. No destructive failure injection on either user's real data.

## C7. Exact source and installed-artifact release qualification

Qualify the final source tree and exact wheel, not only this initial base. Preserve the configured coverage surface and 92% statement-and-branch floor with six-place precision; do not add exclusions, weaken typing, or relabel an internal-closure diagnostic as full typing. Execute the repository's full required check set in a suitable authorized thermal/network/model window, preserving commands, versions, exit results, logs, and tested hashes. A deferred heavy gate remains deferred, not a release pass. Retain the supported-platform/Python CI evidence for the claimed release support.

The current base's CONTRIBUTING.md requires:

```text
uv run ruff check src tests scripts addons
uv run ruff format --check src tests scripts addons
uv run mypy --strict src
uv run pytest -m "not slow"
uv run pytest -m eval --no-cov
uv run pytest -m "slow and not eval" --no-cov
uv run python scripts/check_no_silent_except.py
uv run python scripts/check_release_tags.py
uv run python scripts/check_landed_commitments.py
uv run python scripts/check_seams.py
uv run python scripts/check_docs_links.py
uv run python scripts/check_dependency_advisories.py
uv run python scripts/check_verification_preservation.py
uv run python scripts/verify_history.py --output .cairntir/verification/history
uv run python scripts/verify_mutations.py --output .cairntir/verification/mutations
uv run mkdocs build --strict
uv build
uv run python scripts/verify_package.py --wheel dist/cairntir-<release-version>-py3-none-any.whl --output .cairntir/verification/package
```

The wheel placeholder must be replaced with the one exact artifact being released and recorded by hash. Use the unchanged final repository configuration/lock; reconcile any reviewed maintenance change to these commands explicitly before execution. Model provisioning and network-dependent checks are separate authorized preparation, not permission granted here. Installed CLI/MCP checks must exercise the actual built installation and entrypoints outside the checkout; native-host proof in C2-C5 is still additionally required. Deliberate isolated mutations must demonstrate the critical controls reject the corresponding broken behavior, with a clean positive control.

## C8. Lightweight resource limits and honest release status

Before measurement, approve and hash-pin numeric budgets and the measurement recipe. No numeric budgets were supplied for this basis. Undefined budgets cannot pass, and results must not determine the threshold retroactively. The pre-run amendment must name the selected machines/hosts, representative synthetic store/history sizes, cold/warm conditions, repetition count and statistic, sampling window, process aggregation, and allowed background activity.

Measure separately: process launch to usable handshake; first and warm acknowledged save; exact resume/direct retrieval; cold and warm local semantic retrieval; steady idle CPU and resident memory; and simultaneous selected hosts' aggregate resource use/latency. Separate fresh-store/model provisioning from normal startup and report due-backup/update/warmup conditions. No claim of zero idle cost from a short SDK run, no provider latency claim from Hash32, and no extrapolation from historical source comments. Existing synchronous due backups and accumulated task-history reads require representative conditions in the chosen recipe. Establish a safe thermal stop rule; exceeding it produces DEFERRED/INCONCLUSIVE rather than a passing resource result.

The release packet must update CHANGELOG, user/operator instructions, and CHANGE-STATUS with what is implemented, tested, installed, verified live, blocked, and parked. Explain explicit-save boundaries, acknowledgement/uncertainty, store/host identity, scope, health freshness, recovery/rollback, and measured limits in user terms. Keep later all-35 work distinct from this core release without erasing its evidence or commitments. Final release claims require all eight applicable checks and predeclared resource budgets to pass on the exact artifact; otherwise report the specific blockers. Publication/live installation remains a separate concrete operator action.

## Initial result

All C1-C8 execution results are NOT RUN under this basis. Resource limits are PENDING PRE-RUN AMENDMENT. Native-client access is currently unavailable to this agent. No source modifications, model loads, tests, builds, installation, registration, live-store access, or host restart occurred while preparing this document.