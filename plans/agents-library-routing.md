# Agents library routing — why `C:\Dev\AGENTS` doesn't fire, and the one fix

**Date:** 2026-08-04
**Status:** Research + proposal. **Nothing was changed.** No files under
`C:\Users\pnmcg\.claude\` or `C:\Dev\AGENTS` were modified, no junctions created,
no settings edited.

---

## TL;DR

Two separate things are going on, and only one of them is a bug.

1. **Discoverability — partly broken.** 402 of your agents *are* already global
   and loaded in every project. 228 are not. The global copy is a stale snapshot
   taken *before* the big `thinkers` restructure.
2. **Auto-firing — not a bug.** Subagents in Claude Code 2.1.219 **never fire
   automatically.** The Agent tool's own description tells the main agent not to
   spawn one unless you ask. No amount of file-linking changes this. This is the
   real answer to "they don't seem to fire off automatically."

There is also a finding neither of those covers: **your current agent roster
costs roughly 8,400 tokens in every session of every project.** Deploying the
full library would take that to roughly 17,000. That is the largest single
context line item on this machine.

---

## 1. Inventory of `C:\Dev\AGENTS`

`C:\Dev\AGENTS` and `c:\Dev\agents` are the same directory (Windows paths are
case-insensitive). It is a git repo called **Claude Arsenal**, last three
commits:

```
59505820 fix: resolve agent-installer deploy collision in meta-orchestration
95179a69 docs: reframe emergent-behavior callout from warning to methodology
ddbabc43 feat: restructure thinkers into nested subcategories (+89 agents, 571→660)
```

### Top level

| Path | What it is |
|---|---|
| `agents/` | 660 agent definition files in 15 category dirs |
| `skills/` | 1,357 skill directories |
| `deploy.sh` | real, 68 lines — a copier, described below |
| `README.md` | documents the collection as "Claude Arsenal" |
| `.claude/` | contains only `scheduled_tasks.lock` — untracked, not agent config |

### Agent counts by category — 660 files total

| Category | `.md` files |
|---|---:|
| `thinkers-named/` (9 nested subcats) | 89 |
| `business-product/` | 78 |
| `specialized-domains/` | 66 |
| `infrastructure/` | 62 |
| `quality-security/` | 58 |
| `meta-orchestration/` | 44 |
| `data-ai/` | 39 |
| `developer-experience/` | 38 |
| `core-development/` | 38 |
| `thinkers/` | 36 |
| `thinkers-math/` (6 nested subcats) | 36 |
| `language-specialists/` | 34 |
| `research-analysis/` | 16 |
| `thinkers-methods/` | 15 |
| `project-specific/` | 11 |
| **Total** | **660** |

`thinkers-named/` and `thinkers-math/` are **nested two-to-three levels deep**
(e.g. `agents/thinkers-named/philosophy/modern-philosophers/thinker-alan-watts.md`).
Every other category is flat. This nesting matters for the fix — see §3.

### Format — clean and consistent

All 660 files are Markdown with YAML frontmatter. Coverage is **100%** on all
four fields:

| Field | Files having it |
|---|---:|
| `name:` | 660 / 660 |
| `description:` | 660 / 660 |
| `tools:` | 660 / 660 |
| `model:` | 660 / 660 |

Example (`agents/thinkers/thinker-alan-watts.md`):

```yaml
---
name: thinker-alan-watts
description: Non-dual philosopher who dissolves problems by showing you ARE the problem
tools: Read, Glob, Grep, Bash
model: sonnet
last_evolved: 2026-04-01
evolution_cycles: 0
---
```

This is exactly the shape Claude Code expects. **Nothing is malformed.** Format
is not the problem.

### Two naming generations live side by side

The library mixes two styles of `name:` value:

- **Title-case**, e.g. `name: AD Security`, `name: Auth Patterns`
- **kebab-case**, e.g. `name: ad-security-reviewer`, `name: backend-developer`

They are frequently *the same agent twice under different names* —
`code-reviewer` vs `Code Review`, `cpp-pro` vs `C++`, `data-scientist` vs
`Data Science`. This becomes important in §5.

### Duplicate names inside the library

37 basenames appear twice. The cause is benign and documented: the README calls
`agents/thinkers/` a *"flat convenience bundle: 15 methods + 21 named thinkers"* —
it is a deliberate redundant copy of `thinkers-methods/` + parts of
`thinkers-named/`.

Exclude `agents/thinkers/` and the picture is almost perfectly clean:

- 624 files, **622 unique `name:` values**
- Only **2** collisions remain:
  - `error-coordinator.md` in `core-development/` and `meta-orchestration/` —
    **byte-identical** (`md5 bfe897318f`), harmless
  - `thinker-richard-feynman.md` in `thinkers-math/teachers-translators/` and
    `thinkers-named/science/popularizers/` — genuinely different files

---

## 2. Where Claude Code actually looks — with evidence

### The installation

- `which claude` → `/c/Program Files/nodejs/claude`
- That npm package is a thin wrapper; the real binary is native:
  `C:\Users\pnmcg\AppData\Roaming\Claude\claude-code\2.1.219\claude.exe`
  (265 MB, single executable)

### Evidence pulled from the binary

Grepping `claude.exe` for agent path patterns returns `.claude/agents/*.md` —
a **single-level glob**, and **no `agents/**` recursive variant exists anywhere
in the binary.

The decisive string is this piece of Claude Code's own bundled guidance:

> Scan the agent definition files the session would load: `` `.claude/agents/*.md` ``
> in the project (subdirectories included) and `` `~/.claude/agents/*.md` ``. A file
> whose frontmatter has a `name` but fails validation (e.g. missing `description`)
> never loads … Two files in the SAME directory whose frontmatter `name` matches
> collide: the loser is discarded silently and the winner follows unsorted readdir
> order.

Three facts fall out of that sentence:

1. **Exactly two locations are read**: project `.claude/agents/` and user-level
   `~/.claude/agents/`. There is no third, and no setting that adds one.
2. **Project-level is explicitly recursive** — "(subdirectories included)".
3. **User-level is written without that qualifier.** See §4 — this is the one
   thing I could not confirm.

### What is actually in those locations

**`C:\Users\pnmcg\.claude\agents\`** — 402 `.md` files, completely flat, zero
subdirectories, plus a `_manifest.txt`. Dated 24 Mar and 4 Apr 2026.

**`C:\Dev\Cairntir\.claude\`** — contains only `settings.local.json` and
`worktrees/`. **There is no `.claude/agents/` in Cairntir**, so this project
contributes no project-level agents.

**`C:\Users\pnmcg\.claude\settings.json`** — 4 top-level keys only:
`permissions`, `statusLine`, `enabledPlugins`, `effortLevel`. There is **no
setting anywhere that points at `C:\Dev\AGENTS`.** `permissions.additionalDirectories`
lists three memory/config paths for other projects and is a *permission* grant,
not an agent search path. Two `Read(...)` permission entries reference
`~/.claude/agents/**`, which again is permission, not discovery.

### Proof that `~/.claude/agents/` is the live source

The deployed `~/.claude/agents/thinker-alan-watts.md` has:

```yaml
name: "Alan Watts"
description: "Non-dual philosopher who dissolves problems by showing you ARE the problem"
```

The agent roster available to a running session contains, verbatim:

> `Alan Watts: Non-dual philosopher who dissolves problems by showing you ARE the problem`

Exact match. Meanwhile the *library* version of the same agent has
`name: thinker-alan-watts` — and `thinker-alan-watts` does **not** appear in the
roster. Confirmed: the session loads `~/.claude/agents/`, not `C:\Dev\AGENTS`.

The same test run negatively against library-only agents — `code-mapper`,
`api-designer`, `accessibility-oracle`, `backend-developer` — none appear in the
roster.

### `deploy.sh` is real, and it is a copier

`C:\Dev\AGENTS\deploy.sh`, 68 lines. Usage:

```
bash deploy.sh <project-path> <category|--all|agent-names...>
```

It does `mkdir -p "$PROJECT/.claude/agents"` then `cp` files in. Three things
about it matter:

- It targets **a project**, not the user-level directory. It was never designed
  to make agents global.
- It **flattens** — `cp "$f" "$DEST/"` drops everything into one directory,
  discarding the category nesting.
- It is a **one-shot copy with no sync-back**, which is exactly how the current
  global directory went stale.

---

## 3. Why the library is not reachable from every project

Not because of format, and not because of a missing setting. Because of a
**stale, partial, manual copy**.

| | Count |
|---|---:|
| Unique agent names in library | 622 |
| Deployed to `~/.claude/agents/` | 402 |
| **In library, never deployed** | **228** |
| Deployed but no longer in library | 8 |

The 8 orphans are `autonomous-code-reviewer`, `autonomous-doc-updater`,
`autonomous-migration`, `autonomous-refactorer`, `autonomous-test-generator`,
`dotnet`, `dotnet-framework`, `meta-orchestration-agent-installer`. Some are
newer work that exists *only* in the global dir — so a blind overwrite would
lose them. Back up first.

**The copy predates the restructure.** All 660 library files were touched after
2026-04-01 (commit `ddbabc43`, "+89 agents, 571→660"). **Zero** of the 402
deployed files were modified after 2026-04-05. The global directory is a
snapshot from before the thinkers reorganisation landed.

Worth noting by contrast: **skills are fine.** `C:\Dev\AGENTS\skills` has 1,357
entries and `~/.claude/skills` has 1,358. Skills got deployed globally and
agents did not. That asymmetry is the whole story.

---

## 4. The honest answer on auto-firing

**Subagents in Claude Code 2.1.219 do not fire automatically. Ever.**

This is not a misconfiguration and it is not fixable by moving files. It is the
documented behaviour of the Agent tool. From `claude.exe`:

> … A task with "multiple angles," "thorough," or several parts is not a request
> to spawn; handle it inline with your own tools. **Only use this tool when the
> user explicitly says to use a subagent, or names one of the available agent
> types.**

That instruction is delivered to the main agent in its system prompt on every
session. Under it, the correct behaviour for a model that notices you're doing
security work is to *keep doing the work itself*, not to reach for
`security-engineer`.

Separating your two possible problems cleanly:

| | Problem | True for you? | Fix |
|---|---|---|---|
| **(a)** | Agents not **discoverable** | Partly — 228 of 622 missing, rest stale | §5, mechanical |
| **(b)** | Agents discoverable but never **auto-invoked** | Yes, for all 402 | Not fixable by file placement |

You are hitting **both**, but (b) is the one you noticed, and (b) is the one
that will still be true after any linking change.

A secondary contributor: agent descriptions are how a model decides an agent is
relevant. **0 of your 402 deployed agents** say "proactively" in their
description, and only 8 of 660 in the whole library do. By comparison the
plugin-supplied agents that *do* get picked up read like
`"Use proactively when a skill needs to search the web…"`. Your descriptions are
written as labels ("Non-dual philosopher who dissolves problems…"), not as
triggers. Even under a permissive spawn policy they would rarely be selected.

**How they actually fire:** name one. "Use the red-teamer agent on this plan."
"Have Buckminster Fuller look at this architecture." Naming the agent type is
the documented, supported invocation path, and it works today for all 402.

---

## 5. The cost finding — read this before deploying anything

Every agent's `name` + `description` is injected into the system prompt of every
session, in every project, whether or not you use it. Measured:

| Roster | Chars | ≈ Tokens per session |
|---|---:|---:|
| Current 402 deployed | 33,728 | **~8,400** |
| Full library (624, excl. `thinkers/`) | 67,878 | **~17,000** |

For scale, this project's own `cairntir cost` work treats the 19-tool Cairntir
MCP catalog at **2,307 tokens** as a cost worth closing a HIGH-risk audit gap
over. Your agent roster is **3.6× that already**, and deploying the rest would
make it **7.4×**.

And roughly 200 of the 228 undeployed agents are the kebab-case generation —
near-duplicates of agents you already have under title-case names
(`code-reviewer`/`Code Review`, `cpp-pro`/`C++`). You would be paying ~8,500
tokens per session, forever, largely for a second copy of the roster you already
have.

This is why the recommendation below is a *junction*, not a copy: a junction
makes `C:\Dev\AGENTS` the single control point, so pruning the library once
prunes every project at once.

---

## 6. Recommended fix

**Replace the stale copy at `~/.claude/agents` with a directory junction
pointing at `C:\Dev\AGENTS\agents`.** One command, one control point, zero
drift, everything global forever after.

Run these in an **elevated PowerShell** (junction creation needs it on Windows
10 Home), one block at a time.

### Step 1 — back up the current global directory

Non-negotiable: it holds 8 agents that exist nowhere else.

```powershell
Copy-Item -Recurse "$env:USERPROFILE\.claude\agents" `
  "$env:USERPROFILE\.claude\agents-backup-20260804"
```

### Step 2 — rescue the 8 orphans into the library

```powershell
$lib = "C:\Dev\AGENTS\agents\meta-orchestration"
$src = "$env:USERPROFILE\.claude\agents"
foreach ($n in @(
  "autonomous-code-reviewer","autonomous-doc-updater","autonomous-migration",
  "autonomous-refactorer","autonomous-test-generator")) {
  Copy-Item "$src\$n.md" "$lib\$n.md"
}
Copy-Item "$src\dotnet.md"           "C:\Dev\AGENTS\agents\language-specialists\dotnet.md"
Copy-Item "$src\dotnet-framework.md" "C:\Dev\AGENTS\agents\language-specialists\dotnet-framework.md"
```

(`meta-orchestration-agent-installer.md` is already resolved in the library by
commit `59505820`; skip it.)

### Step 3 — delete the redundant `thinkers/` bundle

The README calls it a convenience duplicate of `thinkers-methods/` +
`thinkers-named/`. Keeping it means 37 duplicate `name:` values in the roster.

```powershell
Remove-Item -Recurse "C:\Dev\AGENTS\agents\thinkers"
```

Then commit the library so the rescue and the deletion are versioned:

```powershell
cd C:\Dev\AGENTS
git add -A
git commit -m "chore: absorb global-only agents, drop redundant thinkers bundle"
```

### Step 4 — swap the copy for a junction

```powershell
Remove-Item -Recurse -Force "$env:USERPROFILE\.claude\agents"
New-Item -ItemType Junction `
  -Path "$env:USERPROFILE\.claude\agents" `
  -Target "C:\Dev\AGENTS\agents"
```

### Step 5 — verify, and know what each outcome means

Open a **new** Claude Code session in any project and run `/agents`.

- **You see agents from nested categories** (e.g. `thinker-alan-watts`,
  which now lives only at
  `agents/thinkers-named/philosophy/modern-philosophers/`) → user-level
  discovery is recursive. **Done.** All 622 are global, the library is the
  single source of truth, and editing a file in `C:\Dev\AGENTS` is live
  everywhere immediately.
- **You see nothing, or only a handful** → user-level discovery is flat-only
  (see §4 caveat below). Roll back with
  `Remove-Item "$env:USERPROFILE\.claude\agents"` then
  `Rename-Item "$env:USERPROFILE\.claude\agents-backup-20260804" agents`, and
  instead build one flat directory and junction to *that*:

  ```powershell
  $flat = "C:\Dev\AGENTS\agents-flat"
  New-Item -ItemType Directory -Force $flat
  Get-ChildItem "C:\Dev\AGENTS\agents" -Recurse -Filter *.md |
    ForEach-Object { Copy-Item $_.FullName "$flat\$($_.Name)" -Force }
  Remove-Item -Recurse -Force "$env:USERPROFILE\.claude\agents"
  New-Item -ItemType Junction -Path "$env:USERPROFILE\.claude\agents" -Target $flat
  ```

  This costs one flatten step whenever you add a category, which is the only
  drift in the whole plan and is why it is the fallback rather than the default.

### Step 6 — the part that actually addresses your complaint

Linking changes nothing about auto-firing. To make the library get *used*, add a
routing block to `C:\Users\pnmcg\.claude\CLAUDE.md` — that file is read in every
project, so it is the right global home:

```markdown
## Agent library

~600 specialist subagents are available (thinkers, security, language
specialists, infrastructure). They do not self-select — name one to invoke it.

Reach for them when: stress-testing a plan (`red-teamer`, `devils-advocate`,
`assumption-auditor`), reviewing before a release (`security-engineer`,
`code-reviewer`), or wanting a specific lens (`thinker-buckminster-fuller`,
`thinker-peter-joseph`).

If a task would clearly benefit from one, say so and ask before spawning.
```

That last line is the lever. It converts "never fires" into "offers to fire,"
which is as close to automatic as the current Agent tool policy permits.

---

## What I could not determine

Stated plainly, because a confident guess here would be worse than the gap:

1. **Whether `~/.claude/agents/` is scanned recursively.** This is the one fact
   Step 4 depends on. The evidence is genuinely ambiguous: Claude Code's own
   text says project-level is `.claude/agents/*.md` **"(subdirectories
   included)"** and describes user-level as `~/.claude/agents/*.md` **without**
   that qualifier — suggestive of flat-only, but an omission is not a
   specification. I could not test it empirically without writing into
   `~/.claude\agents`, which is out of scope for this task. The current
   directory has no subdirectories, so it offers no evidence either way, and
   plugin-supplied agents all sit flat in their own `agents/` folders. **Step 5
   is written as a decision point precisely because of this**, and the fallback
   is a complete, working path.

2. **Whether the ~8,400 / ~17,000 token figures match Claude Code's internal
   accounting.** They are computed from `name` + `description` lengths at
   4 chars/token. The relative sizes and the ~2× jump are reliable; the absolute
   numbers are an estimate.

3. **Whether the 228 undeployed agents were excluded deliberately or just
   missed.** They are overwhelmingly the kebab-case generation and look like a
   separately-sourced set, but I found no note recording a decision. If you
   dropped them on purpose, Step 3's deletion instinct should probably extend
   further — worth a look before committing.

4. **Whether the `Read(//c/Users/pnmcg/.claude/agents/**)` permission entries in
   `settings.json` were added for a reason that a junction would break.** A
   junction changes the resolved target path, and I did not test whether
   permission matching follows the junction or the literal path.

---

## Alternatives, briefly

A **one-time flat copy** (essentially `deploy.sh --all` retargeted at
`~/.claude\agents`) is simpler and sidesteps the recursion question entirely,
but it is exactly what produced the current stale, four-month-out-of-date state
— it drifts silently and gives no signal that it has. A **sync script** run on a
schedule is strictly worse: one more moving part that fails quietly. **Per-project
`.claude/agents/`** is confirmed recursive and would work reliably, but it must
be repeated for every project, which is the opposite of what you asked for.
Finally, packaging the library as a **local Claude Code plugin** is the most
"correct" long-term answer and would give namespaced agents
(`arsenal:red-teamer`), but it means authoring a marketplace manifest and
maintaining a release process — a lot of machinery for something one junction
solves.
