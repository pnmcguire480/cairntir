# Worked Example: March 2026 Structural Analysis

> **Source:** Nate B. Jones, "Reading Under the Fog of War," AI News &
> Strategy Daily, April 2026.
>
> **Method:** Five-step Signal Reader protocol applied to five structural
> events from March 2026. Each produces a prediction-bound drawer ready
> for `cairntir_remember`.

---

## Signal 1: Sora Shutdown — The Inference Wall

### Step 1 — Split the Two Stories

**Surface:** OpenAI shut down Sora on March 24th — the API, the ChatGPT
integration, the standalone app. Six months after public launch. The
Disney billion-dollar deal collapsed with it.

**Structural:** The hard constraint in AI shifted. For three years, the
narrative was about training: who can build the biggest cluster, who can
afford the most data. Sora's economics revealed that the constraint has
moved to inference. Serving models at scale is a fundamentally different
problem from training them, and the chipsets optimized for training are
not the right chipsets for inference.

### Step 2 — Name the Constraint

```
Training cost as the primary bottleneck → Inference cost per delivered
unit of revenue as the primary bottleneck
```

The most important metric in AI product development is no longer the
training FLOP count. It's the ratio of inference cost to revenue
generated per served request.

### Step 3 — Project Who Gains, Who Loses

- **Gains:** Companies working on inference optimization — quantization
  (Google's TurboQuant), model compression, inference-specific silicon,
  efficient serving architectures. Also gains for smaller/distilled
  models that serve cheaply.
- **Loses:** Companies whose product thesis requires frontier-model
  inference at consumer scale without a clear revenue-per-request model.
  Video generation, real-time image generation, any high-compute
  generative product aimed at free/low-cost tiers.
- **Value migrates to:** The inference efficiency layer. Whoever solves
  cost-per-served-token wins the ability to ship product.
- **New bottleneck:** Inference-optimized silicon and serving
  infrastructure become the next supply constraint.

**Prediction (3-12 month horizon):** By Q4 2026, at least two major AI
product shutdowns or pivots will cite inference economics as the primary
driver. Model compression / distillation papers will see citation rates
increase 2-3x. Inference-focused chip startups will see funding rounds
at higher valuations than training-focused ones.

### Step 4 — Crucible

1. **Wrong if:** Inference costs drop dramatically due to a breakthrough
   (new architecture, hardware advance) that makes the current cost
   curve irrelevant. If serving becomes cheap fast enough, the wall
   doesn't bind.
2. **Contradicting evidence:** A frontier-scale generative product
   (video, 3D, real-time) launching successfully at consumer pricing
   with sustainable unit economics within 6 months.
3. **Counter-argument:** Training is still the moat. Inference is a
   commodity that will be competed away. The real value is in having
   the best model, not serving it cheaply.
4. **Unstated assumption:** That the revenue models for AI products
   remain similar to current approaches. A radically different
   monetization model (subscription bundles, enterprise-only, etc.)
   could change the cost-per-unit calculus.

**Verdict:** Survives. The counter-argument (training is the moat) was
the consensus for 3 years and is now being challenged by the data.
The unstated assumption about revenue models is worth tracking.
**Uncertainty: low.**

### Step 5 — Portfolio Mapping

- **ForgeLink:** Directly affected. Every MCP connection ForgeLink
  enables carries inference overhead. Unit economics of "every API
  becomes agent-ready in 60 seconds" depend entirely on how much
  inference each connection costs to maintain. Action: model the
  inference cost per ForgeLink connection.
- **Cairntir:** Minimal direct impact — Cairntir is local-first, memory
  operations are SQLite, not inference-heavy. But the MCP server
  interactions do consume tokens. Monitor.
- **BrainStormer:** The 374-agent architecture is inference-heavy by
  design. The tiered model routing (Tier 5 Opus → Tier 1 Ollama)
  was prescient — it's already an inference cost management strategy.
  Validate: is the tier routing actually saving money, or is it
  advisory-only (per the harness audit)?
- **Image360/SignPro:** If SignPro uses voice-first AI for knowledge
  capture, the inference cost of continuous speech-to-text +
  LLM processing matters. The 10-second usability constraint puts
  pressure on fast, cheap inference.

---

## Signal 2: Criteo/ChatGPT Ads — Conversational Commerce

### Step 1 — Split the Two Stories

**Surface:** Criteo became the first ad tech company to integrate with
OpenAI's advertising pilot. Ads are coming to ChatGPT.

**Structural:** The surface where purchase decisions happen is migrating
from search results pages to conversational interfaces. Early data showed
1.5x conversion rates from LLM-referred traffic. The purchase funnel
is collapsing from a multi-step journey (search → browse → compare →
buy) into a single conversation where discovery, consideration, and
conversion happen in the same context window.

### Step 2 — Name the Constraint

```
Search results page as the primary commercial intent surface →
Conversational interface as the primary commercial intent surface
```

The ad industry's budget follows attention. If attention moves from
search to conversation, the budget follows.

### Step 3 — Project Who Gains, Who Loses

- **Gains:** AI platform companies building conversational surfaces
  (OpenAI, Anthropic, Google if they pivot). Existing programmatic
  ad infrastructure companies (Criteo, The Trade Desk) who can pipe
  into new surfaces.
- **Loses:** Businesses whose revenue depends on search visibility
  (SEO-driven businesses, content farms, affiliate marketers).
  Potentially Google's core ad business if conversational AI captures
  intent upstream.
- **Value migrates to:** Whoever controls the conversational context
  where decisions are made. The model provider creates context; the
  adtech layer fills it.
- **New bottleneck:** Trust. A recommended product in a conversation
  carries implicit endorsement. If that trust is violated by bad
  recommendations, the entire surface loses value.

**Prediction:** By Q4 2026, at least three major adtech platforms will
have active integrations with conversational AI surfaces. Google will
accelerate Gemini's ad integration timeline. SEO-dependent businesses
will begin reporting measurable traffic declines from AI-referred
substitution.

### Step 4 — Crucible

1. **Wrong if:** Users reject ads in conversational interfaces. If the
   trust signal collapses (users feel manipulated by product
   recommendations in conversations), the surface becomes toxic.
2. **Contradicting evidence:** Conversion rates dropping below search
   baselines as the novelty effect wears off. User backlash leading
   to ad-free competitive positioning.
3. **Counter-argument:** Google has survived every "Google killer" for
   20 years. Search intent is habitual. Conversational AI is a niche
   that won't capture enough commercial intent to matter.
4. **Unstated assumption:** That the 1.5x conversion rate from a small
   sample and short time window is representative of steady-state
   behavior, not a novelty effect.

**Verdict:** Survives with caveats. The small sample size is a real
concern. The direction of the signal matters more than the magnitude.
**Uncertainty: medium.**

### Step 5 — Portfolio Mapping

- **getKith:** If mutual aid discovery moves to conversational
  interfaces, getKith needs a presence in that surface. An MCP server
  that surfaces local mutual aid resources in AI conversations could
  be a distribution channel. This is a non-obvious connection worth
  exploring.
- **Triangulate:** Designed to surface news convergence across outlets.
  If the ad migration is real, Triangulate's convergence trust-signal
  algorithm could apply to evaluating which product recommendations
  in AI conversations are editorially honest vs. sponsored.
- **Image360:** If local business discovery moves from search to
  conversation, sign shops become less findable via Google and more
  findable via AI recommendations. What does Image360's presence look
  like in a conversational discovery surface?

---

## Signal 3: Data Center Moratoriums — The Geography Trap

### Step 1 — Split the Two Stories

**Surface:** 12 states have filed data center moratorium bills. 54 local
governments have passed short-term freezes. Federal moratorium bill
introduced by Sanders/AOC.

**Structural:** A three-layer contradiction: the White House is clearing
the regulatory path for AI, communities are blocking the physical path,
and the Gulf conflict is closing the geopolitical path. Where AI
physically lives is now a function of which constraint gives first.

### Step 2 — Name the Constraint

```
Regulatory environment as the primary infrastructure constraint →
Physical geography (zoning + energy + water + conflict) as the
primary infrastructure constraint
```

Federal preemption of state AI law does not override a county that
won't rezone farmland for a gigawatt campus.

### Step 3 — Project Who Gains, Who Loses

- **Gains:** Asian compute geography — easiest place to build right now.
  Countries/regions with permitting speed and energy surplus.
- **Loses:** US-centric hyperscalers who assumed domestic buildout.
  Gulf states whose data center investment thesis is threatened by
  kinetic conflict.
- **Value migrates to:** Wherever the physical constraints are loosest.
  Compute is fungible; geography is not.
- **New bottleneck:** Data sovereignty. If compute moves to Asia,
  regulatory requirements about where data lives create new friction.

**Prediction:** By Q1 2027, the center of gravity for new hyperscaler
data center construction commitments will have measurably shifted
toward Southeast Asia. At least one major US data center project will
be canceled or indefinitely delayed due to state/local opposition.

### Step 4 — Crucible

1. **Wrong if:** Gulf conflict resolves quickly and the US passes
   federal infrastructure preemption that overrides local zoning.
2. **Contradicting evidence:** A wave of successful US data center
   approvals in Q3-Q4 2026 that breaks the moratorium trend.
3. **Counter-argument:** NIMBY resistance is temporary. Communities
   will accept data centers when they see the tax revenue and jobs.
   The economics always win eventually.
4. **Unstated assumption:** That the Gulf conflict persists or
   escalates. A resolution would reopen Middle Eastern geography.

**Verdict:** Survives. The "economics always win" counter-argument
has a timescale problem — eventually is not soon enough for $700B
in capex that needs to land this year. **Uncertainty: medium.**

### Step 5 — Portfolio Mapping

- **All cloud-dependent projects:** If compute geography shifts, latency
  and data residency implications matter for any product with real-time
  requirements. SignPro's voice-first interface needs low-latency
  inference — where that inference physically runs matters.
- **Cairntir:** Local-first architecture is partially insulated. The
  MCP server runs on the user's machine. But if Claude Code's backend
  infrastructure shifts geographically, response times could change.

---

## Signal 4: Atlassian Layoffs — Per-Seat Death Spiral

### Step 1 — Split the Two Stories

**Surface:** Atlassian cut 1,600 jobs. CTO replaced by two AI-native
executives. Stock ticked up 2% after being down 60% in 12 months.

**Structural:** The SaaS industry is experiencing a pricing model
crisis. The market recognized that AI agents compress seat counts (10
agents doing the work of 100 humans = 90% revenue compression for
per-seat SaaS vendors) before SaaS companies recognized it themselves.
The CEO who promised more engineers 5 months earlier is now cutting
them. The dislocation between market awareness and company awareness
is the structural signal.

### Step 2 — Name the Constraint

```
Per-seat pricing as the default SaaS revenue model →
Outcome-driven pricing as the survival requirement
```

The market is punishing every SaaS company that hasn't pivoted to
outcome-driven pricing, regardless of individual fundamentals.

### Step 3 — Project Who Gains, Who Loses

- **Gains:** SaaS companies that pivot to outcome-based pricing early.
  AI-native tools that were never per-seat to begin with. Companies
  building the AI agents that are compressing the seat counts.
- **Loses:** SaaS incumbents with large per-seat installed bases and
  no pricing model transition plan. Companies whose entire valuation
  is a multiple of seat-count revenue.
- **Value migrates to:** Outcome-based platforms and the agent/AI
  layer that delivers the outcomes.
- **New bottleneck:** Measuring outcomes. Per-seat pricing was simple
  to meter. Outcome-based pricing requires defining, measuring, and
  attributing outcomes — a much harder problem.

**Prediction:** By end of 2026, at least five major SaaS companies
(>$1B revenue) will announce pricing model transitions away from
pure per-seat. The ones that don't will continue to trade at
compressed multiples.

### Step 4 — Crucible

1. **Wrong if:** AI agent adoption stalls. If enterprises don't
   actually deploy agents at scale, seat compression doesn't happen
   and per-seat pricing survives.
2. **Contradicting evidence:** SaaS seat counts stabilizing or growing
   across the sector by Q3 2026.
3. **Counter-argument:** Per-seat pricing is simple, understood by
   procurement, and easier to budget for. Enterprises resist
   outcome-based pricing because it's unpredictable. Inertia wins.
4. **Unstated assumption:** That the current market sell-off is
   structural repricing, not a sentiment-driven overcorrection that
   will bounce back.

**Verdict:** Survives. The inertia counter-argument is strong but
Atlassian's first-ever enterprise seat count decline is a data point
that weakens it. **Uncertainty: low.**

### Step 5 — Portfolio Mapping

- **BrainStormer:** Currently uses HMAC 4-tier licensing
  (community/pro/team/enterprise). Is this per-seat or outcome-driven?
  If it's per-seat or per-developer, the same compression logic
  applies. Action: evaluate whether BrainStormer's pricing model
  aligns with outcome-driven principles.
- **Cairntir:** MIT, open source. Not directly monetized. But if
  Cairntir becomes a library that commercial products depend on,
  the pricing of those commercial products is relevant context.
- **ForgeLink:** "Every API becomes agent-ready in 60 seconds" is an
  outcome claim. Pricing should probably be per-connection or
  per-outcome, not per-seat. Validate this early.

---

## Signal 5: Anthropic/DoD — The Great Sorting

### Step 1 — Split the Two Stories

**Surface:** Anthropic refused Pentagon's terms on autonomous weapons
and mass surveillance. Got blacklisted. Lawsuit filed. OpenAI captured
the defense revenue.

**Structural:** Safety posture has become a market position with
measurable revenue consequences in both directions. Anthropic lost a
$200M contract but gained record consumer adoption and enterprise
goodwill. OpenAI captured defense revenue but absorbed reputational
risk. Every AI company, every enterprise buyer, every developer is
now sorting around the safety posture spectrum.

### Step 2 — Name the Constraint

```
Safety as an ethics/talent concern →
Safety posture as a market position with revenue consequences
```

The "great sorting" has begun. The question is no longer whether you
care about safety — it's where you sit on the spectrum and what
customers that positioning attracts or repels.

### Step 3 — Project Who Gains, Who Loses

- **Gains:** Whichever positioning creates a larger total addressable
  market. In the near term, the "no restrictions" position captures
  government/defense revenue. In the medium term, the "safety-first"
  position may capture more enterprise revenue from buyers who need
  AI governance assurances.
- **Loses:** Companies who try to occupy both positions simultaneously.
  The sorting forces a choice.
- **Value migrates to:** The position that aligns with the larger
  budget pool. Defense is large but concentrated. Enterprise is larger
  and distributed.
- **New bottleneck:** Defining what "safety posture" actually means in
  contract language. The spectrum between "model does whatever you
  want" and "model maker retains control" needs concrete terms.

**Prediction:** By end of 2026, enterprise AI procurement processes
will include explicit safety posture evaluation criteria. At least one
major enterprise RFP will disqualify a vendor based on their defense
department positioning.

### Step 4 — Crucible

1. **Wrong if:** Enterprise buyers don't actually care about safety
   posture in practice. If procurement decisions remain purely
   capability-driven, the sorting doesn't create market consequences.
2. **Contradicting evidence:** Anthropic's enterprise pipeline
   declining despite the consumer goodwill narrative.
3. **Counter-argument:** Safety posture is a luxury of frontier labs
   with venture funding. Once Anthropic needs to be profitable, the
   red lines will soften. Economics beats principles.
4. **Unstated assumption:** That the legal challenge resolves in a way
   that doesn't set a precedent eliminating safety-posture-based
   refusals entirely.

**Verdict:** Survives. The "economics beats principles" counter-argument
is the most threatening. Monitor Anthropic's financial trajectory
closely. **Uncertainty: medium.**

### Step 5 — Portfolio Mapping

- **All products:** As a developer building on Claude, the Anthropic/DoD
  outcome directly affects platform risk. If Anthropic's financial
  position weakens due to the blacklist, that's a risk to any product
  built on Claude's API. Conversely, if the goodwill drives adoption,
  the platform strengthens.
- **Campaign operations:** The safety-posture-as-market-position
  dynamic has a political dimension. Understanding where candidates
  sit on the AI governance spectrum is relevant to the political
  education curriculum.

---

## Summary: Drawer Inventory from This Analysis

| # | Constraint Shift | Prediction Window | Uncertainty | Projects Affected |
|---|-----------------|-------------------|-------------|-------------------|
| 1 | Training → Inference wall | Q4 2026 | Low | ForgeLink, BrainStormer, SignPro |
| 2 | Search → Conversational intent | Q4 2026 | Medium | getKith, Triangulate, Image360 |
| 3 | Regulatory → Physical geography | Q1 2027 | Medium | All cloud-dependent |
| 4 | Per-seat → Outcome pricing | End 2026 | Low | BrainStormer, ForgeLink |
| 5 | Safety ethics → Safety market position | End 2026 | Medium | All (platform risk), Campaign ops |

**15 drawers total:** 5 in the `signals` wing + 10 cross-referenced in
project wings.

**First review date:** May 15, 2026 (30 days).

---

*This example demonstrates the full Signal Reader protocol applied to real
content. The prediction-bound drawers are ready for `cairntir_remember`.
The review cycle begins in 30 days.*
