# Plan: Signal Reader — Structural Analysis Recipe for Cairntir

**Plan ID:** signal-reader
**Status:** PROPOSED
**Author:** Patrick McGuire (@pnmcguire480)
**Date:** 2026-04-14
**Serves the North Star:** Yes — prediction-bound drawers are the substrate;
the Signal Reader fills them with falsifiable structural claims about
the AI landscape that compound across sessions.

---

## One-Liner

A recipe that chains Cairntir's `reason` loop and `crucible` skill into
a repeatable protocol for reading *under* AI news headlines and producing
prediction-bound drawers that track whether your structural reads hold.

---

## Why This Exists

The AI news cycle produces massive noise. Model drops, funding rounds,
product launches — these dominate attention but rarely represent the
structural shifts that actually reshape the industry over 12 months.

The skill of reading under the fog — separating the headline story from
the structural story, identifying which constraint moved, and projecting
who gains and who loses — is a reasoning discipline, not an information
retrieval problem. It compounds: a structural read from March informs
how you interpret April's events. A prediction that failed tells you
something about your model of the industry.

Cairntir already has every primitive this needs:

- **Prediction-bound drawers** — `claim`, `predicted_outcome`,
  `observed_outcome`, `delta`, `supersedes_id`
- **Reason loop** — `ReasonLoop.step()` with predict→observe→update
- **Crucible** — stress-test assumptions before committing them
- **Belief-as-distribution** — reinforce/weaken based on outcomes
- **Contradiction detection** — flags when new signals contradict prior
  structural reads
- **Forgetting curve** — demotes analyses that never panned out

The Signal Reader doesn't add a 4th skill. It's a *recipe* that uses
the existing three in a structured sequence to produce high-quality
structural analysis drawers.

---

## Lineage

This recipe is a transformation of methodology observed in Nate B. Jones'
structural analysis work (AI News & Strategy Daily). Specific inspirations:

- **Research Synthesis Skill Pack** (NateBJones-Projects/OB1) — source
  set synthesis into findings, contradictions, confidence markers
- **Panning for Gold Skill Pack** (OB1) — transcript→evaluated idea inventory
- **News-to-implications prompt** (natebjones.com/prompts) — domain-specific
  implications from AI news briefs

The transformation: Nate's approach produces one-shot analysis. Cairntir's
prediction-bound drawers make it *longitudinal*. You don't just read the
signal — you commit a falsifiable prediction about what the signal means,
and the reason loop tracks whether you were right. Over time, your
structural reading ability compounds because you have a record of which
reads held and which didn't.

---

## The Five-Step Protocol

### Step 1: Separate headline from structural shift

**Input:** A news event, transcript, article, or briefing.

**Operation:** Identify two stories:
- The **surface story** — what happened, who's involved, the engagement hook
- The **structural story** — what changed about power dynamics, constraints,
  incentive structures, or resource allocation

**Output:** Two short paragraphs. The surface story is noted for context.
The structural story becomes the input to Step 2.

**Cairntir mapping:** The surface story is a standard drawer (on_demand layer).
The structural story feeds into a prediction-bound drawer.

### Step 2: Identify the constraint that moved

**Operation:** Name the specific constraint that shifted. Constraints are
the load-bearing walls of an industry. Examples from March 2026:
- Training wall → inference wall (Sora shutdown)
- Search intent → conversational intent (Criteo/ChatGPT ads)
- Regulatory path → physical infrastructure path (data center moratoriums)
- Per-seat pricing → outcome-driven pricing (SaaS apocalypse)
- Deploy-first → safety-as-market-position (Anthropic/DoD)

**Format:** `[OLD CONSTRAINT] → [NEW CONSTRAINT]` with a one-sentence
explanation of why the shift matters.

**Cairntir mapping:** The constraint shift is the `claim` field of the
prediction-bound drawer.

### Step 3: Project who gains, who loses

**Operation:** For the identified constraint shift, ask:
- Who is structurally advantaged by this shift?
- Who is structurally disadvantaged?
- Where does value migrate?
- What new bottleneck does this create?

**Important:** This is structural analysis, not moral judgment. "Who gains"
means "whose existing position or strategy is validated by this shift."

**Cairntir mapping:** The projection becomes the `predicted_outcome` field.
This is the falsifiable part — you're committing to a prediction about
how the power dynamics play out over 3–12 months.

### Step 4: Crucible stress-test

**Operation:** Before committing the drawer, run the structural read
through the Crucible skill:
- What would have to be true for this read to be wrong?
- What evidence would contradict it?
- What's the strongest counter-argument?
- What am I assuming that I haven't stated?

**Cairntir mapping:** Invoke `cairntir_crucible` on the claim +
predicted_outcome. If the crucible reveals a fatal weakness, revise
before committing. If it reveals a known uncertainty, note it in the
drawer's metadata (tags: `uncertainty:high`, `uncertainty:low`).

### Step 5: Map to portfolio

**Operation:** For each structural read that survives the crucible, ask:
- Which of my active projects does this affect?
- Does it validate, threaten, or reshape any of my current bets?
- Is there an action I should take in the next 30 days?
- Is there something I should start watching that I'm not currently?

**Cairntir mapping:** Create linked drawers in the affected project wings.
Cross-wing references (via tags or supersedes_id chains) let the
contradiction detector surface when a new signal conflicts with a prior
structural read in a specific project context.

---

## Drawer Schema for Signal Reader Entries

All Signal Reader drawers share a consistent metadata shape:

```
wing:     signals          # dedicated wing for structural analysis
room:     {YYYY-MM}        # month of the analysis
tags:     [signal-reader, {constraint-type}, {affected-projects...}]
layer:    on_demand         # most analyses; promote to essential if validated

# Prediction fields (already in Cairntir's schema):
claim:              "{constraint shift statement}"
predicted_outcome:  "{who gains/loses projection, 3-12 month horizon}"
observed_outcome:   ""   # filled in by future reason loop steps
delta:              ""   # filled in when observation arrives
supersedes_id:      null # filled in if this revises a prior read
```

### Constraint type tags (extensible):

- `constraint:inference-cost`
- `constraint:pricing-model`
- `constraint:distribution-surface`
- `constraint:physical-infrastructure`
- `constraint:regulatory`
- `constraint:safety-posture`
- `constraint:talent-market`
- `constraint:capital-allocation`

### Portfolio project tags (Patrick-specific, update as portfolio evolves):

- `project:cairntir`
- `project:forgelink`
- `project:signpro`
- `project:getkith`
- `project:stars2026`
- `project:brainstormer`
- `project:triangulate`
- `project:unsubmittable`
- `project:campaign-ops`
- `project:image360`

---

## Implementation Plan

### Phase 1: Recipe document (no code changes)

**Effort:** 1 session
**Changes:**
- Place `docs/recipes/signal-reader/README.md` (the methodology document)
- Place `docs/recipes/signal-reader/examples/march-2026.md` (worked example
  from the Nate B. Jones March 2026 transcript — five structural reads,
  fully formatted as prediction-bound drawers)
- No code changes. The recipe is a *protocol* that a human + Claude follow
  using existing Cairntir tools.

**Validates:** Can a fresh Claude Code session follow the recipe and produce
well-formed prediction-bound drawers using `cairntir_remember`?

### Phase 2: signals wing bootstrap (optional automation)

**Effort:** 1 session
**Changes:**
- Add a `cairntir signal` CLI command (or MCP tool) that scaffolds the
  five-step protocol as an interactive flow:
  1. Prompts for input (paste transcript / article / URL)
  2. Runs Step 1-3 with the reason skill's methodology
  3. Runs Step 4 via crucible
  4. Runs Step 5 portfolio mapping
  5. Commits the resulting drawers
- This is convenience, not necessity. Phase 1 works with manual tool calls.

**Governance note:** This does NOT add a 4th skill. It's a CLI command that
*chains* the existing reason and crucible skills. Like `cairntir setup`
chains multiple backend operations — it's orchestration, not a new primitive.

### Phase 3: Review cycle integration

**Effort:** 1 session
**Changes:**
- Add a `cairntir review signals` command that:
  1. Lists all prediction-bound drawers in the `signals` wing with empty
     `observed_outcome` fields
  2. For each, prompts: "Has this played out? What happened?"
  3. Fills in `observed_outcome` and `delta`
  4. Runs `reinforce` or `weaken` on the belief mass
  5. Surfaces contradictions with existing drawers
- Recommended cadence: monthly, aligned with the Signal Reader's monthly
  room structure.

---

## What This Does NOT Do

- **Does not add a 4th core skill.** Three skills maximum is locked governance.
- **Does not require external APIs.** No web scraping, no news feeds. Input
  is whatever the human pastes in — a transcript, an article, their own notes.
- **Does not automate judgment.** The five-step protocol is a reasoning
  scaffold. The human makes the calls at every step. User sovereignty applies.
- **Does not require new dependencies.** Everything runs on existing Cairntir
  infrastructure.

---

## Success Criteria

1. A fresh Claude Code session can follow the recipe document and produce
   5 well-formed prediction-bound drawers from a single news transcript.
2. Those drawers are retrievable via `cairntir_recall` with appropriate
   constraint-type and project tags.
3. A monthly review cycle can fill in observed_outcome for drawers where
   the prediction window has elapsed.
4. After 3 months of use, the signals wing contains a longitudinal record
   of structural reads — some validated, some refuted, some still pending —
   with belief masses that reflect track record.
5. The contradiction detector surfaces when a new structural read conflicts
   with a prior one in the same constraint domain.

---

## Execution Order

1. **Read `docs/recipes/signal-reader/README.md`** — the methodology document.
   This is the intellectual core; everything else is plumbing.
2. **Read `docs/recipes/signal-reader/examples/march-2026.md`** — worked
   example showing the five steps applied to real content.
3. **Bootstrap the signals wing:** `cairntir_remember` with wing=signals,
   room=meta, content describing the Signal Reader protocol and its purpose.
   This gives future sessions context on what the signals wing contains.
4. **Run the first analysis.** Paste a transcript or article. Follow the
   five steps. Commit the drawers.
5. **Schedule monthly reviews.** Mark your calendar. The compounding only
   works if you close the prediction loops.

---

*"The skill of reading under the news, of pulling the structural signal out
of the noise, of seeing the pattern behind the product launch — that's
becoming one of the most valuable skills you can practice."*

*Cairntir makes it compound.*
