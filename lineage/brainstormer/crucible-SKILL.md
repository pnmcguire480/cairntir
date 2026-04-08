---
name: crucible
description: >
  The epistemic forge. Sits upstream of every other BrainStormer skill. Before you
  build, before you scaffold, before you ideate — CRUCIBLE forces you to enumerate
  what you actually know, what you're assuming, and what you can verify. Four phases:
  Pre-Flight (assumption enumeration), Architecture (falsifiable structure), Quality
  Gate (verification contracts), Evolution (compounding knowledge). This is the
  assumption-audit muscle promoted from debugging to default mode. Every skill,
  agent, feature, and design decision passes through CRUCIBLE's epistemic filter
  before resources are committed.

  Trigger on: "crucible", "epistemic check", "what do we actually know",
  "assumption audit", "prove it first", "verify before building",
  "falsifiability check", "pre-flight", "epistemic clarity",
  "what are we assuming", "challenge assumptions".
---

# CRUCIBLE — The Epistemic Forge

## The Principle

**The assumption enumeration pattern you use when debugging is the same muscle that
should govern everything you build.** CRUCIBLE makes it the default mode *before*
anything gets built, not just when things break.

Three truths that created CRUCIBLE:

1. **Falsifiability is the only honest filter.** If a claim about your system can't
   be tested, it's decoration. Every architectural decision, every skill description,
   every agent routing signal must be falsifiable or it's noise.

2. **Context sensitivity beats universal rules.** What works in Project A fails in
   Project B. CRUCIBLE doesn't hand you answers — it forces you to enumerate the
   conditions under which your answers hold.

3. **Descriptions are routing signals.** In an agent ecosystem, the description of
   what something does IS the thing that determines whether it gets used correctly.
   Vague descriptions create misrouting. CRUCIBLE pressure-tests descriptions before
   they become load-bearing.

---

## Position in the Stack

```
CRUCIBLE (Priority 0) — Epistemic clarity: what do you know, what are you assuming?
    │
    ├── feeds → Kernel (Priority 1) — Validated assumptions become scaffold decisions
    ├── feeds → Comprehension (Priority 2) — Verified understanding, not assumed
    ├── feeds → Ideation (Priority 3) — Ideas grounded in tested premises
    ├── feeds → Design (Priority 4) — Design choices traceable to evidence
    ├── feeds → Quality (Priority 5) — Falsifiability checks become test cases
    └── feeds → Auto-Research (Priority 6) — Hypothesis quality pre-validated
```

CRUCIBLE is the **upstream gate**. It doesn't replace any skill — it makes every
skill start from verified ground instead of assumed ground.

---

## THE FOUR PHASES

```
┌─────────────────────────────────────────────────┐
│  PHASE 1: PRE-FLIGHT              [Enumerate]   │
│  List every assumption. Rate by evidence.        │
├─────────────────────────────────────────────────┤
│  PHASE 2: ARCHITECTURE            [Structure]    │
│  Make each claim falsifiable. Define contracts.  │
├─────────────────────────────────────────────────┤
│  PHASE 3: QUALITY GATE            [Verify]       │
│  Test what you claimed. Kill what fails.         │
├─────────────────────────────────────────────────┤
│  PHASE 4: EVOLUTION               [Compound]     │
│  Feed verified knowledge back. Update priors.    │
└─────────────────────────────────────────────────┘
```

**Rule: Phase 1 is never skipped. Phases 2-4 scale with the stakes of the decision.**

---

## PHASE 1: PRE-FLIGHT (Assumption Enumeration)

The same pattern you use when Claude Code is spiraling for 40 minutes. Stop.
Enumerate what you actually know vs. what you're assuming.

### Step 1.1 — State the Goal

One sentence. What are you trying to build, decide, or verify?

### Step 1.2 — Enumerate Assumptions

For every claim that supports the goal, classify it:

| Category | Symbol | Meaning |
|----------|--------|---------|
| **Known** | `[K]` | Verified by observation, test, or documentation |
| **Assumed** | `[A]` | Believed true but not verified |
| **Unknown** | `[U]` | No basis for judgment either way |
| **Contested** | `[C]` | Evidence exists both for and against |

Format:
```
[K] Python 3.9+ is required — verified in setup.py and CI matrix
[A] Users will run this from project root — no evidence, just convention
[U] Whether MCP clients cache tool descriptions — never tested
[C] Obsidian sync is fast enough — works on 3 projects, failed on 1 large vault
```

### Step 1.3 — Rate Evidence Strength

For each `[K]` and `[C]` item, rate the evidence:

| Rating | Meaning |
|--------|---------|
| **Strong** | Multiple independent confirmations, automated tests pass |
| **Moderate** | Single confirmation, manual test, or recent observation |
| **Weak** | Anecdotal, outdated, or from a different context |
| **Stale** | Was verified but conditions have changed since |

### Step 1.4 — Identify Load-Bearing Assumptions

Which `[A]` items, if wrong, would break the entire plan? These are your
**epistemic risks**. Mark them:

```
[A] ⚠️ LOAD-BEARING: Users will run this from project root
    If wrong: all path resolution breaks, init fails silently
    Mitigation: add cwd detection + warning
```

### Step 1.5 — Decision: Proceed, Investigate, or Abort

- **Proceed** — All load-bearing items are `[K]` with Strong/Moderate evidence
- **Investigate** — Load-bearing `[A]` items exist but can be resolved quickly
- **Abort** — Critical `[U]` items with no path to verification

---

## PHASE 2: ARCHITECTURE (Falsifiable Structure)

Every architectural decision, routing signal, and output contract must be falsifiable.
If you can't write a test for it, it's not a decision — it's a wish.

### Step 2.1 — Description as Contract

For any skill, agent, or feature being created:

```
CLAIM: [What this thing does]
FALSIFIABLE AS: [How you would prove it doesn't do that]
ROUTING SIGNAL: [When should this be selected over alternatives?]
ANTI-ROUTING: [When should this explicitly NOT be selected?]
```

Example:
```
CLAIM: The quality command produces a 0-100 score reflecting code health
FALSIFIABLE AS: Run on a project with known P0 issues — score must be <60
ROUTING SIGNAL: User says "is this ready", "ship it", "quality check"
ANTI-ROUTING: User is exploring ideas (→ ideation), asking "what is this" (→ comprehension)
```

### Step 2.2 — Output Contract

What does the consumer of this output actually need?

```
OUTPUT: [What is produced]
CONSUMER: [Who/what reads this output]
CONTRACT: [Minimum viable shape the consumer requires]
VIOLATION: [What happens if the contract is broken]
```

### Step 2.3 — Composability Check

How does this piece connect to the rest of the system?

- **Upstream dependency:** What must exist before this runs?
- **Downstream consumer:** What reads this output?
- **Side effects:** What state does this change?
- **Idempotency:** Can it run twice without damage?

### Step 2.4 — Complexity Assessment

Before building, honestly assess:

| Dimension | Question |
|-----------|----------|
| **Scope** | How many files/modules does this touch? |
| **Coupling** | How many other systems depend on this working? |
| **Reversibility** | If this is wrong, how hard is it to undo? |
| **Novelty** | Has something like this been built here before? |
| **Verification** | Can you write an automated test for the core claim? |

Score each 1-3. Total > 10 = break it down further before proceeding.

---

## PHASE 3: QUALITY GATE (Verification)

Turn Phase 2's falsifiable claims into actual tests. This is where CRUCIBLE
hands off to PALADIN — but CRUCIBLE defines *what* to test, PALADIN defines *how*.

### Step 3.1 — Falsifiability → Test Cases

For each `FALSIFIABLE AS` statement from Phase 2:

```
TEST: [Human-readable test description]
TYPE: [unit | integration | manual | observation]
PASS CONDITION: [Exact condition that constitutes passing]
FAIL CONDITION: [Exact condition that constitutes failure]
AUTOMATED: [yes | no — if no, why not?]
```

### Step 3.2 — Assumption Validation

For each load-bearing `[A]` item from Phase 1 that was marked "Investigate":

```
ASSUMPTION: [The assumption]
VALIDATION METHOD: [How to verify it]
RESULT: [verified | falsified | inconclusive]
ACTION: [What changes based on the result]
```

### Step 3.3 — Kill What Fails

If a core assumption is falsified:
- **Don't patch around it.** Revisit Phase 1 with updated knowledge.
- **Update the assumption registry.** Mark it `[K]` with the actual finding.
- **Propagate.** If downstream decisions depended on it, they need re-evaluation.

### Step 3.4 — PALADIN Integration

CRUCIBLE's falsifiability checks feed directly into PALADIN:

| CRUCIBLE Output | PALADIN Input |
|-----------------|---------------|
| Falsifiable claims → | Tier 2 test generation (structural) |
| Output contracts → | Tier 3 test generation (behavioral) |
| Load-bearing assumptions → | Tier 5 security/perf checks |
| Complexity scores → | Entropy audit weighting |

---

## PHASE 4: EVOLUTION (Compound Knowledge)

Every CRUCIBLE pass generates knowledge. That knowledge compounds across sessions
and projects.

### Step 4.1 — Update Priors

After verification, update the assumption registry:

```
BEFORE: [A] Users will run this from project root
AFTER:  [K] Users run from project root 94% of the time (verified across 27 projects)
        Edge case: 2 projects used monorepo subdirectories
        Mitigation: cwd detection added in v2026.13
```

### Step 4.2 — Pattern Deposit

If this CRUCIBLE pass revealed a reusable pattern:

- **Assumption pattern:** "When X is assumed, verify by Y" → save to vault
- **Failure pattern:** "X seemed true but was false because Z" → save to vault
- **Routing pattern:** "Description phrased as X caused misrouting" → save to vault

These feed into the Comprehension pattern library and the global rules.

### Step 4.3 — Cross-Project Propagation

Via the Obsidian vault and project registry:

- Verified assumptions in one project become `[K]` evidence in similar projects
- Falsified assumptions become warnings in similar contexts
- Pattern deposits are available to all future CRUCIBLE passes

### Step 4.4 — Skill-Creator Handoff

When CRUCIBLE is used upstream of skill creation:

```
CRUCIBLE (epistemic clarity)
    → What does this skill actually need to do? [verified]
    → What are the routing signals? [falsifiable]
    → What's the output contract? [testable]
    → What assumptions is it built on? [enumerated]
        → skill-creator (packaging + eval mechanics)
            → PALADIN (quality enforcement)
```

---

## QUICK-REFERENCE CHECKLIST

For rapid audits on existing skills, agents, or features:

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
□ Does this compound — does it get smarter over time?
```

Score: count the checked boxes.
- **10/10:** Ship with confidence
- **7-9:** Ship with noted risks
- **4-6:** Investigate before shipping
- **0-3:** Back to Phase 1

---

## MODES OF USE

### Full CRUCIBLE (New Skill / Major Feature)
Run all four phases. Takes 10-20 minutes. Worth it for anything load-bearing.

### Quick Audit (Existing Skill / Agent Review)
Use the quick-reference checklist. 2 minutes. Good for spot-checks.

### Debug CRUCIBLE (When Things Break)
You already do this. Phase 1 only — enumerate assumptions, find the one that's wrong.
CRUCIBLE just formalizes what you do when agents thrash for 40 minutes.

### Pre-Init CRUCIBLE (New Project)
Before `brainstormer init`, run CRUCIBLE Phase 1 on the project itself:
- What do you actually know about this project's needs?
- What are you assuming about the stack, the audience, the scope?
- Which assumptions are load-bearing for the init decisions?

---

## REFERENCE FILES

- `references/assumption-patterns.md` — Common assumption categories and verification methods
- `references/falsifiability-guide.md` — How to make any claim falsifiable
- `references/quick-checklist.md` — Standalone quick-reference checklist (printable)

## TEMPLATES

- `templates/crucible-audit.md` — Full four-phase audit template
- `templates/assumption-registry.md` — Per-project assumption tracking

## INTEGRATION POINTS

- **Upstream of:** skill-creator, kernel, ideation, design
- **Feeds into:** PALADIN (test generation), Comprehension (pattern library), Obsidian (knowledge vault)
- **Referenced by:** debugging complexity assessment, oracle agents (assumption-auditor, first-principles)

---

## ORACLE INTEGRATION

CRUCIBLE naturally pairs with oracle agents for deeper epistemic work:

| Phase | Oracle Agent | Role |
|-------|-------------|------|
| Phase 1 | assumption-auditor | Systematic bias detection in assumption list |
| Phase 1 | first-principles | Strip assumptions to fundamental truths |
| Phase 2 | devils-advocate | Argue against architectural decisions |
| Phase 2 | red-teamer | Find how the structure breaks |
| Phase 3 | socratic-questioner | Recursive questioning on verification methods |
| Phase 4 | systems-thinker | Map feedback loops and unintended consequences |

These are optional depth tools, not required for every CRUCIBLE pass.
