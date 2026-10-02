# Change and adoption status

Updated 2026-10-02. This is a portable maintenance record, not an installation
receipt. The current published release is **1.12.3**; the changes below remain
an unmerged, unreleased candidate. Source version and a configured launcher do
not establish what a running host loaded.

## Release boundary

Deliver dependable lightweight local memory first for Patrick and Lou, then
add one or two features per measured release. Explicit acknowledged saves,
verbatim retrieval, corrections, task recovery, provenance and existing access
protections remain the core. The broader 35-commitment v2 plan and its candidate
are preserved separately; they are not silently deleted or called complete.
Ten pilot users are not required for this first core release.

The two current improvements are truthful continuity/status and this plain
change/adoption record. No new health database, monitoring service, lifecycle
controller, automatic chat ingestion or remote access is added.

## Exact source and observed installations

| Subject | Recorded identity | Limit |
| --- | --- | --- |
| Core branch | `codex/core-reliability-20261001` | Isolated candidate, not merged or installed |
| Core base | `29c62abbd46f2d5e1b7ca0aec813bd2b4818cf43` | Initial tree `dbbc71b5425b1089f46e79561330e3f195b5bb8e` |
| Published 1.12.3 tag | `f65ff36c56c2a1f324778b308101cd9fdb6e4f19` | See [release evidence](release/v1.12.3.md) |
| Parked broad candidate | Tree `a70564526fab58e2b91f0fee9d0e88846403a29a` | Preserved separately; no wholesale import |
| Patrick's installed metadata | 1.12.1 observed 2026-10-01 | Actual host-loaded process/version remains unverified |
| Lou's supplied audit | uv metadata 1.12.2 | Historical observation, not a current remote handshake |
| Maintenance PR122 | Recorded head `9c086f3c7793f11de23814b4c1c222b2269d3f39` | Reverified open draft; its three dependency fixes and handoff guide are incorporated in the 1.12.4 release branch |

The current user reports Cairntir works. No deployed-runtime failure is inferred
from these different versions. PR111's historical false-success and store/launcher
repairs were published in 1.12.3; they are not relabeled as newly reproduced bugs.
Dependency lock versions likewise do not prove installed dependency versions.
No installation, host restart, database migration, credential or access change
is part of this candidate's implementation.

## Findings, changes and proof

| Finding | Candidate change | Evidence and remaining limits |
| --- | --- | --- |
| Doctor described configuration as MCP ready without calling a host | Show configured/missing/unknown separately from live=unverified | Independent frozen synthetic CLI controls; actual native-host identity remains unverified |
| Diagnostic root callback could register hosts or check for updates | Doctor/status/version bypass those side effects after existing access validation | Frozen callback controls; scoped administration remains denied |
| Missing doctor/status store could create its directory | Resolve paths without creation; retain normal doctor failure and gate SKIP exit codes | Frozen absent-home/cache controls; SKIP is not a health pass |
| Status opened a writable store and lacked a close owner | Count metadata through a temporary read-only snapshot, without constructing an embedding provider | Real-store controls replace the insufficient mocked seam; index readiness remains unverified and snapshot resource cost is not yet measured |
| Setup called direct get recall and claimed global readiness | Identify local write/read proof, semantic and live-host limits, and exact receipt/fresh-chat recovery steps | Frozen normal, missing-host and warmup-warning controls; no real setup was performed |
| Current docs disagreed on release/support | Distinguish published 1.12.3 from the 1.12.4 maintenance candidate | Historical release evidence remains unchanged; strict full docs/release checks still required |

The independently frozen diagnostic controls live under
`plans/acceptance/core-diagnostics-20261001/`, with a normal pytest collection
wrapper. Original baseline: 13 failures and 7 passes out of 20. After the first
repair all 20 passed. Six of these cases check the wording oracle; they are
not six additional native-client or end-to-end successes. One original unknown
configuration predicate was too broad; its separate strengthening amendment
preserves the original evidence. Its four actual-doctor cases failed on the
pinned baseline; its two oracle controls passed. All 26 original-plus-amended
cases then passed through the repository's normal collection wrapper. Five
existing doctor gate regressions and seven selected CLI regressions also passed
with synthetic stores. These short checks do not replace full qualification.
Independent follow-up found the earlier status seam insufficient: an existing
store with mismatched or unavailable embeddings failed before returning counts.
That candidate is superseded, with its evidence preserved. Seven independently
frozen real-store cases now pass, including unchanged source bytes, error cleanup,
retained semantic mismatch refusal and restricted-session denial. A mismatched
store also passed through the actual snapshot subprocess. Earlier fixture import
and connection-close errors were corrected by explicit frozen amendments; they
are not product failures. Normal collection replaces only the obsolete mocked
status assertion and retains the other 25 diagnostic cases.

Detailed commands, hashes and outcomes belong in the maintenance packet and
candidate verification report.

## Maintenance release scope supersedes the earlier pilot gate list

On 2026-10-02 Patrick explicitly narrowed this release to version 1.12.4:
existing stable behavior, applicable dependency repairs and reviewed diagnostic
fixes. Existing repository CI/release checks and focused regression controls are
required. Earlier cross-host expansion, paired-machine pilots and proposed
resource budgets remain future work; they do not gate this maintenance patch.
The frozen earlier basis is retained with a dated maintenance-scope amendment.

See [1.12.4 release evidence](release/v1.12.4.md) for current readiness. No new
native-client or performance qualification is claimed. Current installed hosts
and private stores are unchanged. The synthetic Claude registration/grant/ACL
detour was cancelled before any activation. Heavy local work remains deferred;
the existing hosted CI performs clean qualification without private data.
