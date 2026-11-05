# Managed runtime tests

Carried from draft PR 131. They protect managed-session intake, acknowledgement, dispatch,
crash recovery, close completeness, the JSONL command envelope and projection integrity,
using disposable stores and real child processes with a hash embedding provider.

`MANIFEST.json` and `SOURCES.json` in `plans/acceptance/alpha-portable-tests-20261105`
record each test's origin and every change made while carrying it across.
