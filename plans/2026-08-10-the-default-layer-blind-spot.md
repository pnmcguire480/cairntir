# 2026-08-10 — The default write layer was invisible to the documented entry point

Patrick opened the session with: *"i think cairntir is beyond broke. it snot
working for others. it doesnt seem to be working too well here either."*

Both halves were true. This plan covers the half that is fixed. The other half
— the embedder truncating at 128 tokens — is diagnosed in drawer #408 and
**deliberately not touched here**, because it needs a live reindex and this
repo's own rule (drawers #182, #210) is rehearse-on-snapshot with explicit
approval.

---

## The defect

`cairntir_remember` declares `"default": "on_demand"` in its MCP schema.
`handoff` gathered only `IDENTITY` and `ESSENTIAL`. So the default write path
produced memory the documented read path could not see.

Reproduced in a clean room — fresh venv, `pip install cairntir==1.4.1` from
PyPI, isolated `CAIRNTIR_HOME`, empty store:

```
DAY 1  Stored drawer #1 in myapp/decisions (layer=on_demand).   #2, #3 likewise.
DAY 2  session_start -> Identity (0) / Essential (0) / On-demand (0) / Deep (0)
       handoff      -> "Wing 'myapp' holds 3 drawer(s), but none are identity,
                        essential, an open question, or anchored to the files
                        given. Nothing here is broken."
```

A new user follows the documented policy, takes the defaults, and gets silence.
That is the exact cross-chat amnesia Cairntir exists to kill, reproduced by its
own defaults. It also explains why **zero GitHub issues have ever been filed**:
nothing crashes, so there is nothing to report. People just leave.

## Why it survived from v1.3.0 to 2026-08-10

This is the part worth remembering. The behaviour was not merely untested — it
was **asserted as correct** by `test_a_populated_wing_with_nothing_to_brief_is_not_reported_as_broken`,
whose docstring reasoned:

> `on_demand` drawers are, by the layer taxonomy, loaded when a query makes
> them relevant — and handoff runs no query. So a wing can hold plenty and
> still brief to nothing.

That argument is locally coherent and reachable by any future session reading
the taxonomy. A test encoding it turns a bug into a specification. The fix
therefore has to include something that makes the argument fail on contact with
both sides at once, or it will be re-derived.

## What changed

1. **`RECENT_ACTIVITY` section, zero reserve.** Skipped entirely in pass 1; it
   can only ever be filled from budget no higher-priority section wanted. It
   cannot outbid identity or essential material. Leftover budget spent on a
   real decision beats leftover budget returned unspent.
2. **`DEEP` stays excluded.** "Skipped unless explicitly requested" is a real
   decision. `on_demand`'s exclusion was an accident of running no query.
3. **The empty-brief message names what it skipped.** The old string said
   "Nothing here is broken" at the precise moment the caller got nothing —
   reassurance in place of a reason. It now reports the deep-layer count and
   says plainly that the brief is not evidence the wing is empty.
4. **A seam guard**, registered in `scripts/check_seams.py`. The test reads the
   declared default off the live tool schema rather than hardcoding it, so
   changing either side alone fails the build.

**Explicitly not done:** flipping the default to `essential`. That would starve
the budget every drawer competes for, which is the other half of what is wrong
here — 253 of 407 drawers in this store are already `essential`.

## Verification

- 668 tests, 83.8% coverage; ruff, `ruff format`, `mypy --strict` (51 files) clean.
- All six gate scripts green, including the new seam.
- **The seam guard was verified to fail when the fix is removed**, with the
  message a future session needs. A guard nobody has watched fail is the
  defect this repo keeps re-finding.
- Clean-room reproduction re-run against the fix: Day 2 returns all three
  decisions; the deep-only wing reads honestly.

```cairntir-commitments
symbol src/cairntir/handoff.py RECENT_ACTIVITY
symbol src/cairntir/handoff.py _gather
param  src/cairntir/handoff.py _fit:deep_total
test   tests/unit/test_handoff.py test_on_demand_drawers_are_briefed_when_the_budget_has_room
test   tests/unit/test_handoff.py test_on_demand_never_displaces_identity_or_essential
test   tests/unit/test_handoff.py test_the_default_write_layer_is_a_layer_handoff_loads
test   tests/unit/test_handoff.py test_a_wing_of_only_deep_drawers_names_what_it_skipped
file   scripts/check_seams.py

# Bug 2 — the embedder window, landed the same session
symbol src/cairntir/memory/embeddings.py PRODUCTION_MODEL
symbol src/cairntir/memory/embeddings.py PRODUCTION_TOKEN_WINDOW
symbol src/cairntir/memory/embeddings.py PRODUCTION_DIMENSION
symbol src/cairntir/cost.py EMBEDDER_TOKEN_LIMIT
file   tests/eval/test_embedder_window.py
test   tests/eval/test_embedder_window.py test_declared_embedder_window_matches_the_model
test   tests/eval/test_embedder_window.py test_the_tail_of_a_long_document_changes_its_vector
test   tests/eval/test_longmemeval_subset.py test_longmemeval_subset_recall_at_5_production_embedder
```

---

# Bug 2 — the embedder window (same session, approved and landed)

Patrick approved the reindex explicitly: *"Bug 2 is now the whole ballgame.
Complete the fix!"*

## What was wrong

`all-MiniLM-L6-v2` truncates at **128 tokens (~500 chars)**, read off the live
model as `truncation: {'max_length': 128}`. On 407 drawers that hid **73.4% of
all stored text** from semantic recall; only 66 drawers were fully searchable.
`cosine(full_content, first_1500_chars)` was exactly `1.000000` for the five
longest drawers — their tails contributed literally nothing.

Three numbers described this window and no two agreed: `cost.py` hardcoded
512, fastembed's description advertised 256, the tokenizer was configured to
128. **The number the tool reported was the most flattering one.**

## Why a model swap, not chunking

Chunking means multiple vectors per drawer, which breaks the
`vector_count == drawer_count` invariant that `vec_drawers` and every health
check are built on — a schema migration on a live store, for a problem a
bigger window solves outright. `jina-embeddings-v2-small-en` has an
**8,192-token** window; the longest drawer in the store is **2,377 tokens**.
The whole corpus fits in one vector. One row per drawer, unchanged.

Verified empirically rather than from the model card, because the model card
is what lied last time: `tokenizer.truncation['max_length'] == 8192`, and
appending a sentence to a long document now moves its vector (cosine 0.9999
instead of 1.0000000000).

## Rehearsal, then live

Rehearsed on a `backup_database` snapshot before touching the live store, per
drawers #182 and #210:

- 414 drawers before and after, ids identical
- **0 content SHA-256 mismatches** — every drawer byte-identical
- index state `verified`, dimension 512, new generation stamped
- **Acceptance test: a query using text found only at character 8,624 of an
  8,924-char drawer returned that drawer at rank 1.** Under MiniLM that text
  was never embedded at all.

## Still open after this

- **`session_start` has the same on_demand blind spot** as `handoff` did and is
  unchanged. Its description already points at `handoff`; fixing the composer
  first was the smaller, safer move.
- **The `untrusted` migration stamp** and the write-time guard in
  `DrawerStore.add()` remain from the 2026-08-04 ledger.
