# Continuity demo

This demonstration is part of the unreleased continuity foundation. It creates
synthetic memories, closes the store, opens it again, and retrieves the exact
unfinished request with the relevant current evidence. A second request shows
explicit abstention. The report exposes both payloads and their measured sizes.

From the development checkout:

```bash
uv run cairntir context-demo ./continuity-demo --budget 8192
```

Open `continuity-demo/report.html`. The directory also contains `report.json`
and the synthetic SQLite store. Choose a fresh output directory for each run;
existing demo artifacts are preserved. No production store, network service,
or model download is needed. HTML uses escaped text and embedded CSS only.

The report labels the corpus as synthetic and the evaluation as local backend
calls. The baseline includes all original memories and provenance; the selected
payload is the actual task-handoff response. Character lengths and percentage
reduction are recomputed from these strings. Token figures use characters
divided by four and are estimates. There is no billed-token or task-success
claim. CLI/MCP transport tests and real-embedding acceptance are separate gates;
this demo does not evaluate commercial hosts or models.

## Use task-aware handoff

```bash
cairntir handoff myapp --task "repair cache invalidation" --file src/cache.py --budget 8192
```

The existing MCP tool accepts the same request:

```json
{"wing":"myapp","task":"repair cache invalidation","files":["src/cache.py"],"budget_chars":8192}
```

Task JSON returns whole original evidence with provenance and no instruction
authority. It identifies excluded, omitted and conflicting candidates, and
abstains when no eligible evidence matches or none fits. Future-valid, expired,
superseded, secret and suspicious candidates cannot become automatic evidence.
These classifications do not establish authenticated permissions.

The ceiling covers the complete backend text, CLI newline, and serialized MCP
`CallToolResult`, including its JSON escaping. Outer JSON-RPC framing and text
added by the host are outside the ceiling. `budget.rendered_chars` measures the
backend text; the transport envelope is checked separately. Impossible budgets
produce a typed error.

Task mode requires an initialized store and cached local embeddings. Its read
path does not create or migrate a store, download weights, update access counts,
or append diagnostic logs. Provision the store and model through the normal
setup flow before using it. Use `cairntir recover` separately for opt-in
transcript recovery. Handoff without a task retains the existing behavior.

The task CLI reads a private, committed snapshot even while another WAL client
is open or holds an uncommitted write. Cold reads preserve all source files.
Live CLI and MCP reads preserve stored evidence and access state; SQLite may
maintain existing shared-memory read-lock bookkeeping. Genuine exclusive locks
produce a bounded, explanatory failure. The [independent concurrency tests](../plans/context-concurrency-result.md)
cover concurrent writes, checkpoints and connection shutdown.
