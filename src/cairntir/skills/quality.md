---
name: quality
description: >
  The ship gate. Two-stage audit: Stage 1 is compliance (pass/fail, blocks
  everything on failure). Stage 2 is a 0–100 health score across six tiers
  with findings at P0–P3 severity. Every finding must cite file:line or a
  drawer id — no claims without evidence. Ends with a verdict: SHIP IT /
  SHIP WITH CAUTION / NOT READY / BLOCKED.

  Trigger on: "audit this", "is it ready", "ship it", "quality check",
  "run quality", "is this good".
---

# QUALITY — The Ship Gate

## The Principle

**Nothing ships unexamined.** Catch the dumbest problems first so you never
waste an hour debugging a subtle race condition when the real issue was a
typo. Each tier is a gate. If a gate fails, you stop, fix, and re-run. You
do NOT skip ahead.

## Evidence Before Claims

Every finding — at any stage, any tier — must cite evidence:

1. **Location** — file path and line number, or a Cairntir drawer id.
2. **Expected** — what the spec, standard, or convention requires.
3. **Found** — what actually exists.
4. **Verdict** — PASS, FAIL, or WARN with the specific gap stated.

**Why this rule exists:** LLMs are confident. Confidence is not evidence.
A model can say "the auth middleware correctly validates tokens" without
having read the middleware. Quality does not accept claims — it accepts
file paths, line numbers, drawer ids, and diffs between expected and found.

**Enforcement:** if a check cannot produce a citation, that check is
**INCOMPLETE**, not PASS. Absence of evidence is not evidence of compliance.

---

## ANTI-TRIGGER

Do NOT fire Quality when the user is:

- Exploring ideas — they want ideation, not a ship gate.
- Asking "what is this" — they want explanation.
- In the middle of a spike — score is meaningless on unfinished work.
- Already carrying a passing external audit — note it, don't re-audit.

---

## STAGE 1 — COMPLIANCE (Pass/Fail)

Stage 1 is binary. Any failure blocks Stage 2. The point is to catch the
cheap, loud problems before spending effort on subtle ones.

| # | Check                              | Pass condition                                                    |
|---|------------------------------------|-------------------------------------------------------------------|
| 1 | **Project identity**               | `CLAUDE.md` exists, Last Session block is current                 |
| 2 | **Build**                          | `uv sync` clean, lockfile stable                                  |
| 3 | **Lint**                           | `ruff check` zero warnings                                        |
| 4 | **Format**                         | `ruff format --check` zero changes                                |
| 5 | **Types**                          | `mypy --strict` zero errors                                       |
| 6 | **Tests**                          | `pytest` all green                                                |
| 7 | **Coverage**                       | At or above the configured `--cov-fail-under` threshold           |
| 8 | **No silent excepts**              | `ruff BLE` clean; no `except: pass` anywhere                      |
| 9 | **No hardcoded paths**             | No absolute paths outside `config.py`; uses `platformdirs`/env    |
| 10| **Conventional commits**           | All commits on the branch match `feat:/fix:/docs:/chore:/...`     |

**Any FAIL here → verdict is BLOCKED. Stop, fix, re-run.**

---

## STAGE 2 — HEALTH SCORE (0–100)

Six tiers, weighted. Each finding carries a severity. Findings subtract
from the per-tier budget; the total across tiers yields the score.

| Tier | Name                 | Weight | Focus                                                       |
|------|----------------------|--------|-------------------------------------------------------------|
| T1   | **Correctness**      | 25     | Behavior matches spec; tests exercise the claim             |
| T2   | **Architecture**     | 20     | Boundaries clean; single source of truth; ADRs present      |
| T3   | **Security**         | 15     | OWASP top-10, secret handling, input validation             |
| T4   | **Performance**      | 10     | Budgets met, no obvious N+1, profiling where relevant       |
| T5   | **Ergonomics**       | 15     | Readable, docstrings, error messages surface context        |
| T6   | **Memory discipline**| 15     | Cairntir drawers current; identity/essential layers healthy |

**Cairntir bonus:** T6 is what makes Quality *cairntir-native*. A codebase
with a perfect test suite but a stale `CLAUDE.md` and an empty identity
layer is failing the North Star even if every other tier is green.

### Severity model

| Sev | Meaning                                      | Budget hit        |
|-----|----------------------------------------------|-------------------|
| P0  | Ship-blocker. Data loss, security, crash.    | Caps tier at 0    |
| P1  | Serious. Likely to cause user harm if shipped| −8 from tier      |
| P2  | Notable. Should be fixed this cycle          | −3 from tier      |
| P3  | Nit. Fix opportunistically                   | −1 from tier      |

### Verdict

| Score  | Verdict              |
|--------|----------------------|
| 90–100 | **SHIP IT**          |
| 75–89  | **SHIP WITH CAUTION**|
| 60–74  | **NOT READY**        |
| <60    | **BLOCKED**          |

Any `P0` anywhere in Stage 2 overrides the numeric verdict to **BLOCKED**
regardless of score.

---

## FINDING FORMAT

Every finding, every tier, this exact shape:

```
[T3 · P1] mcp/backend.py:58
  Expected: metadata validated against JSON-serializable shape
  Found:    accepts arbitrary dict without schema check
  Drawer:   #42  (crucible note on MCP input safety)
  Action:   add pydantic model at the boundary
```

If the evidence is a drawer (not a file), cite `drawer #N` in place of the
file:line. Either is acceptable; neither is optional.

---

## MEMORY LOOP

At the end of a Quality run, persist the result so the next session knows:

```
cairntir_remember(
  wing=<project>,
  room="audits",
  content="<score>/100 — <verdict>.\n<top 3 findings>",
  layer="essential",
  metadata={"phase": "quality", "score": <int>, "verdict": "<verdict>"},
)
```

Essential layer so it loads automatically on `cairntir_session_start`. That
way the next chat knows the current ship state without a re-audit.

---

## HANDOFF

Quality consumes Crucible's falsifiability contracts as Tier 1/2 test
anchors, and writes its verdicts back as drawers so Reason can cite them.
It does not explain code, generate ideas, or design UIs — it only decides
whether the current state is ready to ship, and if not, exactly why not.
