# New-user front door — 2026-08-14

Repair from the first-look audit (drawer #447). Cairntir MCP is off
for this work: editable install means the running server holds the
code under repair.

Patrick 2026-08-14: land the first-look list **and** Jarvis's P3.
Jarvis: 1.7.0 is ready; the 10_000 shape-hunt was the real work;
leave handoff's recency window alone; P3 is `list_by(limit=None)`
materialising objects at existence-only call sites — not urgent,
not a defect, do it anyway because he asked.

## Tier 2 (this PR)

1. `cairntir setup` must complete without the Claude CLI.
2. Installed `MEMORY_POLICY` starts with `cairntir_handoff`.
3. Docs-site How to Use is the 1.7.0 product, not v0.1.0.
4. Cursor user-scope init/setup prints the paste-ready User Rule.
5. Human-facing status surfaces stop advertising a stale current
   version (docs home, MkDocs nav, SECURITY.md, README addendum,
   CLAUDE.md Stage, PyPI classifier).

## Also landed (first-look remainder + Jarvis P3)

- `DrawerStore.wing_exists` — SQL EXISTS for the unknown-wing notice.
- `plans/README.md` — live vs dated map. Files not moved.
- Root `HARNESS_AUDIT.md` is a pointer.
- README structure block labeled a seam sketch; addons + plans named.
- Coverage omit comment tells the truth about `mcp/server.py`.
- `examples/blender-mcp-plugin` points at the working add-on.
- Issue template placeholder `1.7.0`.
- Integration guide no longer presents MiniLM/384 as production.
- `setup` names the optional daemon and CLI-only recipes.

**Not built:** pin embedder model weights. `ModelSource` has no
revision field; fastembed does not expose one yet.

```cairntir-commitments
symbol src/cairntir/hosts.py CURSOR_USER_RULE_PASTE_HINT
symbol src/cairntir/cli.py _setup_wire_user_hosts
symbol src/cairntir/cli.py _echo_manual_cursor_rule
test   tests/unit/test_cli.py test_setup_succeeds_when_claude_cli_missing
test   tests/unit/test_cli.py test_init_cursor_user_prints_paste_ready_rule
test   tests/unit/test_hosts.py test_repo_policy_blocks_match_memory_policy
test   tests/unit/test_readme.py test_how_to_use_is_not_the_v0_product
file   docs/how-to-use.md
file   plans/2026-08-14-new-user-front-door.md
file   plans/README.md
symbol src/cairntir/memory/store.py wing_exists
test   tests/unit/test_store.py test_wing_exists_is_sql_exists_not_a_materialised_row
```
