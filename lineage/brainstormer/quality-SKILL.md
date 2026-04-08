---
name: quality
description: >
  PALADIN quality gatekeeper. Two-stage system: Stage 1 checks spec compliance (pass/fail,
  blocks everything on failure). Stage 2 scores project health 0-100 across 6 tiers.
  Issues verdict: SHIP IT / SHIP WITH CAUTION / NOT READY / BLOCKED.
  Evidence Before Claims: every finding must cite the file, line, and what was expected
  vs what was found. No "looks good" without proof.
  Trigger on: "test", "QA", "ship it", "deploy", "is this ready", "paladin", "quality check".
  NOT for: code explanation (Comprehension), brainstorming (Ideation), design (Design).
---

# Quality (PALADIN) — Ship Gate

## The Principle

Nothing ships unexamined. Catch the dumbest problems first so you never waste time
debugging a subtle race condition when the real issue was a typo. Each tier is a gate.
If a gate fails, you stop, fix, and re-run. You do NOT skip ahead.

## Evidence Before Claims

Every PALADIN finding — at any stage, any tier — must cite evidence. Not summaries.
Not impressions. The actual proof.

**Required for every finding:**
1. **File and line** — where the issue lives
2. **Expected** — what the spec, standard, or convention requires
3. **Found** — what actually exists in the code
4. **Verdict** — PASS, FAIL, or WARN with the specific gap stated

**Why this rule exists:** LLMs are confident. Confidence is not evidence. A model can
say "the auth middleware correctly validates tokens" without having read the middleware.
PALADIN does not accept claims. It accepts file paths, line numbers, and diffs between
expected and found.

**The enforcement:** If a Stage 1 or Stage 2 check cannot produce a file:line citation
for a finding, that check is INCOMPLETE, not PASS. Absence of evidence is not evidence
of compliance.

---

## TRIGGER

- "test", "QA", "ship it", "deploy", "is this ready"
- "paladin", "quality check", "quality audit", "run quality"
- `brainstormer quality run` (CLI command)

## ANTI-TRIGGER — do NOT fire Quality when:

- Explaining code → use Comprehension
- Generating ideas → use Ideation
- Visual/UI direction → use Design
- Research/experimentation phase → use Auto-Research
- Already passed a formal third-party audit → note it, don't re-audit

---

## INPUT CONTRACT

| Input | Source | Required? |
|-------|--------|-----------|
| Project codebase | Filesystem scan | Yes |
| `CLAUDE.md` | Project root | Recommended |
| `ARCHITECTURE.md` | Project root | Optional (integrity checks) |
| `paladin.config.json` | Project root | Optional (custom thresholds) |
| `.brainstormer-quality-history` | Project root | Optional (trend data) |
| Pattern registry | `docs/codeglass/patterns.md` | Optional (anti-patterns) |
| CRUCIBLE falsifiable claims | From CRUCIBLE Phase 3 | Optional (→ test cases) |

## OUTPUT CONTRACT

| Output | Path | Consumer |
|--------|------|----------|
| Score (0-100) | Console + JSON | User, wrapup |
| Verdict (SHIP IT / CAUTION / NOT READY / BLOCKED) | Console + JSON | User, wrapup |
| Findings by severity (P0-P3) | Console + JSON | User |
| History entry | `.brainstormer-quality-history` (append) | Future quality runs, init trend |

---

## INTERCONNECTIONS

```
← Fed by:
  CRUCIBLE        → falsifiable claims → test case generation (Tier 2-3 future)
  COMPREHENSION   → pattern registry (anti-pattern detection)
  KERNEL          → ARCHITECTURE.md (integrity check baseline)
  AUTO-RESEARCH   → improved metrics (new quality baseline)

Feeds →:
  WRAPUP          → score + verdict captured in CLAUDE.md Last Session
  AUTO-RESEARCH   → baseline metrics for optimization loops
  OBSIDIAN        → score trend on project dashboard
```

## OBSIDIAN

| Direction | What | Vault Path |
|-----------|------|-----------|
| Project → Vault | Quality score + trend | `vault/projects/{name}/dashboard.md` |
| Project → Vault | Findings summary | Referenced in vault project page |

---

## Stage 1: Spec Compliance (Pass/Fail Gate)

Stage 1 answers one question: **did we build what was asked for?**

This is a binary gate. PASS or FAIL. No score, no gradient, no "close enough."
If Stage 1 fails, Stage 2 never runs — there is no point scoring code quality
of the wrong implementation.

### When Stage 1 Applies

Stage 1 fires when there is a **spec to check against.** The spec can be:

- `SPEC.md` in the project root (full project specification)
- A task description from the kernel's orchestration (what Challenge decided)
- An explicit user request with verifiable requirements
- A linked issue or PR description with acceptance criteria

If no spec exists (e.g., exploratory work, first-time init, free-form coding),
Stage 1 is SKIPPED with a note: "No spec to check against — Stage 1 skipped."
This is not a pass. It is an explicit acknowledgment that compliance cannot
be verified.

### What Stage 1 Checks

For each requirement in the spec:

| Check | Method | Verdict |
|-------|--------|---------|
| **Requirement exists in code** | Read the implementation. Find the code that fulfills this requirement. Cite file:line. | PASS if found with citation. FAIL if not found. |
| **Requirement is complete** | Does the implementation cover the full requirement, not a partial version? | PASS if complete. FAIL if partial (state what's missing). |
| **No extra scope** | Did the implementation add things the spec didn't ask for? | WARN if extra scope detected (state what was added). |
| **Behavior matches** | If the spec describes behavior (input → output, user flow, error handling), does the code produce that behavior? | PASS if behavior matches. FAIL if divergent (state expected vs found). |

### Stage 1 Output

```
STAGE 1: SPEC COMPLIANCE
Spec source: SPEC.md (or task description, or user request)

Requirement 1: "API must return 429 on rate limit"
  → PASS: src/middleware/ratelimit.ts:42 — returns 429 with Retry-After header

Requirement 2: "Rate limit config from environment"
  → FAIL: Rate limit is hardcoded at src/middleware/ratelimit.ts:8 (const LIMIT = 100)
    Expected: reads from process.env.RATE_LIMIT
    Found: hardcoded constant

Requirement 3: "Log rate limit events"
  → FAIL: No logging found in ratelimit.ts or any imported module

VERDICT: FAIL (2 of 3 requirements not met)
Stage 2 will not run. Fix spec violations first.
```

### Stage 1 Rules

1. **Do Not Trust the Report.** If an agent or the kernel claims "requirement
   implemented," Stage 1 must independently verify by reading the code. The
   claim is not evidence. The file:line is evidence.

2. **Read, don't infer.** Stage 1 reads the actual implementation files. It does
   not infer compliance from test names, commit messages, or file existence.
   A file called `ratelimit.ts` might not implement rate limiting.

3. **Partial is FAIL.** A requirement that is 80% implemented is not 80% passed.
   It is FAIL with a note about what's missing. The user can decide to accept
   partial — PALADIN does not decide for them.

4. **Extra scope is WARN, not FAIL.** Building more than asked is not a spec
   violation, but it should be surfaced. Extra scope may indicate scope creep,
   misunderstood requirements, or gold-plating.

5. **Stage 1 failure blocks Stage 2.** The 6-tier gauntlet does not run until
   Stage 1 passes. This prevents wasting time scoring the quality of code
   that doesn't meet the spec. Fix the spec violations, re-run PALADIN.

---

## Stage 2: The 6 Tiers (Implemented)

These are the actual tiers executed by `brainstormer quality run` (cli/commands/quality.py).
Stage 2 only runs after Stage 1 passes (or is skipped due to no spec).

### Tier 1: Governance Structure
Checks presence of governance files: CLAUDE.md, SPEC.md, SCENARIOS.md, ARCHITECTURE.md,
AGENTS.md, CODEGUIDE.md, ART.md, CONTEXT.md, SNIFFTEST.md, README.md, paladin.config.json.
**Score:** files_present / files_total.

### Tier 2: Code Hygiene
Scans source files (.py, .js, .ts, .jsx, .tsx, .go, .rs, .rb) for TODO and FIXME comments.
Skips: .git, node_modules, __pycache__, .next, dist, build, venv, tests.
**Score:** 0 issues = 100%, 1-10 = 90%, 11-20 = 80%, >20 = 60%.

### Tier 3: Dependency Health
Checks for dependency declarations (package.json, pyproject.toml, Cargo.toml, go.mod, etc.)
and corresponding lockfiles (package-lock.json, poetry.lock, Cargo.lock, etc.).
**Score:** deps + lockfile = 100%, deps without lockfile = 50% (P1), no deps = 100%.

### Tier 4: Test Presence
Counts test files (test_*.py, *.test.ts, *.spec.js, *_test.go, *_test.rs, etc.)
relative to source files.
**Score:** ratio >0.3 = 100%, 0.1-0.3 = 70%, <0.1 = 40%, 0 tests = 0% (P1).

### Tier 5: Git Health
Checks: .git exists, .gitignore present, uncommitted changes count.
**Score:** no git = 0% (P1), no .gitignore = 60% (P2), >50 uncommitted = 60% (P2),
>20 = 80%, else = 100%.

### Tier 6: Entropy Score
Checks for dangerous patterns: .env not in .gitignore (P0, -30 points), build artifacts
(dist/, .next/, node_modules/) not ignored (-5 each).
**Score:** 100 minus deductions, minimum 0.

---

## Stage 3: Adversarial Verification

Stage 3 answers the hostile question: **"How does this break?"**

Stages 1 and 2 are cooperative — they check if you built the right thing
and built it well. Stage 3 is adversarial. It actively tries to break the
code using the same techniques that production, malicious users, and edge
cases will use.

Full technique reference: `references/adversarial-techniques.md`

### The Five Attack Surfaces

| Surface | What breaks | Example technique |
|---------|------------|-------------------|
| **Boundary** | Where code meets the unknown | Empty strings, MAX_INT+1, null where object expected, emoji in names |
| **State** | Where state accumulates or leaks | Race conditions, partial failures, stale cache, 1000x accumulation |
| **Dependency** | Where external things fail | API down, 30s latency, wrong schema, connection pool full |
| **Logic** | Where intent ≠ implementation | Off-by-one, inverted conditions, missing else/default, semantic gaps |
| **Security** | Where developers forget | Injection, auth bypass, IDOR, secrets in error messages, insecure defaults |

### When Stage 3 Runs

- After Stage 2 passes (code is spec-compliant and well-built)
- On request: "try to break this", "adversarial check", "red team"
- When the kernel's Confirm phase detects Risk Awareness signals
- When the change touches auth, payments, data models, or external APIs

### When Stage 3 is Skippable

- Documentation-only changes
- Config/copy changes with no logic
- User explicitly says to skip adversarial check
- Stage 2 score < 60 (fix quality basics first — no point attacking fragile code)

### Stage 3 Output

Every attack reports evidence — same as the Evidence Before Claims rule:

```
ATTACK: Boundary — Numeric limits
TARGET: src/billing/calculate.ts:28
TECHNIQUE: Pass quantity = -1 to calculateTotal()
EXPECTED: Rejection or error
FOUND: Returns negative total — no validation
IMPACT: Financial — negative totals credit accounts
SEVERITY: P1
```

Clean findings also report what was checked:

```
ATTACK: Injection — SQL
TARGET: src/api/users.ts (8 query calls)
TECHNIQUE: Searched for string concatenation in queries
FOUND: All queries parameterized via ORM
CONFIDENCE: High
```

### Stage 3 Verdicts

| Result | Verdict | Effect |
|--------|---------|--------|
| No P0/P1 attacks succeeded | **SURVIVES** — code is adversarially verified | Confidence report attached |
| P2+ attacks succeeded | **SURVIVES WITH NOTES** — minor hardening suggested | Ship decision is user's |
| Any P1 attack succeeded | **VULNERABLE** — significant weakness found | Fix recommended before ship |
| Any P0 attack succeeded | **COMPROMISED** — critical exploit path found | Fix required. BLOCKED. |

---

## Verdicts

### Stage 1 Verdicts

| Condition | Verdict | Effect |
|-----------|---------|--------|
| All requirements PASS | **SPEC COMPLIANT** | Proceed to Stage 2 |
| Any requirement FAIL | **SPEC VIOLATION** | Stage 2 blocked. Fix and re-run. |
| No spec available | **SPEC SKIPPED** | Proceed to Stage 2 with note |

### Stage 2 Verdicts

| Condition | Verdict |
|-----------|---------|
| Any P0 finding | **BLOCKED** — critical issue, fix immediately |
| Any P1 finding | **WARN** — fix this sprint |
| Score >= 80 | **SHIP IT** |
| Score 60-79 | **SHIP WITH CAUTION** |
| Score < 60 | **NOT READY** |

---

## Severity Levels

- **P0 Critical** — BLOCK. Security exposure, secrets in repo. Fix before anything else.
- **P1 High** — WARN. No tests, no lockfile, no git. Fix this sprint.
- **P2 Moderate** — INFORM. Too many TODOs, no .gitignore, high uncommitted count.
- **P3 Incremental** — SUGGEST. Minor hygiene. Nice to have.

---

## The Three-Stage Pipeline

```
Stage 1: Spec Compliance (pass/fail)
  ↓ PASS
Stage 2: 6-Tier Gauntlet (score 0-100)
  ↓ PASS
Stage 3: Adversarial Verification (attack/survive)
```

Stage 1 asks: "Did we build the right thing?"
Stage 2 asks: "Is the thing built well?"
Stage 3 asks: "Can the thing be broken?"

Each stage gates the next. The order matters: there is no value in attacking
code that doesn't meet spec, and no value in attacking code that has basic
quality problems. Fix the foundation first, then stress it.

## Future Roadmap

The following tiers are documented in the original PALADIN philosophy but are NOT yet
implemented in `quality.py`. They represent the aspiration for deeper automated testing:

- **Static Analysis** — Linting, type checking, build verification
- **Unit Tests** — Function-level correctness, edge cases, coverage gates
- **Integration Tests** — Component interaction, API contracts, state management
- **UI/UX Verification** — Accessibility, responsive, visual regression
- **Performance & Security** — Bundle analysis, Lighthouse, security scans
- **Human Wall** — Manual QA checklists (generated, human-executed)

Auto-bootstrap scripts for these tiers exist at `scripts/paladin-bootstrap.sh` and
stack-specific references exist in `references/` (react-vite.md, python.md, rust.md, etc.).

---

## REFERENCE FILES

- `references/adversarial-techniques.md` — Stage 3: Five attack surfaces, adversarial mindset, thinker integration
- `references/universal.md` — Stack-agnostic checks (always applies)
- `references/entropy-audit.md` — Entropy scoring algorithm (detailed)
- `references/severity-tiers.md` — P0-P3 classification protocol
- `references/config-schema.md` — paladin.config.json schema
- `references/react-vite.md` — React + Vite test setup- `references/python.md` — Python test setup- `references/rust.md` — Rust test setup- `references/static-site.md` — Static site checks- `references/supabase.md` — Supabase backend checks
## TEMPLATES

- `templates/paladin-config-default.json` — Default config
- `templates/human-qa-checklist.md` — Tier 6 human checklist (future)
