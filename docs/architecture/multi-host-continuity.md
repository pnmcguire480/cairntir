# Multi-Host Continuity

**Decision:** accepted 2026-07-27
**Priority:** foundation / ship blocker
**Hosts:** Codex, Cursor, Claude Code

## Invariant

A memory written through any supported host is the same memory seen through
every other host. “Same” means:

- one canonical database path;
- one embedding-space identity and index generation;
- one wing identity for the same project;
- one MCP tool contract;
- verbatim drawer content and stable IDs;
- host/model provenance that does not change retrieval meaning.

There is no Codex memory, Cursor memory, or Claude memory. There is Cairntir
memory, reached through three adapters.

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

Primary references:

- https://github.com/openai/codex/blob/main/docs/agents_md.md
- https://github.com/openai/codex/blob/main/codex-rs/README.md
- https://docs.cursor.com/context/rules
- https://docs.cursor.com/context/model-context-protocol
- https://docs.anthropic.com/en/docs/claude-code/cli-usage

## Implemented foundation

`cairntir init --host claude|codex|cursor|all [--user]` now installs
host-specific MCP wiring while keeping one host-neutral policy body:

- Claude: project `.mcp.json` or authoritative user registration through the
  `claude` CLI; `CLAUDE.md` policy;
- Codex: project `.codex/config.toml` or authoritative user registration
  through the `codex` CLI; `AGENTS.md` policy;
- Cursor: project or global `mcp.json`; project `.cursor/rules/cairntir.mdc`.

Existing JSON/TOML/instruction content is preserved. Cairntir only updates
blocks carrying its own markers and fails closed on ambiguous conflicts.
`cairntir doctor` inspects both project and user wiring without changing it.

Cursor's global User Rules are managed through Cursor Settings and have no
documented file-backed API. User-scope setup therefore installs the global MCP
entry and reports the one manual rule step instead of claiming false success.

Host/model/session provenance is now immutable on every write, and the
automated three-adapter continuity fixture proves that all three hosts can
write and recall through one store without changing drawer identity. One
real-host release-candidate smoke test is still required because this test
session cannot truthfully impersonate three independently running clients.

## Acceptance test

For a temporary project and temporary Cairntir home:

1. each adapter reports installed and resolves the same MCP command;
2. Codex writes a uniquely identified drawer;
3. Cursor retrieves the complete verbatim drawer;
4. Claude Code supersedes it;
5. Codex sees the full supersession chain;
6. doctor reports one database path, embedding-space ID, and generation for
   all three;
7. the provenance records which host performed each action without changing
   the wing or drawer identity.

The test may use adapter simulators in CI. A release candidate also requires a
human-operated smoke test against current host versions because configuration
surfaces change faster than the Cairntir core.
