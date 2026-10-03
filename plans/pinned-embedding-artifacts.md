# Pinned embedding artifacts (E22)

This single 1.14.0 source candidate is stacked on reviewed PR124 head
`65126e49faf49f542ddc4ee8d3361a2402e2838b`. Neither feature is published.
It selectively ports the previously planned E22 foundation, without importing
other parked v2 work, new dependencies, schema changes or MCP tools.

## User outcome

Semantic memory must use the same model and tokenizer bytes that produced its
index. A matching model name or vector dimension cannot establish that.
FastEmbed identifies registry-declared assets and exact runtime package versions
with a canonical SHA256 manifest, and loads only the pinned local directory.
Relocating identical assets under the same runtime preserves identity; changing
required bytes or runtime versions changes it. Mutable Hub refs cannot redirect
an already pinned provider. A loaded model retains its pinned identity.

`FastEmbedProvider.artifact_manifest()` returns detached JSON-compatible evidence
without constructing inference, acquiring assets or writing files. Manifest
schema, canonicalization, asset containment and lifecycle requirements are in the
[independent contract](acceptance/embedding-artifacts-1.14/CONTRACT.md).

Existing `doctor`, raw `get`, semantic recall/write guards and explicit
`reindex --yes --backup PATH` form the usable workflow. See the
[operator guide](../docs/embedding-artifacts.md). Hash/custom provider identities
remain supported. Missing assets may be acquired only by the existing explicit
first-use/prewarm routes; the temporary acquisition object never supplies
accepted vectors. Invalid evidence is not an acquisition trigger.

## Acceptance and boundaries

Thirty-five public synthetic controls were frozen before this port: the original
25 controls, two configured-cache controls and eight workflow/adversarial controls.
Baseline failures and fixture amendments are preserved separately. They cover
canonical identity, equal-size mutation, relocated assets, missing files,
path containment, detached manifests, moving refs, exact local construction,
legacy refusal/raw reads, empty stores, backed-up rebuilding and rollback.
Integrated bounded verification: 90 pytest cases pass with three Windows
symlink privilege skips. Independent review passes its 12 underlying controls
and detects deliberate verification bypass. Two bounded product repair rounds
closed invalid acquisition classification in plain/Hub caches and offline typed
filesystem errors. Original tests and assertions remain preserved. Windows symlink skips are not
passes; hosted platform evidence is reported separately.

At most two product repair rounds and at least 25 percent verification reserve.
Repository CI, focused independent adversarial review and exact-tree patch
reconstruction remain required before feature completion. Current results belong
in the PR and evidence packet; this plan does not claim pre-qualification success.

The earlier combined v2 plan's two-customer-machine and protected-evaluator
evidence remains unproved. Public CI or shared-workspace tests do not establish
it. No authentication, host grants, live migration, production install, merge or
release is authorized by implementing this feature. No token/cost saving is
claimed. Review completion and production adoption are separate gates.
