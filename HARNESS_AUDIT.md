# BrainStormer Harness Primitive Gap Analysis

**Date:** 2026-04-03
**Auditor:** Claude Opus 4.6 (1M context)
**Scope:** 12 harness primitives evaluated against actual source code
**Method:** Direct code reading of cli/, kernel/, quality/, agents/ -- not docs

Findings ordered by severity (most critical gaps first).

---

## P5: Token Budget / Cost Tracking

**Status:** MISSING

**Evidence:**
- `cli/core/telemetry.py` tracks command names, success/failure, OS, and version (lines 126-133). It explicitly never tracks token counts, API costs, or model usage.
- `kernel/references/five-tier-system.md` describes a 5-tier LLM routing system (Autocomplete through Strategist) but contains zero cost awareness. No price-per-tier, no token estimates, no budget gates. The tiers are conceptual guidance for humans, not enforced routing.
- No file in the entire codebase contains the strings "token_count", "budget", "cost", "api_cost", or "usage_limit".
- The telemetry event schema (line 126) records: `ts`, `mid`, `cmd`, `ok`, `v`, `os`, `py`. No token or cost fields exist.

**Gap:** BrainStormer has no mechanism to track, limit, or even observe token consumption. A session could burn through an entire API budget with no visibility. The five-tier system is advisory prose -- it does not programmatically route requests or enforce tier boundaries.

**Risk:** Users running BrainStormer with Claude API keys have no guardrails against runaway costs. The init/wrapup loop fires skills, scans diffs, reads vault context, and runs quality audits -- all of which consume tokens with no accounting.

**Fix complexity:** HIGH -- requires architecture change. Would need: (a) a token counting interface at every LLM invocation point, (b) a budget ledger integrated with the existing TSV ledger system, (c) tier-aware routing that enforces model selection, (d) budget gates that halt before exceeding thresholds.

---

## P2: Permission Boundaries / Capability Enforcement

**Status:** ADVISORY-ONLY

**Evidence:**
- `cli/core/license.py` defines 4 tiers (community/pro/team/enterprise) with capability maps (lines 25-74). Capabilities include `max_projects`, `bidirectional_sync`, `agent_create`, `agent_pipelines`, `team_rulesets`, `priority_updates`.
- `_verify_signature()` at line 199-208 has a critical bypass: when no signing secret is available (the default for any user who has not set `BRAINSTORMER_SIGNING_KEY`), it accepts ANY key with 8+ characters in the signature field. This means `BS-PRO-20990101-ABCDEFGH` would activate Pro features for anyone.
- `check_capability()` and `require_pro()` exist (lines 271-359) but are called in exactly ONE place across all command modules: `cli/commands/sync.py` line 43, which gates bidirectional vault sync.
- `check_project_limit_with_warning()` exists (lines 401-417) but is NEVER called from `cli/commands/init.py`. The community tier's 3-project limit is defined but not enforced.
- `check_agent_limit()` at lines 282-289 always returns `(True, limit)` regardless of the limit value -- the boolean is always True, making this a no-op gate.
- No other command checks `require_pro()`, `check_capability()`, or any tier restriction. Agent creation, pipelines, team rulesets, and priority updates are ungated.

**Gap:** The license system is a complete capability definition with no enforcement. Of the 7 capability flags defined, 1 is checked in 1 place. The HMAC validation can be bypassed without the signing key. The project limit counter exists but is never called.

**Risk:** The entire tiering model is decorative. Any user on community tier has full access to all features. If monetization is ever needed, every command would need retrofit gating.

**Fix complexity:** MEDIUM -- the infrastructure exists. Requires: (a) calling `require_pro()` or `check_capability()` at each gated command entry point, (b) fixing `check_agent_limit()` to actually return False when over limit, (c) calling `check_project_limit_with_warning()` from init, (d) requiring a signing key for HMAC validation (removing the bypass).

---

## P3: Crash Recovery / Session Persistence

**Status:** PARTIAL

**Evidence:**
- `cli/commands/wrapup.py` uses the `_step()` wrapper (lines 17-28) which catches exceptions per step and continues. This is resilient -- individual step failures do not crash the wrapup. However:
- CLAUDE.md updates at line 167 (`_update_claude_md`) are NOT atomic. The function reads the file, modifies content in memory via regex replacement, and writes the full file back. A crash between read and write loses the update. A crash during write corrupts the file.
- There is no temp-file-then-rename pattern anywhere in wrapup. The Obsidian sync (line 206), quality persistence (line 177), and CLAUDE.md update all write directly to their target files.
- `cli/commands/autosave.py` provides partial crash recovery via the stop-hook mechanism (saves state after every Claude response). But autosave itself writes non-atomically to CLAUDE.md (lines 176-196) using the same read-modify-write pattern.
- The autosave marker at `.brainstormer-autosave` (line 107) is a git-state hash, not a transaction log. It detects "something changed" but cannot recover or replay lost writes.
- `cli/commands/init.py` scaffolding IS idempotent as claimed: `scaffold.py`'s `copy_if_missing()` (lines 20-41) checks `dest.exists()` before writing. Confirmed: re-running init will not overwrite existing files.
- `cli/core/ledger.py` uses append-only writes (line 111: `open(path, "a")`), which is the safest pattern in the codebase -- partial writes produce a truncated row, not data loss.

**Gap:** No atomic writes for CLAUDE.md (the single most important state file). No write-ahead log. No recovery mechanism if wrapup crashes mid-execution. The autosave mechanism mitigates but does not solve this -- it uses the same non-atomic write pattern.

**Risk:** A crash during wrapup or autosave can corrupt CLAUDE.md, losing the entire session handoff state. Since CLAUDE.md is the primary carrier of inter-session continuity, this would cause the next init to have no context.

**Fix complexity:** LOW -- replace direct file writes with write-to-temp-then-rename (Python's `os.replace()` is atomic on all platforms). Approximately 3 functions need this fix: `_update_claude_md` in wrapup, `_update_claude_md_silent` in autosave, and `_write_preserving_user_notes` in vault.

---

## P12: Agent Type System / Species Constraints

**Status:** ADVISORY-ONLY

**Evidence:**
- `kernel/references/agent-species.md` defines 6 species with rich behavioral descriptions: task-harness, project-harness, dark-factory, auto-research, orchestration, oracle (lines 1-148).
- `agents/registry.md` classifies all 571 agents by species (lines 18-26).
- `cli/core/registry.py` parses species from agent frontmatter (line 14: `"species"` in `ALLOWED_KEYS`; line 69: `agent.update({k: str(v) ...})`).
- However, species is NEVER used for routing, permissions, or behavioral constraints. The `_matches_stack()` function (lines 107-114) filters by category only. `list_agents()` filters by stack relevance only. `get_top_agents()` matches by name only.
- No function in registry.py or any command module reads `agent["species"]` to make a routing decision.
- The oracle integration document (`kernel/references/agent-species.md` lines 116-133) describes 3 pipeline integration points for oracles but these are prose descriptions, not wired code.
- Named thinker agents "deliberately break standard agent format rules" (line 127) but there is no code that enforces or validates agent format rules in the first place.

**Gap:** Species is a classification label stored in metadata and documentation. It has no runtime effect. An oracle agent and a task-harness agent are treated identically by every code path.

**Risk:** Species was designed to prevent the "Don't Mix Species" anti-pattern (agent-species.md line 109). Without enforcement, users could invoke oracles for coding tasks or coding agents for thinking tasks, producing poor output with no system-level warning.

**Fix complexity:** MEDIUM -- requires: (a) species-aware filtering in `list_agents()` and `get_top_agents()`, (b) species validation when init recommends agents for a maturity stage, (c) optional species constraint at invocation time (warn if species mismatches the active skill).

---

## P8: Two-Level Verification

**Status:** PARTIAL

**Evidence:**
- `quality/SKILL.md` defines PALADIN as a 6-tier project code audit (lines 1-79). It checks: governance structure, code hygiene, dependency health, test presence, git health, entropy score.
- `cli/commands/quality.py` implements these 6 tiers (lines 25-303). Every tier checks PROJECT artifacts: file existence, TODO counts, lockfiles, test ratios, git status, gitignore coverage.
- PALADIN does NOT verify:
  - Agent definitions (no scan of `~/.claude/agents/` for malformed frontmatter, missing required fields, or contradictory metadata)
  - CLAUDE.md structural validity (checks file existence at line 53 but not whether the "Last Session" block is parseable, whether the rules section is intact, or whether the handoff protocol fields are populated)
  - Harness configuration (no check of `~/.brainstormer/config.json`, `obsidian/config.yaml`, or license state)
  - Governance drift between CLAUDE.md rules and actual code behavior
- The Tier 1 check (lines 42-66) verifies governance FILE EXISTENCE but not content validity. A CLAUDE.md containing only "hello" would pass Tier 1.
- There are separate audit scripts (`cli/audit_agents.py`, `cli/audit_frontmatter.py`, `cli/tools/audit_agent_content.py`) but these are standalone tools, not integrated into the PALADIN pipeline.

**Gap:** PALADIN verifies project code health but not harness health. It cannot detect: a corrupted CLAUDE.md, a bad agent definition, a misconfigured vault path, or a stale/broken governance file. The existing agent audit scripts are siloed -- they should feed into PALADIN as a meta-governance tier.

**Risk:** The harness itself can degrade without detection. A broken CLAUDE.md will cause init to lose session context. A malformed agent frontmatter will cause silent filtering failures. These are invisible to the current quality system.

**Fix complexity:** MEDIUM -- add a "Tier 0: Harness Health" check to PALADIN that validates: CLAUDE.md parseable structure, agent frontmatter completeness for top-N agents, vault config reachability, license state. The audit scripts already contain the logic -- it needs integration.

---

## P9: Observability / Audit Trail

**Status:** PARTIAL

**Evidence:**
- `cli/core/ledger.py` defines 6 append-only TSV ledgers (lines 15-58): session, quality, failure, assumption, pattern, routing. These are well-designed with column schemas and timestamp auto-fill.
- `cli/commands/wrapup.py` writes to the pattern ledger (lines 262-283) for detected patterns and decision triggers.
- `cli/commands/quality.py` writes to the quality ledger (lines 281-295) after each audit.
- `cli/commands/init.py` writes to the session ledger (lines 784-795) at returning init.
- `cli/core/telemetry.py` records command-level events (lines 107-148) with timestamps.
- `cli/commands/autosave.py` appends to a session log at `docs/codeglass/session-log.md` (lines 263-289).
- HOWEVER: the routing ledger is NEVER written to. It has a schema (lines 53-58) but no code calls `append_ledger(root, "routing", ...)`. Skill routing decisions during init are logged to the session ledger instead, without recording whether the routing was correct.
- The failure ledger defines 4 failure types (lines 61-66: misroute, contract-violation, context-waste, drift) but is NEVER written to from any command.
- The assumption ledger is NEVER written to from any command.
- There is no single "reconstruct this session" capability. Session data is spread across: CLAUDE.md (handoff state), TSV ledgers (structured events), autosave markers (git hashes), codeglass session logs (markdown), and telemetry JSONL files. No tool aggregates these.

**Gap:** 3 of 6 ledger schemas (routing, failure, assumption) are defined but never populated. The audit trail exists for patterns and quality scores but not for skill routing decisions, failures, or assumptions. Session reconstruction requires manually correlating 5 different data sources.

**Risk:** Cannot diagnose misroutes (init recommended wrong skill), cannot track assumption validity over time, cannot measure failure rates. The infrastructure is built but the instrumentation is incomplete.

**Fix complexity:** LOW to MEDIUM -- the ledger infrastructure works. Needs: (a) routing ledger writes in init when a skill is recommended, (b) failure ledger writes in wrapup when steps fail, (c) a `brainstormer audit trail` command that aggregates all sources for a date range.

---

## P1: Metadata-First Agent Registry

**Status:** PARTIAL

**Evidence:**
- `cli/core/registry.py` parses YAML frontmatter from agent `.md` files (lines 47-90). It extracts: name, description, species, severity, thinker_lineage, category, tags, and more (line 12-16: `ALLOWED_KEYS`).
- Agents are discoverable by stack via `list_agents(filter_stack="python")` (lines 26-43) and `_matches_stack()` (lines 107-114).
- `get_top_agents()` (lines 184-207) provides curated priority lists per stack.
- `agents/registry.md` contains a full table of 571 agents with severity and species columns.
- `agents/classification-full.tsv` provides machine-readable classification data.
- HOWEVER: filtering is category-based, not metadata-first. `_matches_stack()` checks whether the agent's category (derived from filename prefix, line 84) matches a hardcoded category list (lines 94-104). This is filename-glob-with-extra-steps.
- There is NO query by severity (e.g., "show me all P0 agents"), NO query by species (e.g., "show me all oracle agents"), NO query by tags, NO compound query ("P0 task-harness agents for Python").
- The `ALLOWED_KEYS` are parsed but only `category` drives filtering. Severity, species, tags, and thinker_lineage are stored but never queried.
- Metadata is not enforced. An agent file with no frontmatter returns `None` from `parse_agent_frontmatter()` (line 54-55) and is silently skipped. There is no validation that required fields (name, severity, species) are present.

**Gap:** The registry parses rich metadata but only uses one derived field (category from filename) for filtering. Severity, species, and tags are carried but inert. No compound queries. No schema enforcement.

**Risk:** The 571-agent roster cannot be effectively navigated by the properties that matter most (severity for prioritization, species for routing). As the roster grows, filename-prefix-based categorization will not scale.

**Fix complexity:** MEDIUM -- add `filter_severity`, `filter_species`, `filter_tags` parameters to `list_agents()`. Add a `validate_agent()` function that checks required frontmatter fields. Wire these into `brainstormer agent list --severity P0 --species oracle`.

---

## P7: Structured Handoff Protocol

**Status:** IMPLEMENTED (with caveats)

**Evidence:**
- `cli/commands/wrapup.py` gathers session signals (git commits, file changes), runs CodeGlass scan for patterns/decisions, checks drift, and writes all of this into CLAUDE.md's "Last Session" block (lines 167-170).
- `cli/commands/init.py` reads the "Last Session" block via `_read_last_session()` (lines 130-194), parsing date, accomplished items, files changed, uncommitted count, and next_steps.
- Init also reads: quality history (lines 284-338), vault context from Obsidian (lines 341-447), global rules, project rules, and cross-project summary (lines 750-777).
- The autosave mechanism (`cli/commands/autosave.py`) provides incremental state capture between wrapup calls, reducing the blast radius of a missed wrapup.
- The session ledger records each init with project, maturity, and recommended skill.

**Gap:** Information loss is NOT measured. There is no diff between "what wrapup saved" and "what init recovered." If a field fails to parse (regex mismatch), init silently falls back to defaults (empty list, 0, None) with no warning. The `_read_last_session()` function returns `{"found": False}` for any parse failure, and init simply prints "No previous session found" -- indistinguishable from a genuinely new project.

**Risk:** Silent handoff degradation. If the CLAUDE.md format drifts (e.g., someone edits the "Last Session" block manually and breaks the regex), init loses all continuity silently. The user sees "No previous session found" and assumes it is correct.

**Fix complexity:** LOW -- add a warning when CLAUDE.md exists but "Last Session" block fails to parse. Log handoff quality (fields recovered vs expected) to the session ledger.

---

## P6: Tool Pool Assembly / Dynamic Agent Selection

**Status:** PARTIAL

**Evidence:**
- `cli/commands/init.py` uses maturity-based skill routing (lines 487-598: `SKILL_ACTIONS` dict) to recommend the right skill for the project phase (new -> ideation, active -> comprehension, mature -> quality, launch-ready -> crucible).
- `cli/core/registry.py` filters agents by stack (lines 26-43, 94-114) and provides curated top-10 lists per stack (lines 126-207).
- Init displays the recommended skill and its actions but does NOT dynamically assemble a tool pool. It recommends a skill category (e.g., "comprehension") and the human decides which agents to invoke.
- All 571 agents remain available via `brainstormer agent list` regardless of what init recommends. The filtering is a display filter, not an access control.
- The agent list command (`cli/commands/agent.py`) applies stack filtering but the `--all` flag bypasses it entirely.

**Gap:** Agent selection is advisory, not enforced. Init recommends a skill but does not constrain which agents are available. There is no "for this session, only these 15 agents are relevant" mechanism.

**Risk:** Low immediate risk for a CLI tool (the human is the gatekeeper). Higher risk if BrainStormer ever routes agents programmatically -- without pool assembly, irrelevant agents could be invoked, wasting tokens and producing off-target output.

**Fix complexity:** MEDIUM -- requires: (a) session-scoped agent pool that init assembles based on maturity + stack + skill, (b) agent list respecting the active pool by default, (c) explicit `--all` to break out of the pool.

---

## P4: Workflow State vs Conversation State

**Status:** PARTIAL

**Evidence:**
- `cli/core/ledger.py` defines durable, queryable workflow state via 6 TSV ledgers (session, quality, failure, assumption, pattern, routing). These survive across conversation windows.
- `cli/commands/init.py` reads quality history (line 672: `_read_quality_history`), session continuity from CLAUDE.md (line 628: `_read_last_session`), vault context (line 697: `_read_vault_context`), and cross-project state (line 752: `_read_cross_project_summary`).
- Quality score trends are tracked with sparkline visualization (lines 284-338).
- Session ledger records which skill was recommended per session (line 785).
- `.brainstormer-quality-history` persists scores in `YYYY-MM-DD score` format.

**Gap:** Workflow state is partially durable but not fully queryable. There is no command like `brainstormer history` or `brainstormer sessions` that shows the workflow timeline. The session ledger records `recommended_skill` but never fills in `actual_skill` or `outcome` (line 788-790 show empty strings that should be populated at wrapup). There is no "what skills have fired for this project" view.

**Risk:** Cannot answer "what did BrainStormer recommend vs what actually happened" for any project. The feedback loop for improving routing accuracy is broken because `actual_skill` and `outcome` are never recorded.

**Fix complexity:** LOW -- populate `actual_skill` and `outcome` fields in wrapup by reading which skills actually fired during the session. Add a `brainstormer sessions` command that reads the session ledger.

---

## P10: Graceful Degradation

**Status:** IMPLEMENTED (with known weakness)

**Evidence:**
- YAML import has a fallback in `cli/core/registry.py` (lines 6-9: `try: import yaml; except: yaml = None`) with a line-by-line parser fallback (lines 73-81). Same pattern in `cli/core/vault.py` (lines 8-10).
- `cli/commands/wrapup.py` wraps every step in `_step()` (lines 17-28) which catches all exceptions, logs to stderr, and continues. Wrapup will complete even if individual steps fail.
- Vault path not configured: `get_vault_path()` returns `None` (vault.py line 56), and callers check for None before attempting sync (e.g., init.py line 206, wrapup.py line 205).
- No git repo: multiple functions check `(project_root / ".git").exists()` before running git commands (init.py line 212, wrapup.py's codeglass scan, quality.py line 160).
- No agents directory: `registry.py` line 33 returns empty list if agents_dir doesn't exist.
- 226 total `except` clauses across 32 files in cli/ (grep count). 41 of these catch broad `Exception` or bare `except:`.

**Gap:** The known weakness (documented in CLAUDE.md "What's Broken") is 180+ silent error swallowing blocks. The `_step()` wrapper in wrapup prints to stderr, but many other locations use `except: pass` or `except Exception: pass`, making failures invisible. Vault.py's `wiki_link_audit()` and `sync_vault_to_project()` are documented as incomplete/crash-prone.

**Risk:** The system degrades gracefully in the sense that it does not crash. But it degrades silently -- the user has no visibility into what failed. A misconfigured vault path, a broken agent file, or a git timeout all produce the same result: silence.

**Fix complexity:** LOW to MEDIUM -- replace `except: pass` with `except Exception as e: logger.debug(...)` and add a `--verbose` flag that surfaces these. The wrapup `_step()` pattern is the right model -- extend it to other modules.

---

## P11: Cross-Project Learning

**Status:** PARTIAL

**Evidence:**
- `cli/commands/learn.py` supports `--global` flag (lines 1-16) to add rules to `~/.brainstormer/rules.md` that apply to all projects.
- `cli/commands/init.py` reads global rules (line 750: `_read_global_rules()`) and shows which are active vs overridden by project rules (lines 762-764).
- `cli/commands/init.py` reads cross-project patterns from the Obsidian vault (lines 403-447: `_read_vault_context()`) by scanning other projects' comprehension directories for P0/P1 patterns.
- Cross-project metrics from vault ledgers are read during init (lines 719-746).
- Wrapup registers the project in a cross-project registry (line 181: `_register_project()`).
- Wrapup checks cross-project insights (line 118: `_cross_project_check()`).

**Gap:** Pattern propagation is read-only and manual. Init reads patterns from other projects' vault directories but never automatically promotes a pattern seen in 3+ projects into a global rule. The `learn rule --from-diff` command proposes rules from git diffs but does not cross-reference with patterns seen in other projects. There is no "this pattern appeared in 5 projects, consider making it a global rule" automation.

**Risk:** Knowledge silos form despite the infrastructure. The same anti-pattern can be detected independently in 10 projects without ever being promoted to a global rule. The human must manually run `brainstormer learn rule --global` after noticing the pattern themselves.

**Fix complexity:** MEDIUM -- add a threshold counter in the cross-project registry. When a pattern name appears in N+ projects (configurable, default 3), auto-propose it as a global rule candidate during wrapup.

---

## Summary Table

| # | Primitive | Status | Risk Level | Fix Complexity |
|---|-----------|--------|------------|----------------|
| P5 | Token Budget / Cost Tracking | **MISSING** | HIGH | HIGH |
| P2 | Permission Boundaries | **ADVISORY-ONLY** | HIGH | MEDIUM |
| P3 | Crash Recovery / Session Persistence | **PARTIAL** | MEDIUM | LOW |
| P12 | Agent Type System / Species Constraints | **ADVISORY-ONLY** | MEDIUM | MEDIUM |
| P8 | Two-Level Verification | **PARTIAL** | MEDIUM | MEDIUM |
| P9 | Observability / Audit Trail | **PARTIAL** | MEDIUM | LOW-MEDIUM |
| P1 | Metadata-First Agent Registry | **PARTIAL** | MEDIUM | MEDIUM |
| P7 | Structured Handoff Protocol | **IMPLEMENTED** | LOW | LOW |
| P6 | Tool Pool Assembly | **PARTIAL** | LOW | MEDIUM |
| P4 | Workflow State vs Conversation State | **PARTIAL** | LOW | LOW |
| P10 | Graceful Degradation | **IMPLEMENTED** | LOW | LOW-MEDIUM |
| P11 | Cross-Project Learning | **PARTIAL** | LOW | MEDIUM |

## Verdict

**0 of 12 primitives fully implemented without caveats.**
**2 implemented with known gaps** (P7 handoff, P10 degradation).
**7 partially implemented** -- infrastructure exists but instrumentation/enforcement is incomplete.
**2 advisory-only** -- code defines the concept but has zero runtime enforcement.
**1 completely missing** (token/cost tracking).

The pattern across all gaps is consistent: BrainStormer builds excellent infrastructure (ledger schemas, license tiers, species definitions, capability maps) but does not wire the enforcement layer. The ledgers exist but 3/6 are never written to. The license system exists but gates 1 of 20+ commands. The species taxonomy exists but filters nothing. The fix path is clear for most primitives because the foundation is already in place -- what is missing is the last mile of enforcement and instrumentation.

## Recommended Fix Order

1. **Atomic writes for CLAUDE.md** (P3) -- lowest effort, highest reliability impact
2. **Populate the 3 empty ledgers** (P9) -- wiring existing infrastructure
3. **License enforcement at command boundaries** (P2) -- if monetization matters
4. **Species-aware and severity-aware agent filtering** (P1, P12) -- if agent routing matters
5. **Handoff quality measurement** (P7) -- detect silent degradation
6. **Token budget system** (P5) -- architectural, defer until cost becomes a real concern
