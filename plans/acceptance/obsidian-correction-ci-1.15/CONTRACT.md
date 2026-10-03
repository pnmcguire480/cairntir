# Independent correction CI adaptation contract

Hosted head `31a8fd6` retains the required CRLF-preserving projection read through
`Path.open(encoding="utf-8", newline="")`. An existing maintained fault fixture
still intercepts `Path.read_text`, so its read case no longer injects a fault.

Preserve the original test bytes and its hosted failure evidence. Adapt only the
saved callable, fallback and monkeypatch target to `Path.open`. Every original
assertion and `pytest.raises` call must retain an identical AST. A focused original
read-case run must reproduce failure before adaptation; all seven original cases
must pass after adaptation, proving typed ProjectionError, exact user-note and
database preservation, successful retry and malformed-note refusal.

Twenty-one finite additive cases qualify actual new error/security contracts:
three closed-owner operations (state, correction, sync) raise MemoryStoreError;
six scoped operations with a revoked or write-only grant raise AccessDenied before
any database or vault change; twelve exact-schema, canonical UUID, UTF-8 scalar,
identifier and numeric/digest boundary cases reject without writes.

Original and adapted fixtures, this contract, preservation inspection and new
controls are independently hash-frozen before runtime execution. New controls run
through normal tests/verification collection and reject changed frozen bytes.
Inspect unchanged preservation checker bindings before editing the maintained test.

This adaptation changes tests only. No previous sealed acceptance artifact,
runtime, coverage floor/configuration, dependency, private store, native graphical
claim or protected-custody claim changes. No full suite, local coverage measurement,
model inference, installation, network or release is part of this bounded check.
