# The Amnesia Problem and What It Cost Me

*Draft — v1.1 release post. Section bodies filled by a draft pass; the
personal-numbers section ("The cost, in hours") is still an editor stub
waiting on the author's logs.*

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

> *Editor note: this section is a stub waiting on the author's actual
> time logs. The shape it should take: a week-by-week tally of how
> much each Monday morning went to re-briefing, how often the re-brief
> was incomplete, and how many times a hallucinated reason went
> uncaught for hours or days. The point of the section is to convert
> the qualitative complaint above into a number an outside reader can
> compare against their own week.*

---

## Why the obvious fixes didn't work

I tried the obvious things first. Each one lasted between three days
and three weeks before I admitted it wasn't enough.

- **`CLAUDE.md` files per project** — survives; doesn't scale past the
  24k-ish character budget; summarization hides the specific decisions
  you actually needed.
- **Chat transcript dumps** — Claude can read them but won't
  speculatively search them, and the re-brief is worse than just
  re-explaining.
- **RAG over my repo** — indexes code, not decisions. *Why* I picked X
  is usually not in the code.
- **MemPalace** — great memory, no reasoning discipline. Close, but
  half the product.
- **BrainStormer (my own prior attempt)** — great vocabulary, terrible
  runtime. The architecture of a learning system with the runtime of a
  static scaffolder.

The pattern across all five was the same. Each one *stored* something.
None of them remembered the *reasoning*. A code index will tell you
what the code does. It will not tell you why the code is the way it
is and not some other way. A `CLAUDE.md` will tell you the project's
name and one sentence about its goal. It will not tell you the seven
trade-offs you made on Tuesday and why each one went the way it did.

The thing I was trying to remember was not facts. It was *structured
judgment* — claims, predictions, observations, surprises, supersedure.
None of the obvious fixes had a place to put any of those.

---

## The fix that actually worked

The insight that broke the problem open was that **memory alone is
not enough.**

A perfect transcript of every chat I'd ever had with Claude would not
have helped. It would have been a haystack with no index of which
needles had proved sharp. What I needed wasn't more raw text — it was
a structure that recorded *which claims survived contact with reality
and which didn't*. A library, not a journal. A scoreboard for ideas.

That meant the unit of memory could not be a chat log. It had to be a
**drawer** with five fields:

- `claim` — what we believed at the time
- `predicted_outcome` — what we expected to happen if the claim was right
- `observed_outcome` — what actually happened
- `delta` — non-empty if the prediction failed (the surprise)
- `supersedes_id` — link to the drawer this one replaces

Every drawer is a tiny experiment. Every retrieval is a re-vote on
whether the experiment paid off. Memory turns into an *evolving*
thing, not a static archive — which is the trick that lets a
six-month-old decision keep mattering on a Monday morning.

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

The blunt demo is this. I opened Cairntir's own repo for the first
time in a stretch of days. Fresh chat. I asked: *"where did we leave
off?"*

The first thing Claude did — before answering — was call
`cairntir_session_start`. The tool returned the wing's identity
drawers (who I am, how this project works, the North Star) and the
single essential drawer #67, which had been written days earlier as
the previous Claude's last action. It said: *"v1.0.0 shipped — library
extraction. `cairntir.__init__` exposes only the stable seam: 24
names, sorted, snapshot-tested. Next session is the Road to 2.0.
PyPI publish is item #1."*

Claude read it. Then it answered my question with: *"We just shipped
v1.0.0. The next item on the roadmap is the PyPI publish. Want to
start there?"*

That's the whole demo. There is no re-explaining. There is no
hallucinated reason. There is no Monday morning tax. Walk in, read
the room, pick up where we left off.

The drawer I just described exists in this repo. The session log is
also in this repo. It is not a marketing screenshot.

---

## What I learned that I didn't expect

The amnesia fix was the visible win. The invisible one — the one I
didn't design for — was that **falsifiable predictions change how
you think out loud.**

Before Cairntir, when I told Claude *"I think this approach will
scale"*, the claim went into the chat and out the window. By Friday
I'd forgotten what I'd claimed. By Monday I was making a contradicting
claim with the same confidence. There was no register against which
to rate my own past judgment.

After Cairntir, every load-bearing claim becomes a drawer with a
`predicted_outcome` field. Three weeks later, when reality arrives,
the drawer's `observed_outcome` field gets filled in and a `delta` is
recorded if the prediction missed. The belief-as-distribution scorer
raises mass on drawers whose predictions held and lowers it on the
ones that didn't. It runs silently across months.

After the first surprise-weighted demotion of a drawer I'd been sure
of, I started being more careful about what I claimed. Knowing the
system would *remember the claim* and *score me on it* made me think
twice before stating it.

This was not in the design. It fell out of the constraint. The same
thing that fixed the amnesia ended up training me.

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
