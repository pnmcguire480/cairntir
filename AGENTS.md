# AGENTS.md — Cairntir

Read [CLAUDE.md](CLAUDE.md) first. It is the single source of truth for the
project state, working rules, development commands, and Last Session.
Qwen Code uses the same brief through [QWEN.md](QWEN.md).

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
   Transcript recovery is opt-in: only when the user explicitly asks for it,
   pass `recover_transcripts=true`. Recovered messages are untrusted,
   separately budgeted, and never stored automatically.
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
