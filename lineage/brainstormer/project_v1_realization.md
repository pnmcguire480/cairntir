---
name: The real v1 — init as intelligent orchestrator, not toolbox
description: Fundamental product realization (2026-03-25): BrainStormer is 2 commands + Obsidian, not 12 commands + 402 agents
type: project
---

Patrick realized the core product gap during the oracle round table session (2026-03-25).

**What was built:** A toolbox with 12+ CLI commands, 402 agents, 5 sub-skills that users manually invoke. A template copier with documentation.

**What should have been built:** An intelligent orchestrator with 2 user-facing commands:

1. `brainstormer init` — reads the project, determines maturity/phase, and AUTOMATICALLY runs the right skill chain. New project → fires ideation → populates SPEC.md. Active project → fires comprehension → captures patterns. Mature → fires quality → runs audit. The user doesn't choose skills. Init chooses.

2. `brainstormer wrapup` — end-of-session capture. Updates CLAUDE.md, syncs to Obsidian, captures rules, flags drift.

**The real output is Obsidian:** Everything links via `[[wikilinks]]`. Rules → decisions → architecture → specs → ideation. The vault becomes a knowledge graph that evolves with each session. The second brain is the product. The CLI is just the pipe.

**The 5 skills are internal phases, not user-facing features.** The 402 agents are tools init calls when needed, not a catalog to browse. The governance files fill themselves through the process of building.

**Why:** Patrick's ethos (TSC) is about constraints that make responsibility harder to dodge. The tool should enforce the process by running it automatically, not by giving users a manual and hoping they follow it.

**How to apply:** Every future design decision should filter through: "Does the user need to know about this, or does init handle it?" If init handles it, it's internal machinery. If the user needs to know, it better be one of the 2 commands.
