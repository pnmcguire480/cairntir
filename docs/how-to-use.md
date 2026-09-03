# How to Use Cairntir

This is the human front door. If a command or version here disagrees
with the code, this file is wrong.

**Current source: 1.9.0 release candidate. Latest published: 1.8.0.**
Zero-prior-knowledge walkthrough:
[cairntir-for-dummies.md](cairntir-for-dummies.md).

## Install

You need Python 3.11+ and a shell. You do **not** need Claude Code
installed. Cursor, Codex, and Qwen Code are first-class hosts too.

```bash
pip install cairntir
cairntir setup
```

That one wizard initializes the store, wires every supported host it
can find at user scope, and prints the Cursor User Rule that Cursor
cannot install from a file. Missing CLIs are skipped, not fatal.

Then fully quit and reopen the host you use.

`uv tool install cairntir` and `pipx install cairntir` work the same
way. Contributors clone the repo and `pip install -e .` instead.

To wire a single host later:

```bash
cairntir init --host cursor --user    # or claude, codex, qwen, or all
```

Project-local Cursor setup (`cairntir init --host cursor`, no
`--user`) writes both the MCP config and the always-apply rule.
Cursor's **global** User Rule still has to be pasted into
**Cursor Settings → Rules → User Rules** — `setup` and
`init --host cursor --user` print the text to paste.

## Check it worked

```bash
cairntir version    # 1.9.0 from this candidate; 1.8.0 from PyPI until release
cairntir status     # where the store lives, drawer counts
cairntir doctor     # host wiring without changing anything
```

Open a chat in any folder and ask: *what is cairntir?* If the agent
answers with real knowledge and offers to call `cairntir_handoff`,
you are done.

## The four words

1. **Wing** — a project.
2. **Room** — a topic inside a project.
3. **Drawer** — one verbatim memory.
4. **Layer** — identity / essential / on_demand / deep. Default writes
   land on `on_demand`. That is why agents start with **handoff**, not
   `session_start`: handoff still returns recent default-layer
   memories; `session_start` does not unless you pass a query.

## What you type as a human

Almost nothing. Once it is installed, the agent reads and writes
memory. The commands a person actually types:

```bash
cairntir recall "database decisions" --wing myapp
cairntir handoff myapp
cairntir recover --host codex --wing myapp
cairntir cost myapp
```

Transcript recovery is opt-in. Use `recover`, or add `--recover-from codex`
to `handoff`, only when you want Cairntir to inspect the host's newest
non-live transcript tail. Qwen Code, Claude Code, and Codex are supported.
Cursor returns an unsupported receipt rather than guessing at undocumented
SQLite tables. Recovered text is untrusted evidence and is never stored unless
you explicitly pass `--write N` to `recover`.

## Bounded hotfixes

Use `cairntir_hotfix` when a repair must follow an explicit, inspectable order:
open the observed failure, compare evidence-cited candidates, authorize one
exact candidate, record an independent preflight, let the host perform one
attempt, then record independent verification or an exact rollback. Follow the
`legal_actions` returned by every receipt.

```bash
cairntir hotfix status --wing myapp --case-id hf-abc123
```

Mutating actions also require `--idempotency-key` and an action-specific JSON
`--payload`. The MCP tool exposes the complete discriminated payload schema.
Cairntir does not run the repair, sign the authority, or prove that a caller's
identity is independent; it preserves those claims and rejects out-of-order or
binding-mismatched records. See the
[Bounded Hotfix recipe](recipes/bounded-hotfix/README.md).

## Day 30

You open a fresh chat in a project you have not touched in three
weeks. The installed policy tells the agent to call
`cairntir_handoff(wing)` first. It gets whole drawers under a budget:
the protocol, the last session deltas, open questions, and memory
anchored to the files in play. Then you ask your question.

That is the North Star. Details live in the repository README.

## Troubleshooting

- **Tools appear, agent never uses them.** The MCP server is wired
  but the policy is missing. Re-run `cairntir setup`, and if you are
  on Cursor at user scope, paste the printed User Rule.
- **`cairntir setup` warned that `claude` is not on PATH.** Expected
  on a Cursor-only machine. Cursor and Qwen still got wired.
- **Wrong Python / venv.** `cairntir init --user --force --host all`.

File a bug at
[github.com/pnmcguire480/cairntir/issues](https://github.com/pnmcguire480/cairntir/issues).
