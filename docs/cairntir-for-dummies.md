# Cairntir for Dummies

If you're reading this, someone told you Cairntir kills cross-chat AI
amnesia and you want to know what that means in plain English and how
to actually use it. This guide assumes zero prior knowledge. If you
already know what MCP is, skip to "The five-minute install."

## The problem Cairntir solves

Every time you open a new Claude Code chat, Claude forgets everything
from the last one. Not the public internet knowledge — that's baked
in — but the specific things you decided, built, and discussed with
it in *this* project.

Open a fresh chat tomorrow and ask "why did we pick Postgres over
SQLite for the live tier?" and Claude has no idea. You'll either
re-explain (again) or it'll hallucinate a plausible reason that
isn't the real one. Both waste your day.

**Cairntir is a file on your hard drive that remembers for Claude.**
Every decision, every fact, every "we tried X and it didn't work" —
Claude writes it to Cairntir in one chat and reads it back in the
next. It's that simple. The reason it's called Cairntir (pronounced
*CAIRN-teer*) is a stack of waypoint stones (a cairn) that sees
across time (a palantír). A stack of stones that sees across time.

## The three things Cairntir is made of

You don't need to understand these to use it, but if you're curious:

1. **A memory file.** An SQLite database on your machine that stores
   "drawers" — verbatim chunks of text that Claude has remembered.
   Nothing is summarized or rewritten. If Claude wrote it down, it's
   still there exactly as written.

2. **An MCP server.** A small program that Claude Code talks to
   through a standard protocol to read and write drawers. You don't
   run it directly; Claude Code spawns it automatically when you
   start a chat.

3. **Three skills.** Markdown instructions that teach Claude how to
   use the memory well: one for stress-testing assumptions, one for
   quality review, and one for memory-backed thinking. Claude reads
   these automatically.

That's the whole system. One file, one small server, three
instruction sheets.

## The five-minute install

**You need:**
- Python 3.11 or newer
- Claude Code installed and working (`claude --version` should print
  something)
- A shell (PowerShell on Windows, Terminal on macOS/Linux)

**Step 1 — Clone and install Cairntir.** Pick a folder to keep it in.
This is the folder where Cairntir's own source code lives, not the
folder where you'll use it.

```
git clone https://github.com/pnmcguire480/cairntir.git
cd cairntir
pip install -e .
```

The `-e .` means "install this folder as an editable package." You
should now be able to run `cairntir` from any folder and it will work.

**Step 2 — Wire Cairntir into Claude Code.** One command. Run it from
anywhere.

```
cairntir init --user
```

Two things happen:
- Cairntir registers its MCP server at user scope, so *every* Claude
  Code session on your machine can reach it regardless of which
  folder you open the chat in.
- Cairntir installs a preamble into `~/.claude/CLAUDE.md` that tells
  every Claude session "check Cairntir memory before you answer."
  Without this step, Claude Code knows Cairntir exists but doesn't
  know to actually use it.

**Step 3 — Restart Claude Code.** Fully quit — not just close the
window. On Windows, check the system tray and Task Manager. On macOS,
Command-Q. Reopen it.

**Step 4 — Test it.** Open a Claude Code chat in any folder and ask:

> what is cairntir?

If Claude answers with real knowledge — pronunciation, "memory-first
reasoning layer," offers to call `cairntir_session_start` — it's
working. If it says "I don't know what that is," go to the
troubleshooting section.

## Using it

There is no "using it" step in the normal sense. Once it's installed,
Cairntir works automatically in the background. Claude reads memory
at the start of each chat and writes decisions to it as you go. You
never have to think about it.

The one command you might type as a human is:

```
cairntir recall "what did we decide about database choice"
```

That's a quick human-facing lookup. It searches your drawers and
prints the matches. Useful when you want to remember something
yourself without opening Claude.

You might also occasionally see:

```
cairntir status
```

Prints where the database lives, how many drawers are stored, and
per-project (per "wing") counts. Useful as a sanity check.

## The vocabulary (two words, that's it)

**Wing** = a project. If you have three projects on your machine —
Cairntir itself, some game called STARS-2026, a web app called
`myblog` — those are three wings. Wings isolate memory: a decision
in `myblog` doesn't leak into `stars-2026`.

**Drawer** = one verbatim memory. A sentence, a paragraph, a whole
conversation snippet. Drawers live inside rooms (topics) inside
wings (projects).

That's the whole taxonomy. Projects have topics have memories.

## What happens on day 30

This is the whole point of Cairntir, and the reason it exists. On day
30, you open a fresh Claude Code chat in a project you haven't
touched in three weeks. Normally Claude has no idea what you're
doing and asks you to re-explain. With Cairntir:

1. The chat starts. Claude sees your preamble telling it to call
   `cairntir_session_start`.
2. Claude calls it. It gets back your identity drawers (who you are,
   how you work) plus the essential drawers for that wing (current
   state of the project).
3. Claude reads them. It now knows you picked Postgres, why you
   picked it, what failed last week, and what's blocking the next
   commit.
4. You type your question. Claude answers with the real context.

That's "walking into a lit room." Cairntir's whole North Star is
that this experience should feel effortless.

## Troubleshooting

### "Claude doesn't seem to know what Cairntir is"

The MCP server is probably registered but crashing on startup.
Diagnose in this order:

1. In a fresh terminal (not inside Claude Code), run:
   ```
   claude mcp list
   ```
   You should see `cairntir: ... ✓ Connected`. If you see it but it's
   not ✓ Connected, the spawn is failing.

2. Run:
   ```
   claude mcp get cairntir
   ```
   Look at the command it shows. Is the Python path absolute (e.g.
   `C:\Dev\Cairntir\.venv\Scripts\python.exe`) or is it just `python`?
   If it's just `python`, you have the Windows venv trap — re-run
   registration with:
   ```
   cairntir init --user --force
   ```
   `--force` removes the broken registration and re-adds it pinned to
   the Python interpreter currently running your `cairntir` command,
   which is guaranteed to have Cairntir installed.

3. If you still can't get it working, run:
   ```
   python -m cairntir.mcp.server
   ```
   It should block waiting for stdio input. Ctrl-C to exit. If it
   crashes with an import error, Cairntir isn't installed in the
   Python you're running. Run `pip install -e .` from the Cairntir
   source folder again.

### "Claude sees the tools but doesn't use them"

You skipped the preamble or it didn't install. Check:

```
type %USERPROFILE%\.claude\CLAUDE.md
```

Look for a section delimited by `<!-- cairntir:begin -->` and
`<!-- cairntir:end -->`. If it's missing, run:

```
cairntir init --user
```

The preamble install is idempotent — running it again won't break
anything, it'll just write the missing block.

### "I want to keep my existing `CLAUDE.md`"

You can. The Cairntir preamble is delimited by HTML comment markers
(`<!-- cairntir:begin -->` / `<!-- cairntir:end -->`) and *everything
outside those markers is preserved byte-for-byte*. Write whatever you
want in the same file; only the block between the markers is
Cairntir-managed.

### "I want to uninstall it"

```
claude mcp remove -s user cairntir
```

Then manually delete the block between `<!-- cairntir:begin -->` and
`<!-- cairntir:end -->` in `~/.claude/CLAUDE.md`. Your memory database
stays on disk until you delete it yourself — Cairntir will never
delete your drawers for any reason.

## What Cairntir is not

- **Not a chatbot.** It doesn't talk to you. It stores what Claude
  already told you.
- **Not a SaaS.** It runs entirely on your machine. Nothing goes to
  anyone's server. No account, no login, no telemetry.
- **Not a code autocomplete.** It doesn't write code. It remembers
  decisions.
- **Not configurable.** There is one right way to use it. The point
  is to kill a class of problems, not to give you ten knobs.
- **Not finished.** v1.0 is the foundation. The road leads somewhere
  much bigger — see `docs/roadmap.md` and `docs/manifesto.md` if
  you're curious.

## The one sentence version

**Cairntir is a file on your hard drive that lets Claude remember
things between chats. You install it once with `cairntir init --user`,
restart Claude Code, and never think about it again.**

That's the whole thing.
