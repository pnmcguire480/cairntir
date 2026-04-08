# Agent Species Framework — Extracted from Nate B.

> Source: *"Agents" Means 4 Different Things and Almost Nobody Knows Which One They Need*
> Key insight: "Agent" is too vague. There are at least four distinct production patterns, and using the wrong one for your problem is the #1 mistake people make.

---

## The Four Species

### 1. Coding Harness (Task-Scale)

The simplest pattern. One agent replaces one developer. It has file access, code execution, search — the same tools a human IC would use. The human acts as manager, the agent grinds.

**When it works:** Single-threaded tasks with clear boundaries. Developer decomposes the problem, assigns chunks to agents, reviews output. Karpathy runs agents 16 hours/day this way. Steinberger ran multiple Codex agents in parallel on OpenClaw — each on a ~20min task, checking back in with him as manager.

**The unlock:** Decomposition. If you can break the work into well-defined chunks, you can parallelize across many single-threaded agents. This is the BabyTierOS sweet spot — chunk-based development IS this pattern.

**BrainStormer mapping:** This is your Kernel (BabyTierOS) workflow at its most literal. Claude Code as T4 agent, you as the manager-decomposer. Every chunk doc is essentially a task spec for a coding harness agent.

---

### 2. Coding Harness (Project-Scale) → Planner-Executor

When projects outgrow one developer's mental model, you need an agent managing agents. Cursor built browsers and compilers with this — millions of lines of code.

**Architecture:**
- **Planner agent** — tracks tasks, maintains memory/notes, evaluates executor output
- **Executor agents** — short-lived, single-purpose grunt workers spun up per-task
- Human involvement shrinks to bookends (design + final review)

**Critical finding from Cursor:** They tried 3 management layers. It failed. **Simple scales well with agents.** Two layers (planner → executor) was the sweet spot.

**BrainStormer mapping:** This is where BabyTierOS 2.0 could evolve. Your chunk decomposition is already the planner function — the question is whether Claude Code could run as the planner while spinning up sub-tasks. Your scaffold script is basically a manual planner. Automating it = stepping into this species.

---

### 3. Dark Factory

Spec in, software out, humans at the edges only. The middle runs autonomously until it hits an eval gate.

**Key properties:**
- Human does heavy design/spec work upfront
- Human reviews eval results at the end
- The middle is fully autonomous — agents iterate until tests pass
- Removing humans from the middle actually *reduces* strain (agents move too fast for human bottlenecking)

**Risk calibration:** Most serious companies still have a senior engineer review code before prod. Amazon learned this the hard way — called principal engineers to Seattle over AI-generated production incidents from unsupervised junior devs.

**Hybrid approach (recommended):** Run the middle as dark factory, but gate production behind human eval review. Gets 80% of the speed benefit without the risk.

**BrainStormer mapping:** PALADIN (your quality sub-skill) is already an eval framework. The dark factory pattern suggests: what if PALADIN ran autonomously between chunks, and you only reviewed failures? Your 735 curated agents could be the dark factory workforce — the question is trust calibration per agent.

---

### 4. Auto Research

Not about building software. About optimizing a metric. Descended from classical ML hill-climbing.

**Examples:**
- Toby Lütke optimizing Shopify's Liquid framework for runtime performance
- Karpathy auto-researching toward GPT-2 scale as independent proof-of-concept
- Conversion rate optimization on landing pages
- Any problem where you have data + a measurable target

**The diagnostic question:** *"Is my problem software-shaped or metric-shaped?"* If you can express success as a rate or score, it's auto research. If you need working code as output, it's one of the other three.

**BrainStormer mapping:** This could power a future eval-optimization loop. Imagine auto-researching prompt quality across your 735 agents — hill-climbing toward better output scores per agent. Also relevant for Triangulate's clustering algorithms (optimizing convergence accuracy).

---

### 5. Orchestration Framework

Multiple specialized agents with handoffs. Researcher → Writer → Editor. Ticket pickup → Research → Resolution → Comment.

**When it's worth it:** Scale. If you're processing 10K+ tickets or documents, the coordination overhead pays for itself. Below that threshold, it might not.

**Key distinction from planner-executor:** Orchestration gives agents *specialized roles* (marketing agent, finance agent, copywriting agent). Planner-executor gives generic executors *specific tasks*. Orchestration = role identity. Planner-executor = task assignment.

**Current state:** Heavy on human involvement at the joints. Frameworks like LangGraph and CrewAI are trying to reduce that friction.

**BrainStormer mapping:** Your Ideation sub-skill (BrainStormer chain) already has a flavor of this — multiple thinking modes in sequence. The 735 agents organized by specialty are essentially an orchestration roster waiting for a routing layer.

---

## The Cheat Sheet

| Your Problem Shape | Agent Species | Human Role | Optimize For |
|---|---|---|---|
| Task in front of you | Coding Harness (Individual) | Manager/judge | Your judgment as quality gate |
| Large project, team-scale | Coding Harness (Project) | Designer + reviewer | Planner-executor coordination |
| Repeatable pipeline, high trust | Dark Factory | Spec writer + eval reviewer | Eval pass rate, throughput |
| Measurable metric to improve | Auto Research | Experiment reviewer | Hill-climbing a rate/score |
| Multi-step workflow, specialized roles | Orchestration | Joint reviewer at handoffs | Handoff quality at scale |

---

## Patterns Worth Stealing

### "Simple Scales Well"
Cursor's biggest lesson. Don't add management layers. Two levels (planner → executor) outperformed three. This validates BabyTierOS's flat chunk architecture — resist the urge to over-nest.

### "Decomposition Is the Unlock"
The single most repeated theme. The developer who can decompose well can parallelize agents effectively. BabyTierOS chunk docs ARE decomposition artifacts. This is already your superpower.

### "Humans at the Edges"
Design and review are where human judgment matters most. The middle is where agents should run free. This argues for investing more in your spec/chunk doc quality upfront and your PALADIN eval quality at the end — and trusting the agent more in between.

### "Don't Mix Species"
The biggest anti-pattern Nate sees: people trying to use auto-research to build software, or coding harnesses to write novels, or individual task agents as dark factories. Match the species to the problem shape.

### "Is It Software-Shaped or Metric-Shaped?"
The clearest diagnostic. If you need working code → coding harness or dark factory. If you need to optimize a number → auto research. If you need workflow routing → orchestration. Most people know immediately once they frame it this way.

---

### 6. Oracle (Thinking Methodology)

Not task-completion agents. Perspective-shifting tools that challenge assumptions, reframe problems, and surface blind spots. They produce questions, inversions, analogies, and dialectical tensions — not code or deliverables.

**When it works:** Before major design decisions, during ideation, when stuck, when a plan feels too neat, when you need adversarial pressure beyond what CEO Review provides. Also useful mid-build when you suspect you're solving the wrong problem.

**Human role:** Thinking partner. The oracle provokes; you decide.

**Two sub-types:**
- **Methodology agents** (15) — Generic, reusable thinking tools with consistent output format. Devil's advocate, lateral thinking, Socratic questioning, systems thinking, bias auditing, etc.
- **Named thinker agents** (8) — Embody a specific philosopher's worldview with unique voice and delivery. Diogenes provokes, Socrates only asks questions, Alan Watts speaks in paradoxes. These deliberately break standard agent format rules to create emergent perspectives.

**BrainStormer mapping:** Integrates with the Ideation pipeline at three points:
1. **Office Hours** (after Q2) — Optional perspective check before investing in an idea
2. **Core Extraction** (Step 1) — Oracle-generated angles tagged `[oracle: agent-name]`
3. **CEO Review** (Component 2) — Oracles as specialized adversarial attack vectors

**Severity range:** P1 (assumption-auditor, first-principles, systems-thinker) to P3 (jester, alan-watts). Most are P2.

---

## Agent Constraints Schema

Each agent can declare machine-readable constraints in its YAML frontmatter. These are enforced at the tool-pool level by any runtime that consumes BrainStormer agents.

### Constraint Fields

```yaml
constraints:
  allowed_tools: [read, grep, glob]     # null = all tools allowed
  denied_tools: [edit, write, bash]     # tools explicitly blocked
  max_turns: 10                         # maximum conversation turns
  requires_approval: false              # human must approve before execution
  sandbox_scope: read-only              # read-only | project | isolated
  output_format: markdown               # markdown | structured | plan | metrics | any
```

### Species-Level Defaults

| Species | denied_tools | max_turns | requires_approval | sandbox_scope |
|---------|-------------|-----------|-------------------|---------------|
| oracle | edit, write, bash | 10 | no | read-only |
| dark-factory | (none) | 50 | yes | isolated |
| task-harness | (none) | 30 | no | project |
| planner-executor | (none) | 20 | no | project |
| auto-research | edit, write | 100 | yes | isolated |
| orchestration | (none) | 40 | no | project |

Agent-level constraints override species defaults. If an agent declares `constraints.max_turns: 5`, that overrides the species default.

---

## Upgrade Opportunities for BrainStormer

1. **Agent Species Classifier** — Add to the Ideation sub-skill: before project scaffolding, classify the problem as software-shaped, metric-shaped, or workflow-shaped. Route to the appropriate workflow pattern.

2. **Planner-Executor Mode** — Evolve the Kernel beyond manual chunk decomposition. Let the planner agent generate and assign chunks, with human approval as a gate before execution begins.

3. **Dark Factory Pipeline** — For high-trust, well-eval'd projects: spec → autonomous chunk execution → PALADIN eval → human review only on failures. Skip the per-chunk human check-in.

4. **Auto-Research Integration** — For projects like Triangulate where you're optimizing algorithms, add a metric-driven experiment loop that hill-climbs toward better scores.

5. **Species-Aware Routing in the 735 Agents** — Tag agents by which species they best serve. A "code reviewer" agent is a coding harness tool. A "conversion optimizer" agent is auto-research. A "researcher → writer" pipeline is orchestration.
