# Cairntir 2.0.0a1 preview

An experimental preview of the work toward 2.0. Stable PyPI remains 1.12.4. This preview makes the new code available for feedback; it is not the completed 2.0 release.

## Install from the preview branch

Use Python 3.11–3.13 in a separate virtual environment. Install the published preview branch:

```sh
python -m venv .venv-alpha
# Activate .venv-alpha for your shell, then:
python -m pip install "git+https://github.com/pnmcguire480/cairntir.git@codex/v2-alpha-preview"
cairntir version
cairntir --help
```

Set `CAIRNTIR_HOME` to an absolute disposable directory before starting Cairntir or its MCP client. This preview uses database schema 8 and creates a backup before migrating an older store. The full upgrade/restore/rollback workflow is still unqualified; use a separate store and pilot vault for this preview.

Connect your client's MCP configuration to the virtual environment's `cairntir-mcp` executable. Ensure that client inherits the same isolated `CAIRNTIR_HOME`. The existing MCP tool names remain available. Ordinary memory does not require enabling experimental background workers or native agent adapters.

## What you can try

| Area | Available preview behavior | Guide |
| --- | --- | --- |
| Memory provenance and correction | Origin-qualified references, explicit derivation/currentness and bounded whole-drawer recall. Work/home stores do not silently share numeric IDs. | [Origin and derivation](docs/origin-and-derivation.md) |
| Obsidian workspace | Explicit correction forms/outbox and visible accepted/conflicted/failed state, preserving human notes. | [Desktop plugin](addons/cairntir_obsidian/README.md), [correction protocol](docs/obsidian-corrections.md) |
| Managed agent continuity | Opt-in managed sessions and a supported Codex acknowledgement/cold-resume route. | [Managed sessions](docs/managed-sessions.md), [Codex](docs/codex-managed.md) |
| Practices and inspectable checks | Governed practice history, review scheduling, conflict/lifecycle handling, Python/resource checks and offline verification bootstrap. | [Practices](docs/practice-register.md), [resources](docs/resource-verification.md), [bootstrap](docs/verification-bootstrap.md) |
| Creative and Blender workflows | Source-bound editable calendar, stored iteration bytes, Blender scene capture and dated prior print recall. | [Calendar](docs/ideation-calendar.md), [artifacts](docs/iteration-artifacts.md), [Blender](addons/cairntir_blender/README.md) |

These capabilities have component-specific evidence from development. That evidence is not a passing result for the complete alpha or stable 2.0 suite. Existing v1 memory features and the bundled recipe files are foundations, not newly invented capabilities.

English text saying a decision was reversed does not automatically create a supersession relationship. Origin-qualified references are not continuous synchronization or live SQLite merging. Supported managed Codex continuity does not install universal editor hooks or recover text that was never captured.

## Experimental and unfinished work

Dream is an explicit opt-in preview with bounded background scheduling, candidates and stop/cancellation handling. Integrated usefulness/resource qualification remains incomplete; proposals do not automatically authorize code edits, rule promotion or memory deletion.

Audience/angle/channel/outline pipelines, HumanFlow teaching, UI/visual verification, claim-to-test generation, field pilots and feedback efficacy remain unfinished. Candidate lessons stay candidates/HOLD. The local study exporter is usable, but actual NotebookLM delivery/update remains open. The calendar does not publish content to external platforms.

## Known verification limits

Current measured head `81ed7897` passes all assertions across nine OS/Python
jobs: 2,664 passes on Windows; 2,662 passes and two skips on Linux/macOS.
Coverage alone remains below 90%, at 84.131543–85.109404%. Installed/evaluation
jobs remain blocked downstream. The [finish-line checklist](docs/release/v2-finish-line.md)
tracks the remaining release requirements. The earlier measurements below are
historical; they do not describe the current head.

- The latest complete source matrix (`2dd31354`) passes every assertion on all nine OS/Python jobs: 2,382 cases plus two skips per Linux/macOS job and 2,384 per Windows job. Coverage remains below the unchanged 90% floor: 78.70–78.74% on POSIX and 79.64–79.65% on Windows. The AST compatibility failure is cleared. Another 107 resource/bootstrap/Dream/practice cases pass locally; their hosted contribution remains unmeasured. Every earlier failure remains visible in the [CI record](docs/release/v2-alpha-ci.md).
- The subsequent `460e4223` run exposes 53 resource setup errors from shared runtime/cache drift and five Ubuntu bootstrap failures from its generated `lib64` alias. Its completed samples measure 80.54–80.57% coverage. The bounded bootstrap repair preserves the strict integrity guard, passes a frozen cold-runtime witness and the nine local bootstrap regressions; fresh POSIX/full-matrix qualification remains pending. Local symlink capability skips do not count as POSIX verification.
- The local admission harness currently loses its Guard profiler during an expected Git refusal: 21 selected checks produced 18 complete passes and 5 stage errors across 3 checks. The observer repair remains deferred; its failure has not been relabelled.
- Native Windows version reporting is independently verified in five framework cases, including real values, restoration and retained shell refusal. This is a test-harness improvement, not an extra product feature.
- Independent protected evaluator custody, second supported-machine readiness and complete installed upgrade/restore/rollback qualification remain open.
- Local packaging smoke checks establish a build/install/basic-memory/MCP server construction and tool metadata only. They do not establish model efficacy, graphical host adoption or stable release readiness.

## Follow-up roadmap

The original 35 commitments remain assigned: 23 component criteria complete, 12 open. This count is not a count of new features. The stable 2.0 planning target remains 6 November 2026, with 7 November reserve and 5 November GO/NO-GO; unresolved gates still determine readiness.

| Follow-up | Target |
| --- | --- |
| I01 audience workflow | 11 November 2026 |
| R12 HumanFlow teaching | 12 November 2026 |
| R13 NotebookLM delivery/update | 13 November 2026 |
| I02 audience-bound angles | 17 November 2026 |
| I03 channel adaptation | 19 November 2026 |
| Q04 UI/visual verification | 20 November 2026 |
| I05 outlines/action workflow | 24 November 2026 |
| Q08 claim-to-test generation | 25 November 2026 |
| R14 code-specific quizzes, audio and cross-project learning | 27 November 2026 |
| C50 LongMemEval/calibration and independent reproduction | 3 December 2026 |
| R16 ten-user pilot and structured feedback | 4 December 2026 |

E22 embedding artifact identity on a second supported machine remains open. Protected evaluator custody is a separate open release gate. [The portable 35-item register](docs/alpha-roadmap.json) retains every item; local proof archives and machine-specific paths are excluded from this branch.

Report the alpha version, host/OS, minimal reproduction and observed versus expected behavior when opening an issue. Do not upload private memory stores, vaults or authentication files.
