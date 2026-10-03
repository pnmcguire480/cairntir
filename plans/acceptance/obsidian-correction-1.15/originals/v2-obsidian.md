# Obsidian correction loop — Week 1 increment

The desktop workspace can submit a correction to a recorded memory and receive
a durable acknowledgement. SQLite retains the original and the correction;
Obsidian shows their relationship with links. This exposes the existing memory
inventory (R11) and adds the previously missing correction workflow.

The user amended scheduling on 20 September 2026: physical evaluator setup must
not block feature work. Public acceptance is independently authored and frozen.
Protected holdout custody remains unverified. The original approved roadmap
snapshot and all 35 commitments remain unchanged.

## Contract

An explicit correction identifies the current drawer by local ID, portable
source UUID and SHA256 of its exact UTF-8 content. Its request UUID is permanently
bound to the payload. A transaction appends the replacement and its receipt;
repeating the identical request after a restart returns the same receipt.
Changed payloads, stale sources and mismatched identities are rejected.

The original content, metadata and provenance remain unchanged. Corrections
inherit the source's room, layer and privacy classification. Their provenance
is untrusted: a writable local file does not authenticate its author or make
its claims true. Task checkpoints, prediction records and other structured
workflow records require their own lifecycle adapters and cannot be edited
through this generic text correction command.

Only explicit JSON requests in `cairntir-sync/outbox` are consumed. Personal
notes and edits to generated text are not interpreted as commands. Requests
remain available for retry. A committed database write is reported separately
from a failed acknowledgement file or failed projection, so retry can finish
the view without duplicating the correction.

## Use

Select an explicit disposable `CAIRNTIR_HOME` for a rehearsal, then run:

```sh
cairntir obsidian-sync PATH_TO_VAULT --wing PROJECT_WING
```

The vault must already contain `.obsidian`. The generated workspace is bound
to one wing and lives in `cairntir-sync`. `workspace.json` contains exact text
and source identities; `index.md` and `memory/drawer-ID.md` expose current and
historical records. Secret records are excluded. Text outside owned Markdown
blocks is preserved. Generated-marker literals are escaped in Markdown while
the exact content remains in JSON and SQLite.

The desktop plugin in [addons/cairntir_obsidian](../addons/cairntir_obsidian/README.md)
provides refresh and correction commands. Configure the Python executable,
Cairntir home and wing explicitly. Nothing runs automatically on plugin load.
Submitting a correction stores an outbox request and invokes the same CLI.
The plugin reports acknowledgement only after receiving a matching committed
receipt; pending and failed operations remain visible.

The existing one-way `obsidian-project` and walkthrough `vault-sync` commands
retain their contracts. This increment does not claim automatic lifecycle
dispatch (R06/R09), promise capture (R07), question resolution (R08), generated
Last Session (R10), embedding artifact pinning (E22), or MCP recall budgeting
(E23). Those remain named Week 1 commitments.

## Verification

Public acceptance covers exact content, source preservation, wrong-store
routing, stale edits, atomic failures and restart retries against disposable
SQLite stores. File and plugin acceptance exercise acknowledgement recovery
and explicit desktop command behavior. These checks are public, and simulated
Obsidian APIs do not establish that a graphical user performed the workflow.
Reserve 25% of this increment for verification and at most two repair rounds.


### Local result — 2026-09-20

**COMPLETE for the public implementation increment**, with graphical deployment
still pending. Independent core/file acceptance: 27 passed, 21 subtests and one
Windows privilege skip. Source suite: 1,790 passed at 92.060586% coverage.
Evaluation, slow, static, integrity, documentation, five historical regression
pairs, 15 mutation pairs, build and installed CLI/MCP gates passed.

[Plugin evidence](acceptance/v2-obsidian-plugin/README.md) records 46 cases and
401 assertions, plus actual CLI partial-write/retry and clean-process pilots.
A separate installed-wheel check, using Python 3.11.9 and all 61 locked
dependencies, confirms exact Unicode/CRLF correction, unchanged original,
exactly two records and the same acknowledgement after reopening. The tested
wheel SHA256 is `52278f0cf661897f46f33b7e734f1086e99188b8e9465058b6896c9719f112f4`.

Earlier failed outcomes remain recorded. Test-harness repairs are independently
owned, versioned and hash-frozen; a changed expectation never substitutes for
a product repair. Frozen [bridge acceptance](acceptance/v2-obsidian/CORE-ACCEPTANCE.md)
includes negative controls. The [host helper](../scripts/evaluator/README.md)
passes 263 Windows PowerShell 5.1 assertions. Neither these public checks nor a
separate model establishes private evaluator custody.
