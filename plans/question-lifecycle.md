# R08: explicit question lifecycle

Port the existing Week 1 question contract onto qualified combined PR128
`9e65c37c9a734f88d54935933047bda598e03146`. Its full hosted CI and CodeQL passed;
that does not qualify the new question feature automatically.

## Finite outcome

Explicitly open exact questions with an owner or unassigned state, list them,
and append evidence-linked declared resolutions. Retain original content and
provenance, stable portable identity and payload-bound retry after restart.
Validate local ID, portable UUID and exact UTF-8 content hashes. Resolution
records a declaration, not proof of answer truth or authenticated ownership.

Ordinary corrections, supersession and forged-looking metadata cannot close
typed questions. Preserve the existing distinction between current legacy
questions and superseded unverified history. Withhold a scoped lifecycle if
any required evidence is unavailable; do not reopen hidden resolutions.

Deliver the existing question CLI group, explicit Obsidian outbox and forms,
linked Markdown/JSON register, preserved human annotations and consistent
handoff classification. Startup and ordinary note edits never submit requests.
Retain 21 MCP tools, existing restricted-session boundaries, dependencies and
database schema. A committed receipt requires actual durable storage: caller
transactions are refused before any question write or acknowledgement.

## Frozen acceptance and verification reserve

The original [72-file package](acceptance/v2-questions/README.md) remains
byte-identical, including every earlier failure, amendment and binding correction.
Its 34 Python cases and two plugin harnesses are reused against the new source.
The [fresh port contract](acceptance/questions-port-1.16/CONTRACT.md) adds 12
independent controls for caller transactions, rollback, separate-connection
visibility and restart replay. Structural baseline absence is recorded distinctly
from assertion-level regression evidence. Fresh source bindings accompany runs.

Actual subprocess and installed-wheel proof remain distinct from CliRunner and
mocked UI. Freeze any new process helper before executing it; preserve old counts
as historical evidence rather than claiming them for this port. Existing
correction/practice and ordinary handoff regressions remain required.

Reserve at least 25% of effort for verification and permit at most two product
repair rounds. Preserve original failures; do not edit frozen assertions or
weaken the unchanged 92% full-source coverage floor. Run local checks serially
with synthetic stores and isolated paths; full source, models and installed
qualification run only on the authorized public hosted CI environment.

## Status and boundaries

Independent local acceptance passes 48 checks and 51 subtests after one product
repair: revoked scoped grants now pass through the existing question-error
translation. The original question plugin matrix passes 81 cases/957 assertions.
A separately frozen actual-process case passes five synthetic CLI launches,
including retained retries, partial failures and restart refresh. The original
correction plugin passes 46 cases/401 assertions; selected retained regressions
pass 68 checks/21 subtests with one inherited Windows symlink privilege skip.
Both durable-acknowledgement and ordinary-supersession fault controls detect their
injected faults. The first ineffective supersession injector and its additive
versioned amendment remain preserved; no frozen product assertion changed.

The installed verifier retains every existing assertion and adds a hash-bound
question helper. Its execution, full coverage and exact-head hosted qualification
remain pending. Draft creation is not publication. Parent coordinates review and
integration; no redundant reviewer gate is introduced.

Native graphical Obsidian acceptance, actual operator/authentication/provisioning,
protected evaluator custody and broader 35-commitment product outcomes remain
separate and unproven by these public tests. No production install, store change,
base/main merge, credential/security change or separately billed model API call.
No measured cost/token saving is claimed.
