# Next Map — Attribution-First Scoping After v1.2.0

**Status:** proposed, not started
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

**Gate before build.** Drawer #173 recorded two load-bearing assumptions and a
Crucible verdict of *investigate, do not proceed*. Both resolve in about an hour
and both must pass first:

- **A1 — Are drawers actually about code symbols?** Sample 30 drawers across
  wings, count how many name a file or symbol that still exists. Set the pass bar
  *before* looking. If most drawers are about decisions, releases, and
  preferences rather than code, anchors sit empty and Track A dies here.
- **A2 — Does symbol identity survive refactoring?** Replay Cairntir's own git
  history across a rename and a file move. If every refactor floods false "stale"
  flags, the signal is noise and nobody will trust it twice.

**If both pass — Tier 1 only:**

- optional `metadata.anchors` of `{path, symbol, content_hash}`; no schema break,
  the store already carries arbitrary JSON
- `cairntir_recall_for_change(files)` — drawers whose anchors intersect a diff
- staleness flagging when an anchored symbol's hash moves: flag as a supersession
  *candidate*, never mutate, never delete

**Hard constraint carried from #173:** the index is a cache, never a drawer. No
belief mass, no provenance receipts, no supersession chain. Deletable and
rebuildable at any moment. The verbatim floor does not move.

**If A1 fails:** stop, and write the negative result as a drawer. A falsified
assumption recorded is worth more than a feature shipped on a hunch.

**Not doing:** Tier 3 (communities, hubs, bridges, wiki, refactor-apply,
cross-repo search). Cairntir sits at 17 MCP tools by deliberate restraint.
Anyone who wants that surface should run code-review-graph — it is MIT, actively
maintained, and better at it than a reimplementation would be.

**Attribution deliverable:** `docs/lineage/code-review-graph.md`, same format as
`mempalace.md`, written *before* Tier 1 code.

## Track B — The glossary drawer (from mattpocock/skills)

**The borrowed idea:** a shared domain vocabulary makes the agent terser and more
consistent. Matt's version is a `CONTEXT.md` the agent reads. The insight is
right and the storage is wrong — a markdown file goes stale silently, has no
provenance, and gets rewritten in place.

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

- **C1 — Branch protection (Patrick's decision).** The v1.2.0 `main` push
  reported `Bypassed rule violations`; protection wants a PR plus two status
  checks and admin overrode it. Either releases go through a PR, or the rule
  relaxes to match practice. A rule that exists but never binds is worse than no
  rule, because it produces false confidence.
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
