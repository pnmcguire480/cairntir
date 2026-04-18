# Wings — state-of-each as of 2026-04-17

> Captured during the install-hardening + cold-start session. Every
> active wing is listed below with its current state, last
> identifiable milestone, and the next concrete step. Future Claude
> sessions in any of these projects can read this file as a fast
> sniff-test fallback, then call `cairntir_session_start` for the
> actual identity / essential drawers.
>
> Why this doc exists: Cairntir was effectively offline for a window
> (cold-start handshake timeout — fixed today as `d505e99`), so no
> drawers were captured for any project during that gap. This file
> closes the gap with a verbatim narrative; once the embedder warmup
> ships and the user runs Cairntir again in each project, drawers can
> be backfilled to memory directly.

---

## cairntir — `c:/Dev/Cairntir/`

**State:** Live on `main` at `d505e99`. v1.0.1 published behavior on
GitHub (PyPI still at 1.0.0). Two PRs landed today: install hardening
(#11, `9fdf678`) and cold-start handshake fix (#12, `d505e99`).
Tools loading correctly in fresh Claude Code sessions.

**Most recent work:** Embedder background warmup (this session, not
yet committed). Catches the second half of the cold-start problem —
`__init__` is fast, but the first `embed()` call still cold-loads
sentence-transformers. Warmup spawns a daemon thread post-handshake
so first `cairntir_remember` is also instant. ValidationError catch
in `_call` so invalid wing/room/content surfaces as a clean string
instead of crashing the tool call.

**Next concrete step:** v1.1 synergy stack — Cross-Wing Recall (#2),
Production Reason Loop (#1), Recipe Runtime (#3). Plan committed at
`plans/v1.1-synergy-stack.md`. Implementation order: #2 → #1 → #3.
Bundles with cold-start fix as 1.1.0; PyPI catches up.

---

## stars-2026 — `c:/Dev/STARS-2026/`

**State:** Active. Browser-native deterministic *Stars!* (1995)
remake. Atom C closed; Atom D in progress.

**Most recent commits:**
- `33e5748` — D.3: extend determinism fingerprint with resources +
  mining
- `912d6ff` — D.1+D.2: resource output + mineral extraction (FR-6/FR-7)
- `860b2be` — close Atom C, sync for Atom D
- `7ab4d5f` — C.6: extend determinism fingerprint with hab + growth
- `6cecf05` — C.3–C.5: max population + population growth (FR-5)

**Identity (from cairntir wing #1, #2):** STARS 2026 — browser-native,
deterministic, multiplayer-ready remake of Stars! (1995). Faithful 1995
recreation. Hard rules: sniff test after every function — 5 gates
(test, clippy, fmt, wasm32 check, wasm-pack test).

**Next concrete step:** Atom D continuation — D.4+ if D.1–D.3 are
landed. Resource generation (FR-6) and mineral extraction (FR-7)
shipped. Continue with whatever the BACKLOG marks as Atom D's next
sub-step.

---

## ground-zero — `c:/Dev/Ground Zero/`

**State:** Docs-driven project, no git repository at root. Has full
documentation suite (AGENTS / ARCHITECTURE / ART / CLAUDE / CODEGUIDE
/ CONTEXT / README / ROADMAP / SCENARIOS / SKILLS).

**Identity (from cairntir wing #14, #15):** Zombie apocalypse survival
RPG. Next.js 16 App Router, TypeScript strict, Zustand 5. Hard rules:
engine functions are pure (no React, no store imports), AI narrative
layer separate from engine.

**Next concrete step:** Unknown without reading the in-project
ROADMAP.md / CLAUDE.md. Suggested first action for next session:
`cat ROADMAP.md` then `cairntir_session_start ground-zero` to see
what was last decided.

---

## swarmcast — `c:/Dev/SwarmCast/`

**State:** Early stage. 4 commits to date, working on UI scaffolding.

**Most recent commits:**
- `e8c9737` — feat(ui): add onboarding, dashboard, CRUD, offline
  shell, and bottom nav
- `8dae673` — feat: scaffold Next.js app with auth, Supabase, PWA, CI
- `c2c0bba` — docs(claude): connect 15 beekeeping thinker agents to
  project
- `0576892` — feat: SwarmCast project foundation — complete spec and
  documentation suite

**Identity (from cairntir wing #27, #28):** Free beekeeping community
app by Patrick McGuire (Patrick IV). Mobile-first Next.js. Hard rules
came from April 2026 round table with all 15 beekeeping agents
(non-negotiable).

**Next concrete step:** Build out the UI scaffolding from `e8c9737`
into actual feature flows. Identity drawer #28 is the canonical
non-negotiables list — consult before any feature work.

---

## cort4congress — `c:/Dev/Cort4Congress/`

**State:** Pre-launch / launched. Full Spanish i18n, SEO audit, RSS,
automated event pipeline, accessibility passes done.

**Most recent commits:**
- `01e8245` — Full site audit: fix SEO, security, and link issues
- `ccce5d3` — Add automated event pipeline: daily rebuild + RSS
  event scanner
- `9ace1b3` — Data-driven events with auto-expire: add JSON, rebuild
  on each deploy
- `af77d43` — Pre-launch overhaul: full Spanish i18n, SEO audit, RSS
  feed, scaffold cleanup
- `29ef8ca` — Fix 5 Paladin a11y failures: contrast, focus, headings,
  keyboard nav

**Identity:** Not in cairntir wing yet — should be added on next
session in this folder. Likely a campaign site for Cortney
McGuire's congressional run (inferred from the project name).

**Next concrete step:** Whatever the next campaign milestone is — the
infrastructure (i18n, RSS, events, a11y) is mature. Likely content +
events ongoing.

---

## claude-arsenal — `c:/Dev/AGENTS/`

**State:** Major library. 660 agents + 1,344 skills as of latest
audit.

**Most recent commits:**
- `59505820` — fix: resolve agent-installer deploy collision in
  meta-orchestration
- `95179a69` — docs: reframe emergent-behavior callout from warning
  to methodology
- `ddbabc43` — feat: restructure thinkers into nested subcategories
  (+89 agents, 571→660)
- `70e0e243` — docs: update README with correct repo name and URLs
- `aa62284e` — feat: audit cleanup — normalize 571 agents, add 1,344
  skills, housekeeping

**Identity (from cairntir wing #35, #36, #57):** Claude Code agents &
skills library at `c:/Dev/AGENTS`. Emergent-behavior playbook: how to
invoke claude-arsenal agents with intent. Drawer #57 supersedes the
older #36 warning framing.

**Next concrete step:** No obvious gap from commit history — library
is being maintained. Likely incremental additions / curation as new
agents and skills land.

---

## video-capture — `c:/Dev/Video Capture/`

**State:** v0.1.0 scaffolded, single commit so far.

**Most recent commits:**
- `11c7f0d` — Initial commit: Video Capture v0.1.0

**Identity (from cairntir wing #61, #62):** Personal video
acquisition desktop app. Tauri (Rust backend + TypeScript frontend).
Hard rules: no AI/LLM dependencies — deterministic logic only. AI is
not needed for video acquisition.

**Next concrete step:** Build past the scaffold. Identity drawer #62
is the constraint manifest — every feature must pass "deterministic,
no AI" check.

---

## transcript-capture — `c:/Dev/Transcript Capture/`

**State:** Working v1 pipeline.

**Most recent commits:**
- `3ddb590` — feat: v1 — working transcript capture pipeline
- `8ca0db9` — feat: initial scaffold — Transcript Capture v0.1.0

**Identity (from cairntir wing #63, #64):** Personal transcript
acquisition desktop app. Sister to Video Capture. Tauri (Rust backend
+ TypeScript frontend). Hard rules: local AI is embraced — Whisper.cpp
for transcription, Gemma for summarization (note: the cairntir
identity drawer #64 truncates here — the next session should re-read
the full hard-rules drawer).

**Next concrete step:** Build out features beyond the v1 pipeline.
Differentiator from Video Capture: this one CAN use local AI
(Whisper, Gemma) — that's why it's a sister project, not the same
project.

---

## intakeforms — *folder not located in `c:/Dev/`*

**State:** Identity drawer exists in cairntir wing (#7, #8) but
project folder not visible at `c:/Dev/IntakeForms/` or similar
case-variations. May live elsewhere on disk or have been moved.

**Identity (from cairntir wing #7, #8):** Public intake form platform
for freelance web developer Patrick McGuire. Collects queries from
prospects. Hard rules: NO AI API dependencies — rule-based
approaches only.

**Next concrete step:** Locate the project folder; if it has been
deprecated or moved, mark the wing's identity drawer as superseded.

---

## How to use this doc

**Tomorrow morning:** open Claude Code in any of these projects.
Claude reads CLAUDE.md, sees this file path mentioned (if you add a
pointer), reads the relevant wing's section, then calls
`cairntir_session_start` for the live identity drawers. The gap from
the down period is closed.

**Once the embedder warmup ships:** the entries in this file can be
backfilled into memory as actual essential drawers per wing — no
more dependence on this doc. Until then, this doc is the bridge.
