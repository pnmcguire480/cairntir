# Roadmap

Cairntir's shipped foundation is the memory-first reasoning layer: verbatim
drawers, wing/room taxonomy, local embeddings, bounded whole-drawer handoff,
prediction and discovery ledgers, structural recall, three skills, recipes,
four first-class host adapters, and a 20-tool MCP server.

The original v0.1 → v1.7 build plans are retained under `plans/` as history.
They are not current status. The live plan map is
[`plans/README.md`](https://github.com/pnmcguire480/cairntir/blob/main/plans/README.md).

## v1.7.1 — New-user front door and truth pass

Patch release for failures in the first five minutes:

- `cairntir setup` works without the Claude Code CLI and configures installed
  hosts while reporting unavailable ones;
- installed host policy starts with `cairntir_handoff`, so default
  `on_demand` writes return on the documented resume path;
- Cursor user-scope setup prints the paste-ready User Rule;
- first-run documentation, status, plan-map, MCP inventory, and release memory
  agree with the shipped product;
- the full local gate, remote operating-system/Python matrix, package build,
  trusted publication, provenance attestations, and fresh Windows install are
  release requirements.

No schema migration or reindex is required.

## v1.8.0 — Bounded transcript recovery

Capture-on-arrival narrows memory loss but cannot close the interval between a
user request and the agent's first tool call. The next release implements the
opt-in recovery contract in
[`plans/2026-08-05-transcript-recovery.md`](https://github.com/pnmcguire480/cairntir/blob/main/plans/2026-08-05-transcript-recovery.md):

1. bounded, whole-message tail readers for Qwen Code, Claude Code, and Codex;
2. a truthful unsupported receipt for Cursor until Cursor exposes a stable
   local transcript surface;
3. untrusted, provenance-visible recovery output that can abstain and never
   silently becomes authoritative memory;
4. acceptance by killing a session immediately after a request, opening a
   fresh session, and recovering the request verbatim.

The transcript adapters are host-specific. The recovery result and trust
boundary remain host-neutral.

## Retrieval preflight — experiment before feature

After transcript recovery, Cairntir will pre-register a holdout evaluation for
a receipt-visible retrieval preflight. The candidate may retrieve only when
relevance, trust, freshness, and authority thresholds pass; it may abstain; it
must show provenance; it must not rewrite the user's prompt or expand stored
content's authority.

It ships only if the holdout shows a measured gain over explicit handoff and
recall without hiding misses or increasing unsafe retrieval. Otherwise the
idea is rejected with the evidence preserved.

## Completion rule

Cairntir is complete for the current arc only when:

- no Tier 1 or Tier 2 finding remains;
- `main` is clean and synchronized with `origin/main`;
- status, roadmap, plan map, MCP surface, changelog, release notes, and memory
  ledger agree;
- published GitHub and PyPI artifacts carry provenance and pass a fresh
  Windows installation;
- every other item is shipped, rejected with evidence, externally blocked, or
  explicitly Tier 3.

## Deliberate boundaries

- The three-skill core remains Crucible, Quality, and Reason. New repeatable
  behavior is a recipe, not a fourth skill.
- Cairntir remains local-first, MIT, host-neutral, and append-only at the
  evidence layer.
- Local Qwen3.8 is a private asynchronous shadow worker/evaluator, never an
  interactive or authority-path dependency.
- Model-weight revision pinning remains externally blocked until the production
  FastEmbed path exposes a usable revision contract.
- `2.0.0` remains reserved for a revolutionary change in what Cairntir is, not
  routine breaking changes.

## Horizon

Cairntir is still pointed at memory that compounds beyond software: AI,
grand-scale 3D printing, and post-scarcity tooling. That horizon guides the
local-first, open, substrate-neutral design; it is not a release commitment.
