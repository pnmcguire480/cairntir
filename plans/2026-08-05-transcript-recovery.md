# Cairntir — Transcript Recovery (no memory loss across chats)

**Date:** 2026-08-05
**Author:** Qwen Code (qwen3.8-max-preview), from the failed recall test of 2026-08-05 (drawers #299, #300, #301)
**Status:** v1.8.0 candidate merged to `main` via PR #74; not published.

---

## The goal, in Patrick's words

> "i should leave a heavy chat, into a clean chat.. with NO memory loss in between chats"

That is the acceptance test for everything below. Not "did the agent remember
to save" — **does anything survive when the agent had no time to save.**

---

## The incident this plan exists because of

2026-08-05, store drawer #300 carries the evidence. Patrick's final request in
Qwen session `91a83e91` (a README addendum for this repo) arrived at
23:25:50Z. The session acknowledged it, began fact-gathering, and the
transcript ends at 23:27:36Z — killed ~10 seconds after the request, during a
restart to fix a stale MCP build. Nothing was persisted: no file change, no
commit, no drawer. The next session, asked to recall the last action, found
nothing, because nothing had been written.

The capture-on-arrival rule added to host policy on the same day (record a
request immediately, before working on it) shrinks the window but cannot close
it: a kill landing between the user's message and the agent's first tool call
still loses everything. Policy is necessary and insufficient.

**The load-bearing fact:** the host transcript survived. Qwen Code keeps every
session as JSONL on disk —
`~/.qwen/projects/<project-hash>/chats/<session-id>.jsonl` — 993 events for
the killed session, including the verbatim request. The host already records
everything Cairntir needs. Cairntir simply never reads it.

---

## What this changes

Cairntir gains a **recovery path**: it mines the host's own transcript store
for requests that were made but never persisted, and surfaces them on the read
path. The memory layer stops depending on the agent's last tool call landing.

### Design

1. **`cairntir recover --host H [--wing W] [--write N]`.**
   Locate the host transcript directory for the current project, find the most
   recent session that is NOT the live one, and extract its tail: the last N
   user messages and whether the host's completion marker followed each one.

2. **Diff against the store.** For each tail request: does a later drawer in
   the same wing contain that exact content? If yes — captured, skip. If no —
   it is an **orphan request**: recovered, verbatim, with its timestamp and the
   session id it came from.

3. **Surface, never auto-store.** Recovery output joins `cairntir_handoff`
   under a clearly-marked section — `## Recovered from host transcript` —
   listed verbatim with session ids. Nothing is written to the store without
   an explicit `cairntir_remember`. Transcript content is untrusted evidence
   exactly like drawer content behind the security banner; auto-importing it
   would be the prompt-injection seam this repo has never opened. The agent or
   Patrick decides what gets banked. `--write N` stores one chosen orphan with
   `trust=untrusted` and `capture_path=transcript_recovered` provenance.

4. **Budget discipline.** Tail extraction only — last N events, bounded
   characters, whole messages or named-not-fetched. This is drawer #213's rule
   applied to a new surface: never return a token the model cannot use.

### Host adapters (the host-neutral contract, drawer #116)

Transcript location and shape are host-specific, so adapters follow the same
pattern as the init/doctor adapters:

| Host | Transcript surface | Status |
|---|---|---|
| Qwen Code | `~/.qwen/projects/<path-encoded>/chats/*.jsonl` | **Verified with 0.21.5** and the killed session that produced drawer #300 |
| Claude Code | `~/.claude/projects/<path-encoded>/*.jsonl` | **Verified with 2.1.222** |
| Codex | `~/.codex/sessions/**/rollout-*.jsonl` | **Verified with 0.149.0-alpha.4.1** |
| Cursor | local SQLite history | **Unsupported honestly:** no documented stable transcript schema |

A host with no readable transcript surface reports that plainly instead of
guessing. Same rule as anchors: a wrong source poisons recovery worse than no
source.

### Phases

- **R1 — Qwen-only recovery. Complete.** `cairntir recover` reads the verified Qwen
  surface; handoff section; unit tests against fixture transcripts (including a
  killed-mid-turn fixture built from today's real tail). Done when: replaying
  today's incident in a test recovers the README request verbatim.
- **R2 — Claude Code + Codex adapters. Complete.** Verified paths and fixture
  tests cover unfinished and completed turns for all three readable hosts;
  Cursor returns an unsupported receipt.
- **R3 — handoff integration + opt-in `--write`. Complete locally.** The recovered section in
  `cairntir_handoff` output with budget accounting, and the explicit write
  path with `transcript_recovered` provenance. The automated acceptance test
  launches a transcript-writing session, kills it immediately after its user
  event, and proves the fresh backend's first handoff names that request
  verbatim. The original killed Qwen transcript is also recovered by the
  production parser.

### Non-goals

- No full-transcript ingestion, summarization, or indexing. Recovery reads
  tails, not corpora.
- No automatic drawers, ever. Surface only; consent is the write path.
- No cross-machine recovery. Transcripts are local; so is this.

### Acceptance test (live)

Make a request in a heavy chat. Kill the host without letting it respond.
Open a clean chat. The first `cairntir_handoff` names the request verbatim.
Repeat with a free-tier model driving the second chat — the pieces must be
followable without knowing the right question to ask.

```cairntir-commitments
symbol src/cairntir/transcript.py RecoveryReport
symbol src/cairntir/cli.py recover_cmd
param  src/cairntir/mcp/backend.py handoff:recover_transcripts
file   src/cairntir/mcp/server.py
test   tests/unit/test_transcript.py test_kill_after_request_is_named_verbatim_on_first_handoff
test   tests/unit/test_transcript.py test_cursor_returns_an_honest_unsupported_receipt
test   tests/unit/test_transcript.py test_recovery_never_writes_without_explicit_selection
```
