# Normal-CI integration, fixture-only v2

The initial exact-case plugin intentionally rejected every other test during its
standalone run. This version permits normal unfiltered collection, leaves every
unmatched test untouched, and makes diagnostic report output optional. There is
no test-selection change, marker removal, runtime exemption, assertion rewrite,
preservation-gate change, or dependency addition. All eight adapted cases retain
the original fixture-only behavior described in EXACT-ADAPTER-CONTRACT.md.

The fixture matches both original file suffix and exact case name/parameters.
Collection still verifies complete SHA256 custody of the two original test files
whenever those files participate. Other store tests and other verification files
run normally without registry/asset injection. Optional reports must stay under
the frozen packet; normal CI needs no report argument and emits the number of
adapted cases in its terminal summary. The standalone runner remains limited to
the original 17 cases solely for lightweight local verification; it is not the
normal CI path.

For ordinary CI, copy the frozen plugin, runner and explanatory contracts into
`plans/acceptance/embedding-artifacts-1.14` and the frozen loader into
`tests/e22_fixture_loader.py`. Preserve root tests/conftest.py byte-for-byte as a
prefix, then append only:

```python
pytest_plugins = ("e22_fixture_loader",)
```

The loader hash-checks all frozen integration files before registering the plugin.
No custom pytest invocation/filter is required. If a preservation gate treats the
root fixture extension as protected, report that blocker; do not relax the gate.
Original test outcome/assertion files must remain byte-identical to their recorded
SHA256 values. The root conftest change is an explicit additive fixture hook, not
claimed as byte-identical; its original bytes are preserved as the prefix.

This integration version changes harness applicability/reporting, not E22 semantic
requirements. The primary 35-case freeze, original failures and independent review
reserve remain intact. All setup is synthetic and confined to pytest tmp fixtures.
Requested routing gpt-6.1-sol/high; actual serving variant/effort not exposed; cost
unavailable.
