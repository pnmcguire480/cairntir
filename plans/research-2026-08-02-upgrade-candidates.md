# Cairntir — inception to horizon, and 10 candidates for consideration

**Date:** 2026-08-02 · **Status:** research only. Nothing here is committed.

**Brief.** Trace the concept of Cairntir from inception through the full lineage —
BabyTIEROS, BrainStormer, brainstormer-agents, CodeGlass — recover features
proposed but never built, survey current AI trends, repos and workflows, hunt for
blind spots, and recommend ten upgrades **for consideration, not implementation.**
Patrick's framing: *"we must fully understand the past in order to steer into the
future with confidence."*

**Evidence standard**, per drawer #173 and the attribution contract:

- **Measured** — a number produced on this machine today, reproduction given.
- **Sourced** — a third-party claim, attributed, not independently verified, and
  never restated as ours.
- **Judgement** — my reading. Argue with it.

---

## The finding that reorders everything else

The oldest idea in this lineage is not memory. It is **controlled context**.

BabyTIEROS — the earliest ancestor, before any vector store existed — separated
material into **always-load / load-when-relevant / never-load**. That policy is
the direct ancestor of Cairntir's four retrieval layers.

The `docs/lineage/evolution-audit-2026-07-27.md` audit found that the *policy*
survived and the **budget and exclusion contract did not**, and said so in terms
that read as a warning:

> the current 100-character snippets and fixed limits are not just an MCP
> formatting defect. They are **a regression from the lineage's original
> context-control discipline.**

That audit wrote "explicit context budgets and complete-drawer access" into the
**"Restore in the v1.2 core"** list. v1.2 was then implemented, verified across
three hosts, released to PyPI, and attested.

**It did not land.** *Measured today:*

```
def session_start(self, *, wing: str, query: str | None = None) -> str:
```

No budget parameter. No character limit. No token ceiling.

| | chars | ≈ tokens |
|---|---|---|
| 18 tool definitions — every session, every host | 7,675 | **1,918** |
| `session_start(wing="cairntir")` | 30,950 | **7,737** |
| `session_start(wing="detroit-clone")` | 32,807 | **8,201** |

≈ **10,000 tokens before a single question is answered.** In the real session that
produced the field report, **3 of 51** returned drawers were used. Every one is
truncated, so the payload cannot answer anything — it is pure routing.

The same audit listed **operator-owned holdout eval hooks** in that same v1.2 core
list. *Measured:* `grep -ril holdout src/cairntir/` returns **0 files**. The
CodeGlass recovery plan still reads *"holdout evaluation pending."*

So the sequence is:

1. BabyTIEROS had the discipline.
2. It was lost in the distillation.
3. A careful audit correctly diagnosed the loss on 2026-07-27 and wrote the fix
   into the release plan.
4. The release shipped. The fix did not.
5. On 2026-08-02 Patrick independently rediscovered the same idea and wrote the
   **Token Saver** specification.

**Patrick's Token Saver spec is the third independent rediscovery of the founding
invariant of his own lineage.** That is the strongest argument in this document
for treating it as core rather than as an optimisation.

---

## Part 0 — Inception: the four ancestors

### BabyTIEROS (earliest surviving artifacts, collected 2026-03-28)

An AI-assisted development *methodology and scaffold*, not a memory engine. Ten
durable project documents as externalised context, plus:

1. five-tier model routing with escalation;
2. spec-before-code with explicit out-of-scope boundaries;
3. chunk decomposition with completion gates;
4. human approval for risky operations;
5. structured session handoffs;
6. **human-only sniff tests agents could not optimise against** (`SNIFFTEST.md`);
7. decision logs, debt trackers, performance contracts, lessons learned.

**Judgement:** the ten-doc scaffold is where `CLAUDE.md` and `AGENTS.md` come
from — including the "update every session" header still at the top of both today.
Three ideas here are still unmatched by anything Cairntir ships: the load policy,
the hidden holdout, and typed human-approval checkpoints.

### BrainStormer (`C:\Dev\SKILLS\BrainStormer\`)

Absorbed BabyTIEROS as its **Kernel** and added the vocabulary Cairntir kept —
Crucible, Quality/PALADIN, ETHOS, agent species, severity tiers — on a runtime
that did not work. Its own `HARNESS_AUDIT.md` (2026-04-03) is the most useful
document in the whole lineage:

> **0 of 12 primitives fully implemented without caveats.** … BrainStormer builds
> excellent infrastructure but **does not wire the enforcement layer.**

Scored: 1 MISSING (**P5 token/cost tracking**, risk HIGH), 2 advisory-only
(permissions, agent species), 7 partial, 2 implemented. Six ledgers defined,
three never written to. A licence system gating 1 of 20+ commands. A species
taxonomy that filtered nothing.

### brainstormer-agents (`C:\Dev\brainstormer-agents`)

**372 agent definitions**, markdown with YAML frontmatter, original IP, installed
by dropping into `~/.claude/agents/`. *Measured: 372 files.*

**Judgement — and this is a genuine strategic finding.** Patrick built a portable
capability library in exactly the shape the industry then standardised on:
markdown + frontmatter, filesystem-installed, progressively loaded. Agent Skills
became an open standard at agentskills.io in December 2025 and is now implemented
by roughly 40 clients including Copilot, Cursor, Codex, Gemini CLI and VS Code
(*sourced*). The evolution audit's ruling — *"agent catalogs/species: correct
removal; orchestration belongs to the host"* — was right, and it is now **more**
right, because the host layer became a real standard. The forward move is not to
put agents back into Cairntir. It is that Cairntir becomes **the memory the
installed skills write to and read from.** See candidate 7.

### CodeGlass (`C:\Dev\codeglass-dist`, `codeglass-site`, `src/cairntir/codeglass.py`)

Built for a specific reader: Patrick and other builders who ship useful software
without formal CS training and need unfamiliar code turned into durable
understanding.

The audit's forensic verdict is unusually honest and worth preserving verbatim in
spirit: **the concept succeeded, the generator did not.** Good walkthroughs exist
in Anthropicer; BrainStormer's executable `learn walkthrough --from-diff` extracted
a commit subject, changed filenames and regex'd function names, and left WHY as a
placeholder. *"The good walkthroughs must not be treated as proof that the
generator produced them."*

Current state: core protocol implemented in Cairntir (record / teachback /
retention), **evidence automation and holdout evaluation pending.**

### The through-line

| | BabyTIEROS | BrainStormer | Cairntir |
|---|---|---|---|
| Context control | always / relevant / never | hot-warm assembler + token estimate | 4 layers, **no budget** |
| Stress-testing | escalation checkpoints | Crucible | Crucible ✅ distilled well |
| Ship gate | chunk gates + hidden sniff test | PALADIN | Quality — **holdout lost** |
| Handoff | explicit checklist | wrapup → init | daemon + session_start — **completeness receipt lost** |
| Learning | lessons learned | ledgers (½ empty) | prediction drawers — **0 ever written** |
| Teaching | architecture docs | CodeGlass (half-built) | CodeGlass recipe — evidence automation pending |
| Capability library | tier/skill registry | 571-agent catalog → 372 shipped | removed ✅ correct |

---

## Part 1 — The unbuilt backlog

**From `docs/roadmap.md` (committed 2026-04-14), never started:** v1.4 file-based
team sync; v1.6 Agent Memory (per-skill `agent:` wings); v2.0.0 distribution split;
local-AI proposer (Gemma via Ollama); `SandboxRunner`; cross-wing
`timeline --entity X`; per-wing belief-mass comparison; Codebase Autopsy and
Vendor Drift recipes.

**From the 2026-07-27 evolution audit, committed to the v1.2 core, not landed:**
explicit context budgets (*verified absent*); operator-owned holdout evals
(*verified absent*); typed operational receipts for failures and routing;
capture-completeness signals.

**Deliberately cut, and correctly so:** team-memory CRDTs, triple store, hosted
SaaS, agent marketplace, model-tier routing, licensing, telemetry, generic
scaffolding, ideation/design skills, agent execution runtime. Every one of these
should stay cut. The "this could live on a USB stick" test is the strongest
constraint the project has.

---

## Part 2 — The external landscape, August 2026

### Dedicated memory systems *(all sourced)*

- **Letta** (ex-MemGPT) — memory as an operating system: main context as RAM,
  recall store, archival store, with the model paging via function calls. The
  self-editing idea has no Cairntir equivalent; layers are set at write time and
  only demoted by a staleness pass.
- **Zep / Graphiti** — temporally-aware knowledge graph on Neo4j. Cairntir's
  `supersedes_id` + `as_of` are a lighter, dependency-free answer. **Zep is the
  better fit** for anyone wanting entity resolution and graph traversal; Cairntir
  refused that infrastructure deliberately and should keep refusing it.
- **Mem0** — fact extraction with a two-phase pipeline including **conflict
  detection at write time**. Cairntir has `detect_contradictions` but runs it as a
  batch pass, never at the moment of writing. That is the borrowable concept.

### Context engineering became the discipline *(all sourced)*

- **Progressive disclosure** is the organising principle: load metadata first,
  pull detail only when relevant.
- **Context rot** — accuracy degrades as context grows *even when every relevant
  fact is present*; reported degradations span 13.9–85%.
- **Token usage explains ~80% of performance variance** on agent evaluations —
  a larger lever than model selection.
- **Compaction** and **sub-agent context isolation** (subagents returning
  1–2k-token summaries) are standard practice.

### MCP moved — spec 2026-07-28 *(sourced)*

Cairntir *is* an MCP server, so this is the most directly actionable section.

- **Sampling** — a server can request an LLM completion **from the client**. The
  client owns model selection; the server never sees an API key. Advisory
  `costPriority` / `speedPriority` / `intelligencePriority` hints.
- **Elicitation** — structured user input with accept / decline / cancel.
- **Cacheable list results** — cache hints and deterministic ordering so clients
  can cache tool catalogs and keep upstream prompt caches stable.
- Stateless core, Multi Round-Trip Requests, formal extensions framework,
  12-month deprecation policy.

### Benchmarks *(sourced)*

LoCoMo, LongMemEval and **BEAM** are the three memory benchmarks proper. The older
two are criticised in 2026 for modest context lengths, synthetic dialogue, and —
for LoCoMo — not explicitly scoring knowledge updates. **BEAM** runs at 1M and 10M
token scale, targeting what a bigger context window cannot solve.
**LongMemEval-V2** exists, built from web-agent trajectories.

---

## Part 3 — Blind spots

**1. One failure mode, inherited and now four generations deep.** BrainStormer's
audit named it: *infrastructure without the enforcement layer.* It recurred today,
three times in one codebase — anchors validated nowhere, 0 predictions ever
written, a repair tool that could not repair. And it recurred at the level of the
*recovery plan itself*: the audit that diagnosed the regression shipped a release
that did not fix it. **The pattern is not "we build badly." It is "we do not
verify that a commitment landed."**

**2. Cairntir is currently a context-rot generator.** ~10k fixed tokens, ~6%
observed utilisation, everything truncated. The tool built to fight amnesia
spends its budget on material that provably degrades the model reading it.

**3. The calibration system is uncalibrated.** `cairntir calibration` reports
0 predictions, 0 resolved, 0 confirmed/failed. Cairntir asks its users to be
falsifiable and has never been falsifiable about itself.

**4. It gates CI on the axis where it is ordinary.** LongMemEval R@5 is the gate.
Cairntir's real differentiator is `supersedes_id` — *knowledge update over time* —
which is precisely what 2026 criticism says these benchmarks under-score.

**5. Agents can read every test.** BabyTIEROS hid `SNIFFTEST.md` from the
implementing agent. Today's agents inspect and optimise against anything in
context, which makes hidden holdouts *more* necessary, not less — and there are
zero in the source.

**6. Lineage awareness stopped.** Letta, Zep, Mem0 and the MCP spec have all moved
substantially and appear nowhere in the repo. There is no standing mechanism to
notice. This is the gap Patrick named directly.

**7. The tool's own deployment is unmonitored.** Found today: the maintainer's
install is editable, so whatever branch is checked out is what every AI host runs,
and a partially-failed `pip install -e .` left the package unimportable with no
check anywhere that would have caught it.

---

## Part 4 — Token Saver, in lineage terms

Structurally, Patrick's Token Saver spec is **three things at once**:

- **P5** from the 2026-04-03 harness audit — the one primitive scored MISSING, at
  HIGH risk, deferred with "until cost becomes a real concern";
- **BabyTIEROS's always/relevant/never policy**, restated in modern terms;
- the **v1.2 context-budget commitment** that was written down and never landed.

Three independent lines say the deferral has expired: token usage explains ~80% of
performance variance (*sourced*); context rot degrades accuracy even when nothing
relevant is missing (*sourced*); Cairntir's own fixed session cost is ~10k tokens
at ~6% utilisation (*measured*).

Its own framing — *"Token reduction is subordinate to correctness. Do not omit
material that could materially alter the result"* — matches the ethos exactly, and
its Safety Boundary section is what makes it adoptable without weakening the
verbatim floor. **The verbatim floor governs what is stored; Token Saver governs
what is loaded.** They do not conflict.

| Token Saver clause | Cairntir surface |
|---|---|
| smallest sufficient context | `session_start` — candidate 1 |
| load only tools the job can use | 18-tool catalog — candidate 6 |
| deterministic tools for exact work | already true; `recall_for_change` is the model case |
| compact canonical task state | `cairntir_handoff` — candidate 1 |
| clean stage handoffs | the R-00 → G0 phase template Patrick wants reusable |
| never repeat a failed approach | **nothing in Cairntir records failed approaches as first-class** |
| unnecessary output becomes input later | the single best argument against today's `session_start` |

**Judgement:** adopt as **written policy plus measurement**, not as an automatic
optimiser. Today proved that a contract nobody reads changes nothing — so it
belongs in tool descriptions and a budget, not in a doc.

---

## The 10 candidates

Each states what it displaces, because the identity is distillation.

### 1. `cairntir_handoff(wing)` — one call, one composed brief, hard budget
Replace `session_start → recall → get` with a single bounded brief: active work
item, last N session deltas **in full text**, open questions, anchors for files in
play, operating protocol. No ranking involved. **Lineage:** restores BabyTIEROS's
load policy and the v1.2 budget commitment simultaneously. **Why now:** measured
~10k/6%. **Cost:** low — composition over existing data. **Displaces:**
`HANDOFF.md`, and the reason Patrick still needs one.

### 2. Token and context accounting — close P5 at last
Per-tool token receipts, a `cairntir cost` view, and a budget the brief must fit
inside. **Lineage:** the only primitive the 2026-04-03 audit scored MISSING.
**Why now:** its own deferral condition — "until cost becomes a real concern" — is
met three ways. **Cost:** medium. **Displaces:** guesswork, including mine; every
number in Part 3 had to be measured by hand because nothing reports it.

### 3. A landed-commitment check — the anti-pattern killer
The blind spot in Part 3 #1 is worth its own mechanism: when a plan says "restore
X in v1.2," something should fail if v1.2 ships without X. Concretely: plan
documents carry checkable assertions (a symbol exists, a parameter exists, a test
exists), and a CI script verifies them the way `check_release_tags.py` already
verifies that changelogged versions were tagged. **Lineage:** this is the one
defect present in *all four* generations. **Why now:** the precedent already
exists in-repo and works. **Cost:** low. **Displaces:** the need to rediscover the
same regression a fourth time.

### 4. MCP **elicitation** to close the prediction gap
0 predictions in the entire corpus because nothing ever asks. Elicitation asks the
user in-flow when a decision is recorded, with a clean decline path.
**Lineage:** BabyTIEROS's human-approval checkpoints, in modern protocol form.
**Cost:** low. **Displaces:** the assumption that agents volunteer falsifiable
claims. They do not.

### 5. MCP **sampling** for the Reason loop
The new spec lets a server request a completion from the client — making the
long-deferred production Reason loop possible with **no API key, no billed call,
no telemetry**, client-owned model choice. **Why now:** it did not exist when the
roadmap was written. **Cost:** medium, gated on client support. **Displaces:**
both the ClaudeProposer plan *and* the local-Gemma proposer.

### 6. Cacheable, progressively-disclosed tool catalog
1,918 measured tokens of tool definitions in every session in every host. The new
spec adds cache hints and deterministic ordering; the ecosystem has moved to
loading schemas on demand. **Cost:** low-medium. **Displaces:** the assumption
that "18 tools" is free.

### 7. Agent Memory (v1.6) — pointed at the Agent Skills ecosystem
Per-skill wings under an `agent:` prefix. Crucible recalls assumptions already
stress-tested; Quality learns which shapes earn ship-it; Reason records which
rabbit holes paid — which is also the *"critical failed approaches that must not
be repeated"* slot Token Saver asks for and Cairntir has nowhere to put.
**Lineage + horizon:** the 372-agent library was correctly removed from the core,
and the host layer has since become a real standard across ~40 clients. Cairntir
should be **the memory those skills write to**, not a catalog. **Cost:** medium.
**Displaces:** nothing; always planned.

### 8. Operator-owned holdout evals
A small suite the implementing agent never sees, covering cold-start continuity,
stale-memory rejection, poisoning, scope isolation and recovery. **Lineage:**
BabyTIEROS's `SNIFFTEST.md`, and the v1.2 commitment verified absent today.
**Why now:** agents optimise against every visible test; this is the only category
of test that stays honest. **Cost:** medium. **Displaces:** the belief that a
green suite means the memory works.

### 9. Fix the benchmark mismatch
Keep LongMemEval R@5 as a regression gate; add a **knowledge-update** measure over
`supersedes_id` chains; treat BEAM-style scale as an aspiration, not a gate.
**Cost:** medium. **Displaces:** the belief that green R@5 means good memory.

### 10. A standing mechanism for staying current
Point the existing **Signal Reader** recipe at Cairntir's own landscape — MCP spec
releases, Letta/Zep/Mem0, benchmark shifts — on a schedule, writing
prediction-bound drawers with resolution dates. **Why now:** Patrick asked for
bleeding-edge *as a priority*, which means a loop, not a survey; this document
starts decaying immediately. **Cost:** low — a recipe, not a feature.
**Displaces:** ever needing to commission this research again.

---

## If only three

**1, 2 and 3.** One fixes what Patrick asked for and is the largest measured
waste. Two makes Cairntir able to see itself, which is the gap behind every blind
spot. Three is the only candidate that addresses the defect present in all four
generations — and without it, one and two are just the next commitments to
quietly not land.

Four is the cheapest real win. Five and six have the highest ceiling but both
depend on client support that should be verified before either is scoped.

---

## Attribution

Per `plans/next-map.md` and drawer #175: concepts never code; a lineage doc before
a line of code that credits a source; credit by name; never restate their
benchmarks as ours; never position as "better than"; say plainly when their tool
is the better fit.

Nothing here is adopted. If Letta's paging model, Zep/Graphiti's temporal graph,
or Mem0's write-time conflict detection is taken up, a lineage doc comes first.
Said plainly: **Zep is the better fit** for anyone wanting entity resolution and
graph traversal, and Cairntir should keep refusing that infrastructure.

**Sources:** [Anthropic — Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills) ·
[Anthropic — Effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) ·
[MCP 2026-07-28 specification](https://blog.modelcontextprotocol.io/posts/2026-07-28/) ·
[MCP 2026 spec changes](https://stacktr.ee/blog/mcp-2026-spec-changes) ·
[Claude Cookbook — memory, compaction, tool clearing](https://platform.claude.com/cookbook/tool-use-context-engineering-context-engineering-tools) ·
[Context Engineering: Agent Reliability Playbook 2026](https://www.digitalapplied.com/blog/context-engineering-agent-reliability-playbook-2026) ·
[Best AI Agent Memory Frameworks 2026](https://atlan.com/know/best-ai-agent-memory-frameworks-2026/) ·
[Best AI Agent Memory Systems in 2026](https://vectorize.io/articles/best-ai-agent-memory-systems) ·
[AI Memory Benchmarks 2026 — LoCoMo, LongMemEval, BEAM](https://mem0.ai/blog/ai-memory-benchmarks-in-2026) ·
[Agent Memory Benchmarks 2026: The Real Numbers](https://memnode.dev/articles/agent-memory-benchmarks-2026-real-numbers) ·
[LongMemEval-V2](https://arxiv.org/html/2605.12493v1)

**In-repo evidence:** `docs/lineage/evolution-audit-2026-07-27.md` ·
`docs/lineage/babytieros.md` · `HARNESS_AUDIT.md` · `docs/roadmap.md` ·
`plans/codeglass-recovery.md` · `plans/field-report-2026-08-02.md`
