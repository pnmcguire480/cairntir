# CLAUDE.md — Project Intelligence

> 🔄 **UPDATE FREQUENCY: EVERY SESSION**
> This is the first file any AI agent reads when entering this project. Update it at the start and end of every working session. Stale information here cascades into bad decisions everywhere.
>
> **Related files:** All other docs reference this file as the entry point. See the file index at the bottom.

---

## Project Identity

- **Name:** BrainStormer
- **One-Liner:** A free, open governance standard for AI-assisted development. Ship responsibly.
- **Repo:** github.com/pnmcguire480/brainstormer
- **Live URL:** N/A (CLI tool, pip-installable)
- **Owner:** Patrick McGuire
- **Stage:** [ ] Concept [ ] Planning [ ] Scaffolding [x] Building [ ] Testing [ ] Deployed [ ] Iterating [ ] Maintained

---

## What This Is

BrainStormer is a pip-installable CLI governance system for AI-assisted development. Two commands (`init` and `wrapup`) bookend every AI session. Init reads where you left off and runs the right skill automatically. Wrapup captures state, detects drift, and syncs to Obsidian. It has 8 skills (Crucible, Kernel, Comprehension, Ideation, Design, Quality, Auto-Research, HumanFlow), 571 agents, and 20+ CLI commands. Free, open, built on The Stewardship Commonwealth.

---

## What This Is NOT

<!-- Guardrails that prevent scope creep. List things this project should never try to do or become. Be specific. These are as important as the features list. -->

- Not a chatbot or conversational AI product
- Not a code completion tool (use Copilot/Continue for that)
- Not an agent runtime — it produces and manages agents, it does not host them
- Not a project management app — it scaffolds docs, it doesn't track tickets
- Not a SaaS platform — it's a CLI tool the developer owns and runs locally

---

## Current State

<!-- This section is the most frequently updated part of the entire system. Treat it as a living journal. -->

### Last Session

- **Date:** 2026-04-08
- **What was accomplished:**
  - Work in progress (57 uncommitted files)
- **Files changed:** 0 files across 0 commits
- **Uncommitted changes:** 57 files
- **Next session should start with:** Continue from where you left off

### What Works Right Now

- 8 skills: Crucible, Kernel, Comprehension, Ideation, Design, Quality, Auto-Research, HumanFlow
- 20+ CLI commands (init, wrapup, quality, status, doctor, sync, update, learn, agent, retro, etc.)
- 571 agents at `c:\Dev\agents\agents\` (6 species, P0-P3 severity, 14 categories)
- Obsidian vault sync (one-way, 50+ projects registered)
- Self-learning rules with confidence scoring
- Free and open — no tiers, no gates, no paywalls
- GitHub Actions CI/CD (test on push, release on tag)
- 9 slash commands for Claude Code plugin (init, crucible, quality, comprehend, ideate, design, wrapup, research, humanflow)
- 12 MCP tools (JSON-RPC over stdio: init, quality, agent_list, wrapup, status, research_scaffold, crucible, doctor, sync, learn, retro, hooks)
- Crucible (epistemic forge — assumption testing, upstream of all skills)
- Auto-Research framework (Karpathy-style experiment loops)

### What's Broken Right Now

- Silent error handling (180+ `except: pass` blocks) — errors swallowed across init, wrapup, vault, scaffold
- Hardcoded magic thresholds in detector.py (no named constants)
- vault.py `wiki_link_audit()` incomplete — will crash if called
- vault.py `sync_vault_to_project()` has TODO stubs
- Duplicate regex patterns in init.py (lines 69 & 88)
- YAML import inconsistency — registry.py has fallback, vault.py doesn't
- 2 hardcoded paths in audit scripts (cli/audit_frontmatter.py, cli/tools/audit_agent_content.py)

### What's Blocked

<!-- Things that can't proceed until something else happens -->

| Blocked Item | Waiting On | Since |
|-------------|-----------|-------|
|             |           |       |

### Active Branch

- **Branch name:**
- **Purpose:**
- **Merge target:**

---

## AI Agent Rules

These rules apply to ALL AI agents at ALL tiers working on this project.

### Must Do

1. **Read this file first.** Every session. No exceptions.
2. **Read ETHOS.md second.** The 5 principles (Comprehension Before Code, Quality Has No Shortcuts, Ideas Compound, User Sovereignty, Structured Completeness) guide all decisions.
3. **Match existing patterns.** Look at the codebase before writing new code. Follow what's already there.
3. **Small changes, frequent commits.** Don't rewrite the world in one pass.
4. **Update this file** at the end of every session — at minimum, the "Last Session" section.
5. **Check CODEGUIDE.md** before writing code for naming conventions, file structure, and style rules.
6. **Respect tier boundaries.** See AGENTS.md. If the task is above your tier, escalate.

### Must Not

1. **Never read SNIFFTEST.md.** That file is for human testing only. Coding to the test defeats the purpose.
2. **Never hallucinate dependencies.** If a package isn't in package.json (or equivalent), don't assume it's installed.
3. **Never refactor without permission.** Ask before restructuring files, renaming things, or changing patterns.
4. **Never remove comments or TODOs** unless explicitly instructed.
5. **Never install new dependencies** without the human's approval.
6. **Never delete files** without the human's approval.
7. **Never modify CLAUDE.md's rules section, AGENTS.md, or SNIFFTEST.md** without the human's approval.

### When Uncertain

- **Stop and ask.** A question is always better than a wrong assumption.
- **Present options.** Don't make unilateral decisions on things with tradeoffs.
- **Escalate to the next tier** if the task exceeds your capability or scope.

---

## Skill Routing

When a request arrives, route to the right skill:

| User Intent | Route To | Agent |
|------------|----------|-------|
| "brainstorm this", "give me angles", "expand this idea" | Ideation chain | `/brainstormer:ideate` |
| "explain this code", "walk me through this", "how does this work" | CodeGlass | `/brainstormer:comprehend` |
| "test this", "is this ready", "quality check", "review this" | PALADIN | `/brainstormer:quality` |
| "start a new project", "scaffold this", "init" | Kernel (BabyTierOS) | `/brainstormer:init` |
| "stress test assumptions", "what could be wrong" | Crucible | `/brainstormer:crucible` |
| "design review", "check the UI", "brand consistency" | Design | `/brainstormer:design` |
| "research loop", "optimize this metric" | Auto-Research | `/brainstormer:research` |
| "humanflow", "write like a human", "sound natural", "remove AI voice" | HumanFlow | `/brainstormer:humanflow` |
| "save session", "end of day", "context switch" | Wrapup | `/brainstormer:wrapup` |
| "sync vault", "obsidian" | Vault sync | CLI: `brainstormer sync` |
| "what did we do", "retrospective" | Retro | CLI: `brainstormer retro` |

---

## Context Window Management

<!-- Tell AI agents what to load and what to skip. Prevents wasting tokens on irrelevant files. -->

### Always Load (Every Session)

- CLAUDE.md (this file)
- ETHOS.md (the 5 principles that shape all BrainStormer work)
- SPEC.md (know what you're building)
- CODEGUIDE.md (know how to write code here)

### Load When Relevant

- ARCHITECTURE.md (when making tech decisions or touching infrastructure)
- AGENTS.md (when unclear about role boundaries)
- ART.md (when building UI components)
- SCENARIOS.md (when implementing user-facing flows)
- CONTEXT.md (when you need background on why something exists)

### Never Load

- SNIFFTEST.md (human eyes only — always)
- node_modules/, .next/, build/, dist/ (generated directories)
- .env files (sensitive data)

---

## Session Handoff Protocol

When ending a session (regardless of tier):

1. Update "Last Session" above with what happened
2. Note any open questions or unresolved decisions
3. If mid-feature, describe exact stopping point and next steps
4. If a bug was introduced, describe it in "What's Broken"
5. Commit changes with a descriptive message

When starting a session (regardless of tier):

1. Read this file completely
2. Check the "Last Session" section for continuity
3. Read any files listed in "Always Load"
4. Confirm understanding before writing code
5. If anything is unclear, ask before proceeding

---

## 🚨 KNOWN ISSUE / TOP-PRIORITY FIX: Cross-chat amnesia is not solved

**Reported by:** Patrick McGuire, 2026-04-08, live during a STARS 2026 Atom 3 planning session.

**The problem, in Patrick's words:**

> "I'll forget.. just like you from chat to chat I get messed up and off track
> because you do. We are working like amnesia gets us, and I made BrainStormer
> to fix that, and it don't really help.. make a note in brainstormer .claude
> file to fix this lack of declared memory between chats is not working."

**Diagnosis:**

BrainStormer was built specifically to solve the cross-conversation amnesia problem — the fact that Claude loses context between chats and drifts off track, and that Patrick loses track of what was decided, deferred, or in-flight. In practice, the current tools are NOT closing the gap. Specifically:

1. **`.brainstormer/session.json` is local-only** and not reliably read at the start of new sessions.
2. **CLAUDE.md's "Last Session" block is hand-updated and narrative**, so it's only as current as the last person to remember to update it, and too prose-heavy to scan for open questions.
3. **Claude's auto-memory (`~/.claude/projects/.../memory/`) is opt-in on Claude's side** — Patrick has no visibility into what was saved vs. what was silently dropped.
4. **Deferred decisions have no durable home.** If Claude says "I'll remember this for next session," that promise is fiction. It is remembered only if someone writes it into a file that the next session will definitely read.
5. **Wake-up reports live in per-atom docs,** so each new session has to already know where to look — a failure mode that defeats the purpose.
6. **The council → atoms → sniff → commit loop is solid WITHIN a session but brittle ACROSS sessions.** The handoff is the weak link.

**Workaround already installed in STARS 2026 (2026-04-08):**

A `BACKLOG.md` at the repo root, read after CLAUDE.md, is the durable list of deferred work. Rule: write entries BEFORE the chat ends, not after. This is a patch, not a fix, and it's hand-maintained — exactly the thing BrainStormer should be automating.

**Design directions for a real fix (for a future BrainStormer design pass — unprioritized):**

- A **session-start agent** whose only job is: read all state, summarize "here's where you are / here's what's pending / here's what was decided last," produce a one-screen briefing. Runs unconditionally before any other work.
- A **session-close agent** whose only job is: detect deferred items, pending decisions, and unanswered questions from the conversation, and write them to a well-known location before the chat ends. Runs unconditionally at session end, even on abrupt close.
- A **machine-readable `open-questions.yaml`** that any agent can append to when it punts a decision. The session-start agent surfaces every entry until it's explicitly resolved.
- An **explicit "what you promised to do next time" contract** written to a durable file at every session close. If the next session doesn't read it first, it blocks.
- **Stop relying on CLAUDE.md's "Last Session" block being manually accurate.** Generate it from a structured log.
- **Observable memory** — give Patrick a command like `brainstormer remember` that prints every memory the agent has stored about this project, so "silent auto-memory" becomes visible.

**Priority:** HIGHEST. Patrick is losing work to this, and every other BrainStormer feature matters less than fixing this one gap. If BrainStormer doesn't solve amnesia, it isn't doing its core job.

---

## File Index

| File | What It Covers | When to Reference |
|------|---------------|-------------------|
| **CLAUDE.md** | Project state, AI rules, session handoffs | Every session (you're here) |
| **SPEC.md** | User stories, features, acceptance criteria | Before building any feature |
| **SCENARIOS.md** | User flows, journeys, edge cases | When implementing UX flows |
| **ARCHITECTURE.md** | Tech stack, data model, APIs, deploy pipeline | Technical decisions |
| **AGENTS.md** | Tier assignments, escalation, handoff rules | Role clarity |
| **CODEGUIDE.md** | Naming, style, file structure, git workflow | Before writing any code |
| **ART.md** | Colors, typography, layout, component styles | Building any UI |
| **CONTEXT.md** | Why this exists, domain knowledge, stakeholders | Background and motivation |
| **SNIFFTEST.md** | Human-only test scenarios | ⛔ NEVER (AI agents) |
| **README.md** | Public project overview | External communication |
