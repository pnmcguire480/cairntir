# Handoff prompt — paste this into a new chat

Copy everything between the lines.

---

We're correcting Cairntir. This is the "honest and whole" update — the most important one to date.

**Start here, in this order:**

1. `cairntir_session_start` with wing `cairntir`, then read drawers **#275** (what was just fixed and what's left), **#237** (why memory was lost), **#212** (the generalized defect, in my own words from a prior session).
2. Read the plan: `C:\Dev\Cairntir\plans\2026-08-04-honest-and-whole.md`. It has a measured baseline — every number in it was verified against the live store on 2026-08-04, not asserted.
3. Confirm the baseline still holds before you build anything. If a number has moved, say so and update the plan first.

**The goal, and it is the acceptance test for every change:**

I want a memory store where *even a free model with terrible output* can follow the pieces and reassemble the whole. Not "is the store correct" — **can a weak model get the right context without knowing the right question to ask.** If a change only helps a smart agent that already asks good questions, it is not the change I want.

**Do P0 first** (structural recall / anchor backfill). It is the highest-leverage item by a wide margin: `recall_for_change` fires from the files being edited and needs no cleverness from the agent, and it currently covers 10.9% of the store, with 19 of 22 wings at zero.

**Hard rules — this is my memory bank, it is irreplaceable:**

- **Never write an unverified anchor.** A wrong path silently poisons structural recall and is worse than no anchor. Verify every candidate path against the real repo on disk. Report what you cannot verify; do not guess.
- **Backup → sandbox → verify → live.** Always. Set `CAIRNTIR_HOME` to a scratch dir holding a copy, apply there, verify there, and only then touch the live store. This worked twice on 2026-08-04; do not shortcut it.
- **Write through `DrawerStore.add()`, never direct SQL inserts.** Direct SQL skips embedding generation and produces unreachable rows — the exact stray-drawer failure we just spent a session correcting.
- **Verbatim content is sacred.** Metadata can be repaired; authored text does not move. The one exception already taken was stripping non-authored tool-call envelopes, and even that preserved the stripped bytes.
- **Run `python scripts/check_store_health.py` before and after any store mutation.** It must exit 0 at the end.
- **Ask before mutating existing rows.** Appending is safe; rewriting is not. I want to approve those individually.

**The defect you are working against**, named in drawer #212 and confirmed four times since: *builds excellent infrastructure but does not wire the enforcement layer.* Cairntir's anchors, Triangulate's P0, the vault sync, and the v1.2 context budget all failed this same way — designed correctly, never connected, nothing complained.

So: **when you finish a phase, add its assertions to the `cairntir-commitments` block in the plan** and confirm `scripts/check_landed_commitments.py` passes. Do not delete an assertion to make the build green. If you built it, prove it. If you did not, leave it red and tell me.

Finally: record what you learn with `cairntir_remember` in wing `cairntir` as you go, not at the end. If the session dies mid-way, the next one should be able to pick up from the drawers alone.

---
