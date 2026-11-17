# Use Obsidian with Cairntir

Cairntir keeps your project's memory; Obsidian gives you a place to browse it,
follow links, and add your own notes. Start with the
[coding and 3D-printing showcase](https://github.com/pnmcguire480/cairntir/discussions/182),
then make a setup that fits your work.

## First option: ask your LLM to set it up

Give this prompt to a coding agent that can work with files and run commands
on your computer, such as Codex, Claude Code, Cursor, or Qwen Code. A chat-only
LLM can walk you through the steps instead.

```text
Help me set up Obsidian with Cairntir on this computer, then customize it
for my projects. Follow this guide:
https://github.com/pnmcguire480/cairntir/blob/main/docs/obsidian-setup.md

First inspect my OS, installed versions, Python environment, Cairntir store,
and existing Obsidian vaults. Ask which project I want to organize and where
its notes belong. Reuse working installations and preserve my existing notes
and agent configuration.

Start with a new pilot vault and a separate test store. Use the Cairntir
Workspace plugin from the matching release, with an explicit Python
executable, Cairntir home, and project wing. Run the first refresh, add one
harmless test question, and show me its saved receipt and matching note.
Add a personal annotation and refresh again to check that it survives.

Once the pilot works, help me choose and back up the real store and vault
before connecting them. Make sure my agent and the plugin use the same
intended store and wing. Do not upgrade or reindex an existing store without
explaining the required backup and getting my agreement.

Create a simple Home note linking to the memory index and my project notes.
Suggest useful folders, templates, and optional dashboards for my work.
Use my paths, not the showcase author's paths. Show me how to refresh,
where to write my own notes, and how to check that an update really worked.
Report what you actually tested and anything that still needs my action.
```

You can add a sentence such as “I want separate coding and 3D-printing
vaults,” “Help me organize research questions,” or “Keep a troubleshooting
journal for my home lab.” The project and layout are yours to choose.

## What this guide sets up

The starting point is **Cairntir Workspace**, the desktop plugin in this
repository. It refreshes one project wing into a vault's `cairntir-sync/`
folder and provides explicit question and correction commands. A wing is a
project; a room is a topic within it.

The showcase uses an additional custom **Cairntir Vault Refresh** adapter,
multiple wings, and a Dataview dashboard. Those are examples of customization.
The Workspace plugin below gets you a linked memory view first, without
having to write an adapter or install Dataview.

These steps target **Cairntir 1.14.1** and **Cairntir Workspace 0.1.0**.
The plugin requires **Obsidian desktop 1.13.7 or later**. Review the
[current feature status](https://github.com/pnmcguire480/cairntir/blob/main/ALPHA.md)
and use a disposable store and vault for the first run.

## Manual setup

### 1. Create a pilot vault

Install [Obsidian desktop](https://obsidian.md/download), then
[create a new vault](https://obsidian.md/help/vault), for example
**Cairntir Pilot**. Open it once so Obsidian creates its `.obsidian` folder.
Keep the vault separate from the Python environment and Cairntir store.

### 2. Choose a Python environment

Use Python 3.11–3.13. If Cairntir is already installed, identify the full path
of the Python interpreter that contains it. For a new isolated installation,
run these commands in a new folder outside the vault.

**Windows PowerShell:**

```powershell
py -3.12 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install "cairntir==1.14.1"
& .\.venv\Scripts\python.exe -c "import sys; print(sys.executable)"
& .\.venv\Scripts\python.exe -m cairntir version
```

**macOS or Linux:**

```sh
python3.12 -m venv .venv
./.venv/bin/python -m pip install 'cairntir==1.14.1'
./.venv/bin/python -c 'import sys; print(sys.executable)'
./.venv/bin/python -m cairntir version
```

Substitute an installed 3.11–3.13 interpreter if `py -3.12` or `python3.12` is
unavailable. Save the printed executable path for the plugin settings.
For an existing store from 1.12 or earlier, follow the
[upgrade guide](embedding-artifacts.md) before changing its installation.

### 3. Install the Workspace plugin

Download and extract the
[v1.14.1 source archive](https://github.com/pnmcguire480/cairntir/archive/refs/tags/v1.14.1.zip).
From `addons/cairntir_obsidian/`, copy **only** `main.js` and `manifest.json`
into this folder in the pilot vault:

```text
Cairntir Pilot/
  .obsidian/
    plugins/
      cairntir-workspace/
        main.js
        manifest.json
```

Restart Obsidian or reload its plugin list. In **Settings → Community
plugins**, enable community plugins for this pilot vault, then enable
**Cairntir Workspace**. This is a manual installation from the repository;
there is no npm build step. See Obsidian's
[community plugin instructions](https://obsidian.md/help/community-plugins)
for the enable/reload controls.

### 4. Set the three connection fields

Open **Settings → Cairntir Workspace** and fill in:

| Setting | What to enter |
| --- | --- |
| Python executable | The full interpreter path printed in step 2, not the `cairntir` command or a shell command. |
| Cairntir home | A new absolute directory for the pilot memory store, outside the vault. This is a directory, not the `cairntir.db` filename. |
| Wing | A project name such as `obsidian-demo`. Use that exact name for this vault's workspace. |

Use actual paths on your computer. The plugin sets `CAIRNTIR_HOME` for its
Python subprocess; it does not change another agent's store configuration.
The first refresh initializes an empty store if needed. First use can also
download model assets, so allow it to finish before assuming a failure.

### 5. Refresh and verify a real result

1. Open the command palette with **Ctrl+P** on Windows/Linux or **Cmd+P** on
   macOS. Run **Cairntir Workspace: Refresh workspace**.
2. Open `cairntir-sync/index.md`. A new store starts with zero memories;
   existing data appears only when you select the store and wing containing it.
3. Run **Cairntir Workspace: Open question**. Enter a harmless question such
   as “What should I organize in this pilot vault?” and submit it. Wait for
   the committed result, then open **Cairntir Workspace: Show question register**.
4. Follow the new question's memory link. Confirm its text matches what you
   submitted. The workspace and `cairntir-sync/acknowledgements/` contain the result;
   creating an outbox file alone is not a confirmed save.
5. Add a sentence in the note's **My Notes** section, outside the generated
   block. Refresh again and confirm your sentence remains.

For a terminal check, use the **same** interpreter, home, vault, and wing as
the plugin. Replace all example paths below with your actual pilot paths.

```powershell
# Windows PowerShell; affects this shell's child processes only.
$env:CAIRNTIR_HOME = 'C:\path\to\pilot-memory'
& 'C:\path\to\.venv\Scripts\python.exe' -m cairntir obsidian-sync 'C:\path\to\Cairntir Pilot' --wing obsidian-demo
```

```sh
# macOS/Linux; applies the store selection to this command only.
CAIRNTIR_HOME='/absolute/path/to/pilot-memory' /absolute/path/to/.venv/bin/python -m cairntir obsidian-sync '/absolute/path/to/Cairntir Pilot' --wing obsidian-demo
```

A successful report has `projection.status` equal to `complete` and exits
with code 0. Refresh also retries queued requests in `cairntir-sync/outbox/`;
keep those files intact if you need to diagnose an error.

### 6. Connect the project you actually use

After the pilot works, back up the intended store and vault. In the Python
environment and store context your agent uses, `python -m cairntir status`
reports the home and database paths. Match that home, compatible Python
environment, and the exact project wing in the plugin settings. Use a new
vault for a different wing: an existing workspace is bound to its wing.

If your coding agent is not connected to Cairntir yet, follow
[installation and host setup](how-to-use.md#install). Ask it to save a small
project note and keep the receipt, then refresh Obsidian and compare the
matching note. A pilot plugin and an agent using another store will not see
each other's memories.

## Make the vault your own

Create a regular `Home.md` outside `cairntir-sync/`. This works without any
additional plugin:

```markdown
# My project

- [[cairntir-sync/index|Project memory]]
- [[cairntir-sync/questions|Open questions and resolutions]]
- [[Projects/Next steps]]
- [[Learning/What I learned]]
```

Create the linked personal notes when you need them. Add folders such as
`Projects`, `Decisions`, `Learning`, and `Templates`, or use your existing
organization. Write personal annotations under **My Notes**; refresh replaces
the content inside Cairntir's generated markers. Ordinary note edits stay in
Obsidian. Use **Correct current memory** for an explicit memory correction;
the [correction workflow](obsidian-corrections.md) explains receipts and retries.

For a dashboard like the showcase, ask your agent:

```text
Add a Home dashboard for this vault using its actual Cairntir workspace.
Read cairntir-sync/workspace.json to discover the available fields and note
paths. Show current memories with their room and links to the source notes.
Keep my layout and annotations outside generated files. If you use Dataview,
explain what needs installing and verify the query against real notes.
```

The standard Workspace notes do not contain the showcase adapter's
`wing::`, `room::`, and `status::` Dataview fields. Have the agent adapt the
dashboard to the data present instead of copying that query unchanged.
Start with one wing per vault; repeat the setup for separate projects. A
multi-wing dashboard or a button that refreshes several vaults is a custom
adapter, which your agent can build and test after the basic flow works.

## If something does not work

| Symptom | Check |
| --- | --- |
| Plugin missing | Confirm the two files are directly inside `.obsidian/plugins/cairntir-workspace/`, then reload and enable it. |
| Python or Cairntir not found | Use the full interpreter path and run that interpreter with `-m cairntir version`. |
| Empty index | Check the home and wing against the agent's actual save receipt. An empty pilot store is expected. |
| Missing `.obsidian` | Open the folder as a vault in Obsidian desktop first. |
| Workspace bound to another wing | Use a separate vault for the new wing. |
| Timeout on first refresh | Run the same terminal command to finish model setup and inspect its output, then retry from Obsidian. |
| Index identity or legacy-store refusal | Follow the backed-up [upgrade procedure](embedding-artifacts.md); keep the original store intact. |
| “Saved” with refresh still needed | Keep the request and receipt; retry the refresh as explained in the [correction workflow](obsidian-corrections.md). |

## Share your setup

Post your workflow, screenshots, or ideas in the
[showcase discussion](https://github.com/pnmcguire480/cairntir/discussions/182).
Tell people what you organize and what helped. Research, learning journals,
creative projects, and troubleshooting logs are all welcome.

For setup problems, [open an issue](https://github.com/pnmcguire480/cairntir/issues)
with your OS, Cairntir/Obsidian versions, the step you tried, and the error.
Check screenshots and logs for private details before sharing; keep memory
databases and private vault contents local.
