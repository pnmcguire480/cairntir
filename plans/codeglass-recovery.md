# CodeGlass Recovery — Comprehension for Vibecoders

**Status:** core protocol implemented; evidence automation and holdout evaluation pending
**Recorded:** 2026-07-27
**Ancestry:** BrainStormer CodeGlass → Cairntir recipe + Anthropicer projection

## User outcome

A developer with minimal or no formal computer-science training can inspect a
project, change, or subsystem and come away understanding it well enough to
reason about it safely. The artifact should teach, not merely inventory.

CodeGlass is for Patrick and other vibecoders first. Expert readers may select
a denser mode, but novice comprehension is a first-class contract rather than
an apology or simplified afterthought.

## Forensic verdict

The strong walkthroughs in Anthropicer show that the concept can work. The
BrainStormer rewrite did not automate their quality:

- interactive mode created an empty WHAT/HOW/WHERE/WHEN/WHY template;
- diff mode listed commit text, files, and regex-discovered symbols;
- WHY remained a manual placeholder;
- wrapup/autosave scanners logged heuristics rather than explanations;
- there were no source citations, uncertainty labels, comprehension checks,
  hallucination controls, or outcome measurements.

The rewrite is therefore reference material, not an implementation to port.

## Modern form

CodeGlass becomes a **recipe**, not a fourth Cairntir skill.

### Inputs

- project, commit, diff, subsystem, or explicit file scope;
- reader level: novice, intermediate, or expert;
- the reader's question or learning goal;
- optional prior walkthrough/drawer to update rather than duplicate.

### Stage 1 — deterministic evidence

Collect only inspectable facts:

- changed files and exact diff;
- symbols, imports, call sites, configuration, tests, and build results;
- relevant git history and decision drawers;
- entry points, boundaries, data flow, side effects, and failure paths.

Raw evidence is stored separately from interpretation.

### Stage 2 — explanation

Produce:

- WHAT it is;
- HOW it works;
- WHERE it lives and connects;
- WHEN it runs;
- WHY it exists;
- a data/control-flow walkthrough;
- glossary and plain-language analogies;
- danger zones and “what breaks if this changes”;
- observed alternatives and tradeoffs.

Every factual claim cites a file/line, commit, test receipt, or drawer. WHY
statements are labeled **observed**, **inferred**, or **unknown**.

### Stage 3 — teach-back

Ask two or three short questions that require the reader to explain the flow,
predict a behavior, or identify a safe change. Record misunderstood concepts
and revisit them in later walkthroughs.

### Stage 4 — memory and projection

Persist linked drawers for:

- evidence set;
- generated walkthrough;
- user annotations/corrections;
- teach-back result;
- later usefulness or invalidation.

Project the verified walkthrough one-way into Anthropicer with Obsidian
wikilinks. SQLite remains authoritative; user notes remain visibly distinct
from generated text.

Teach-back changes, persistent misconceptions, and newly mastered concepts
also feed the Evolving Mind Human Learning Log. CodeGlass is the pedagogical
sensor; the log is the longitudinal human-facing record.

## Quality gates

- no unfilled placeholders;
- all five WHAT/HOW/WHERE/WHEN/WHY sections present or explicitly “unknown”;
- factual claims are cited;
- inference is labeled;
- verification commands and results are recorded;
- reader level is declared;
- teach-back is completed or explicitly skipped by the user;
- regeneration is idempotent for the same evidence set;
- a holdout evaluation measures whether a reader can answer real code questions
  after using the walkthrough.

## Dependency on foundation hardening

CodeGlass depends on trustworthy retrieval, complete drawer access, provenance,
durable workflows, and a safe Anthropicer projection. It begins after those
substrates are reliable so its explanations cannot silently cite a mixed or
truncated memory index.

## Implementation snapshot — 2026-07-27

The working tree now ships CodeGlass as a recipe plus dedicated MCP
operations. Walkthroughs require all five teaching sections, reader level,
evidence citations, glossary, and danger zones. Durable idempotency prevents
duplicate regeneration. Immediate and delayed teach-backs form a supersession
chain, produce a retention report, and feed evidence-backed candidates into
the Human Learning Log.

`cairntir obsidian-project <vault> [--wing ...]` projects verified learning
into `cairntir-sync/` while preserving human notes and excluding secret
memories. The actual Anthropicer vault was confirmed at `C:\Dev\Anthropicer`;
its existing drawer convention is under `cairntir-sync/drawers/`.

What remains is the host-side deterministic evidence collector/generator and
a real learner holdout study. Cairntir validates and stores cited
walkthroughs; it does not yet autonomously inspect arbitrary repositories and
author a trustworthy lesson without an agent supplying the evidence.
