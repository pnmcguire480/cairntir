# R18 independent qualification

This lane implements the existing R18 requirement: actual trigger,
false-positive, override and impact evidence; date- or evidence-triggered review;
simulated measurements never establish a field quarter, and missing metrics remain
unknown. The finite API contract was settled and independently frozen before
runtime implementation. [Usage and persistence limits](../../../docs/practice-review.md)
describe the result.

The authorized base is PR128 commit
`9e65c37c9a734f88d54935933047bda598e03146`, tree
`5ee79667e3923dc30237249b4b65194fdf983995`. Runtime ownership is solely
`src/cairntir/procedures.py`. Store/schema/access adapters, questions, CLI,
Obsidian/plugin, dependencies and shared version/changelog/navigation work are
outside this lane.

`controls.zip` preserves the independent acceptance contract, frozen 79 assertions,
exact base and candidate sources, original results, source identities, a meaningful
isolated wrong-metric control, and the ordinary pytest adapter. The adapter verifies
the manifest and exact assertion hashes before replaying all controls. A structural
missing-API baseline is recorded honestly; it is distinct from the direct metric
assertion failure in the wrong copy.

`redteam-controls.zip` preserves independently authored adversarial probes, original
and additive freezes, raw results, transparent fixture corrections and final
verdict. The reviewer did not read the acceptance assertions or modify runtime.
The original run included reviewer SQL/shape fixture failures; the original logs
remain alongside separately frozen corrected fixtures. Storage-level malformed
whole-ledger objects retain existing typed store errors; newly loaded malformed
R18 materials raise `ProcedureError`.

The reviewer reproduced two introduced defects: a later disjoint-period review
forgot previously acknowledged observations, and a locally constructed frozen
observation receipt retained the caller's mutable source-hash list. One product
repair round unions acknowledged snapshots across completed reviews of the same
revision and detaches that sequence. Original failures and final passing controls
remain reconstructable; no frozen assertion was weakened.

Final runtime SHA256 is
`f3797a36fd610d26a895e0ed049cced0ecca2bbdcf0d80715da2fc5ea62d4342`.
Final independent results and archive receipts bind to this source. Tests use
bounded inert synthetic stores, offline hash embeddings and disposable homes;
there is no model inference, live migration, grant change or field-quarter claim.

Normal hosted PR CI and CodeQL must qualify the eventual exact PR head. The
external handoff records that head/tree, workflow run IDs and conclusions, and
SHA-bound reconstruction artifacts after the qualification finishes. Parent
independent review and separately authorized integration remain required; draft
qualification does not authorize merge, release, installation or live adoption.
