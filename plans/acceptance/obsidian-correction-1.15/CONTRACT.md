# Frozen correction-loop acceptance, 2026-10-03

Baseline: reviewed PR125 head `37ab0b1bb7e641adec8d2305b1546d1a35b1cd7e`.
Outcome: an explicit Obsidian proposal appends an exact correction, preserves
the original, receives a durable matching acknowledgement, and can retry after
restart or projection/receipt failure without duplicate records.

The finite acceptance set is the byte-identical original Python core (13),
file-flow v2 (10), lifetime (3), newline (1), source-state v2 (2), and Node
plugin v3 (46 cases/401 assertions) suites, plus the bounded integration items
below. Original v1/v2 harnesses and earlier failed verification receipts remain
copied unchanged and excluded from the active count only because the recorded
independent revisions supersede their fixtures. No expectation is weakened.

1. Exact UTF-8/Unicode/CRLF and source SQL row/provenance/portable UUID survive.
2. Request UUID permanently binds payload; replay survives restart and validity
   expiry; stale edits, wrong store/local ID/hash/wing and malformed JSON reject.
3. Transaction failure rolls back append and workflow receipt; retry succeeds.
4. Source privacy, layer and validity inherit; correction trust is untrusted.
   Secret, expired/future and structured workflow sources reject generic edits.
5. Only explicit outbox JSON is consumed; proposals and personal annotations
   persist. Inventory is wing scoped, excludes secrets, preserves owned-marker
   literals safely and exposes current/history relationships.
6. Existing-vault and bound-wing boundaries hold. Symlink requests reject where
   the host permits symlink creation; inability is an explicit platform skip.
7. Actual fresh CLI subprocesses use a synthetic provider, exact request/receipt
   JSON, nonzero rejection/partial failure, and restart retries without duplicates.
   Receipt-path and projection conflicts preserve user bytes and committed data.
8. Restricted CLI session denies administrative sync before touching vault/store;
   owner inventories exclude other-wing/secret content; direct scoped facade use
   cannot gain unrestricted write authority.
9. Current pinned synthetic identity works; legacy nonempty semantic identity
   remains refused without guessed provenance/reindex; raw source stays readable.
   Existing obsidian-project and vault-sync contracts remain available.
10. Node v3 is mandatory through a normal pytest wrapper in hosted qualification.
    Additive real-process plugin routing exercises the actual CLI with a synthetic
    provider and simulated UI, if normal installed Node is available.

Dependencies: existing Python test/runtime dependencies and an existing Node
executable; no installation, model inference, network or private store use.
Non-goals: questions lifecycle, MCP additions, store migration, release, merge,
live installation, authentication changes, protected evaluator custody and
native graphical Obsidian/operator acceptance.

Budget: freeze before implementation; serial synthetic subprocesses <=60 seconds
each; preserve at least 25% for verification; at most two product repair rounds.
Any fixture amendment is separately hash-frozen with prior red evidence retained.
Terminal vocabulary: PASS/FAIL/INCONCLUSIVE; COMPLETE/BLOCKED/EXHAUSTED according
to the finalization recipe. Local synthetic success does not claim native UI use.
