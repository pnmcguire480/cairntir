# Independent foundation acceptance contract

Frozen on 2026-09-06 UTC. Tester: `/root/foundation_tester`. Independent coverage
review: PASS by `/root/foundation_review`; coordinating scope review: PASS.
The root agent and future implementers must not edit the tester-owned artifacts.
Exact hashes and support inputs are in
[v2-foundation-freeze.json](v2-foundation-freeze.json).

Authority: the foundation criteria in [v2-continuity.md](v2-continuity.md),
[issue #88](https://github.com/pnmcguire480/cairntir/issues/88), and the
[Finalization Mode recipe](../docs/recipes/finalization-mode/README.md).
This acceptance step ends at a reviewed hash freeze. Runtime implementation,
release, later portability/procedural-learning milestones, dependencies,
production stores and installed software are outside this step.

## Public contract refinement

The plan did not define task-mode wire fields. These are a deliberately small,
tester-authored interface contract, proposed before implementation and approved
for review by the coordinating agent. They specify observable results, not the
selection algorithm, schema migrations, ranking weights or internal modules.

`CairntirBackend.handoff` retains its current parameters and adds optional
`task: str | None = None` and `candidate_limit: int | None = None`. Omission of
`task` keeps legacy behavior; an explicit blank task is a typed error. The
existing MCP `cairntir_handoff` tool exposes both additions. CLI equivalents are
`handoff WING --task TEXT --candidate-limit N`, alongside existing options.
There remain exactly 21 MCP tools.

Task mode returns one JSON document. Required fields are:

| Field | Meaning |
| --- | --- |
| `wing`, `task` | Exact requested wing and task. |
| `status` | `selected` or `abstained`. |
| `evidence` | Whole original records with `drawer_id`, `resource`, `content`, complete `provenance`, `instruction_authority: "none"`, and nonempty `reasons`. |
| `excluded`, `omitted` | Content-free receipts with `drawer_id` and `reasons`; no private content or source metadata copied from excluded drawers. |
| `omitted_count` | Total budget omissions, even when individual receipts do not fit. |
| `conflicts` | Groups with `drawer_ids` and `status: "unresolved"`. |
| `scan` | `limit` (integer or null), `scanned` (integer), `complete` (boolean). |
| `budget` | `limit_chars`, `rendered_chars`, `estimated_tokens`, descriptive `token_basis`. |
| `abstention_reason` | Required on abstention: `no_matching_evidence` or `budget_exhausted` for the tested cases. |

Reason vocabulary exercised by the suite: `exact`, `semantic`, `anchor`,
`expired`, `future_valid`, `secret`, `suspicious`, `superseded`, and `budget`.
Additional reasons and nonsecret fields are permitted. Full provenance means
the existing `WriteProvenance.to_dict()` receipt, including validity timestamps.
JSON quoting never grants source content instruction authority.

Task selection scopes evidence and successor relationships to the requested
wing. A current successor suppresses its predecessor even if the successor
does not independently match the task. A future successor or a successor in a
different wing does not suppress current evidence. Branching current claims
remain an explicit unresolved conflict; a branch without lexical/vector task
overlap must not disappear and create apparent agreement. Automatic selection
excludes expired, future-valid, secret and suspicious candidates even when
their declared trust is `system`. These classifications are evidence handling,
not authenticated permission enforcement.

`candidate_limit=3` over twelve eligible candidates must disclose exactly three
scanned candidates and `complete: false`. Without an explicit cap, an internal
cap must still be disclosed. The 150-candidate omission test requires a complete
scan of that small corpus and an honest aggregate omission count. Receipts may
be bounded; original evidence may not be truncated.

## Exact budget envelope

The budget counts characters, using Python `len(str)`, rather than UTF-8 bytes
or billed tokens. It covers the largest actual response representation tested:

1. the complete backend JSON text, including task, evidence, provenance,
   escaping, exclusions, omissions, conflicts and all receipts;
2. CLI stdout, including its terminating newline;
3. the serialized existing MCP `CallToolResult.model_dump_json()`, including
   `TextContent` wrapper fields and the second layer of JSON escaping.

The outer JSON-RPC envelope, request ID, protocol framing and host-added
material are outside this character contract. No combined host context or
billing ceiling is claimed. Backend and MCP evidence text remain identical;
backend packing therefore needs enough reserve for the transport envelope.
An optional update banner cannot be prepended to task JSON and invalidate its
format or ceiling; the suite injects an oversized pending banner twice.

`budget.rendered_chars` is the measured backend JSON text length, not evidence
content length and not the outer MCP envelope length. `estimated_tokens` is that
measured text length divided by four, rounded down, and `token_basis` explicitly
calls it an estimate. The envelope is measured independently at transport.
Positive budgets 2,048, 4,096 and 8,192 must work for the tested fixtures.
Zero, negative, boolean, fractional, string and impossibly small budgets (1 and
32 characters) must produce surfaced typed errors in the backend, with clean
CLI/MCP error responses. Error messages are outside an impossible output budget.

## Recovery and legacy compatibility

Legacy handoff has a fixed golden SHA-256 in the suite, captured from the
unmodified base runtime for its deterministic fixture (1,098 characters):
`5d125140f11bfc0ca4fa9fa0a79a073b0d9b9864d7783a7930ab47d14a71689a`.
The full unchanged legacy regression files listed below are mandatory gates.
Together they prove existing handoff, interrupted Claude/Codex/Qwen request
recovery, explicit unsupported Cursor, consent and no automatic storage.

Task mode must not read transcripts without explicit opt-in. A task request
combined with requested recovery may either raise a typed error naming the
task/recovery incompatibility, or return a `recovery` object inside the same
fully bounded JSON document. The supported form has `status`, `budget_chars`
and whole `requests` with `content` and `instruction_authority: "none"`; its
separate content budget and the complete combined response ceiling both hold.
Neither route may mutate memory or transcript files. This latitude reflects
the plan's prohibition on silently ignoring recovery, not a mandate to support
every combination immediately.

## Demo interface and evidence

Extend existing `cairntir.cost` with
`run_context_demo(output_dir: Path, *, budget_chars: int)`. Its return value is
unconstrained. It creates `report.json`, `report.html` and temporary-demo store
files under the supplied directory. No store may open elsewhere; no network
connection is permitted. The test observes real store opens/closes and real
backend handoff calls, and requires reported selection and abstention to be
actual calls made after closing and reopening the same database.

The JSON report contains `request`, `full_history_payload`, `selected_payload`,
`abstention_payload`, `metrics` and `fixtures`. `full_history_payload` is a JSON
object with an `evidence` array containing every persisted drawer content;
the test compares that multiset to the reopened database, including stale/noisy
evidence. The selected response retrieves the exact request and contains only
original persisted content. The fixture inventory contains nonempty lists
`stale`, `noise`, `secret`, `suspicious`, and an `html_probe` string containing
a script-tag attack. The first four categories occur in history but never
selected evidence. The HTML displays the probe as inert escaped text.

Classification is `fixture_kind: "synthetic"`,
`evaluation_kind: "local_backend"`, with empty `transport_evaluations`,
`commercial_host_evaluations`, and `model_evaluations`. CLI/MCP transport proofs
are separate suite tests; the demo must not claim that it ran them or used a
commercial host/model. HTML visibly labels synthetic evidence, estimates and
the distinction from transport evaluation.

Metrics contain `full_history_chars`, `selected_chars`,
`payload_reduction_percent`, `token_basis`, and `billing_savings: null`.
Lengths are recomputed from actual payload strings; reduction may be negative
and must remain honest. Repeated runs in different directories produce the
same selected/abstention payloads and metrics. HTML must contain the measured
character values, use escaped untrusted content, have no executable script,
forms, event handlers, remote/local asset references, CSS URLs or imports.
It must not execute or promote recovered instructions.

## Acceptance mapping and required evidence

| Plan item | Executable proof in `tests/unit/test_context_acceptance.py` |
| --- | --- |
| Relevant whole original evidence, scoped provenance, no authority | `test_exact_original_and_full_provenance_are_delivered`, deterministic semantic route, anchor boundary test, current provenance test. |
| Validity, supersession, unresolved conflict | Parameterized exclusions and inapplicable-successor tests, unmatched-successor test, branching-successor conflict test. |
| Abstention and bounded scan disclosure | No-match cases, explicit candidate-limit case, aggregate omission case. |
| Complete budgets and typed errors | Parameterized escaping/provenance/receipt budgets, invalid budgets, blank tasks, actual MCP envelope/banner test. |
| Pure reads, no network dependency | All-table SQLite snapshots plus file hashes around repeated backend/CLI/MCP reads; blocked socket tests. Snapshots include vector/shadow tables, provenance, counters, beliefs and schema. |
| Legacy behavior and 21-tool CLI/MCP parity | Golden legacy hash, tool schema test, actual CLI/MCP handler parity and surfaced errors; unchanged full regression gate below. |
| Recovery consent, no automatic storage, explicit combination handling | Guarded transcript reads and opt-in compatibility test; unchanged `test_transcript.py` gate. |
| Actual semantic quality beyond deterministic geometry | Mandatory `eval`/`slow` test with cached FastEmbed production model. Deterministic vectors prove plumbing only. |
| Isolated repeatable honest demo | Real close/reopen and handoff observation, persisted corpus comparison, recomputed metrics, escaped offline HTML and repetition tests. |

The real semantic test explicitly pins the current foundation production choice,
`FastEmbedProvider`; it is separate from deterministic fixture tests and from
commercial-model evaluation. Set `CAIRNTIR_ACCEPTANCE_MODEL_CACHE` to an already
provisioned local FastEmbed model cache. The test copies it into its isolated
temporary home, forces offline mode, and forbids network connections. Missing
or unusable assets fail with `FOUNDATION_INFRASTRUCTURE` and are reported as
INCONCLUSIVE for semantic behavior, never skipped, counted as behavior PASS,
or substituted with a hash embedder. A future production-provider change needs
an explicit contract amendment, not a silent weaker test route.

No finite test suite proves absence of every network path or arbitrary code
execution. Independent source review, full regression, lint, strict types,
package/CLI/MCP smoke, docs build and visual report inspection remain required
at implementation finalization. The implementation's final quarter is reserved
for verification, with at most two repair rounds. Acceptance artifact changes
after freeze invalidate the run; amendments require a new independent freeze.

## Reproduction and pre-implementation baseline

Run from the repository root with the existing development environment:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_context_acceptance.py --no-cov -q -m 'not eval' --tb=no
.\.venv\Scripts\python.exe -m pytest tests/unit/test_context_acceptance.py --no-cov -q -m eval --tb=short
.\.venv\Scripts\python.exe -m pytest tests/unit/test_handoff.py tests/unit/test_transcript.py tests/unit/test_mcp_server.py tests/integration/test_mcp_backend.py tests/unit/test_cost.py --no-cov -q
.\.venv\Scripts\python.exe -m ruff check tests/unit/test_context_acceptance.py
.\.venv\Scripts\python.exe -m ruff format --check tests/unit/test_context_acceptance.py
```

Baseline record: [v2-foundation-baseline.json](v2-foundation-baseline.json).
Base runtime HEAD: `ad3ccee95d6d4c0bc5cb5b57e1ec76d799d23c3e`; Python 3.11.9.

| Gate | Independent baseline result |
| --- | --- |
| Deterministic foundation | **FAIL:** 39 failed, 1 passed, 1 eval test deselected in 2.02s. |
| Required real embeddings | **INCONCLUSIVE:** 1 failed, 40 deselected in 1.17s; explicit local cache prerequisite unset. |
| Complete five-file legacy regression gate | **PASS:** 153 passed in 14.73s, with no marker narrowing. |
| Acceptance Ruff and format | **PASS**. |
| Isolation harness probes | **PASS:** access mutation and transcript mutation detected; temporary database cleanup succeeded. |

The deterministic failures are expected absent task mode, MCP schema additions
and demo helper. The one pass is the frozen legacy golden/parity proof. No
collection errors, skips or xfails occurred. Semantic infrastructure failure is
kept separate from behavioral red and supplies no semantic evidence.

Before freeze, a separate probe exposed a tester-side Windows database handle
leak: `with sqlite3.connect()` controls transactions but does not close the
connection. Both read-only inspection sites now use `contextlib.closing`.
Independent review verified this was the only change after the first coverage
PASS, with no assertion weakening; the final helper probes and acceptance gates
were then rerun. The unchanged legacy regression evidence remains applicable.

Artifact readiness is **PASS**. Foundation implementation acceptance is **FAIL**;
the real semantic item is **INCONCLUSIVE**. This frozen test-authoring step is
complete and carries no implementation, full-repository, demo, shipping or 2.0
completion claim.
