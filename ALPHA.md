# Cairntir 1.13.0: the work toward 2.0

Version 1.13.0 publishes the work toward 2.0 on PyPI, so it can be used and tested while the rest of the roadmap is finished. It is not the completed 2.0 release: 2.0.0 is reserved for the finished roadmap. Earlier builds of this work were GitHub-only previews numbered 2.0.0a1 to 2.0.0a4, and this version replaces them. Some features below are still experimental and say so.

## Install or upgrade

Use Python 3.11–3.13.

```sh
python -m pip install --upgrade cairntir
cairntir version
cairntir --help
```

**Upgrading an existing store from 1.12 or earlier needs one manual step.** This version uses database schema 8 and binds the semantic index to the exact model files and runtime versions. Until you rebuild the index, semantic search and saving new memories are refused; reading a drawer by id with `cairntir get` and counting with `cairntir status` keep working. Stop every client that uses the store, then run `cairntir reindex --yes --backup /absolute/path/to/new-backup.db`. The command writes that backup before it changes anything. Read the [upgrade guide](docs/embedding-artifacts.md) first. This upgrade, its restore and its rollback have been exercised on two Windows machines; other platforms have automated coverage only.

If you installed a 2.0.0a preview, `pip` treats it as newer than 1.13.0. Install this version explicitly with `python -m pip install "cairntir==1.13.0"`.

Connect your client's MCP configuration to the `cairntir-mcp` executable, or run `cairntir setup`. The existing MCP tool names remain available. Ordinary memory does not require enabling experimental background workers or native agent adapters.

## What you can try

| Area | Available preview behavior | Guide |
| --- | --- | --- |
| Memory provenance and correction | Origin-qualified references, explicit derivation/currentness and bounded whole-drawer recall. Work/home stores do not silently share numeric IDs. | [Origin and derivation](docs/origin-and-derivation.md) |
| Obsidian workspace | Explicit correction forms/outbox and visible accepted/conflicted/failed state, preserving human notes. | [Desktop plugin](addons/cairntir_obsidian/README.md), [correction protocol](docs/obsidian-corrections.md) |
| Managed agent continuity | Opt-in managed sessions and a supported Codex acknowledgement/cold-resume route. | [Managed sessions](docs/managed-sessions.md), [Codex](docs/codex-managed.md) |
| Practices and inspectable checks | Governed practice history, review scheduling, conflict/lifecycle handling, Python/resource checks and offline verification bootstrap. | [Practices](docs/practice-register.md), [resources](docs/resource-verification.md), [bootstrap](docs/verification-bootstrap.md) |
| Audience lock | Provisional audience revisions, confirmation by a person at a terminal and transfer into a specification. | [Audience lock](docs/audience-lock.md) |
| Content angles | A local model proposes 20 or more distinct angles for a captured audience, each ranked with a written reason per goal; you record your own pick beside the automatic one. | [Angles](docs/ideation-angles.md) |
| Channel drafts | `cairntir channels generate` turns a stored angle into a hook and format for a community post, a newsletter note and a short video, linked back to the angle. Drafts are model output, provisional and never posted. | [Channels](docs/ideation-channels.md) |
| Creative and Blender workflows | Source-bound editable calendar, stored iteration bytes, Blender scene capture and dated prior print recall. | [Calendar](docs/ideation-calendar.md), [artifacts](docs/iteration-artifacts.md), [Blender](addons/cairntir_blender/README.md) |

These capabilities have component-specific evidence from development. That evidence is not a passing result for the complete alpha or stable 2.0 suite. Existing v1 memory features and the bundled recipe files are foundations, not newly invented capabilities.

English text saying a decision was reversed does not automatically create a supersession relationship. Origin-qualified references are not continuous synchronization or live SQLite merging. Supported managed Codex continuity does not install universal editor hooks or recover text that was never captured.

## Experimental and unfinished work

Dream is an explicit opt-in preview with bounded background scheduling, candidates and stop/cancellation handling. Integrated usefulness/resource qualification remains incomplete; proposals do not automatically authorize code edits, rule promotion or memory deletion. A first real-model run (Mistral 7B through Ollama, 10 November 2026) found that Dream discarded every real answer because it never asked for its reply format; that is fixed in Unreleased. After the fix the run met the input, call-budget, stop and offline limits, but the original one-second tick limit of under 4 seconds failed in two of four timed runs (4.045 and 4.114 seconds). Those runs had no usefulness threshold or hardware limit to measure against. The maintainer set both afterwards. Dream is useful enough if the maintainer marks at least 3 of 10 proposals as worth acting on and none cites the wrong memories. The hardware limit is a model that fits in 5 GB of graphics memory and 8 GB of RAM, with Dream's own processes under 0.2 GB. The recorded resource use is within that limit: about 4.1 GB of graphics memory, 1.4 GB of RAM and 0.11 GB for Dream itself. The maintainer marked 3 of 10 real suggestions as worth acting on, with no wrong citations, which meets the bar exactly. The suggestions were drawn from made-up test notes, so this is weak evidence that Dream is useful on real memory. The tick limit stays at 4 seconds, and its failures stay recorded.

Channel and outline pipelines, HumanFlow teaching, UI/visual verification, field pilots and feedback efficacy remain unfinished. Candidate lessons stay candidates/HOLD. The local study exporter is usable and `cairntir study-deliver` stages uniquely named upload files with an add/replace/keep plan, proven locally against a simulated notebook; actual NotebookLM arrival and update in a real notebook (R13) remains open until the maintainer confirms it. The calendar does not publish content to external platforms.

## Known verification limits

Local Windows installed-wheel checks now pass CLI/MCP, interrupted-session
resume, all-table backup/restore, restored semantic recall and failed-write
rollback/retry. Retained evidence also verifies actual 1.12.4 upgrade/reindex
and restoration under 1.12.4. The [CI record](docs/release/v2-alpha-ci.md)
preserves three failed runner reports and the exact limits of that assessment.
These results do not establish protected evaluator custody or multi-platform
release readiness. The older packaging limitations below are historical.

**Coverage floor.** On 9 November 2026 the maintainer set an 87% coverage floor for this release, with 90% owed on a later date. The alpha previews used an 85% floor set on 4 November 2026. Earlier runs keep their results under the 90% floor they were measured against. See the [CI record](docs/release/v2-alpha-ci.md).

**2.0.0a1 search bug, fixed here.** In 2.0.0a1, every semantic search fails once a store passes 4,096 indexed chunks. Upgrade to this alpha if you installed that one.

**Historical: 2.0.0a1 did not pass its release gate.** The measurement at that time,
`5015aa9d`, passes all assertions across nine OS/Python jobs: 2,719 passes on
Windows; 2,717 passes and two skips on Linux/macOS. Coverage remains below the
unchanged 90% floor, at 86.11–86.13% on Linux/macOS and 87.11–87.12% on Windows.
Hosted installed/evaluation jobs are skipped downstream of that failure. Seven
later cases pass locally and await their own complete matrix; they add tests and
change no runtime code.
The [finish-line checklist](docs/release/v2-finish-line.md)
tracks the remaining release requirements. The earlier measurements below are
historical; they do not describe the current head.

- The latest complete source matrix (`2dd31354`) passes every assertion on all nine OS/Python jobs: 2,382 cases plus two skips per Linux/macOS job and 2,384 per Windows job. Coverage remains below the unchanged 90% floor: 78.70–78.74% on POSIX and 79.64–79.65% on Windows. The AST compatibility failure is cleared. Another 107 resource/bootstrap/Dream/practice cases pass locally; their hosted contribution remains unmeasured. Every earlier failure remains visible in the [CI record](docs/release/v2-alpha-ci.md).
- The subsequent `460e4223` run exposes 53 resource setup errors from shared runtime/cache drift and five Ubuntu bootstrap failures from its generated `lib64` alias. Its completed samples measure 80.54–80.57% coverage. The bounded bootstrap repair preserves the strict integrity guard, passes a frozen cold-runtime witness and the nine local bootstrap regressions; fresh POSIX/full-matrix qualification remains pending. Local symlink capability skips do not count as POSIX verification.
- The local admission harness currently loses its Guard profiler during an expected Git refusal: 21 selected checks produced 18 complete passes and 5 stage errors across 3 checks. The observer repair remains deferred; its failure has not been relabelled.
- Native Windows version reporting is independently verified in five framework cases, including real values, restoration and retained shell refusal. This is a test-harness improvement, not an extra product feature.
- Independent protected evaluator custody and complete installed upgrade/restore/rollback qualification remain open. Second supported-machine readiness is verified for embedding identity only (E22, below).
- Local packaging smoke checks establish a build/install/basic-memory/MCP server construction and tool metadata only. They do not establish model efficacy, graphical host adoption or stable release readiness.

## Follow-up roadmap

The original 35 commitments remain assigned: 27 component criteria complete, 8 open. This count is not a count of new features. The stable 2.0 planning target remains 6 November 2026, with 7 November reserve and 5 November GO/NO-GO; unresolved gates still determine readiness.

| Follow-up | Target |
| --- | --- |
| R12 HumanFlow teaching | 12 November 2026 |
| R13 NotebookLM delivery/update | 13 November 2026 |
| I03 channel adaptation | 19 November 2026 |
| Q04 UI/visual verification | 20 November 2026 |
| I05 outlines/action workflow | 24 November 2026 |
| R14 code-specific quizzes, audio and cross-project learning | 27 November 2026 |
| C50 LongMemEval/calibration and independent reproduction | 3 December 2026 |
| R16 ten-user pilot and structured feedback | 4 December 2026 |

I03 stays open. `cairntir channels generate` is built and a real local model (Mistral 7B through Ollama, 12 November 2026) produced accepted drafts for two angles, each with three channel-shaped outputs inside their limits, three different hooks, and a link back to the angle. Four earlier real attempts (Mistral three times, qwen3:8b once) were refused by the checks, each copying one hook into every channel, as the earlier attempt did. The accepted runs followed removing the angle's own hook from the text the model sees. The drafts are generic: hooks differ only slightly, wording is near-identical across channels, and one claims "our innovative solution" that the idea does not mention. Whether that meets "channel-specific hooks and formats" needs an independent reader; the register row is not marked complete.

I02 is complete against its original criterion: "Generate and rank distinct angles with human selection." `cairntir angles generate` asked a real local model (Mistral 7B through Ollama, 12 November 2026) for angles for a captured audience. It returned 20, all with different angles and hooks, each with a score and a written reason for both goals and a rank. `angles show` in a separate process returned the identical set, and `angles choose` recorded a pick beside the automatic top choice without replacing it. The model's reasons are thin (several only repeat the audience description) and many scores tie, so the ranking is weak evidence of quality; it is stored as model judgment and labelled provisional.

Q08 is complete against its original criterion: "Known-bad behavior falsifies the claim and corrected behavior passes; prompt text alone is never reported as an executed test." `cairntir claim-test` exports a stored claim and its predicted outcome to a packet with no subject source, freezes tests written by a different author by SHA-256, and runs exactly those bytes against a subject. On 11 November 2026 a separate agent that saw only the packet wrote 13 cases. They failed 7 of 13 against a deliberately broken subject (`FALSIFIED`) and passed 13 of 13 against the corrected one (`HELD`). A packet with no executed case is `NOT_EXECUTED`, and a test that passes against the broken subject is `NOT_QUALIFIED`. Cairntir does not write the tests itself; any host or person can be the author.

E22 is complete against its original criterion. A second physical machine (the work PC, not Patrick's own) acquired the model into an empty cache and produced the same five file hashes and the same identity as the home machine, and refused a one-byte model change (receipts dated 3 and 4 November 2026 on commit 5015aa9d, and again on 10 November 2026 on the 1.13.0 release commit 3b02538f, all 18 checks passing). This does not cover upgrade/restore/rollback or any other feature on that machine. Protected evaluator custody is a separate open release gate. [The portable 35-item register](docs/alpha-roadmap.json) retains every item; local proof archives and machine-specific paths are excluded from this branch.

Report the alpha version, host/OS, minimal reproduction and observed versus expected behavior when opening an issue. Do not upload private memory stores, vaults or authentication files.
