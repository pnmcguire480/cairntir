# Next Map — Attribution-First Scoping After v1.2.0

**Status:** Track A verdict **ratified by Patrick 2026-08-01** — build
`recall_for_change` first, scoped per-room; staleness flagging **on hold**. Track
B attribution doc delivered; glossary drawer not started. Track C1 resolved.
**Recorded:** 2026-07-31
**Memory source:** Cairntir drawers #173 (code-review-graph assessment),
#174 (v1.2.0 release and the untagged-release gap), #66 (project identity),
#117 (North Star), #118 (Evolving Mind architecture)
**Sources under consideration:**
[tirth8205/code-review-graph](https://github.com/tirth8205/code-review-graph) (MIT),
[mattpocock/skills](https://github.com/mattpocock/skills) (MIT)

## Standing

v1.2.0 published 2026-08-01. For the first time since May, `pip install cairntir`
resolves to a version without the twelve-minute cold start. Downloads at the
moment of discovery were 33/month, 4/week, 0/day — measured against an artifact
that hung on first run, so they say more about the defect than about demand.

That changes the next question. It is no longer "why does nobody use this." It is
"what do we build, and how do we show up." This map answers the second half
first, because it is the half that involves other people.

## The attribution contract

Cairntir has already done this twice. MemPalace gave it the memory taxonomy;
BrainStormer gave it the reasoning vocabulary. Both are credited in
`docs/lineage/`, both were reimplemented rather than copied, and `mempalace.md`
ends by thanking its author by name. That was good practice arrived at by
instinct. Writing it down turns it into a standard that does not depend on
anyone remembering to be decent at 2am.

**The rules, binding on every future source:**

1. **Concepts, never code.** Already `CLAUDE.md` policy for BrainStormer and
   MemPalace; it now applies to every source. MIT would permit vendoring. We
   don't, because reimplementation is what makes it ours to maintain and theirs
   to keep.
2. **A lineage doc lands before a line of code.** Named author, linked repo,
   what we kept, and — load-bearing — **what we dropped and why**. The
   "what we dropped" section is the actual respect. It proves we read the thing
   and formed a judgment, rather than skimming it for parts.
3. **Credit by name and handle**, in the repo and in any public writing about
   the feature. Not a footnote added after someone complains.
4. **Never restate their benchmarks as ours.** code-review-graph's 82x and
   MemPalace's 96.6% are theirs, measured their way. Cairntir cites them as
   *their* claims or generates its own. Drawer #173 already records why both of
   code-review-graph's headline numbers are weaker than they look; that critique
   stays internal and evidence-based, and never becomes a marketing line.
5. **Never position as "better than."** Different layer, different tradeoff.
   Any comparison must state what Cairntir *doesn't* do.
6. **Disclose interest up front** in any community we engage.
7. **Say when their tool is the better fit.** `mempalace.md` already does this in
   writing. That sentence is the real test of good faith, and it stays in every
   lineage doc we write.

## Track A — Structural anchors (from code-review-graph)

**The borrowed idea:** memory should be reachable by *what you are changing*, not
only by what you thought to ask. code-review-graph gets there with a full
tree-sitter graph. Cairntir needs only the anchor.

### Gate results — run 2026-07-31, bars pre-registered (drawer #176)

**A1 — anchorability. Bar: ≥30% of cairntir-wing drawers. MARGINAL.**
Census of all 45 cairntir-wing drawers (and all 175 globally), resolved against
the repo as it stands. **33.3% permissive, 28.9% strict** — the result straddles
the bar. The permissive pass leaned on anchors like `sym:__init__` that resolve
but locate nothing. Not a clean pass.

*Post-hoc diagnostic — a hypothesis for a future pre-registered test, not a
rescue of this one:* anchorability splits by room. Code-facing rooms anchor
(architecture 1/1, predictions 2/2, lineage 3/5, audits 2/4, journey 4/10);
collaboration-facing rooms anchor at 0% and structurally should
(host-acceptance 0/6, identity, model-handoffs, north-star, project-identity,
project-portfolio, release, working-preferences). **Anchors belong per-room and
opt-in, not per-wing.**

**A2 — staleness signal quality. Bar: ≥50% of firings meaningful. The naive
spec FAILED; the corrected spec passes.**
Replayed real git history over the 23 symbols and 6 paths A1 found, comparing
each anchored symbol's exact AST source segment across every commit pair.

- **File-scoped** anchoring (hash the whole file): **40.3% precision** (29 of 72).
  **Fails.** Noise factor **2.48x** — about two and a half flags per real change.
  `replay_cmd` fired 17 times for 3 real changes. `EmbeddingProvider`,
  `ManualProposer`, `parse_capture` and all five `Ollama*` error classes fired
  only false.
- **Symbol-scoped** anchoring (hash the anchored symbol's source segment):
  **100%** by construction. A2's contribution is proving the file-scoped
  alternative is the noisy one.

**The defect this caught.** Drawer #173 and the first draft of this plan both
specified the anchor as `{path, symbol, content_hash}`. Read naturally as the
file's hash, that *is* the 40.3% design. **Corrected: the hash is of the anchored
symbol's source segment, never the file.** Caught before a line of feature code.

**Untested, not passed.** `git log --diff-filter=R -M` finds **zero** rename or
move events in Cairntir's entire history, and 0 of 6 path anchors are dead. The
corpus cannot answer "does symbol identity survive refactoring." That question is
**open**, and closing it needs a synthetic rename test or replay against a repo
that has renames.

### Verdict — conditional proceed, and split the tier

The two Tier 1 capabilities rest on different evidence and must not ship together.

1. **`cairntir_recall_for_change(files)` — BUILD FIRST, scoped per-room.** Rests
   on A1: marginal but usable, and path anchors are the robust half (17 of 46
   strict hits, 0 of 6 dead).
2. **Staleness flagging — HOLD.** The corrected symbol-scoped design is sound,
   but rename survival is untested. A staleness signal that floods false
   positives on the first refactor loses trust permanently and does not get a
   second chance.

**Ratified by Patrick, 2026-08-01, verbatim:** *"The two Tier 1 capabilities rest
on different evidence and shouldn't ship together... Staleness flagging — hold.
The corrected design is sound, but a staleness signal that floods false positives
on someone's first big refactor loses trust permanently. It doesn't get a second
chance. Not shipping it on an untested assumption."*

The hold is **not** a scheduling decision to be revisited when convenient. It
lifts only when rename survival is actually tested — a synthetic rename fixture,
or replay against a repo whose history contains renames. Cairntir's own history
contains zero (`git log --diff-filter=R -M`), so the corpus cannot answer it and
no amount of waiting will change that.

Anchor shape: optional `metadata.anchors` of
`{path, symbol, symbol_source_hash}` — no schema break, the store already
carries arbitrary JSON.

**Hard constraint carried from #173:** the index is a cache, never a drawer. No
belief mass, no provenance receipts, no supersession chain. Deletable and
rebuildable at any moment. The verbatim floor does not move.

**Not doing:** Tier 3 (communities, hubs, bridges, wiki, refactor-apply,
cross-repo search). Cairntir sits at 19 MCP tools by deliberate restraint.
Anyone who wants that surface should run code-review-graph — it is MIT, actively
maintained, and better at it than a reimplementation would be.

**Attribution deliverable — DELIVERED 2026-08-01:**
`docs/lineage/code-review-graph.md`, same format as `mempalace.md`, written
*before* Tier 1 code. It also corrects this plan's and drawer #173's
characterization of his benchmarks as *"inflated by a strawman."* That was too
harsh: he names his baseline plainly, publicly corrects people who over-quote his
best number in his favor, states the impact-analysis circularity in his own
README, and publishes results that make his tool look worse (MRR 0.35, flow
recall 33%, small changes costing more than a naive read). The surviving note is
a disagreement about which baseline is representative, not an accusation.

## Track B — The glossary drawer (from mattpocock/skills)

**The borrowed idea:** a shared domain vocabulary makes the agent terser and more
consistent. Matt's version is a `CONTEXT.md` the agent reads.

**Corrected 2026-08-01, after reading the file rather than assuming it.** This
section previously read: *"The insight is right and the storage is wrong — a
markdown file goes stale silently, has no provenance, and gets rewritten in
place."* That was unfair. His `CONTEXT.md` carries `## Language` (terms plus an
`_Avoid_:` list of banned synonyms — a disambiguation instrument, not a
dictionary), `## Relationships` (a small domain model), and
`## Flagged ambiguities`, which records *resolved* terminology conflicts along
with their resolution. That third section **is** a provenance mechanism. He
identified the drift problem and solved it in-file, by hand.

The remaining divergence is narrow and is a tradeoff, not an improvement:
Cairntir records resolutions as superseded drawers — mechanical, timestamped,
queryable across months, and resilient to the author forgetting to write the
entry. His file is legible to a human in ten seconds and needs zero
infrastructure. See `docs/lineage/mattpocock-skills.md`.

**Cairntir's version:** an identity-layer glossary drawer per wing. Loaded at
every `session_start` by construction, superseded rather than edited, so
terminology drift becomes a visible chain instead of a lost diff. CodeGlass
already requires a `glossary` field, so the concept is half-built.

**Deliverables:** a `glossary` room convention, emission at `session_start`, and
`docs/lineage/mattpocock-skills.md`.

**Not doing:** porting his skills. Superpowers already covers roughly 70% of that
footprint (TDD, debugging, code review, planning, skill authoring), the
three-skill core is locked, and anything that would be a fourth skill becomes a
recipe. Installing fifteen more overlapping skills is precisely the cargo cult
v0.1 was built to kill.

### On engaging his community — sequencing, not tactics

This is the part that can go wrong, so it is written down explicitly.

Cairntir and mattpocock/skills are **not competitors** and the pitch must never
imply otherwise. He operates at the prompt layer and does it extremely well.
Cairntir operates underneath, at the memory layer. The one true sentence is:
*none of those skills remember anything after the session ends.* That is a gap,
not a criticism, and it is the only claim worth making.

**The sequencing:**

1. Build the thing. A memory skill that is genuinely useful standalone.
2. Publish it in **Cairntir's own repo and plugin** first. Let it earn real use.
3. Only then, and only if it has earned it, offer it anywhere else.

**Do not open a PR into his repo as an opening move.** He is carrying 258 open
issues. An unsolicited PR whose real payload is a dependency on someone else's
package is a tax on a maintainer, however well-intentioned. If we ever do
approach, it starts as a disclosed question — "would this be welcome?" — not as
a merge request, and the authorship interest is stated in the first sentence.

**Never** frame Cairntir as the fix for a deficiency in his work.

## Track C — Process hygiene left over from the release

- **C1 — Branch protection. RESOLVED 2026-08-01: releases go through a PR.** The
  v1.2.0 `main` push reported `Bypassed rule violations` because it went straight
  to `main`, skipping the PR. The rule is cheap: a PR plus two status checks and
  **zero approving reviews** — one click for a solo maintainer. PR #16 went
  through it with no bypass. The rule stays as configured; go through the branch,
  never around it.
- **C2 — Done this session.** `scripts/check_release_tags.py` now fails the build
  when a released changelog header has no matching tag — the defect that hid
  1.0.1 and 1.1.3.

## Sequencing

1. **Attribution docs** — both lineage files, before any feature code.
2. **A1 / A2 gates** — cheap, falsifiable, and either may kill Track A outright.
3. **Whichever track survives** — Tier 1 anchors and/or the glossary drawer.
4. **Community engagement last**, and only if step 3 produced something real.

The order is deliberate. The lineage docs are the cheapest work on this map and
the only part that is about other people. Doing them first makes it structurally
impossible to ship first and credit afterward.

## What this map explicitly refuses

- Forking, vendoring, or rebranding either project
- Reusing anyone else's benchmark numbers as our own
- "Better than X" positioning in any public writing
- Opening a PR into someone else's repository as an opening move
- Building Tier 2 or Tier 3 before Tier 1 has earned it
- Shipping a feature borrowed from a named source before that source is credited
  in `docs/lineage/`
