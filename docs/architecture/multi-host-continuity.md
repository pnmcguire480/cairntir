# Multi-Host Continuity

**Decision:** accepted 2026-07-27
**Priority:** foundation / ship blocker
**Hosts:** Codex, Cursor, Claude Code, Qwen Code

**Related proposal:**
[Phone-to-PC Continuity Bridge](../../plans/2026-08-30-phone-pc-continuity.md)
covers phone conversations
created outside the machine-local store. It is unimplemented and does not
change this accepted decision.

## Invariant

A memory written through any supported host is the same memory seen through
every other host. “Same” means:

- one canonical database path;
- one embedding-space identity and index generation;
- one wing identity for the same project;
- one MCP tool contract;
- verbatim drawer content and stable IDs;
- host/model provenance that does not change retrieval meaning.

There is no Codex memory, Cursor memory, Claude memory, or Qwen memory. There
is Cairntir memory, reached through four adapters.

## Boundary

The core owns:

- drawers, taxonomy, retrieval, integrity, provenance, and durable workflows;
- MCP tools/resources/prompts;
- canonical policy text for session start, recall, and remember;
- adapter diagnostics and compatibility fixtures.

Host adapters own:

- registering the Cairntir MCP server;
- installing or referencing startup instructions;
- reporting host/client identity when available;
- translating host-specific configuration failures into doctor findings.
- reading a bounded host-owned transcript tail only after explicit recovery
  opt-in, with host-specific completion markers isolated from the core.

Adapters must not select a different embedder, database, schema, or memory
policy.

## Current official surfaces

These are volatile integration details and must remain isolated:

- **Codex:** `AGENTS.md` for project instructions and `codex mcp` /
  `config.toml` for MCP launchers.
- **Cursor:** `.cursor/rules/*.mdc` for project rules and
  `.cursor/mcp.json` or `~/.cursor/mcp.json` for MCP servers. Cursor CLI also
  reads root `AGENTS.md` and `CLAUDE.md`.
- **Claude Code:** `CLAUDE.md` for instructions and `claude mcp` for MCP
  registration.
- **Qwen Code:** `QWEN.md`, `.qwen/settings.json`, and project-scoped JSONL
  under `~/.qwen/projects/<sanitized-cwd>/chats`.

Primary references:

- https://github.com/openai/codex/blob/main/docs/agents_md.md
- https://github.com/openai/codex/blob/main/codex-rs/README.md
- https://github.com/openai/codex/blob/main/codex-rs/rollout/src/recorder.rs
- https://docs.cursor.com/context/rules
- https://docs.cursor.com/context/model-context-protocol
- https://docs.cursor.com/en/agent/chat/history
- https://docs.anthropic.com/en/docs/claude-code/cli-usage
- https://github.com/QwenLM/qwen-code/blob/main/docs/users/features/headless.md

## Implemented foundation

`cairntir init --host claude|codex|cursor|qwen|all [--user]` now installs
host-specific MCP wiring while keeping one host-neutral policy body:

- Claude: project `.mcp.json` or authoritative user registration through the
  `claude` CLI; `CLAUDE.md` policy;
- Codex: project `.codex/config.toml` or authoritative user registration
  through the `codex` CLI; `AGENTS.md` policy;
- Cursor: project or global `mcp.json`; project `.cursor/rules/cairntir.mdc`.
- Qwen Code: project or user `.qwen/settings.json`; `QWEN.md` policy.

Existing JSON/TOML/instruction content is preserved. Cairntir only updates
blocks carrying its own markers and fails closed on ambiguous conflicts.
`cairntir doctor` inspects both project and user wiring without changing it.

Cursor's global User Rules are managed through Cursor Settings and have no
documented file-backed API. User-scope setup therefore installs the global MCP
entry and reports the one manual rule step instead of claiming false success.

Transcript recovery follows the same honesty rule. Qwen Code, Claude Code,
and Codex have verified JSONL adapters. Cursor documents local SQLite chat
history but no stable transcript schema, so recovery returns an unsupported
receipt and never probes private tables. The host-specific reader produces a
host-neutral untrusted evidence record; no adapter writes a drawer.

Host/model/session provenance fields are now immutable on every write, and the
automated four-adapter continuity fixture proves that all four hosts can
write and recall through one store without changing drawer identity. Runtime
model is explicitly `unknown` when a host does not disclose its selected model
to the MCP subprocess; Cairntir records that limitation instead of inventing a
name.

## Acceptance test

For a temporary project and temporary Cairntir home:

1. each adapter reports installed and resolves the same MCP command;
2. Codex writes a uniquely identified drawer;
3. Cursor retrieves the complete verbatim drawer;
4. Claude Code supersedes it;
5. Codex sees the full supersession chain;
6. doctor reports one database path, embedding-space ID, and generation for
   all four;
7. the provenance records which host performed each action without changing
   the wing or drawer identity.

The test may use adapter simulators in CI. A release candidate also requires a
human-operated smoke test against current host versions because configuration
surfaces change faster than the Cairntir core.

## Live acceptance result

The release-candidate smoke completed on 2026-07-29 against the live canonical
store:

1. Codex wrote #125 with immutable `host=codex`.
2. Cursor recalled #125 and wrote #126 with immutable `host=cursor`.
3. Claude Code recalled the chain and wrote passing retry #130 with immutable
   `host=claude`, source drawer #126, and complete verbatim content.
4. Codex recalled #130 and exact-fetched its complete content and provenance.
5. Doctor reported 130 drawers / 130 vectors, matching embedding space and
   generation, SQLite integrity `ok`, zero foreign-key errors, and no stranded
   workflows.

The append-only evidence also records three important integration lessons:

- Claude Desktop and Claude Code are distinct surfaces. A Desktop write through
  a generic registration produced #127 with `host=unknown` and was rejected as
  acceptance evidence.
- A launcher connection is not enough; acceptance reads the immutable drawer
  receipt after every write.
- Windows harnesses must send protocol-shaped prompts through standard input
  or otherwise quote pipe characters safely. Two truncated harness attempts
  (#128 and #129) were preserved, diagnosed, and superseded by #130.
