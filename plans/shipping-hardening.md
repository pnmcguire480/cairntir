# Shipping hardening

Scope: audit the 1.9.0 tree, fix reproduced persistence and trust-boundary
defects, and remove material unrelated to building, operating, or maintaining
Cairntir. No new product features or dependencies.

Keep the public contracts, user guides, release receipts, attribution,
`lineage/`, and executable regression commitments. Consolidate commitments
before removing closed plans. Git history retains removed narratives and
speculative product proposals.

## Acceptance

- Portable imports cannot promote external input to trusted user assertions or
  link source-local drawer ids to unrelated destination history.
- Malformed captures are quarantined without blocking valid pending captures.
- Portable exports preserve the previous file on failure.
- Obsidian projection cannot follow an output symlink outside its owned tree.
- Documentation describes implemented behavior and has no broken local links.
- Lint, format, strict types, non-slow tests with at least 80% coverage, evals,
  commitment/seam gates, strict docs build, and package smoke checks pass.

## Finalization Mode

Supply-chain amendment (2026-09-05): the public PyPI advisory check found
14 affected packages among 134 locked registry entries. Updating those existing
dependencies is in scope for shipping hardening; no new direct dependency is
authorized. Verify zero remaining active advisories for the resulting lock,
then rerun the complete suite and package smoke test. If compatible patched
versions or existing acceptance fail, record the blocker rather than weakening
tests. Existing core acceptance is frozen and remains unchanged.

Independent tester: `independent_acceptance`, owning only
`tests/unit/test_shipping_hardening.py`. Freeze that independently authored
artifact and its baseline failures before production changes; the coder does
not edit it. Existing tests remain additional gates, not substitute evidence.

Reserve the final verification phase for the complete inventory above and
the independent rerun. At most two repair-and-verification rounds after the
initial implementation. Repeated identical failures without new evidence
stop the loop. No benchmark tuning, live-store experiments, host installation
changes, release publication, or unrelated dependency updates.

Terminal disposition: `COMPLETE` only with evidence for every acceptance
item; otherwise `BLOCKED` (external prerequisite) or `EXHAUSTED` (repair budget).
Land changes through a green pull request and return the checkout to `main`.

## Verification record

Implementation acceptance passed, including independent frozen tests. See the
[audit record](../docs/release/hardening-2026-09-05.md) for exact results and
remaining boundaries. The protected pull request supplies cross-platform CI
and merge receipts; publication is a separate human gate.
