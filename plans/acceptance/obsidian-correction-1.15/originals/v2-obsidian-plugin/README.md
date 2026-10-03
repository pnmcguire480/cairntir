# Public Obsidian plugin acceptance

From the repository root with Node.js:

```sh
node plans/acceptance/v2-obsidian-plugin/test-obsidian-plugin-v3.cjs addons/cairntir_obsidian/main.js
```

The revised public contract passed 46 cases and 401 assertions after one
candidate repair. `verification-final.json` binds the final LF-normalized source,
manifest, README, and acceptance hashes. The harness uses disposable synthetic
vaults and mock Obsidian/child-process APIs. It does not verify a graphical
Obsidian session or backend persistence.

`verification-real-process.json` separately records an actual Python CLI pilot
with synthetic SQLite/vault state and mock Obsidian UI. Five normal exit-1 calls
exercised receipt and projection failures after commit, mixed rejected requests,
and idempotent retries. Independent read-only inspection confirmed exact
Unicode/CRLF content, preserved history, unchanged proposals and no duplicates.
The initial fault-fixture failure ran no backend calls and remains inconclusive.
`verification-clean-process.json` adds an actual exit-zero refresh after the
known malformed synthetic request was preserved in quarantine. Both correction
receipts replayed; the three database rows, proposal bytes and prior results
remained unchanged.

Evidence history is preserved:

- `freeze.json` records initial contract/harness authorship before implementation.
- `freeze-v2.json` adds missing documented framework APIs to the fixture before
  implementation, leaving the contract and assertions unchanged.
- `verification-v2.json` retains the first 23-case PASS and its narrower model:
  structured reports used exit zero and an incomplete receipt fixture.
- `freeze-v3.json` adds the actual normal-exit-1 protocol and complete receipt
  contract before repair. `verification-v3-round0.json` retains the reproduced
  missed-acknowledgment failure. The revised suite verifies truthful partial
  commit feedback and rejects invalid receipt or process evidence.
- `verification-v3-round1.json` preserves the first repaired-byte PASS;
  `verification-final.json` records the complete rerun after source line-ending
  normalization, with unchanged frozen acceptance.

The first direct Node launch was inconclusive because the sandbox denied a
module-loader ancestor lookup. Testing used a byte-identical hash-verified copy
inside the authorized workspace; that environmental failure was not counted as
a detected product defect.

Preserve frozen artifact bytes. A test change requires a separately reviewed
revision and cannot overwrite the earlier result. The original v1/v2 harnesses
are historical evidence; use v3 for current verification.
