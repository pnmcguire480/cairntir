# PALADIN Severity Tiers: Leverage-First Agent Ordering

**Applies to**: All 735 existing agents + new agents
**Source Insight**: "Most performance work fails because it starts too low in the stack. If a request waterfall adds half a second, it doesn't matter how optimized your calls are." Vercel orders 40+ rules across 8 categories by impact. We do the same.

---

## The Problem

BrainStormer's 735 agents are curated but flat. When PALADIN runs a quality pass, it checks everything with equal weight. This means:

- A micro-optimization warning competes for attention with a critical waterfall detection
- Engineers (and AI) can "fix" 20 low-impact issues while missing the one that actually matters
- The illusion of progress: lots of green checkmarks, but the high-leverage problems persist

## The Fix: P0-P3 Severity Tiers

Every agent gets classified into exactly one tier. PALADIN runs tiers in order. Higher tiers must pass before lower tiers are even evaluated.

### P0 — Critical (Eliminate First)

**Definition**: Issues that make everything downstream irrelevant. Fixing P1-P3 issues while P0 issues exist is wasted work.

**Examples**:
- Request waterfalls in critical paths (checkout, auth, page load)
- Bundle size > threshold (shipping 300KB of JS makes micro-optimizations pointless)
- Missing error boundaries in production paths
- Security vulnerabilities (auth bypass, injection, data exposure)
- Broken caching (cache that never hits, like Nate's Example 2)
- Architectural boundary violations that create circular dependencies
- Data loss risks

**Agent behavior**: BLOCK. Cannot proceed until resolved or explicitly overridden via ADR.

### P1 — High (Fix This Sprint)

**Definition**: Issues that cause measurable degradation but don't invalidate all other work.

**Examples**:
- Inefficient data fetching (N+1 queries, over-fetching)
- Missing or broken memoization on genuinely expensive operations
- Event listener leaks (Nate's Example 1 — popup hooks multiplying)
- Synchronous operations that should be parallel
- Missing loading/error states in user-facing flows
- Abstraction opacity (functions > 200 LOC, deeply nested async)
- Pattern drift from ARCHITECTURE.md (non-blocking but tracked)

**Agent behavior**: WARN with fix guidance. Track in entropy dashboard. Escalate to P0 if unaddressed for 2 sprints.

### P2 — Moderate (Fix When Convenient)

**Definition**: Code quality issues that increase entropy but don't cause immediate user impact.

**Examples**:
- Inconsistent error handling patterns across modules
- Missing TypeScript strict mode in non-critical paths
- Unused dependencies in package.json
- Test coverage gaps in utility functions
- Inconsistent naming conventions
- Missing JSDoc on public APIs
- Code duplication (2-3 instances, not yet a pattern)

**Agent behavior**: INFORM. Include in entropy score calculation. Surface during refactor chunks, not feature chunks.

### P3 — Incremental (Nice to Have)

**Definition**: Polish and advanced optimizations that matter only after P0-P2 are clean.

**Examples**:
- Advanced rendering optimizations (virtualization, lazy loading non-critical components)
- Tree-shaking edge cases
- Micro-optimizations in non-hot paths
- Code style preferences beyond team conventions
- Advanced TypeScript type narrowing
- Perf optimizations on operations that aren't measured as bottlenecks

**Agent behavior**: SUGGEST. Only surface when explicitly requested or during dedicated optimization sprints. Never block shipping.

---

## Classification Protocol for Existing Agents

To classify the existing 735 agents:

### Step 1: Impact Test
Ask: "If this issue exists and we fix nothing else, does the user notice?"
- Yes, immediately → P0
- Yes, within days/weeks → P1
- Only if they're looking → P2
- Only in synthetic benchmarks → P3

### Step 2: Leverage Test
Ask: "Does fixing this make other fixes more effective?"
- Yes, dramatically → promote one tier (P2 → P1)
- No, it's isolated → keep current tier

### Step 3: Entropy Test
Ask: "Does this issue compound over time?"
- Yes, it gets worse as codebase grows → promote one tier
- No, it's stable → keep current tier

### Batch Classification Process

```
For each agent in the 735:
  1. Read agent description and trigger conditions
  2. Apply Impact Test → initial tier
  3. Apply Leverage Test → adjust if needed
  4. Apply Entropy Test → adjust if needed
  5. Tag agent with severity: P0 | P1 | P2 | P3
  6. Log classification rationale (one sentence)
```

Expected distribution (approximate):
- P0: ~50-80 agents (10%)
- P1: ~150-200 agents (25%)
- P2: ~250-300 agents (40%)
- P3: ~150-200 agents (25%)

---

## PALADIN Execution Order

```
QUALITY PASS:
  1. Run all P0 agents
     → If any BLOCK: stop here, report, require resolution
  2. Run all P1 agents
     → Report WARNs, track in dashboard
  3. Run P2 agents ONLY IF:
     → This is a refactor chunk, OR
     → All P0 and P1 are clean, OR
     → Explicitly requested
  4. Run P3 agents ONLY IF:
     → This is an optimization sprint, OR
     → Explicitly requested
```

## Metadata Format

Each agent's spec gets a new frontmatter field:

```yaml
---
name: "cache-referential-equality"
category: "performance"
severity: P1
severity_rationale: "Broken cache causes measurable perf degradation but doesn't invalidate other work"
escalation: "Promote to P0 if in critical path (checkout, auth, page load)"
---
```

## Governance

- Severity tiers are reviewed quarterly
- Agents that trigger frequently with no user-visible impact → demote
- Agents whose issues compound across modules → promote
- New agents default to P2 until validated with production data
- Team can override tier per-project via project-level config
