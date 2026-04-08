---
name: crucible
description: >
  The epistemic forge. Before building, deciding, or committing, CRUCIBLE
  forces you to enumerate what you actually know, what you're assuming, and
  what you can verify. Four phases — Pre-Flight, Architecture, Quality Gate,
  Evolution — scale with the stakes of the decision. Findings are persisted
  as Cairntir drawers so the next session doesn't re-litigate settled ground.

  Trigger on: "crucible", "stress test", "what are we assuming",
  "prove it first", "what could be wrong", "assumption audit",
  "falsifiability check".
---

# CRUCIBLE — The Epistemic Forge

## The Principle

**Falsifiability is the only honest filter.** If a claim about the system
can't be tested, it's decoration. Every load-bearing decision passes through
CRUCIBLE before resources are committed — and every CRUCIBLE pass leaves a
trail of drawers the next session can trust.

Three truths that created CRUCIBLE:

1. **Assumption enumeration is the debugging muscle promoted to default mode.**
   Use it *before* things break, not just during the 40-minute thrash.
2. **Context sensitivity beats universal rules.** CRUCIBLE doesn't hand you
   answers — it forces you to enumerate the conditions under which your
   answers hold.
3. **Descriptions are routing signals.** Vague descriptions create misrouting.
   Pressure-test the words before they become load-bearing.

---

## THE FOUR PHASES

```
┌─────────────────────────────────────────────────┐
│  PHASE 1: PRE-FLIGHT              [Enumerate]   │
│  List every assumption. Rate by evidence.       │
├─────────────────────────────────────────────────┤
│  PHASE 2: ARCHITECTURE            [Structure]   │
│  Make each claim falsifiable. Define contracts. │
├─────────────────────────────────────────────────┤
│  PHASE 3: QUALITY GATE            [Verify]      │
│  Test what you claimed. Kill what fails.        │
├─────────────────────────────────────────────────┤
│  PHASE 4: EVOLUTION               [Compound]    │
│  Write drawers. Update priors. Next session     │
│  starts on verified ground.                     │
└─────────────────────────────────────────────────┘
```

**Rule: Phase 1 is never skipped. Phases 2–4 scale with the stakes.**

---

## PHASE 1 — PRE-FLIGHT (Assumption Enumeration)

### 1.1 State the goal
One sentence. What are you trying to build, decide, or verify?

### 1.2 Enumerate assumptions
Classify every claim that supports the goal:

| Tag  | Meaning                                              |
|------|------------------------------------------------------|
| `[K]`| **Known** — verified by test, observation, or docs   |
| `[A]`| **Assumed** — believed true but unverified           |
| `[U]`| **Unknown** — no basis for judgment either way       |
| `[C]`| **Contested** — evidence exists for and against      |

Example:
```
[K] sqlite-vec is installed — imported successfully in cairntir.memory.store
[A] Users will run MCP via .mcp.json — no telemetry yet
[U] Whether session_start latency matters under 1k drawers — untested
[C] HashEmbedder is "good enough" for eval — passes smoke, fails paraphrase
```

### 1.3 Rate evidence strength
For every `[K]` and `[C]`: **Strong / Moderate / Weak / Stale**.

### 1.4 Identify load-bearing assumptions
Which `[A]` items, if wrong, break the whole plan? Mark them:

```
[A] ⚠️ LOAD-BEARING: session_start fits in one tool-call budget
    If wrong: the amnesia killer never fires; Cairntir fails its North Star
    Mitigation: add layer budgets + truncation rules before Phase 4 daemon
```

### 1.5 Decide
- **Proceed** — load-bearing items are `[K]` with ≥Moderate evidence
- **Investigate** — load-bearing `[A]` items can be resolved quickly
- **Abort** — critical `[U]` items with no path to verification

---

## PHASE 2 — ARCHITECTURE (Falsifiable Structure)

### 2.1 Description as contract
For any feature, skill, or tool:

```
CLAIM:          [What this thing does]
FALSIFIABLE AS: [How you would prove it doesn't]
ROUTING SIGNAL: [When should this be chosen?]
ANTI-ROUTING:   [When should it explicitly NOT be chosen?]
```

### 2.2 Output contract

```
OUTPUT:    [What is produced]
CONSUMER:  [Who/what reads it]
CONTRACT:  [Minimum viable shape the consumer requires]
VIOLATION: [What happens if the contract breaks]
```

### 2.3 Composability check
- **Upstream dependency:** what must exist before this runs?
- **Downstream consumer:** what reads this output?
- **Side effects:** what state does this change?
- **Idempotency:** can it run twice without damage?

### 2.4 Complexity score (1–3 each)
**Scope · Coupling · Reversibility · Novelty · Verification**.
Total > 10 → break it down before proceeding.

---

## PHASE 3 — QUALITY GATE (Verification)

### 3.1 Falsifiability → test cases
For each `FALSIFIABLE AS` from Phase 2:

```
TEST:           [Human-readable description]
TYPE:           [unit | integration | manual | observation]
PASS CONDITION: [Exact passing condition]
FAIL CONDITION: [Exact failing condition]
AUTOMATED:      [yes | no — if no, why not?]
```

### 3.2 Assumption validation
For each load-bearing `[A]` marked *Investigate* in Phase 1:

```
ASSUMPTION:        [...]
VALIDATION METHOD: [How to verify it]
RESULT:            [verified | falsified | inconclusive]
ACTION:            [What changes based on the result]
```

### 3.3 Kill what fails
If a core assumption is falsified: **don't patch around it.** Go back to
Phase 1 with updated knowledge. Propagate the correction to every
downstream decision that depended on it.

---

## PHASE 4 — EVOLUTION (Compound Knowledge)

Every CRUCIBLE pass ends by writing drawers so the next session starts on
verified ground. Call `cairntir_remember` for each:

```
wing:    <current project>
room:    crucible
layer:   essential   # if load-bearing
content: [K] <assumption>  — verified by <evidence>
metadata: {"phase": "4", "source": "crucible", "confidence": "strong"}
```

If a CRUCIBLE pass revealed a reusable pattern — an assumption category, a
failure mode, a misrouting signal — drop it in `room: patterns` with
`layer: identity` so it applies across every future wing.

---

## QUICK-REFERENCE CHECKLIST

For rapid audits on existing decisions:

```
□ Can I state in one sentence what this does?
□ Can I write a test that proves it doesn't do that?
□ Are the routing signals specific enough to avoid misrouting?
□ Are there anti-routing signals (when NOT to use this)?
□ Is the output contract defined (shape, consumer, violation)?
□ What assumptions is this built on? Are any load-bearing?
□ Have the load-bearing assumptions been verified?
□ Can this run twice without damage (idempotent)?
□ If this is wrong, how hard is it to undo?
□ Does this compound — does the next session inherit verified knowledge?
```

- **10/10:** Ship with confidence
- **7–9:** Ship with noted risks
- **4–6:** Investigate before shipping
- **0–3:** Back to Phase 1

---

## MODES OF USE

- **Full CRUCIBLE** — all four phases, 10–20 minutes. For anything load-bearing.
- **Quick Audit** — checklist only, 2 minutes. Spot-checks.
- **Debug CRUCIBLE** — Phase 1 only. Formalizes the assumption-hunt when
  something breaks.
- **Pre-session CRUCIBLE** — run Phase 1 on the session goal itself before
  touching code. What do you actually know? What are you assuming?

---

## HANDOFF

CRUCIBLE feeds into **Quality** (verification contracts become test cases),
into **Reason** (memory-backed thinking grounds itself in `[K]` items), and
into the drawer store (every pass compounds). It does not replace any of
them — it makes each one start from verified ground instead of assumed ground.
