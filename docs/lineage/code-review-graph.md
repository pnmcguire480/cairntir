# Lineage: code-review-graph

Cairntir's structural-recall work is influenced by **code-review-graph**
(https://github.com/tirth8205/code-review-graph) by **Tirth Kanani**
([@tirth8205](https://github.com/tirth8205)). This document records what we
learned, what we borrowed, and — the part that matters — what we deliberately
left behind. **No code from code-review-graph is copied into Cairntir.**
Concepts only.

**Disclosure:** written by the author of Cairntir, about a concept borrowed for
Cairntir. The interest is not hidden. Nothing here has been sent to Tirth.

**Status: written before the code.** Project policy is that a lineage doc lands
before a line of the feature it credits. At the time of writing,
`cairntir_recall_for_change` is designed and unbuilt. This document exists so
that shipping first and crediting afterward is structurally impossible.

## What code-review-graph Is

A local-first code intelligence graph for MCP and CLI. It parses a repository
with tree-sitter into nodes (functions, classes, imports) and edges (calls,
inheritance, imports, test coverage), persists that graph to SQLite in
`.code-review-graph/`, and answers "what is the blast radius of this change?"
so an assistant reads a minimal review set instead of the whole corpus.

The pipeline is repository → tree-sitter parser → SQLite graph → blast radius →
minimal review set. On top of the base graph it derives Leiden community
detection, execution flows from entry points ranked by criticality, hub nodes by
degree, bridge nodes by betweenness, FTS5 search, and optional embeddings. The
surface is 30 MCP tools plus 5 workflow prompts (`review_changes`,
`architecture_map`, `debug_issue`, `onboard_developer`, `pre_merge_check`), a
CLI, and a GitHub Action that posts risk-scored PR comments.

MIT, Python 3.10+, created 2026-02-26. As of 2026-08-01 it carries 27,902 stars,
2,580 forks, and 56 open issues, and was last pushed 2026-07-30. Those are
**his** numbers describing **his** project. They are context here, never
repeated as a claim about Cairntir.

## On His Benchmarks — And A Correction To Our Own Assessment

Project rule: never restate another project's benchmarks as ours. His numbers
are cited here as *his claims, measured his way*, and Cairntir generates its own
or stays quiet.

His stated results: median per-question token reduction of ~82x across 6 repos
(range 38x–528x); impact-analysis F1 averaging 0.714 across 13 commits, with
precision 0.578 and recall 1.0; search latency 0.4–1.5ms; flow detection
95–128ms; ~10s initial build on a 500-file project and under 2s incremental.

**Cairntir's internal assessment (drawer #173) was harsher than the evidence
supports, and that is corrected here.** It characterized the token-reduction
figure as *"inflated by a strawman."* Having now read his README rather than
summarized it, that word is wrong, and the reason is that **he discloses more
against his own interest than we credited him for**:

- He names the baseline plainly rather than burying it.
- He actively pushes back on his own best number: *"The frequently quoted 528x
  is the maximum — a single best-case repo (fastapi) — not the typical
  result."* Publishing a correction to people over-quoting you in your favor is
  rare and it is the opposite of a strawman.
- He states the circularity himself, in his own README: the impact ground truth
  *"is derived from the same graph the predictor traverses, so it is circular by
  construction,"* and recall 1.0 is *"an upper bound by construction."*
- He publishes results that make his tool look worse: small single-file changes
  can cost more than a naive file read, search quality sits at MRR 0.35 and
  needs work, and flow detection reaches only 33% recall.

The one methodological note that survives, stated as disagreement rather than
accusation: the token-reduction baseline is full-corpus, and no agent actually
reads a whole repository — the realistic baseline is grep plus targeted reads.
Against that baseline the multiple would be smaller. The underlying win is real;
we would simply measure it differently. He is transparent about which baseline
he used, so a reader can make exactly this judgment themselves. That is what
honest benchmarking looks like.

**Cairntir's own anchor numbers (A1/A2, drawer #176) are ours, generated our
way, against our own corpus, and they are not comparable to his.** Neither set
of numbers should ever be quoted as the other's.

## What We Borrowed (Concepts Only)

### Structural recall

One idea, and it is the good one: **memory should be reachable by what you are
changing, not only by what you thought to ask.**

Cairntir has a concrete instance of this gap in its own corpus. Drawers #94 and
#95 record the entire cold-start arc — five patch commits chasing symptoms,
resolved by defaulting to fastembed and dropping torch from the MCP hot path.
Today they surface only if someone semantically asks about cold starts. Anchored
to `src/cairntir/memory/embeddings.py`, *touching that file* would surface the
arc unprompted. That is a direct instrument for two metrics already committed in
the Evolving Mind contract (drawer #118): recall improvement and stale
rejection.

### The graph is a cache, never a drawer

Borrowed as a hard constraint rather than a feature. Cairntir stores episodic
and semantic memory of the *collaboration* — verbatim, immutable, append-only,
belief-weighted. code-review-graph stores structural memory of the *artifact* —
derived, regenerable, disposable. Keeping that line sharp is what makes any
integration honest: Cairntir's anchor index carries no belief mass, no provenance
receipts, and no supersession chain, and can be deleted and rebuilt at any
moment. The verbatim floor does not move.

## What We Deliberately Left Behind

### Tree-sitter and its grammars

The largest thing dropped, and dropped on Cairntir's own stated principles.
`docs/lineage/mempalace.md` rejected ChromaDB over roughly fifteen transitive
dependencies and install fragility. Thirty tree-sitter grammars is a heavier bet
than the one already refused, on a platform — Windows — that produced a real
`cp1252` crash in the v1.2.0 cycle. Refusing ChromaDB and then accepting
tree-sitter would make the earlier decision incoherent.

Cairntir's Tier 1 therefore uses **no parser at all**. Anchors are optional
`metadata.anchors` entries of `{path, symbol, symbol_source_hash}` on drawers
that already exist, in a store that already carries arbitrary JSON. No graph, no
grammar, no new dependency, no schema break.

### 27 of the 30 MCP tools

Communities, hubs, bridges, execution-flow ranking, wiki generation, refactor
apply, and cross-repo search are all out. Cairntir sits at 17 MCP tools by
deliberate restraint; matching this surface would push past 40 and directly
contradict *"fewer tools = fewer decisions for the AI."* Anyone who wants that
surface should run code-review-graph as a second MCP server — it is MIT, it is
actively maintained, and it is better at this than a reimplementation would be.

### Staleness flagging — held, not dropped

Worth recording precisely because it is the borrowed idea we came closest to
shipping and did not. Cairntir's A2 gate replayed real git history and found the
naive file-scoped design fires at 40.3% precision — a 2.48x noise factor, about
two and a half flags per real change. The corrected symbol-scoped design is
sound in principle, but **rename survival is untested**: Cairntir's entire
history contains zero renames (`git log --diff-filter=R -M`), so the corpus
cannot answer the question.

The hold is not scheduling. A staleness signal that floods false positives on
someone's first big refactor loses trust permanently and does not get a second
chance. It lifts only when rename survival is actually tested against a corpus
that has renames.

## What Cairntir Does Not Do

Required by our own rules, because a comparison that lists only strengths is
marketing.

Cairntir has **no** call graph, **no** inheritance or import edges, **no** blast
radius, **no** community detection, **no** hub or bridge analysis, **no**
execution-flow ranking, **no** risk-scored PR comments, and **no** GitHub Action.
It cannot tell you what a change will break. It does not read your code at all —
it reads what you *said about* your code. Cairntir's anchors resolve to drawers
you already wrote; if nobody wrote a drawer about a file, anchoring it returns
nothing, forever.

Cairntir's own A1 gate measured anchorability at 33.3% permissive / 28.9%
strict against a pre-registered 30% bar — **marginal, not a clean pass**, which
is why anchors are per-room and opt-in rather than automatic. We are shipping a
narrower thing on weaker evidence than his graph provides, and doing it because
the dependency cost is near zero, not because it is better.

## When His Tool Is The Better Fit

**Whenever the question is about the code rather than about the collaboration.**

If you want to know what a change breaks, which modules form natural clusters,
where the architectural bridges are, what a new developer should read first, or
you want risk-scored comments on your PRs — install code-review-graph. Cairntir
answers none of those questions and is not going to. It is MIT and it runs
happily as a second MCP server alongside Cairntir; that is a supported
configuration, not a fallback.

Install Cairntir when the problem is that **the reasoning behind a decision
evaporated when the session ended.** These are different memory types. They
compose cleanly precisely because neither is trying to be the other.

## Credit Where It's Due

The idea Cairntir owes to this project is small enough to state in a sentence
and load-bearing enough to reshape the roadmap: *recall should be triggerable by
what you are touching.* Cairntir had semantic recall and exact recall and no
answer to "surface what I need without me knowing to ask."

The second thing owed is a standard rather than a feature. Tirth publishes his
weak numbers next to his strong ones, corrects people who over-quote him in his
favor, and names the circularity in his own methodology before a critic can.
Cairntir's culture — prediction-bound drawers, Crucible, `cairntir_calibration` —
is built to force exactly that behavior. Seeing someone do it voluntarily, in a
repo with 27,000 stars where nobody would have checked, set a bar worth matching.
It also earned him a correction in this document to an assessment that had
judged him too harshly.

**Thank you, [@tirth8205](https://github.com/tirth8205), for showing that the
map of what calls what is a memory worth keeping — and for publishing your
error bars.**
