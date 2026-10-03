# Combined correction and governance acceptance

The finite combined contract passes: six new cross-feature cases; 48 retained cases
plus 21 subtests, with one inherited Windows symlink privilege skip. The deliberate
in-process guard bypass fails the unchanged governed correction-refusal assertion.
No runtime repair was needed. Five source bindings and all 356 prior test/acceptance
paths match. Parent combined hosted CI qualification remains next.

See [the exact result](FINAL-RESULT.json), [frozen contract](CONTRACT.md),
[fixture freeze](FREEZE.json), [input advance](INPUT-ADVANCE-RECEIPT.json),
[new-case log](combined-six-v3.txt), [retained-control log](retained-controls.txt),
and [expected wrong-control failure](wrong-control.txt).

The [v2 amendment](FIXTURE-AMENDMENT-v2.md) canonicalizes full SQLite row values;
the [v3 amendment](FIXTURE-AMENDMENT-v3.md) distinguishes documented monotonic read
telemetry from immutable historical data. Original fixture bytes, manifests and
failing receipts remain under history/v1 and history/v2. No inherited assertion
or frozen archive changed. The existing old-client whole-listing incompatibility
and eight inherited damaged-envelope failures remain explicit contract qualifiers.

SEAL.json binds this public packet. All stores, embeddings and evaluators were
tiny synthetic local fixtures; no model inference, network, API spending, installs,
full suite or coverage run occurred.
