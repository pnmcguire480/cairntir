---
name: reason
description: >
  Memory-backed thinking loop. Reason is the skill that replaces "just
  answer" with a disciplined pass through Cairntir's memory before any
  conclusion is offered. Always starts by loading the wing's context,
  recalls relevant drawers, thinks out loud with citations, flags
  load-bearing assumptions for Crucible, and writes the result back as a
  drawer so the next session inherits it.

  Trigger on: "think about this", "what do we know about",
  "reason through this", "work this out", "use memory".
---

# REASON — Memory-Backed Thinking

## The Principle

**Opinions without memory are hallucinations on schedule.** Reason is the
discipline of grounding every claim in a drawer id or explicitly labeling
it as a new assumption. It is the behavior that earns the word "remember"
in Cairntir's name.

Reason is not a new tool — it is a loop that composes the tools Cairntir
already has:

```
session_start → recall → think → crucible? → remember → answer
```

Every step is mandatory for non-trivial questions. For trivial ones
(single-fact recall, syntax checks) skip to `recall → answer`.

---

## THE LOOP

### Step 1 — session_start

Call `cairntir_session_start(wing=<current>)`. This loads:

- Identity drawers (who, how they work, the North Star)
- Essential drawers (current wing state)

Read them before writing anything. If the identity or essential layer
comes back empty and the question depends on context, **stop and ask**
whether this is a new wing or a memory-store problem. Do not guess.

### Step 2 — recall

Call `cairntir_recall(query=<the user's question>, wing=<current>)`.

Inspect the top hits. For each, decide:

- **Cite it** — it's directly relevant. Note the drawer id.
- **Note it** — it's adjacent context worth keeping in mind.
- **Discard it** — it's a false positive from semantic search.

If recall returns nothing and the question is not trivial, widen the
query (drop the wing filter, try synonyms) before concluding memory is
empty. Only *then* is it legitimate to reason from scratch — and the fact
that memory was empty is itself a drawer worth writing.

### Step 3 — think, out loud, with citations

Compose the answer in the open, with drawer ids inline:

```
Based on #12 (the Phase-1 decision to use sqlite-vec) and #27 (the Phase-2
MCP tool list), the recall tool should scope to the active wing by default
because #12 locked in wing/room/drawer as the primary index.
```

Claims without a citation are fine — but they must be **labeled** as new
assumptions, not smuggled in as remembered fact:

```
[ASSUMPTION] The daemon process will run as the same user as Claude Code.
No drawer covers this; it needs verification before Phase 4.
```

### Step 4 — crucible? (conditional)

If the answer depends on a load-bearing assumption, invoke
`cairntir_crucible(claim=<the assumption>)` before committing to it. A
load-bearing assumption is any claim where being wrong would undo the
plan. If Reason can't tell whether it's load-bearing, it is.

### Step 5 — remember

Write the conclusion back as a drawer so the next session inherits it:

```
cairntir_remember(
  wing=<current>,
  room=<topic>,
  content=<the conclusion, verbatim, with cited drawer ids>,
  layer="on_demand",  # or "essential" if it changes the wing's state
  metadata={"source": "reason", "cited": [12, 27]},
)
```

### Step 6 — answer

Present the conclusion to the user. The drawer id from Step 5 is the
receipt. The answer text should not repeat the full loop — just the
conclusion plus a one-line "reasoning path" summary with cited drawers.

---

## WHEN NOT TO USE REASON

Skip the loop for:

- **Pure syntax questions** — "what's the ruff flag for..." — recall is fine.
- **Tool mechanics** — "what does `cairntir_recall` return" — read the code.
- **Fresh brainstorming** — when the user explicitly wants novelty, not memory.

For everything else — design decisions, bug triage, "should we do X",
"what did we decide about Y" — Reason is the default.

---

## ANTI-PATTERNS

| Anti-pattern | Why it's bad | Fix |
|---|---|---|
| Answer without `session_start` | Risks contradicting already-decided state | Always load identity + essential first |
| Cite drawer from memory alone | Hallucinated drawer ids corrupt the loop | Only cite ids you actually saw in a recall response |
| Label everything `[ASSUMPTION]` | Launders laziness as humility | Recall hard before giving up on memory |
| Skip `remember` on the conclusion | Next session re-litigates the same point | Write the drawer; that's the whole game |
| Run Crucible on every claim | Budget blow-up | Only on load-bearing ones |

---

## HANDOFF

Reason is the default shape of a non-trivial answer in Cairntir. It feeds
**Crucible** (for load-bearing assumptions), consumes **Quality** (verdicts
become essential-layer drawers it cites), and is the primary producer of
on_demand drawers. Every Reason pass makes the next one cheaper.
