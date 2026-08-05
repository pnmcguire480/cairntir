# Cairntir — Completion backlog (everything up to 2026-08-05)

**Date:** 2026-08-05
**Purpose:** One ordered list of what remains to close out the
`2026-08-04-honest-and-whole.md` plan plus the follow-ups surfaced by the
2026-08-05 audit. Drives the next several sessions.

**Context:** the 2026-08-05 audit found `main` fully green — the build was never
broken, the work was *stuck*. PRs #36 and #37 were merged that day and the five
stale dependabot PRs were closed. What remains is below, ordered by risk, not by
excitement.

---

## Ordered backlog

### 1. P1 item 4 — retire the `untrusted` migration stamp (RE-ATTEST)

**Status:** in progress (Patrick approved re-attesting, 2026-08-05).
**Risk:** LIVE STORE — 123 drawers. Follows backup → snapshot-rehearse → verify
→ live, per drawers #182/#210.

123 drawers carry `trust='untrusted'` only because the v6 migration
(2026-07-29) stamped `legacy_provenance()` on pre-provenance rows — it is a
migration artifact, not a judgement, and it renders a security banner over 45%
of the bank that trains every agent to ignore it.

Approach:
- Add `TrustLevel.LEGACY_MIGRATED = "legacy_migrated"` (the honest value:
  "migrated from legacy, not individually attested" — do **not** overclaim
  `user_asserted`).
- A `DrawerStore` re-attest + `scripts/reattest_legacy_trust.py` targeting only
  rows whose provenance is the v6 migration (`host='legacy'`,
  `capture_path='pre-v6-migration'`, `trust='untrusted'`).
- Keep all three copies consistent: `drawers.trust`, the `provenance` JSON, and
  the `vec_drawers.trust` prefilter column. Do **not** do a full reindex (that
  is the embedder bake-off, item 4).
- Gate: drawer count unchanged, every content SHA-256 byte-identical, only the
  123 legacy rows move, banner no longer fires for them.

### 2. P2 item 1 — write-time guard in `DrawerStore.add()`

**Status:** not landed (the 2026-08-04 agent was mid-flight when the session cut
out). No live-data risk; pure code + tests.

Reject content containing tool-call markup and validate `metadata.anchors` via
the existing `parse_anchors` at write time. `check_store_health.py` catches this
after the fact; nothing prevents it. The bug fired 2026-04-26, 2026-05-08, and
five times on 2026-08-02. Add
`test   tests/unit/test_store.py test_add_rejects_tool_call_markup` to the
commitments block when it lands (it is already staged).

### 3. P3 — CodeGlass runs alongside Cairntir (companion-first)

**Status:** scoped, not started. Patrick answered the standalone question
2026-08-05 — see the P3 section of the honest-and-whole plan. **Companion-first
(functional with Cairntir is the priority), standalone-packaging second.**

Increments, each its own PR:
1. **The seam.** CodeGlass reads/writes the same store through the public
   `Store` protocol only — no imports of Cairntir internals. Done when removing
   CodeGlass leaves Cairntir's tools and three skills untouched.
2. **Emergent pattern discovery.** The vault link graph produces at least one
   pattern Cairntir did not already know. This is the part that was never built;
   neither `obsidian.py` nor `vault_sync.py` touches the link structure today.
3. **Standalone packaging.** Only after 1–2: the "someone just wants codeglass
   only" shape.

### 4. Embedder bake-off — ⚠️ NEEDS PATRICK PRESENT

Highest-value open item per the audit, but it requires **reindexing the live
store**, and the project's own rule is rehearse-on-snapshot with the maintainer
awake. Not an autonomous task. `cairntir cost` now measures the problem (29% of
`cairntir`-wing drawers exceed the ~2,048-char window); the bake-off chooses the
chunking/model fix.

### 5. `check_release_tags.py` — verify PyPI presence, not just the tag

Small code + test. Today the gate checks that every changelogged version is
*tagged*; it does not check that the tag actually *published*. That is exactly
how `v1.1.1` shipped to GitHub and never reached PyPI, unnoticed. Extend the
check to verify PyPI presence (with an allowlist for the known-unreleased
1.0.1/1.1.3) so the class of miss is caught.

### 6. `cairntir --version`

Tiny CLI DX: the entry point currently rejects `--version`. Add it, reading the
package version.

---

## Ordering and why

- **1 before 4:** re-attesting trust is metadata-only and cheap; the embedder
  bake-off is a full reindex and is deliberately gated on Patrick.
- **2 is independent** of 1 and can land in parallel.
- **3 is the large one** and is sequenced companion-first so the standalone
  shape falls out of a clean seam rather than a fork.
- **5 and 6** are small hygiene wins that can land any time.

## Needs Patrick's hands or explicit say-so

- Item 4 (embedder bake-off) — live reindex, must be awake.
- Item 3 standalone packaging and the `codeglass-site`/`codeglass-dist` parent
  directory question (drawer #282).
- Final live-apply of item 1 runs only after a clean snapshot rehearsal and a
  fresh backup.
