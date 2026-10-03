# Bounded recall: finite independent acceptance

Frozen before candidate implementation/runtime inspection, 2026-10-03.
Published base: b60c2fbc537b6fcb284aa14f8023b3170f720822.

The preserved E23 contract, ancestry amendment, original 12 tests, four
supplemental tests, and original real stdio fixture are copied byte-for-byte.
Five fresh tests add pre-retrieval strict budget rejection, real Unicode/control
characters and a two-link correction chain containing hostile instructions,
eight boundary budgets, room-scoped visibility, and six negative controls.

Run exactly the 21 test methods across the three test modules with unittest;
select the original classes explicitly so the imported fixture class does not
accidentally duplicate tests. Actual build_server stdio is exercised twice,
including 600 routing hits and a pending oversized update banner. No semantic
model, network, install, production database, or production launcher is used.
The live production launcher and host adoption are explicitly outside scope.

Required outcomes: strict optional integer budget 1024..262144; complete
CallToolResult.model_dump_json() ceiling; whole exact content, UTF-8 SHA256,
full provenance and supersedes_id; eligible prefix semantics; truthful bounded
omission IDs and count; no query/banner overflow; unchanged legacy route;
unchanged visibility and evidence authority. Additional application changes,
test weakening, expectation rebaselining and fixture-specific runtime logic
invalidate acceptance. Review the exact final candidate diff for these limits.

Finite wrong controls must all be rejected: raw-content-only sizing,
post-budget banner, false complete omission list, changed content with a freshly
matching hash, missing provenance, and falsified correction ancestry.

One implementation round and at most two repair-and-verify rounds. Reserve at
least 25 percent of effort for verification/review. Execute serially with
existing Python, no package installation, PYTHONDONTWRITEBYTECODE=1 and isolated
HOME/config/cache. Preserve raw results and final candidate source hashes.
Independent verdict is PASS, FAIL, or INCONCLUSIVE; terminal status is COMPLETE,
BLOCKED, or EXHAUSTED. Test hashes must stay frozen after first execution.
