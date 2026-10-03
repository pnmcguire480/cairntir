# Cairntir Workspace — desktop pilot

This optional Obsidian plugin refreshes one Cairntir wing and submits append-only
corrections. It does not import ordinary vault notes, watch files, sync on
startup, or provide independent evaluator custody. Historical memories remain
preserved; a committed correction creates a new version.

## Install in a disposable pilot vault

Use Obsidian desktop 1.13.7 or later and a Python environment containing the
development Cairntir backend with `obsidian-sync`. No JavaScript build or npm
dependencies are required. Copy `main.js` and `manifest.json` into
`plugins/cairntir-workspace/` under the pilot vault's configuration directory
(usually `.obsidian`), then enable **Cairntir Workspace** in Community plugins.

Configure all three settings explicitly:

- **Python executable:** full path to the development environment's interpreter.
- **Cairntir home:** full path to a disposable, isolated Cairntir store.
- **Wing:** the project wing in that store.

There is no default store fallback. Keep this first pilot separate from the
production memory store and your working vault.

## Refresh and correct

Run **Cairntir Workspace: Refresh workspace** from the command palette. It runs
the configured Python backend explicitly and generates the workspace under
`cairntir-sync/`. The backend also retries existing requests in that wing.

Open a current editable memory note, then run **Cairntir Workspace: Correct
current memory**. The dialog begins with the exact source content from
`cairntir-sync/workspace.json`, excluding generated note formatting. Edit the
text and choose **Submit correction**. Cancel creates no request. Direct edits
to generated Markdown are not correction submissions.

Submission creates one UUID-named JSON request in `cairntir-sync/outbox/`, then
runs the backend. The plugin confirms a save only after receiving a matching
committed receipt bound to the submitted source and exact correction content.
Queuing a file or starting Python is not confirmation. A valid structured report
can accompany the backend's ordinary exit code 1; killed processes, timeouts,
spawn failures and malformed reports cannot confirm a save.

On failure, the request stays in the outbox. **Retry request** in the open
dialog reuses it; **Refresh workspace** also retries queued work. Once queued,
the dialog's text is locked so retries cannot silently change that request.
If the source became stale, refresh and open its current version to make a
new explicit correction. A database commit with failed receipt writing or
failed workspace refresh is reported as saved with a retry still required.

The subprocess uses `execFile` without a shell, a two-minute timeout, a bounded
output buffer and hidden Windows process. It receives the configured
`CAIRNTIR_HOME` and `PYTHONUTF8=1`. Settings are saved locally in the plugin's
Obsidian data. Nothing runs merely because the plugin is enabled.

The plugin uses the documented [Obsidian desktop API](https://github.com/obsidianmd/obsidian-api/blob/master/obsidian.d.ts):
`PluginSettingTab`, `Setting`, `Modal`, `FileSystemAdapter` and `Vault.create`.
Mock integration checks exercise those interfaces; they do not establish a
native Obsidian UI session or independent custody.
