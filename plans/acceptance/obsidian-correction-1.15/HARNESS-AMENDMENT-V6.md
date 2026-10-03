# Structured embedding refusal qualification

The version-5 repair-1 run is retained unchanged: 2 failed, 42 passed, one
Windows symlink privilege skip, and 21 subtests passed. The scoped hidden-child
projection failure is a product defect and requires repair 2. Owner and scoped
enclosing-transaction boundaries pass after repair 1.

The other failed case rejected the exact legacy FastEmbed index correctly,
preserved the source and identity, and returned structured JSON with the error
`semantic index is unverified: legacy FastEmbed index has no artifact provenance`.
The fixture's new substring requirement `embedding` was narrower than the public
contract and incorrectly rejected that typed error. Version 6 requires a
structured rejected request with an explicit embedding or semantic-index error.
It retains nonzero exit, unchanged source and unchanged identity assertions and
strengthens refusal qualification beyond version 2; an absent command cannot
produce the required JSON report. Version 5 is preserved under history/v5.

This amendment changes no original artifact or runtime and keeps 45 pytest cases.
