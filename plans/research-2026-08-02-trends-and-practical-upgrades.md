# Cairntir — moving trends, new models, and practical upgrades

**Date:** 2026-08-02 · **Status:** research only. Nothing here is committed.
**Companion to:** `plans/research-2026-08-02-upgrade-candidates.md` (the past half).
This is the other side of the coin: what is moving *now*, what the new models
change, and concrete practical upgrades.

**Evidence standard:** **Measured** = produced on this machine today, reproduction
given. **Sourced** = third-party, attributed, not independently verified, never
restated as ours. **Judgement** = my reading.

---

## The design objective, stated correctly

Patrick, 2026-08-02, verbatim and load-bearing:

> *"BECAUSE you truncate SO MUCH.. cairntir is supposed to correct that.. not be
> part of that problem. i know its an issue, thats one of he reasons i created
> cairntir. to help get more out of the $20 models, us poor folks can afford."*

This is not a cost-optimisation brief. It is **budget-constrained maximisation**:
a hard monthly ceiling, and the goal is the most useful work underneath it. Those
are different objective functions and they select different designs. Minimising
tokens would say "send less." Maximising work under a cap says **"never spend a
token on something that carries no information"** — which is a far harsher test,
and the one Cairntir currently fails.

### Truncation is the anti-pattern, and Cairntir does it in three places

Truncation is the worst available option because it **pays the full token cost and
destroys the information anyway**. Compression, chunking, and progressive
disclosure all beat it. Measured today, Cairntir truncates:

| Where | What is lost | Measured |
|---|---|---|
| `session_start` output | drawer content cut to 100-char snippets | 51 stubs, ~7,737 tokens, **0 of them answerable** |
| the embedder | everything past 512 tokens is never vectorised | **43% of drawers** affected, worst case 24% embedded |
| `recall` results | truncated stubs, forcing a second `get` call | pure routing cost |

The tool built to stop AI from losing information loses information at every one
of its three main surfaces — and charges ~10,000 tokens for the privilege.

**Judgement.** This is the sharpest possible statement of the field report's
findings 2 and 3, and it reframes the fix. The goal is not a smaller
`session_start`. It is a `session_start` where **every token returned is one the
model can actually use** — fewer drawers, whole, in reading order, instead of 51
headlines that answer nothing. That is candidate 1 in the companion document, and
this framing is the argument for it.

The industry moved the same way and further: the ecosystem's answer to too much
context is now **reversible compression** and **progressive disclosure**, not
truncation. See the tools section below.

---

## The single most actionable finding

**Cairntir's embedding model cannot read 43% of its own corpus.**

*Measured.* Cairntir embeds with `sentence-transformers/all-MiniLM-L6-v2`
(`src/cairntir/memory/embeddings.py:115`) — 384 dimensions, **512-token hard
limit**, roughly 2,048 characters.

Against the live store, 212 drawers:

| | chars |
|---|---|
| median drawer | 1,613 |
| p75 | 3,525 |
| p90 | 4,828 |
| longest | 8,390 |

**93 of 212 drawers (43%) exceed the embedder's window.** Of those, the median is
3,695 characters ≈ 924 tokens — nearly double the limit. The longest drawer has
**24% of its content embedded** and 76% invisible to semantic search.

Reproduce:
```
SELECT length(content) FROM drawers;   -- vs 512 tokens ≈ 2048 chars
```

**Correction to my own hypothesis.** I expected this to explain the field
report's finding 3 outright — the ADR-0013 drawer (#197) that ranked 7th. It does
not, quite. #197 is 3,539 characters, 57% embedded, and the decisive terms *are*
inside the window (`GDScript` first at char 335, `Godot` at 459). What is lost is
**frequency**: 6 of 10 `GDScript` mentions and 9 of 15 `Godot` mentions fall
outside. So truncation **dilutes** the signal rather than erasing it here. The 43%
figure stands; the stronger claim does not, and finding 3's drawer-size hypothesis
is still live.

**Judgement:** this reorders the finding-3 work. The field report proposed one
experiment (split a drawer, re-rank). There are now **two independent causes** to
separate — drawer size *and* embedder truncation — and the second is a config
change, not research.

---

## New models — the map, August 2026 *(all sourced)*

| | context | price /1M in-out | note |
|---|---|---|---|
| **Claude Opus 5** (rel. 2026-07-24) | — | $5 / $25 | top of Artificial Analysis Intelligence Index (61) **and** Agentic Index (55.3) |
| Claude Opus 4.8 | 1M | — | long agentic reasoning chains |
| Gemini 3.1 Pro | **2M** | $5 / $20 | price-to-performance leader; the practical pick when the problem includes diagrams or documents |
| GPT-5.x | 200K | $20 / $80 | |

**What actually changes for Cairntir:** less than it looks.

1. **Context abundance is a trap, not a solution.** 1M–2M windows coexist with
   *context rot* — accuracy degrading as context grows even when every relevant
   fact is present, at reported 13.9–85% (*sourced*). A bigger window is not
   permission to send more. **The handoff should get tighter as windows get
   larger, not looser.**
2. **Agentic ranking is now a published axis.** Cairntir's whole value shows up in
   long agentic chains, which is exactly what the Agentic Index measures. That is
   the benchmark family worth watching, not general intelligence scores.
3. **Cairntir records `model: "unknown"` on every drawer.** *Measured* — visible
   in every provenance record in `session_start` output. Host is captured; model
   is not. The 2026-07-27 evolution audit already asked for this: *"record
   model/agent identity, latency, cost, task type, result, and operator verdict.
   A host can then route using evidence. Cairntir should not become the router."*
   That remains exactly right, and it remains unbuilt.

---

## Embedding models — where Cairntir is furthest behind *(sourced)*

| model | MTEB | size | context | licence |
|---|---|---|---|---|
| Gemini Embedding 001 | 68.32 (Eng) | API | — | commercial |
| Qwen3-Embedding-8B | 70.58 (multiling.) | 4.7 GB Q4 | — | Apache-2.0 |
| **Qwen3-Embedding-0.6B** | **70.7 (Eng v2)** | **639 MB** | — | **Apache-2.0, Ollama-native** |
| nomic-embed-text | — | 274 MB | **8,192 tok** | Matryoshka dimension reduction |
| EmbeddingGemma | — | 622 MB | — | |
| **all-MiniLM-L6-v2 (current)** | — | **46 MB** | **512 tok** | 22M params |

*Note: MTEB v2 scores are not comparable to v1; rankings differ across boards.*

**Judgement.** Two candidates fit Cairntir's constraints, and they solve different
problems:

- **nomic-embed-text** — the direct fix for the 43%. An 8,192-token window covers
  every drawer in the store with room to spare, and Matryoshka truncation lets the
  vector stay small so storage and the `vec0` table barely move.
- **Qwen3-Embedding-0.6B** — the quality play, described as best
  quality-per-VRAM, Apache-2.0, one `ollama pull`.

Both are heavier than 46 MB, which collides directly with the cold-start arc that
took five patch releases to fix (1.1.0 → 1.1.3, ~12 min → 1.4s). **That history is
the binding constraint on this decision, not the MTEB score.**

Two things make this less risky than it sounds: Cairntir already has a verified
reindex path with an `embedding_space_id` guard that fails closed on mismatch, and
that path has been exercised on the live store before (123 drawers, byte-identical,
generation-verified). The machinery for exactly this change already exists.

---

## Prompt caching — the cost half of the token problem *(sourced)*

- Anthropic: cache **writes cost 1.25×** normal input, **reads cost 10%** — a 90%
  discount. Default TTL 5 minutes, 1-hour option at a higher write rate.
- Order content **most-stable → least-stable**: tool definitions, system prompt,
  reference docs, conversation history, live query. **Any change to a block
  invalidates that block and everything after it.**
- Reported impact: 41–80% cost reduction, time-to-first-token 13–31% better.
- ProjectDiscovery moved dynamic working memory out of the system prompt to the
  end and took cache hit rate from **7% → 84%**, cutting LLM cost 59%.

**Measured, and it is good news:** `session_start` is **deterministic**. Two
consecutive calls hash identically (`88ea6c63c894379f`). Cairntir is not poisoning
the host's cache today.

**The nuance that matters most.** Caching makes the ~10,000-token session-start
payload *cheap*. It does not make it *harmless*. Cached tokens are still read by
the model, and context rot is a function of what is in the window, not what it
cost. **Caching solves the money; it does not solve the rot.** Anyone arguing "we
cache it, so the size is fine" is answering the wrong objection.

---

## Local models — the roadmap's pick has aged *(sourced)*

`docs/roadmap.md` specifies "Gemma 4 via llama.cpp or Ollama" for the local
`HypothesisProposer`, written 2026-04. As of August 2026:

- **Qwen3** (8B / 14B / 30B) is the default answer for local work; Qwen3.6 shipped
  a 27B dense coding model beating a 397B MoE on SWE-bench.
- **Gemma 4** is the best all-rounder — multimodal, tool use, Apache-2.0.
- **Devstral** targets multi-file edits and autonomous tasks.
- For agent work specifically, select on function calling, long context, structured
  output, instruction following, and recovery after a failed first plan. DeepSeek
  is noted as less steady than Qwen for strict XML tool-calling schemas.

**Judgement:** do not re-pick yet. **MCP sampling** (candidate 5 in the companion
document) may make the whole local-proposer branch unnecessary — it gets a
frontier model through the client with no API key, no telemetry, and no local
weights to ship. Verify client support first; if it lands, this roadmap item
should be retired rather than updated.

---

## Agentic trends worth tracking *(sourced)*

- **Background agents.** Microsoft moved Copilot from a sidebar assistant to a
  fleet of autonomous background agents across M365, surfacing only for final
  approvals. The interaction model is shifting from "assistant in a chat" to
  "worker that reports."
- **Guardian agents** — agents that monitor other agents in real time for
  compliance violations, hallucination, and **scope drift**, checking actions stay
  inside approved boundaries before they reach production.
- **Governed, gradual autonomy** is the stated production lesson: autonomy works
  when introduced incrementally and governed, not applied everywhere at once.
  *"The question is no longer capability, it's control."*
- Gartner projects 40% of enterprise applications will include task-specific
  agents by 2026, up from under 5% in 2025.

**Judgement — the strategic read.** Background agents make Cairntir *more*
necessary and *more* exposed. More necessary because an agent working while nobody
watches has no human to re-brief it; the handoff **is** the interface. More exposed
because Cairntir's poisoned-memory boundary — JSON-encoded evidence with
`instruction_authority=none` — is already a guardian-agent primitive, and it was
built before the category had a name. That is a genuine position, and it is
currently undocumented as one.

---

## Fast-moving repos and the token-economy ecosystem *(all sourced)*

### Where the gravity is

OpenClaw is the breakout of 2026 and reportedly the fastest-growing open-source
project in GitHub history — 9,000 to 60,000 stars in days after going viral in
late January, now past 210,000. Current leaders by stars: **OpenClaw 210K,
Ollama 162K, n8n 150K, Dify 130K, LangChain 126K, Gemini CLI 99K, Browser Use 84K,
AutoGen 54K, LlamaIndex 47K, CrewAI 44K.** MCP is described as the de facto
protocol for agent-tool connections.

**AgentMemory** is worth naming directly: a persistent knowledge layer built to
carry context across runs — the same problem statement as Cairntir. It should get
a lineage assessment before anything is borrowed, per the attribution contract.

### The token-economy tool ecosystem — an entire category exists now

This did not exist when Cairntir's roadmap was written, and it is squarely on
Patrick's `$20` objective:

| Tool | What it does | Claim |
|---|---|---|
| **Headroom** | drop-in compression for tool outputs, logs, files, RAG chunks; ships as library, proxy **and MCP server**; **reversible** | 60–95% fewer tokens |
| **Caveman** | Claude Code skill rewriting verbose agent responses into terse output | ~65% output reduction |
| **Tokalator** | context-engineering toolkit: VS Code extension with **real-time budget monitoring**, calculators, MCP server | — |
| **LiteLLM** | model gateway routing simple subtasks to cheaper models | — |
| **Continue.dev** | `@codebase` embedding retrieval, pulls only relevant context | — |
| **AnythingLLM** | local RAG over codebases and docs | — |
| Claude API **context compaction** (`compact-2026-01-12` header) | server-side conversation-history condensation | one case: 132,000 → 2,000 tokens |

**Judgement, and it cuts both ways.**

*The honest part.* **Headroom overlaps with anything Cairntir might build as a
generic compressor, and does it better** — reversible compression as a proxy and
MCP server is a real engineering surface Cairntir has no reason to duplicate. Per
the attribution contract's "say plainly when their tool is the better fit":
**if the need is compressing tool output and logs, use Headroom, not Cairntir.**
Likewise Tokalator already does live budget monitoring; candidate 2 (token
accounting) should measure *Cairntir's own* payload, not become a general
token dashboard.

*The part that is Cairntir's.* None of these tools know **what mattered last
week**. Compression shrinks what you already decided to send; Cairntir's job is
deciding what to send in the first place, from persistent memory, across sessions
and hosts. That is upstream of every tool in the table, and it is uncontested by
them. Cairntir should **compose with this ecosystem, not compete with it** — which
also means the reversible-compression pattern is the right model for
`session_start`, and truncation is the wrong one.

*The immediately usable part.* On a $20 plan, `compact-2026-01-12`, prompt caching
at a 90% read discount, and Caveman are available today and independent of any
Cairntir work.

---

## Practical upgrades — ordered by value per unit of work

These are tactical and mostly small. The ten strategic candidates live in the
companion document; these are the things worth doing regardless of which of those
are chosen.

**1. Run the embedder bake-off.** nomic-embed-text and Qwen3-Embedding-0.6B
against all-MiniLM, on the real store, scoring (a) the field report's exact query
where the answer ranked 7th, (b) LongMemEval R@5, (c) **cold-start time**, which
is the constraint that actually decides it. Cheap, decisive, and the reindex path
already exists and is proven.

**2. Separate the two causes of bad ranking before changing anything.** Split one
long drawer into single-topic drawers *and* re-embed with a long-context model, as
two independent arms. Right now finding 3 has two plausible causes and no
experiment distinguishing them.

**3. Add a determinism test on `session_start`.** It is cacheable today —
*measured* — and nothing guarantees it stays that way. One assertion on a stable
hash protects a 90% input discount for every user, in every host, forever. This is
the cheapest item on the list.

**4. Record the model, not just the host.** Every drawer says `model: "unknown"`.
Without it Cairntir can never answer "which model's memories actually get used?",
which is the evidence a host would need to route well. Capture where hosts expose
it; record `unknown` honestly where they do not, as now.

**5. Chunk long drawers at embed time.** A fallback for the 43% that survives
whatever the model decision is: index long drawers as several vectors and keep the
drawer verbatim and whole. The verbatim floor governs storage; nothing requires one
vector per drawer.

**6. Write the guardian-agent position down.** The poisoned-memory boundary
predates the category. A short architecture note in `docs/architecture/` costs an
hour and makes an existing strength legible.

**7. Retire, don't update, the local-proposer roadmap entry** — pending an MCP
sampling check. Leaving a stale 2026-04 model pick in a committed roadmap is how
`AGENTS.md` drifted.

**8. Watch the Agentic Index, not the intelligence leaderboards.** Cairntir's value
appears in long agentic chains. That is the axis that maps to the product, and it
is now published.

**9. Replace truncation with whole drawers, fewer of them.** The direct answer to
the design objective. `session_start` currently returns 51 stubs at 100 characters
each: full token cost, zero answerable content. Returning **3–5 complete drawers
in reading order** would cost less *and* carry information, which is the only
version of "cheaper" that is also "better." This is candidate 1 restated as a
rule: **never return a token the model cannot use.**

**10. Assess `AgentMemory`, and write the lineage doc first.** It targets
Cairntir's exact problem statement and post-dates every lineage document in the
repo. The contract requires the assessment before any borrowing, and drawer #173's
standard — read the source before characterising it — applies.

**11. Adopt the ecosystem instead of rebuilding it.** Use `compact-2026-01-12`,
prompt caching, and Headroom-style reversible compression where they fit rather
than growing Cairntir's surface. Every one of these is free on a $20 plan today.

---

## What has *not* changed, and should not

The local-first, USB-stick-portable, no-server, MIT position is **more**
differentiated in August 2026 than it was in April, not less. Every dedicated
memory system surveyed in the companion document is a hosted service. Nothing in
this research argues for a server, a cloud tier, or a hosted sync. Every practical
upgrade above survives being carried around on a memory stick.

**Sources:** [Best AI Models in August 2026](https://felloai.com/best-ai-models/) ·
[LM Council model benchmarks](https://lmcouncil.ai/benchmarks) ·
[Frontier models 2026](https://www.promptquorum.com/blog/frontier-models-prompt-library) ·
[Embedding Models 2026 benchmark](https://app.ailog.fr/en/blog/news/embedding-models-2026) ·
[Best Ollama embedding models 2026](https://www.morphllm.com/ollama-embedding-models) ·
[Open-source embedding models guide](https://www.bentoml.com/blog/a-guide-to-open-source-embedding-models) ·
[Prompt caching — Claude Platform Docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) ·
[Prompt Caching in 2026: real cost wins](https://technspire.com/en/blog/prompt-caching-2026-real-cost-wins) ·
[Prompt caching engineering guide](https://www.digitalapplied.com/blog/prompt-caching-2026-cut-llm-costs-engineering-guide) ·
[Don't Break the Cache (arXiv)](https://arxiv.org/pdf/2601.06007) ·
[Best local LLMs 2026](https://huggingface.co/blog/daya-shankar/open-source-llm-models-to-run-locally) ·
[Gemma 4 vs Qwen 3.5](https://www.mindstudio.ai/blog/gemma-4-vs-qwen-3-5-open-weight-comparison) ·
[7 Agentic AI trends 2026](https://machinelearningmastery.com/7-agentic-ai-trends-to-watch-in-2026/) ·
[Agentic AI trends — enterprise](https://www.cloudkeeper.com/insights/blog/top-agentic-ai-trends-watch-2026-how-ai-agents-are-redefining-enterprise-automation)
