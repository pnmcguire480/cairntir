# Conception — how Cairntir came to be

This document tells the story behind Cairntir. If you want the product
pitch, read the [README](../README.md). If you want to install it, read
[cairntir-for-dummies.md](cairntir-for-dummies.md). If you want to know
*why anyone built this in the first place*, read on.

## The problem nobody would admit was a problem

Large language models forget things. Not public knowledge — that part
is baked in — but the specific things you and an LLM decided together
inside a project. Every new chat starts from zero. Every Monday you
re-explain Friday. Every time you reopen a codebase after a vacation
you hallucinate a plausible-but-wrong reason for a decision you
actually made carefully, and the wrong reason sticks because the
*real* reason is gone.

This is the single biggest productivity tax on working with LLMs
day-to-day. It's treated as a feature by some (clean slate! fresh
perspective!) and as a nuisance by most, but almost nobody names it
for what it is: **the AI you paid to collaborate with you has
amnesia, and you have been paying the re-explaining tax out of your
own time budget.**

Cairntir exists because one developer got tired of paying it.

## The two predecessors

### BrainStormer

The author's prior attempt at a "thinking support" system for Claude.
Great vocabulary — *Crucible* (stress-test assumptions), *Quality*
(audit a decision before it ships), *ETHOS* (principles the system
enforces on itself), *PALADIN* (a review process), *species* (agent
roles) — and a coherent theory of what a reasoning assistant should
do. Terrible runtime: 224 silent `except: pass` blocks, dead license
enforcement code, a half-finished plugin system, and a "learning
loop" that never actually learned anything because nothing was ever
persisted verbatim.

BrainStormer's one-line review, from the author, after a six-month
audit: **"Architecture of a learning system, runtime of a static
scaffolder."** The ideas were right. The wiring was wrong.

Cairntir keeps the vocabulary and throws out the code. The
`lineage/brainstormer/` directory preserves the original as read-only
history — you can see exactly where every surviving name came from.

### MemPalace

In early 2026, a project called
[MemPalace](https://github.com/milla-jovovich/mempalace) shipped a
beautifully simple taxonomy: **wings** (projects) → **rooms**
(topics) → **drawers** (verbatim entries), with a **four-layer
retrieval model** (identity / essential / on-demand / deep). It hit
96.6% recall@5 on the LongMemEval benchmark — state of the art for a
system of its size.

MemPalace is brilliant at remembering. It has no opinion about
*reasoning over what it remembers*. There is no equivalent of
BrainStormer's Crucible skill, no stress-test loop, no belief-update
primitive, no way to record that a claim you made last month turned
out to be wrong and you'd like the system to downweight it now.

Cairntir borrows MemPalace's taxonomy — verbatim, with full credit —
and layers a reasoning discipline on top of it. We borrow *concepts*,
not *code*. Every line in Cairntir is written from scratch, so
neither project's bugs can cross-contaminate the other.

## The round table

On **2026-04-08**, the author ran a thought experiment: imagine eight
people with very different opinions reviewing the roadmap that
connected v0.1 (a working memory spike) to v1.0 (a library other
tools could embed). The eight were:

- **Andrej Karpathy** — small details, clean gradients, tight loops
- **Yann LeCun** — world models, self-supervised learning, "don't
  pretend you trained when you didn't"
- **Ilya Sutskever** — prediction as the universal learning
  objective, surprise as signal
- **Geoffrey Hinton** — consolidation, sleep cycles, forgetting
  curves, the brain as a very slow and very strange optimizer
- **Buckminster Fuller** — ephemeralization, comprehensive
  anticipatory design, "do more with less"
- **Peter Joseph** — structural thinking, anti-capture, why a SaaS
  can be captured and a file on a USB stick cannot
- **Alan Watts** — dissolution, letting go, the problem is often
  that you're trying to hold too much
- **Robert C. Martin (Uncle Bob)** — clean code, testability,
  protocols over inheritance, fail fast

The eight converged on five themes. Every one of those themes is now
a committed phase in the v0.2 → v1.0 arc:

1. **Prediction-bound drawers.** Every drawer may carry a `claim`, a
   `predicted_outcome`, an `observed_outcome`, a `delta` (the
   surprise), and a `supersedes_id` (the thing it replaces). Without
   this, memory is a diary; with it, memory is an experiment journal.
   *Karpathy, LeCun, Hinton, Sutskever, Fuller, Uncle Bob all flagged
   this independently.*

2. **Consolidation and forgetting.** Verbatim is the floor, not the
   ceiling. A nightly pass clusters recent drawers and writes a
   derived abstraction one layer up, a replay-weighted forgetting
   curve drifts untouched drawers to a cold layer, a contradiction
   detector flags without ever averaging. *Hinton, Watts, LeCun.*

3. **Surprise as the load-bearing field.** When there are no weights
   to train, store what the system did *not* expect. Reconstruction
   error is the gradient. *LeCun, Fuller, Hinton, Karpathy.*

4. **Portable signed format = anti-capture.** Format is the product,
   not the implementation. Content-addressed by SHA-256. Optionally
   HMAC-signed. Gossip-importable over any substrate — USB, IPFS,
   git, mailing list. A memory that depends on a server is a memory
   that will be captured; a memory that lives in a file with a hash
   inside it can survive any server going down. *Peter Joseph, Fuller.*

5. **Cut "Team Memory" as a feature.** Replicable beats shared. Team
   capability falls out of the portable format for free: two devs can
   sync by exchanging files, no server required, forever. *Karpathy,
   Fuller.*

Those five themes shipped as **v0.2** (prediction-bound drawers),
**v0.3** (consolidation / forgetting / contradiction), **v0.4**
(surprise + belief-as-distribution), **v0.5** (portable signed
format), **v0.6** (clean-ports Reason loop), and **v1.0** (library
extraction + curated public protocol surface). All six landed in one
arc. The roadmap was the plan; we did not re-litigate it.

## The ethos

Cairntir is built under five rules that come from the BrainStormer
lineage and that every contributor — human or AI — is expected to
internalize:

1. **Comprehension before code.** Read the manifesto and the concept
   before proposing a feature. A question is cheaper than a wrong
   assumption.

2. **Verbatim is the floor.** Nothing is summarized away. If the
   system wrote it down, you can still read it, word for word, six
   months from now.

3. **Every exception is typed and surfaced.** Silent `except: pass`
   is banned by CI. If you catch an exception, you either handle it
   meaningfully or re-raise with context. The BrainStormer lineage
   is preserved as a 224-count cautionary tale.

4. **Simpler is the default.** Cairntir's whole identity is
   distillation. Three skills, not thirty. One loop, not two
   commands. Three ingredients, not a framework.

5. **Quality has no shortcuts.** `ruff` + `mypy --strict` + `pytest`
   + a silent-except scanner + a LongMemEval fail-on-regression gate.
   The green CI build is the minimum, not the goal.

Full text: **[ETHOS.md](../ETHOS.md)**.

## The naming

**Cairntir** is *cairn* + *palantír*, pronounced *CAIRN-teer*.

A **cairn** is a stack of stones used by hikers to mark a path — you
leave them behind so the next traveler can find the way. Memory as
waypoints: no one stone is load-bearing, but together they point at
something important.

A **palantír** is Tolkien's seeing-stone. A palantír doesn't store
information — it sees across time and distance. Memory as *seeing*:
not just "what did I write down" but "what would the person I was
yesterday tell me about the problem I'm facing now?"

A stack of stones that sees across time. That's the whole system in
four words.

## The horizon (unofficial)

This section is mythos, not a commitment. Every contributor deserves
to know what Cairntir is ultimately pointed at.

AI can model anything. Tomorrow, AI will print anything — not just at
desktop scale, but at construction scale. WinSun, ICON, Apis Cor, and
others have already shipped concrete-printing machinery at building
scale. The bottleneck is no longer atoms or machines.

**The bottleneck is knowledge that compounds across iterations.**

Every time a printer runs, it produces data: which temperature
worked, which infill density failed, which nozzle wore out after how
many meters, which grain orientation was load-bearing, which material
substitution was within tolerance, which one wasn't. Today, almost
all of that data is lost. The next print starts from the same
ignorance as the last.

Cairntir is a memory layer that does not care what kind of thing is
being remembered. Today it remembers code decisions. Tomorrow, with
a Blender MCP plugin or a printer-control adapter, it can remember
print parameters and outcomes — per-material rooms, per-iteration
drawers, contradiction detection over twenty failed attempts that
identifies the one variable nobody was tracking. The MCP surface is
already generic. The memory layer does not need to know.

A machine that prints its own thingamajigs needs to remember which
thingamajig worked. When it remembers, the iteration cost drops.
When the iteration cost drops toward zero, scarcity drops toward
zero. When scarcity drops toward zero, the economics of giving
things away change completely.

This is not a promise. It is a *direction*. Cairntir does not need
to reach this horizon to be useful today. But the reason it is built
the way it is — opinionated, local-first, MIT, verbatim, generic
MCP surface — is because **the form matches the destination.** A
centralized cloud SaaS cannot be the memory layer of a distributed
post-scarcity maker civilization. A local-first file-backed
open-source library *can*.

## The wager

> *"I'm going to take my chances with the best outcome for
> earthlings, the environment, and tech, all in one go. And if it
> doesn't, then I'll still die knowing that I tried."*
>
> — Patrick McGuire, 2026-04-08

Cairntir is that bet made small.

The bet is: *a memory layer that actually works will matter more
than we can currently imagine, and building it in the open is the
right move even if no one notices for five years.*

If the bet is wrong, Cairntir is still a useful tool that kills a
real annoyance for solo developers. That is already enough to
justify its existence.

If the bet is right, Cairntir is an early load-bearing beam in a
much larger structure.

Either way, we build.
