# Lineage: mattpocock/skills

Cairntir's planned glossary drawer is influenced by **mattpocock/skills**
(https://github.com/mattpocock/skills) by **Matt Pocock** ([@mattpocock](https://github.com/mattpocock)).
This document records what we learned, what we borrowed, and — the part that
matters — what we deliberately left behind. **No code from mattpocock/skills is
copied into Cairntir.** Concepts only.

**Disclosure:** this is written by the author of Cairntir, about a concept
borrowed for Cairntir. The interest is not hidden. Nothing here is a request,
and nothing here has been sent to Matt.

**Status: written before the code.** Cairntir's project policy is that a lineage
doc lands before a line of the feature it credits. At the time of writing, the
glossary drawer is *scoped and not built*. This document exists so that it is
structurally impossible to ship first and credit afterward.

## What mattpocock/skills Is

A collection of agent skills — slash commands and behaviors — for Claude Code,
Codex, and other coding agents. Its tagline is exact about the provenance:
*"Skills for Real Engineers. Straight from my .agents directory."* These are
tools Matt actually uses, published as-is, not a framework assembled for an
audience.

It is MIT-licensed, created 2026-02-03, and as of 2026-08-01 carries 197,875
stars and 17,031 forks. Those are **his** numbers, describing **his** project's
reach. They are recorded here as context, never repeated as a claim about
Cairntir.

The skills are organized in buckets. `skills/engineering/` holds `tdd`,
`code-review`, `diagnosing-bugs`, `codebase-design`, `domain-modeling`,
`grill-with-docs`, `implement`, `improve-codebase-architecture`, `prototype`,
`research`, `resolving-merge-conflicts`, `to-spec`, `to-tickets`, `triage`,
`wayfinder`, and `ask-matt`. `skills/productivity/` holds `grill-me`,
`grilling`, `handoff`, `teach`, and `writing-great-skills`. Installation is
either the Claude Code plugin marketplace or `npx skills@latest add
mattpocock/skills`, which copies editable files into your project — a
deliberate choice that keeps the user in control of the text.

## What We Borrowed (Concepts Only)

### The shared-vocabulary document

One idea, and it is a good one. Matt's `CONTEXT.md` establishes project-specific
terminology so the agent stops guessing. His README argues the case under
*"Why These Skills Exist"* → *"#2: The Agent Is Way Too Verbose"*: a shared
language lets the agent decode the jargon a project already uses, which makes it
terser and more consistent. `grill-with-docs` is the skill that builds that
vocabulary through interrogation rather than asking you to write it cold.

The insight Cairntir takes is the premise, not the file: **an agent that shares
your project's vocabulary is a different, better collaborator than one that does
not.** That is a memory problem wearing a prompt-engineering hat, and Cairntir's
whole thesis is that memory problems belong in the memory layer.

### What his CONTEXT.md actually does — and a correction to our own plan

`plans/next-map.md` originally described the storage as *"a markdown file that
goes stale silently, has no provenance, and gets rewritten in place."* Having
now read the file rather than assumed it, **that description was unfair and is
corrected here.**

His `CONTEXT.md` has three sections, and two of them are cleverer than a
glossary:

- `## Language` — each term defined, plus an `_Avoid_:` list of banned synonyms.
  Not just "here is the word" but "here are the words that are *wrong*, stop
  using them." That is a disambiguation instrument, not a dictionary.
- `## Relationships` — how the terms relate to each other, so the agent gets a
  small domain model rather than a flat word list.
- `## Flagged ambiguities` — resolved terminology conflicts, with the
  resolution recorded. Example from his own file: "backlog" once meant both the
  tool and the work inside it; resolved to **Issue tracker** for the tool, with
  "backlog" retired as a domain term.

That third section **is** a provenance mechanism. He identified the drift
problem and solved it in-file, by hand. Our plan claimed the design had no
answer to drift. It has one. Saying so is the point of this section.

## What We Deliberately Left Behind

### The skills themselves — all twenty-two of them

Cairntir is not porting `tdd`, `code-review`, `diagnosing-bugs`, `handoff`, or
any of the rest. Three reasons, in order of weight:

1. **The three-skill core is locked.** Cairntir ships `crucible`, `quality`, and
   `reason`. Anything that would become a fourth skill becomes a *recipe*
   instead. This is governance, not preference — it is the specific rule that
   exists because BrainStormer, Cairntir's own predecessor, died of skill
   sprawl.
2. **Most of the footprint is already covered** for our users by the Superpowers
   skill set — TDD, debugging, code review, planning, skill authoring. Adding a
   second overlapping copy would make the agent choose between two right
   answers, and choices are where things go wrong.
3. **Installing fifteen more skills is precisely the cargo cult Cairntir v0.1
   was built to kill.** That critique is aimed squarely at our own history, not
   at his repo. His skills are curated from real use; a bulk import of them into
   Cairntir would not be.

### The file as the storage layer

This is the one substantive divergence, and it is narrow. Cairntir's version of
the idea is an **identity-layer glossary drawer per wing**: loaded at every
`session_start` by construction, and *superseded* rather than edited, so
terminology drift becomes a queryable chain with timestamps instead of a
hand-maintained prose section.

To be precise about the difference, because it is smaller than it sounds: Matt
records resolutions in `## Flagged ambiguities`, by hand, as prose. Cairntir
records them as superseded drawers, mechanically, with dates and provenance
attached. His approach is legible to a human reading the file in ten seconds.
Ours is queryable across months and survives the author forgetting to write the
entry. **Different tradeoff, not a better one** — a hand-written note stays
readable when the database is gone, and his file works with zero infrastructure.

## What Cairntir Does Not Do

Required by our own attribution rules, because a comparison that only lists
strengths is marketing.

Cairntir has **no equivalent** of what his repo actually is. It has no `tdd`
workflow, no `code-review` protocol, no `triage`, no `wayfinder`, no
`grill-with-docs` interrogation loop, no ticket generation, no merge-conflict
skill, no plugin marketplace listing of curated engineering practice. Cairntir
exposes three skills and a memory layer. It is not a skills library and is not
becoming one.

We are also not claiming his approach loses anything by being a file. For a
single repo with one developer and a stable vocabulary, `CONTEXT.md` is the
right amount of machinery, and Cairntir's version is over-engineering.

## When His Tool Is The Better Fit

**Most of the time, for most people, right now.**

If what you want is a strong set of engineering practices your agent will
actually follow — test-first discipline, structured debugging, real code review,
issue triage — install mattpocock/skills. It is MIT, actively maintained, and
it is *the* answer to that question. Cairntir does not compete for that job and
would lose badly if it tried.

Install Cairntir when your problem is that **the session ended and everything
your agent learned went with it.** Those are different problems. They compose:
his skills make an agent better within a session; Cairntir makes what happened
in that session survive to the next one.

The one true sentence about the relationship, and the only claim worth making:
*none of those skills remember anything after the session ends.* That is a gap
in the layer below them, not a criticism of them. It is not his job to fix, and
saying it is would be dishonest.

## Credit Where It's Due

Matt Pocock did not have to publish his `.agents` directory. Making your working
setup public means every rough edge in it is public too, and the reward is a
mountain of issues from people who did not read it. He did it anyway, under MIT,
and hundreds of thousands of engineers got better tooling for free.

The specific thing Cairntir owes him is smaller and more precise than the repo's
reach suggests: he demonstrated that **a shared vocabulary is worth writing down
as a first-class artifact**, and he designed a format thoughtful enough that
reading it changed our design — including correcting a claim we had already
written about it. That is what a good source does.

**Thank you, [@mattpocock](https://github.com/mattpocock), for showing that
teaching the agent your language is not overhead — it is the work.** Cairntir is
building the layer where that language persists.
