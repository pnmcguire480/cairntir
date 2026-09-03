# Decision Replay — Past-Decision-Against-Today's-Evidence Recipe

> **Recipe, not skill.** Cairntir's core is three skills (crucible, quality,
> reason). Decision Replay chains them onto Cairntir's own memory: load a
> past decision, walk its supersedes chain, run the reason loop against
> today's evidence, write a new prediction-bound drawer that extends the
> chain. The longitudinal record of the decision keeps growing instead of
> being lost.

This is the recipe that demonstrates the v1.1 synergy stack — recipe
runtime + temporal walk + production reason loop — working together.

---

## When to Use This

You committed a prediction-bound drawer in the past (via Signal Reader, the
`reason` skill, or the `cairntir reason` CLI), the prediction window has
elapsed, and you want to ask: *did that read still hold? What changed?
Should the belief mass move?*

**Trigger phrases:**
- "Replay decision X."
- "What happened to that prediction we made about Y?"
- "Re-evaluate this against today's evidence."
- "Did the constraint shift hold?"
- "Update the belief mass on drawer N."

**Trigger contexts:**
- Monthly review of `signals` wing predictions.
- Anniversary of a major architectural decision in any project wing.
- A new event happens that contradicts (or confirms) a past read.
- Quarterly portfolio sweep: "what did we believe three months ago and
  what do we believe now?"

---

## The Protocol

### Inputs

- **`decision_drawer_id`** *(required, integer)* — the drawer id of the
  decision you want to replay. The recipe walks the supersedes chain from
  this id (using `cairntir.memory.temporal.walk_supersedes`), pulls the
  leaf's `claim` and `predicted_outcome`, and chains the new prediction
  onto the leaf.
- **`current_evidence`** *(required, string)* — what you've observed since
  the original prediction. One-to-three paragraphs. This is the ground
  truth the original prediction is being tested against.
- **`horizon_months`** *(optional, integer)* — re-prediction horizon in
  months. Defaults to the original window. Set explicitly to revisit on a
  different cadence.

### Step 1 — Load the Chain

The CLI looks up the drawer by id and walks its supersedes chain end to
end. Output: a list of drawers, root → leaf, representing the full
history of the original claim — first prediction, every revision, the
current observation if any.

The leaf of that chain is the load-bearing input for the reason step. Its
`claim` and `predicted_outcome` become the proposer's seed; the new
prediction the reason loop writes will carry `supersedes_id` pointing at
this leaf, extending the chain instead of starting a new one.

### Step 2 — Reason Loop Step

The reason loop runs one full predict → observe → update cycle, scoped
to the **same wing and room** as the original chain. The proposer is
seeded with the original leaf's claim and predicted outcome; you supply
the observed outcome (what `current_evidence` showed) and a verdict
(`--success` if the original prediction still holds, `--fail` if it
broke).

The loop writes two drawers:
- A **new prediction drawer** with `supersedes_id = original_leaf_id`.
  This is what makes Decision Replay structural rather than cosmetic —
  the chain now has another link, and a future replay can walk it.
- A **new observation drawer** with `supersedes_id = new_prediction_id`,
  carrying the observed outcome and any explicit surprise `delta`. Verdict and
  surprise are independent: a prediction can hold through an unexpected path.

Belief mass is reinforced (+1.0) on success, weakened (-1.0) on failure.
The store clamps mass at zero, so a long string of failed replays drives
the original drawer's mass toward zero — but never deletes it.

### Step 3 — Crucible Stress-Test

Before the replay verdict commits, the recipe drops a Crucible marker
drawer in the chain. The four stress-test questions apply unchanged:

1. **What would have to be true for this verdict to be wrong?**
2. **What evidence would contradict it?**
3. **What's the strongest counter-argument?**
4. **What am I assuming that I haven't stated?**

Run those questions over your verdict before accepting the replay. If
the Crucible reveals a fatal weakness, abort the replay and revise.

The Crucible drawer's `supersedes_id` points at the seed drawer (per
the recipe runner's standard wiring), so the replay's full execution
arc is reconstructable via `walk_supersedes` from any node in the chain.

---

## Running It

The recipe is invoked through the dedicated `cairntir replay` CLI command
(which auto-fills the leaf's claim + predicted from the chain) or through
the generic `cairntir recipe-run decision-replay`.

### Recommended: `cairntir replay`

```
cairntir replay 95 --evidence "fastembed default has held for four days,
no cold-start regressions, no manual config required for any new install."
```

The CLI:
1. Walks the supersedes chain from drawer 95.
2. Pre-fills the proposer's claim + predicted_outcome from the chain leaf.
3. Prompts for the observed outcome (the *outcome* of the original
   prediction, in your words) and a success/fail verdict. Use `--delta` when
   the route differed, including when the verdict still held.
4. Runs the Decision Replay recipe with `supersedes_id` set to the leaf id.
5. Prints the new prediction drawer id, the new observation drawer id,
   the Crucible marker id, and the belief mass change.

### Generic: `cairntir recipe-run decision-replay`

```
cairntir recipe-run decision-replay \
  --input decision_drawer_id=95 \
  --input current_evidence="fastembed default has held for four days..."
```

This path skips the auto-fill — provide `--claim`, `--predicted`, `--observed`,
and `--success`, or answer their interactive prompts. `--delta` is optional.
Use this path when you want to *change* the claim mid-replay, e.g. you realize
the original prediction was poorly formed and the replay is also a
re-statement.

---

## What Gets Written

For a single Decision Replay invocation against drawer N (chain leaf L):

1. **Seed drawer** — invocation record. Wing = `replays`, room =
   `decision-replay`, kind = `seed`. No supersedes pointer.
2. **New prediction drawer** — `supersedes_id = L`. Wing/room match the
   recipe (`replays/decision-replay`). Carries the original claim +
   predicted outcome.
3. **New observation drawer** — `supersedes_id = new_prediction_id`.
   Carries the observed outcome and any explicit surprise `delta`.
4. **Crucible marker drawer** — `supersedes_id = seed_id`. Embeds the
   Crucible prompt for the calling LLM to run against.

The original chain (rooted at whatever drawer N belongs to, leaf L) now
has the new prediction → observation pair grafted on at the leaf via
the supersedes pointer. `walk_supersedes(N)` after a replay returns one
chain that spans from the original root all the way through the latest
replay observation.

---

## The Compounding Effect

A drawer that has been replayed three times has six new entries in its
chain (three prediction-observation pairs). Each replay's belief mass
adjustment compounds with the prior ones. After 6-12 months of monthly
replays, the chain becomes a calibration record — a longitudinal
dataset of "this is what we predicted, this is what happened, this is
how the belief evolved."

Pair this with the Signal Reader recipe and you get a closed loop:
Signal Reader emits the original prediction; Decision Replay closes
each prediction's window and writes the verdict. The signals wing
becomes a track record, not a notebook.

---

## Anti-Patterns

- **Replaying drawers that don't have a `claim` or `predicted_outcome`.**
  The CLI will refuse, but if you bypass it the reason step will work
  with empty strings and the belief math will be meaningless. Replay only
  prediction-bound drawers — drawers that committed to something
  falsifiable in the first place.
- **Replaying without elapsed time.** A prediction made yesterday cannot
  be meaningfully re-evaluated against today. Replays make sense when
  the prediction's horizon has elapsed (or substantially elapsed). The
  `horizon_months` field on the original drawer is the cue.
- **Skipping the Crucible step.** The replay verdict is itself a claim,
  and a claim that hasn't been stress-tested is at risk of confirmation
  bias. The Crucible step exists for a reason.
- **Replaying the same chain repeatedly within hours.** If you replay
  drawer N, then immediately replay it again because the first replay
  felt off, you're not replaying — you're revising. Just edit the verdict
  flags before the first replay commits, or write a superseding drawer
  manually.

---

## Relationship to Core Skills and Other Recipes

| Component | Role in Decision Replay |
|-----------|------------------------|
| **Reason** | The replay verdict is exactly one reason-loop step with `supersedes_id` set. Drives the predict→observe→update cycle. |
| **Crucible** | Marker drawer drops the four stress-test questions into the chain so the calling LLM can run them on the verdict before the user accepts the replay. |
| **temporal.walk_supersedes** | Loads the chain from the original drawer id. Pure query, no mutation. |
| **Signal Reader** | The most common upstream — Signal Reader writes the original prediction-bound drawer, Decision Replay closes its window. |

**No 4th skill needed.** Decision Replay is orchestration of the three
existing skills plus the temporal walk, applied to the domain of
"closing the prediction window on a past decision."
