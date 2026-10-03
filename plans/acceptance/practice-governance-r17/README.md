# Independent finite R17 evidence

`controls.zip` preserves tester-authored preimplementation assertions, contract,
freeze and run receipts as exact bytes. Its SHA256 is
`8871210cfd4db5b3c65fcc08e1cfea6b0680ad8a19a662ff852e3ad8a031bac9`.
Normal pytest replays all 21 fresh frozen controls through the dedicated
`tests/unit/test_practice_governance_independent.py` adapter, verifying original
freeze and assertion hashes. The archive also retains the separately pinned
orchestration adapter and unchanged historical 28-control result.

- Exact-base structural baseline: 2 legacy controls pass; 19 governance controls
  produce 50 absent-API error events, not an asserted runtime defect reproduction.
- Candidate: 21 fresh controls pass without failures/errors/skips.
- Deliberate metadata-stripping copy: 42 direct assertion failures and 4 separately
  disclosed downstream errors, with original assertions unchanged.
- Adapted historical replay: 28 pass without failures/errors/skips. Original
  runner has missing historical plan and predecessor-pin mismatches; this adapted
  evidence does not claim an execution of the old runner and old predecessors.

`redteam.zip` preserves the separate review, frozen adversarial probes and base/
candidate receipts. Its SHA256 is
`9a62e2d382aa0c251be037e5ebcdd59803b607904712b5514ef4dce38fa2ad7c`.
The review passes the approved finite metadata increment with 22 passing probes.
Eight raw whole-registry-envelope assertions fail identically on candidate and
exact base: malformed JSON/null/list/string payloads leak inherited store parsing
errors before procedure reconstruction. These failures remain visible and are
outside the complete governance-object/fingerprint contract; the review does not
claim general damaged-registry handling or request a broader feature repair.

Qualified runtime raw-file SHA256:
`6d0ed499a601857aa41bd3d5fbba93b57cd6f391fa6409853423bc3e46974023`.
Git normalizes source text; raw newline hashes can differ by platform. Archive
entry bytes are preserved across checkouts. All stores and runners are tiny,
synthetic, isolated and inert; archives contain no databases or runtime homes.
Independent agent custody is procedural, not protected evaluator authentication.

The [finite plan](../../practice-governance-r17.md) retains hosted exact-head CI,
parent integration and separately authorized merge/release/adoption gates.
