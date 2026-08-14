# AGENTS.md — Cairntir

> **`CLAUDE.md` in this directory is the single source of truth. Read it first.**
> It carries the project state, the current session log, and the full context
> every agent needs. This file exists because Codex and Cursor look for
> `AGENTS.md`; it is deliberately thin so it cannot drift away from `CLAUDE.md`
> the way it did between 2026-07-29 and 2026-08-02.

This file is host-neutral by design. Cairntir's whole purpose is that work moves
between Claude Code, Codex, Cursor and Qwen Code without a re-brief, so there is
one project brief, not four. Qwen Code reads `QWEN.md`, which is the same kind of
thin pointer as this file.

---

## Project Identity

- **Name:** Cairntir (*CAIRN-teer*)
- **Etymology:** Cairn (stacked waypoint stones marking a path) + Palantir
  (seeing-stone across time and distance). A stack of stones that sees across time.
- **One-liner:** Memory-first reasoning layer. Kills cross-chat AI amnesia.
- **Owner:** Patrick McGuire (@pnmcguire480)
- **License:** MIT
- **Repo:** `c:\Dev\Cairntir\` — https://github.com/pnmcguire480/cairntir
- **Published:** PyPI (`pip install cairntir`) and GitHub releases.

For stage, version, and what shipped last session, read `CLAUDE.md` and
`CHANGELOG.md`. Deliberately not restated here — a second copy of a moving
number is a second copy that goes stale.

---

## The North Star

> **Cross-chat AI amnesia is the problem. Everything Cairntir does serves killing it.**

A fresh chat opened in `c:\Dev\Cairntir\` on day 30 — in *any* host — should feel
like walking into a lit room. No re-briefing. No lost decisions. No "what were we
doing?"

This is the one test that matters. If a feature doesn't serve it, we don't build it.

---

## AI Agent Rules

These are stable. Anything that changes with the project lives in `CLAUDE.md`.

### Must Do

1. **Read `CLAUDE.md` first.** Every session. It is the current state of the world.
2. **Read `docs/manifesto.md` and `docs/concept.md`** before proposing any feature.
3. **Match the ethos.** See `ETHOS.md`. Comprehension before code. Quality has no
   shortcuts.
4. **Small commits, conventional format.** `feat:`, `fix:`, `docs:`, `chore:`,
   `test:`, `refactor:`.
5. **Every exception is typed and surfaced.** No silent `except: pass`. Ever. CI
   will fail you.
6. **Update the "Last Session" block in `CLAUDE.md`** at the end of every working
   session.
7. **Land work on `main` through a pull request.** Zero approving reviews are
   required — it is one click — and it keeps the full matrix green before `main`
   moves.
8. **Before closing a session, check `## [Unreleased]` in `CHANGELOG.md` for a
   `Fixed` entry a current user is hitting.** If there is one, that is a patch
   release now. See `docs/release-cadence.md`.

### Must Not

1. **Never import code from BrainStormer or MemPalace.** Lineage is reference
   material, not source. We reimplement.
2. **Never add a feature not in the plan** without updating the plan first.
3. **Never hardcode paths.** Use `Path.home()`, `platformdirs`, or config.
4. **Never add dependencies** not listed in `pyproject.toml` without discussion.
5. **Never modify `lineage/`** — it is read-only history.
6. **Never treat a changelog entry as a release.** Only a pushed `v*.*.*` tag
   publishes. This gap silently swallowed 1.0.1 and 1.1.3.
7. **Never propose `2.0.0` for a merely breaking change.** It is reserved for a
   revolutionary change in what Cairntir is.

### When Uncertain

- Stop and ask. A question is cheaper than a wrong assumption.
- Default to the simpler option. Cairntir's whole identity is distillation.

---

## Local Development Note

The maintainer's `cairntir-mcp` is an **editable install pointing at this repo**.
Every AI host loads Cairntir from this working tree, so *whatever branch is
checked out is what every agent runs*. Leave the repo on `main` at the end of a
session.

---

## Key Files

Read these in a fresh chat and you have full context. That is the sniff test.

1. `CLAUDE.md` — project state, current session, everything that moves
2. `docs/manifesto.md` — WHY Cairntir exists
3. `docs/concept.md` — WHAT Cairntir is (three ingredients)
4. `ETHOS.md` — the 5 principles
5. `docs/lineage/brainstormer.md` and `docs/lineage/mempalace.md` — what was kept
   and dropped from each predecessor
6. `HARNESS_AUDIT.md` — pointer to the BrainStormer harness audit in `lineage/`
7. `docs/release-cadence.md` — commit vs. merge vs. tag, and how a version is chosen
8. `plans/` — the live execution plans

<!-- cairntir:begin -->
# Cairntir — memory-first reasoning layer

You have access to persistent memory through the `cairntir_*` MCP tools.
At the start of every conversation:

1. Call `cairntir_handoff(wing)` with the wing matching the current project.
   Use the lowercase folder name in the working directory as the wing. If the
   correct wing is ambiguous, ask the user. Prefer this over
   `cairntir_session_start`: handoff returns whole drawers under a budget,
   including recent default-layer memories. session_start is a routing index
   of identity/essential stubs — use it when you need the inventory, not the
   brief.
2. Read the returned drawers before answering anything substantive.
3. Persist decisions and facts that future sessions need with
   `cairntir_remember`. Preserve the user's wording when it is load-bearing.
4. Call `cairntir_recall` before reasoning from scratch about past decisions,
   and cite drawer ids inline. Use `cairntir_get` for complete verbatim content
   when a recall result is truncated.
5. Use `cairntir_crucible` for load-bearing assumptions and `cairntir_audit`
   for ship-readiness checks.
6. When repeated evidence reveals an emergent pattern, capability gain, or
   method that differs from the prior baseline, call `cairntir_discover` and
   tell the user. Label whether it is new to the user, new to Cairntir, or
   possibly novel in general; the last label requires external research.
7. Capture-on-arrival: when the user makes a request that may not be fully
   executed within the current turn — work that starts later, a deferred task,
   a session about to end, restart, or compact — record it with
   `cairntir_remember` IMMEDIATELY, before doing any other work on it, in the
   user's exact wording. Never defer that write to the end of the turn or the
   session: a session can die between the request and the write, and capture
   that waits for a quiet moment never happens. Conversely, when resuming,
   treat open requests surfaced by the handoff as first-class owed work, not
   background noise.

If handoff returns no memory for an established wing, report that the
store may be new or misconfigured. Do not silently substitute model memory.

This policy is host-neutral: every agent must read and write the same Cairntir
store so work can move between Claude Code, Codex, Cursor, and Qwen Code
without a re-brief.
<!-- cairntir:end -->
