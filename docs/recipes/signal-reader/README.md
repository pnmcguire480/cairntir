# Signal Reader — Structural Analysis Recipe

> **Recipe, not skill.** Cairntir's core is three skills (crucible, quality,
> reason). Signal Reader chains them into a repeatable protocol for reading
> under AI news headlines and producing prediction-bound drawers that track
> whether your structural reads hold over time.

---

## When to Use This

You've encountered a piece of AI news — a transcript, article, earnings
report, policy document, product launch, funding round, or industry
briefing — and you want to extract the structural signal that will matter
in 12 months, not the headline that will matter for 12 hours.

**Trigger phrases:**
- "What does this actually mean?"
- "Read under this for me"
- "What's the structural story?"
- "Signal-read this transcript"
- "Run the fog protocol on this"
- "What constraint moved here?"

---

## The Protocol

### Inputs

One of:
- A pasted transcript or article text
- A URL (fetched and read)
- Your own notes or observations about recent events
- Multiple sources about the same event (strongest input — contradictions
  between sources are themselves signals)

### Step 1 — Split the Two Stories

Every significant AI event contains two stories:

**The Surface Story** is what happened. Who announced what. Which numbers
moved. What the hot takes say. This story optimizes for engagement. It
answers "what should I be excited or worried about today?"

**The Structural Story** is what changed. Which constraint moved. Which
power dynamic shifted. Which assumption broke. This story optimizes for
understanding. It answers "what will this mean in 12 months?"

**Your job in Step 1:**
- Write the surface story in 2-3 sentences. Note it. Set it aside.
- Write the structural story in 2-3 sentences. This feeds Step 2.

**The test:** If your structural story could be the opening paragraph of a
newsletter hot take, you haven't gone deep enough. The structural story
should bore a casual reader and alarm a strategist.

### Step 2 — Name the Constraint That Moved

Industries are held up by constraints — load-bearing assumptions that
everyone operates under until they don't. When a constraint moves, the
entire strategic landscape shifts.

**Format your finding as:**

```
[OLD CONSTRAINT] → [NEW CONSTRAINT]
```

With one sentence explaining why the shift matters.

**Examples of constraint shifts (March 2026):**

| Event | Surface Story | Constraint Shift |
|-------|--------------|-----------------|
| Sora shutdown | AI video product failed | Training wall → Inference wall. The hard constraint in AI moved from "can we build it" to "can we afford to serve it." |
| Criteo/ChatGPT ads | Ads are coming to ChatGPT | Search intent capture → Conversational intent capture. The surface where purchase decisions happen is migrating. |
| Data center moratoriums | NIMBYs blocking progress | Federal regulatory path ≠ Physical infrastructure path. The White House can preempt state AI law but not county zoning. |
| Atlassian layoffs | Tech layoffs continue | Per-seat pricing → Outcome-driven pricing. The market saw SaaS seat compression before SaaS companies did. |
| Anthropic/DoD conflict | Political drama | Safety posture → Market position. The "great sorting" has revenue consequences running in both directions. |

**Common constraint categories:**
- Inference cost
- Pricing model
- Distribution surface
- Physical infrastructure
- Regulatory environment
- Safety/trust posture
- Talent market dynamics
- Capital allocation patterns

**If you can't name the constraint:** The event might be noise, not signal.
Not every headline contains a structural shift. It's fine to conclude
"this is a surface event with no structural component" — that's a valid
finding. Don't force a structural read that isn't there.

### Step 3 — Project Who Gains, Who Loses

For the constraint shift you identified:

1. **Who is structurally advantaged?** Whose existing position, strategy,
   or investment thesis is validated by this shift?
2. **Who is structurally disadvantaged?** Whose position depends on the
   old constraint holding?
3. **Where does value migrate?** When a constraint moves, value doesn't
   disappear — it flows to whoever is positioned on the right side of the
   new constraint.
4. **What new bottleneck does this create?** Solving one constraint
   usually reveals the next one.

**This is structural analysis, not moral judgment.** "Who gains" means
"whose strategy is validated," not "who deserves to win." Keep it clinical.

**Your projection should be falsifiable.** Write it as a prediction with a
time horizon: "In 3-12 months, X will happen because Y constraint shifted."
Vague projections ("this will be important") don't compound. Specific
predictions ("Asian data center construction will accelerate as US
permitting gridlock and Gulf conflict channel hyperscaler capex toward
the path of least resistance") do.

### Step 4 — Crucible Stress-Test

Before committing your structural read, run it through the Crucible.

**Four questions:**

1. **What would have to be true for this read to be wrong?**
   Identify the key assumption. If that assumption breaks, the whole
   analysis falls apart.

2. **What evidence would contradict it?**
   What specific data point or event, if it appeared next month, would
   tell you this structural read was incorrect?

3. **What's the strongest counter-argument?**
   Steelman the opposing position. If someone smart disagrees with your
   read, what are they seeing that you might be missing?

4. **What am I assuming that I haven't stated?**
   Unstated assumptions are the most dangerous. Make them explicit so
   future review can check them.

**If the crucible reveals a fatal weakness:** Revise the claim before
committing. The goal is not to produce structural reads — it's to produce
*good* structural reads. A killed analysis is a successful crucible run.

**If the crucible reveals known uncertainty:** Note the uncertainty level
in the drawer tags (`uncertainty:high` or `uncertainty:low`). High
uncertainty means the prediction window should be shorter and the review
cycle more frequent.

### Step 5 — Map to Portfolio

For each structural read that survives the crucible:

1. **Which active projects does this affect?**
   Check each project in your portfolio. Does this constraint shift
   validate, threaten, or reshape any current bet?

2. **Is there an action to take in the next 30 days?**
   If the structural read implies you should change something about
   an active project, note the specific action.

3. **What should you start watching that you're not?**
   Structural shifts often create new leading indicators. Identify
   what to monitor going forward.

4. **Create linked drawers in affected project wings.**
   Cross-reference via tags so the contradiction detector can surface
   conflicts between your structural reads and your project assumptions.

---

## Committing to Cairntir

After completing all five steps, commit the analysis as a prediction-bound
drawer:

```
cairntir_remember

wing:     signals
room:     {YYYY-MM}       # month of analysis
layer:    on_demand
tags:     [signal-reader, constraint:{type}, project:{affected}, ...]

content:  "{Surface story summary. Structural story summary.}"

claim:              "{[OLD] → [NEW] constraint shift statement}"
predicted_outcome:  "{Falsifiable projection, 3-12 month horizon}"
```

For each affected project, create a linked drawer in that project's wing:

```
cairntir_remember

wing:     {project-wing}
room:     signals
layer:    on_demand
tags:     [signal-reader, from:signals/{YYYY-MM}]

content:  "{How this structural shift affects this specific project.
            Action items if any. What to watch.}"
```

---

## The Review Cycle

**Cadence:** Monthly, at minimum. More often during dense news periods.

**Process:**

1. List all prediction-bound drawers in `signals` wing with empty
   `observed_outcome`.
2. For each drawer whose prediction window has elapsed:
   - Did the predicted outcome occur? What actually happened?
   - Fill in `observed_outcome` with what you observed.
   - Fill in `delta` — the gap between prediction and reality.
   - If the prediction was validated: `reinforce` the belief mass.
   - If the prediction failed: `weaken` the belief mass. Write a
     superseding drawer that captures what you learned.
3. Check for contradictions across the signals wing. Do any of your
   current structural reads conflict with each other?
4. Check project-linked drawers. Do any project strategies need updating
   based on resolved predictions?

**The compounding effect:** After 3-6 months, you have a longitudinal
record of your structural reads. Patterns emerge:
- Which constraint categories do you read well?
- Which do you consistently misread?
- Which projects are most sensitive to structural shifts?
- Where are your blind spots?

This is the payoff. The Signal Reader doesn't just produce analysis —
it produces *calibrated* analysis that improves over time because you
have a record of what you got right and what you got wrong.

---

## Anti-Patterns

- **Forcing structure where there is none.** Not every headline contains
  a constraint shift. If Step 2 feels like a stretch, the event is
  probably noise. Say so and move on.

- **Vague predictions.** "This will be important" is not falsifiable.
  "Asian compute geography will attract >40% of new hyperscaler capex
  commitments by Q4 2026" is. Specificity is the price of compounding.

- **Skipping the crucible.** The temptation is to commit the read as
  soon as it feels insightful. The crucible is where overconfident
  reads get caught. Never skip it.

- **Never reviewing.** Prediction-bound drawers without observed outcomes
  are just opinions in a database. The review cycle is where learning
  happens. Schedule it. Do it.

- **Treating this as news consumption.** The Signal Reader is not a
  summarization tool. If you're using it to "keep up with AI news,"
  you're missing the point. It's a reasoning discipline for extracting
  structural signal and committing falsifiable predictions. Less input,
  more depth.

---

## Relationship to Core Skills

| Core Skill | Role in Signal Reader |
|-----------|----------------------|
| **Reason** | Steps 1-3 follow the reason skill's predict→observe→update cycle. Each structural read *is* a reason loop step with the prediction window set to 3-12 months instead of within-session. |
| **Crucible** | Step 4 is a direct crucible invocation. The four stress-test questions are the crucible's standard protocol applied to structural claims. |
| **Quality** | The review cycle is a quality audit of the signals wing. Are predictions being closed? Are deltas being captured? Is belief mass reflecting track record? |

**No 4th skill needed.** The Signal Reader is orchestration of the three
existing skills, applied to a specific domain (structural analysis of AI
industry dynamics), with a specific drawer schema (the signals wing with
monthly rooms and constraint-type tags).

---

*Adapted from methodology observed in Nate B. Jones' structural analysis
work (AI News & Strategy Daily, NateBJones-Projects/OB1). Transformed for
Cairntir's prediction-bound drawer architecture by Patrick McGuire, 2026-04.*
