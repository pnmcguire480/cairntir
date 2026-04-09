# How to Use Cairntir

> 🔄 **This file must be updated as Cairntir grows.** If you add a
> feature, add a section here. If you rename a command, fix it here.
> This is the front door for humans — it cannot be allowed to rot.

---

## What Is Cairntir?

Cairntir is a **notebook for your AI**.

When you talk to Claude in one chat, Claude forgets everything the
next time you open a new chat. That's called **amnesia**, and it's
really annoying. You end up explaining the same stuff over and over.

Cairntir fixes that. It's a little program that runs on your computer
and remembers the important things you and Claude decide together.
Next time you open a new chat, Claude can look in the notebook and
say *"oh right, we already decided that."*

That's it. That's the whole point.

---

## The Four Words You Need to Know

Cairntir stores memories like a big filing cabinet. It has four parts:

1. **Wing** — a project. Like "Cairntir" or "my school essay".
2. **Room** — a topic inside a project. Like "decisions" or "bugs".
3. **Drawer** — one memory. A sentence or a paragraph. Verbatim —
   meaning Cairntir saves it exactly the way you said it.
4. **Layer** — how important a drawer is. Four levels:
   - **identity** — the most important stuff. Who you are, what you're building.
   - **essential** — important decisions you don't want to lose.
   - **on_demand** — useful but not critical. Looked up when asked.
   - **deep** — old stuff. Only pulled out when you're digging deep.

When you walk into a project, Cairntir opens the right wing, looks at
the rooms, and hands Claude the drawers that matter most. The
important ones come first; the deep ones only come if you ask.

---

## Step 1 — Install It

You only do this once.

```powershell
python -m pip install --user pipx
python -m pipx ensurepath
```

**Close PowerShell and open a new one.** (This is important — the
path only updates in new windows.)

Then install Cairntir itself:

```powershell
pipx install -e c:/Dev/Cairntir
```

Check it worked:

```powershell
cairntir version
```

You should see `cairntir 0.1.0` (or newer).

---

## Step 2 — Try the Three Commands You Can Type Yourself

Cairntir has three commands a human types. Everything else happens
automatically inside Claude Code.

### `cairntir version`
Tells you which version you have. Boring but useful.

### `cairntir status`
Shows you where the notebook lives on your computer and how many
drawers are in each wing. Example:

```
cairntir 0.1.0
home: C:\Users\you\AppData\Local\cairntir
db:   C:\Users\you\AppData\Local\cairntir\cairntir.db
wings: 2  drawers: 47
  cairntir  (32 drawers)
  cort4congress  (15 drawers)
```

### `cairntir recall "what you want to remember"`
Searches the notebook for anything that sounds like what you asked.
Example:

```powershell
cairntir recall "why did we pick sqlite"
```

You'll get back the top drawers that match, with their drawer id and
the first line of each.

You can narrow the search to just one wing:

```powershell
cairntir recall "auth decision" --wing cairntir
```

Or to just one room:

```powershell
cairntir recall "bug" --wing cairntir --room bugs
```

That's all three commands. The rest of Cairntir is used **from inside
Claude Code**, which is where the magic really happens.

---

## Step 3 — Let Claude Code Use It

Cairntir's real power shows up when Claude Code talks to it directly.
To turn this on in any project:

1. Go to that project's folder.
2. Create a file named `.mcp.json` at the top of the folder.
3. Put this inside:

```json
{
  "mcpServers": {
    "cairntir": {
      "command": "python",
      "args": ["-m", "cairntir.mcp.server"]
    }
  }
}
```

4. Open Claude Code in that folder.
5. You'll see six new tools Claude can use:

| Tool | What it does |
|---|---|
| `cairntir_remember` | Save a new drawer (something you want to remember) |
| `cairntir_recall` | Search for old drawers |
| `cairntir_session_start` | Load the most important drawers at the start of a chat |
| `cairntir_timeline` | See everything about one topic, in order |
| `cairntir_audit` | Check if a wing is healthy — uses the Quality skill |
| `cairntir_crucible` | Stress-test an idea — uses the Crucible skill |

You don't call these yourself. You just talk to Claude like normal,
and Claude picks the right tool.

Try saying:

> *"Remember that we decided to use sqlite-vec because it's embedded
> and doesn't need a server."*

Claude will call `cairntir_remember` and save it.

Then in a **brand new chat**, in the **same folder**, say:

> *"What did we decide about the database?"*

Claude will call `cairntir_recall`, find the drawer, and answer.
**That's the amnesia cure.** That moment is the whole reason Cairntir
exists.

---

## Step 4 — Use the Slash Commands

If you load the Cairntir plugin (it lives at
`c:/Dev/Cairntir/.claude-plugin/plugin.json`), you get three slash
commands in Claude Code:

- **`/cairntir:remember`** — save something to the notebook
- **`/cairntir:recall`** — search the notebook
- **`/cairntir:reason`** — think through a question using the notebook

The `/reason` one is special. It tells Claude to *first* look at
what's already in the notebook *before* answering. That way Claude
doesn't give you a generic answer — it gives you an answer that fits
what you've already decided.

---

## Step 5 — The Three Thinking Skills

Cairntir comes with three built-in skills. Claude uses them when you
ask the right kind of question.

### 🔥 Crucible — "Stress-test this idea"
When you're not sure if a plan will work, ask Claude to run it
through the Crucible. Example:

> *"Use crucible on my plan to rewrite the auth system this week."*

Claude will pull the Crucible skill text and poke holes in your
plan — looking for assumptions you didn't notice, things that could
break, questions you haven't answered.

### ✅ Quality — "Is this ready?"
When you want a second opinion before shipping, ask for an audit.
Example:

> *"Audit the cairntir wing."*

Claude uses the Quality skill to check the essential drawers and tell
you if anything looks rushed, risky, or half-baked.

### 🧠 Reason — "Think about this with what we already know"
This is the one that uses memory the hardest. Example:

> *"Reason about whether we should switch from sqlite-vec to chromadb."*

Claude will load the wing's 4 layers of context, search the notebook
for anything relevant, and *then* answer — with drawer ids cited
inline so you can check the sources.

---

## Step 6 — The Daemon (Optional, Advanced)

Cairntir also has a background program called the **daemon**. It
watches a folder called the spool and auto-saves any drawers that
land there. This is how Claude Code will eventually save memories
**without you typing anything at all**.

To start it:

```powershell
python -m cairntir.daemon
```

Leave it running in a separate window. Press **Ctrl+C** to stop it.

You don't need the daemon for Cairntir to work — the MCP tools save
drawers directly. The daemon is for later, when auto-capture is fully
wired up.

---

## Where Does Cairntir Keep Its Stuff?

On Windows:

```
C:\Users\<you>\AppData\Local\cairntir\cairntir.db
```

That one file is your whole notebook. You can back it up by copying
it. You can delete it to start fresh (but you'll lose all your
memories). You can move it to a different folder by setting an
environment variable:

```powershell
$env:CAIRNTIR_HOME = "D:\my-cairntir-notebook"
cairntir status
```

---

## Common Questions

**Q: Will Cairntir send my memories to the internet?**
No. Everything stays on your computer. No cloud, no telemetry, no
account. Local-first, always.

**Q: Can I use Cairntir with more than one project?**
Yes. One installation, many wings. Each project becomes its own wing
in the same notebook.

**Q: What if I want separate notebooks per project?**
Set `CAIRNTIR_HOME` to a different folder in each project.

**Q: Does Cairntir work without Claude Code?**
Sort of. You can save and search memories with the `cairntir`
command. But the real value is when Claude Code can read and write
to it automatically.

**Q: What happens when Cairntir gets a new version?**
If you installed with `pipx install -e`, just `git pull` in the
Cairntir folder. The editable install picks up changes immediately.

**Q: How do I report a bug?**
Open an issue at
[github.com/pnmcguire480/cairntir/issues](https://github.com/pnmcguire480/cairntir/issues).

---

## The Five Rules

These are the rules Cairntir lives by. You don't have to memorize
them, but they explain why it works the way it does.

1. **Verbatim.** Cairntir never summarizes your memories. It saves
   them exactly the way you said them.
2. **Local-first.** Your notebook lives on your computer. No cloud.
3. **Opinionated.** There's one right way to do things. Fewer knobs,
   fewer mistakes.
4. **No silent failures.** If something goes wrong, Cairntir tells
   you loudly. No swallowed errors.
5. **Comprehension before code.** Every feature has to make the
   amnesia problem smaller. If it doesn't, it doesn't ship.

---

## What's Next?

Cairntir is at **v0.1.0**. The next things on the road:

- `v0.1.x` — PyPI publish, docs site, polish
- `v0.2.0` — Temporal knowledge graph (who decided what, when?)
- `v0.3.0` — Multi-project synthesis (patterns across all your wings)
- `v1.0.0` — Cairntir as a library other tools can depend on

See [roadmap.md](roadmap.md) for the longer story, including what
this all builds toward. (Hint: it's bigger than code memory.)

---

*Last updated: 2026-04-08 — Cairntir v0.1.0*
