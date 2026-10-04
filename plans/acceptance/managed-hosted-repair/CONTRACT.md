# Managed hosted repair acceptance v1

Finite test/evidence packaging repair for PR131. No runtime algorithm, security
query, dismissal, CodeQL exclusion, coverage threshold or original assertion is
changed. Original failed head, packets, seals, input bytes and manifests remain
preserved. New active controls correct setup/control-flow/cleanup diagnostics only.

Transport exactly eight enumerated immutable Python evidence resources in a pinned
ZIP. `scripts/restore_managed_evidence.py` exposes
`restore(source_root: Path, destination_root: Path) -> Path`. Destination must be
new. Restore precisely the four affected capsule trees into it, with all original
logical paths and bytes, before the unchanged verifier/loader/assertion bodies run.
Never write in the source checkout or overwrite existing/tampered destinations.
Verify transport and every resource hash/size, unique exact member set, confined
canonical paths and regular file metadata before producing any destination.

Keep `ARCHIVE_RELATIVE = 'plans/acceptance/managed-evidence-archive/resources.zip'`,
`ARCHIVE_SHA256`, `FILES` and `SIZES` explicit. Reject malformed/tampered transport,
missing/extra/duplicate/traversal/symlink archive members and conflicting source
resource bytes. Negative member controls vary only the trusted transport digest
to test structural checks; all eight immutable resource hashes remain fixed.

Existing managed runtime, Last Session, installed qualification and managed port
routers redirect only capsule roots to disposable reconstructed snapshots. Their
original integrity/assertion/loader bodies remain. Generic preservation and all
coverage settings stay byte-identical. Installed verifier preserves every prior
assertion and copies from the restored installed capsule. Corrected active controls
are ordinary Python analyzed by CodeQL and executed by an additive normal adapter.

Durable controls retain all 33 original assertion ASTs, same caller transactions,
full snapshots, forced rollback and exact retry. Visibility retains its 14 semantic
assertions, calls close exactly once before checking its result, and imports the
corrected durable fixture. Projection retains the same set-subset oracle using
the more informative unittest method. No assertion or failing receipt is dropped.

Require byte-identical roundtrip/source immutability, all prior manifests and seals
in restored trees, and fresh bounded same-behavior controls. Hosted CodeQL remains
the final analyzer outcome; local AST checks do not claim a CodeQL pass. No heavy
suite, install, production model, API inference, live store or publication occurs.
