# The Amnesia Problem and What It Cost Me

*Draft — v1.1 release post. Not yet published.*

---

## The opening

There's a thing that happens every Monday when I open a fresh Claude
Code chat.

I've been working on a codebase for weeks. I've made decisions.
Rejected approaches. Discovered constraints that only showed up
under load. Argued with Claude about trade-offs and landed on
specific answers for specific reasons. By Friday afternoon Claude
knows my project the way a new teammate knows it at week four.

Then I close the laptop. Monday morning I open a fresh chat and
Claude doesn't know my name.

Not literally — it still knows Python and Postgres and the shape of
an MCP server. But every *specific* thing we built together over
the last week is gone. Which database we picked and why. Which
hack in `auth.py` is protecting which CVE. What's blocking the next
PR. Why we're not using the obvious approach on `api/v2`.

I have to re-explain it. Every Monday. Every time I start a
non-trivial conversation. And when I don't re-explain carefully
enough, Claude hallucinates a plausible-but-wrong reason for a
decision I actually made deliberately — and the wrong reason sticks
because the real one exists only in my head.

This is the amnesia problem. It is the single biggest productivity
tax on working with LLMs day-to-day. It is treated as a feature by
some people ("clean slate! fresh perspective!") and as a nuisance
by most, but almost nobody names it for what it is:

**The AI you paid to collaborate with has amnesia, and you have
been paying the re-explaining tax out of your own time budget.**

I got tired of paying it. This is the story of what I built
instead.

---

## The cost, in hours

*(To be filled in: a quantified week-by-week tally from personal
logs — how much of each Monday morning went to re-briefing, how
many times the re-brief was incomplete, how many times a
hallucinated reason went uncaught for hours or days.)*

---

## Why the obvious fixes didn't work

*(To be filled in: the things I tried first and why each one
failed.)*

- `CLAUDE.md` files per project — survives; doesn't scale past the
  24k-ish character budget; summarization hides the specific
  decisions you actually needed.
- Chat transcript dumps — Claude can read them but won't
  speculatively search them, and the re-brief is worse than just
  re-explaining.
- RAG over my repo — indexes code, not decisions. *Why* I picked X
  is usually not in the code.
- MemPalace — great memory, no reasoning discipline. Close, but
  half the product.
- BrainStormer (my own prior attempt) — great vocabulary, terrible
  runtime. The architecture of a learning system with the runtime
  of a static scaffolder.

---

## The fix that actually worked

*(To be filled in: the core insight. Memory is necessary but not
sufficient. You need the memory to be queryable, the queries to be
cited, the decisions to be falsifiable, and the retrieval to weight
what proved correct over what didn't.)*

### The three ingredients

1. **Verbatim persistent memory.** Nothing summarized away. If the
   model wrote it, you can read it, word for word, six months
   later.
2. **Prediction-bound drawers.** Every claim can carry a predicted
   outcome, an observed outcome, a delta, and a supersedes link.
   Memory becomes an experiment journal, not a diary.
3. **Belief-as-distribution retrieval.** The retrieval distribution
   itself is the belief. Successful uses raise a drawer's mass;
   dead retrievals lower it. No training pipeline — the usage data
   is the gradient.

### The governance rule

Three skills, locked by design (crucible, quality, reason).
Everything else is a recipe chained on top. This keeps the surface
narrow enough to reason about and open enough to grow.

---

## What day 30 looks like now

*(To be filled in: a real example — walking into a cold codebase
after a vacation, the first chat's session_start output, the
specific decision drawers that surfaced, what would have happened
without them.)*

---

## What I learned that I didn't expect

*(To be filled in: the surprise — that the value wasn't just
remembering, it was that **falsifiable predictions change how you
think out loud**. Knowing Claude will commit your claim to a
drawer with a predicted outcome and hold you to it weeks later
makes you more careful about what you claim in the first place.
This was not in the design. It fell out of the constraint.)*

---

## The wager

> *I'm going to take my chances with the best outcome for
> earthlings, the environment, and tech, all in one go. And if it
> doesn't, then I'll still die knowing that I tried.*
>
> — written the day I sat down to build this

The bet is: a memory layer that actually works will matter more
than we can currently imagine, and building it in the open is the
right move even if no one notices for five years. If the bet is
wrong, Cairntir is still a useful tool that kills a real annoyance
for solo developers. That is already enough.

If the bet is right, Cairntir is an early load-bearing beam in
something much larger — AI + grand-scale 3D printing + the
economics of giving things away for free. But that's a different
post.

This post is about a tax I got tired of paying, and the file on my
hard drive that stopped charging it.

---

## Install

```
pip install cairntir
cairntir setup
```

Fully quit Claude Code, reopen it in any folder, ask *"what is
cairntir?"*. If it answers with real knowledge and offers to check
memory, you're done.

- **Source:** https://github.com/pnmcguire480/cairntir
- **Docs (plain English):** [cairntir-for-dummies.md](../cairntir-for-dummies.md)
- **Conception story:** [conception.md](../conception.md)
- **Roadmap (v1.1 → v2.0):** [roadmap.md](../roadmap.md)
- **License:** MIT

---

*Published on: [date]*
*Author: Patrick McGuire ([@pnmcguire480](https://github.com/pnmcguire480))*
