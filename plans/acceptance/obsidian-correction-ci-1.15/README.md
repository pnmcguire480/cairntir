# Independently frozen CI fault-seam adaptation

**PASS: 28 focused cases in 1.26 seconds.** No runtime fix was needed. This packet
is separate from the previous sealed correction acceptance and preserves its
original source, test assertions, error witnesses and coverage policy.

The maintained projection test previously patched `Path.read_text` while the
required CRLF-preserving implementation reads through `Path.open(newline="")`.
The [original read case](original-read-fault-red.txt) reproduced the hosted
`DID NOT RAISE ProjectionError` failure in 0.34 seconds. The adaptation changes
only the saved callable, fallback and monkeypatch target to `Path.open`.
All nine original assertion and `pytest.raises` expressions retain an identical
AST; all seven original cases now pass, including deliberate read, replace and
cleanup failures, exact notes/database preservation, retry and damaged-note refusal.

Twenty-one new finite cases also pass: three closed-owner operations return typed
MemoryStoreError, six revoked/write-only scoped operations deny access without
database or filesystem changes, and twelve exact-schema, canonical UUID, UTF-8,
identifier, integer and digest boundaries reject without writes.

[Version 2 freeze](FREEZE.json) binds the test files and preserved evidence.
Version 1 passed the same runtime controls; its subsequent import-order-only
amendment uses actual repository Ruff classification. The non-import AST is
unchanged. Both actual maintained files pass Ruff and the line-100 formatter.

The unchanged preservation checker does not bind this maintained fault test in
its 24 historical manifests/115 artifacts or four council manifests; see the
[independent inspection](PRESERVATION-INSPECTION.json).

[Final execution](adapted-focused-v2.txt) and [result receipt](FINAL-RESULT.json)
record bounded synthetic checks. No local coverage percentage or full suite was
run. The 92% floor and coverage configuration remain unchanged; hosted CI must
measure the repaired head. Native graphical and private-custody claim limits stay
unchanged.
