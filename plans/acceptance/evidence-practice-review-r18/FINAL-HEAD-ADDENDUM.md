# R18 final-head scope and evidence addendum

The original [README](README.md) is a preserved qualification record for the
earlier candidate. Its procedures-only ownership statement and
`f3797a36fd610d26a895e0ed049cced0ecca2bbdcf0d80715da2fc5ea62d4342`
digest do not describe the final PR130 head. Keep that record and its frozen
archives unchanged.

The final pre-addendum head is
`1c628966321d3c94abd7dd5fd1704ccd226f51e8`. Relative to its authorized
PR128 base `9e65c37c9a734f88d54935933047bda598e03146`, the runtime diff
changes both `src/cairntir/procedures.py` and `src/cairntir/access.py`. The
later repair added 22 lines to `access.py` for complete-wing read authority.
The exact source SHA256 digests at that head are:

| Source | SHA256 |
| --- | --- |
| `src/cairntir/procedures.py` | `e20d3dfcbffa56fae4eaeccf922c982ef50ff37011c38b37f74c1b8938855fd7` |
| `src/cairntir/access.py` | `8202fe58fb4a449d3bb751e8698e029b4ff1fb032ed0501cb7656fd91a49538a` |

The earlier archive results remain evidence for their bound source bytes, not
proof of this later head. The repair and red-team round-two archives and tests
added in `1c62896` must be reviewed against this full two-file runtime diff.
The additive note itself does not qualify the final installed artifact or
authorize integration, merge, release or live adoption. Preserve every frozen
assertion and original result while recording any new exact-head receipts.

Fresh CI on the documentation head found the locked `fsspec==2026.3.0`
advisory. A subsequent security-only lock update pins 2026.6.0 with the same
registry hashes already validated on PR132. This expands the original lane's
dependency exclusion only for that transitive advisory repair; it changes no
runtime source, test or frozen acceptance bytes. The exact new head still
requires its own hosted qualification and parent review.
