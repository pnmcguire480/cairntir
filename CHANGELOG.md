# Changelog

All notable changes to Cairntir will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses three-segment
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) numbering with one
documented deviation: a deprecated public surface may be removed in a MINOR
release after the two-minor warning window, rather than requiring a MAJOR bump.
`2.0.0` is reserved for a revolutionary change in what Cairntir is. See
[docs/release-cadence.md](docs/release-cadence.md) and
[docs/deprecation-policy.md](docs/deprecation-policy.md).

## [Unreleased]

### Added

- **A bounded hotfix ledger preserves the path from failure to terminal
  evidence.** `cairntir_hotfix`, `cairntir hotfix`, and the Bounded Hotfix
  recipe compare cited precedents, seal exact authority and preflight bindings,
  allow one host-executed attempt per authority, reject unchanged failed-state
  retries, require independent verification or exact rollback, and terminate as
  `COMPLETE`, `BLOCKED`, or `EXHAUSTED`. Cairntir records and validates the
  workflow but never executes repairs or elevates memory into authority.

### Changed

- Replaced the duplicated, stale README addendum and hidden keyword list with a
  concise 1.8.0 front door structured around the current release, supported
  agent hosts, verifiable capabilities, and the search language people use for
  persistent AI coding-agent memory. The docs home, setup guide, and issue
  template now identify 1.8.0 consistently.

### Fixed

- The release workflow now allows PyPI index propagation before its independent
  post-publish verification. The 1.8.0 publication succeeded before PyPI's JSON
  response exposed its files, so the first immediate verification saw a stale
  empty result.

## [1.8.0] — 2026-08-30

### Added

- **Bounded, opt-in transcript recovery closes the killed-before-first-tool
  gap.** `cairntir recover --host claude|codex|qwen` and
  `cairntir handoff --recover-from HOST` read only the newest non-live project
  transcript tail. The MCP handoff exposes the same path through
  `recover_transcripts=true`. Whole user messages fit under a separate
  character budget or are named without being truncated.
- **Qwen Code, Claude Code, and Codex adapters are fixture-tested against
  locally observed schemas.** Each adapter ignores tool results and uses its
  host's completion marker. Codex filters app-injected context records; Qwen
  takes only the original first text part rather than hook-appended context.
  Cursor returns an explicit unsupported receipt because its documented local
  SQLite history has no stable transcript schema.
- **Recovered transcript messages remain untrusted evidence.** Output carries
  `trust=untrusted`, `instruction_authority=none`, host/session/timestamp
  provenance, injection signals, and an explicit no-automatic-storage
  receipt. `cairntir recover --write N` is the only write path and preserves
  untrusted `transcript_recovered` provenance.
- **Finalization Mode provides a bounded roadmap-closure recipe.** It freezes
  independently authored acceptance tests, reserves verification capacity,
  limits repair rounds, and terminates as `COMPLETE`, `BLOCKED`, or
  `EXHAUSTED` instead of manufacturing more work after the evidence is green.
- **Verified MCP wiring now covers eight agent hosts.** `cairntir init` supports
  Claude Code, Cline, Codex, Copilot CLI, Cursor, Gemini CLI, OpenCode, and Qwen
  Code without conflating host configuration support with the smaller set of
  transcript adapters. `scripts/wire_hosts.py` inspects and wires the installed
  fleet while refusing to guess unverified configuration surfaces.

### Changed

- **The release-tag gate stops calling an already-published current version
  "in-flight."** The current `pyproject.toml` version is exempt only until its
  tag exists; after tagging, the gate verifies that version on PyPI like every
  other release.

## [1.7.1] — 2026-08-25

### Fixed

- **`cairntir setup` required the Claude Code CLI and exited 1 without
  it**, so a Cursor-only user following the README's first command
  could not install. Setup now detects hosts, wires every supported
  adapter at user scope, and skips missing CLIs instead of failing.
  Cursor's paste-ready User Rule is printed by `setup` and by
  `cairntir init --host cursor --user`.
- **The installed memory policy told every agent to call
  `cairntir_session_start`**, which skips default-layer (`on_demand`)
  writes unless a query is passed. Default `cairntir_remember` is
  `on_demand`. The policy now starts with `cairntir_handoff`, which
  already returns those drawers from leftover budget. Every marked
  policy copy in the repo is checked against `MEMORY_POLICY`.
- **The docs-site How to Use page described a different product** —
  `pipx install -e c:/Dev/Cairntir`, expect `cairntir 0.1.0`, twelve
  tools. It now matches the supported 1.7 series. Docs home, MkDocs nav, SECURITY.md,
  and the README addendum no longer advertise 1.0 / 1.2.0-rc / 1.4.0
  as current.
- **Current-state sources disagreed with shipped behavior.** `CLAUDE.md`
  still reported 466 tests and three already-landed gaps; the roadmap called
  Phase 1 "next" and counted 18 MCP tools; the concept page counted 17; the
  plan map treated completed bootstrap and source-assessment plans as live;
  and memory drawer #215 still surfaced v1.3.0 as prepared but unpublished.
  The repository now agrees on the 20-tool surface and the actual v1.8.0
  transcript-recovery next step. A superseding drawer closes an explicitly
  flagged open question on the handoff path without rewriting its evidence.
- **The production tokenizer-window eval bypassed the production provider.**
  It constructed FastEmbed directly, looked in the temporary default cache,
  and failed the documented offline release gate even when Cairntir's anchored
  model cache was healthy. The test now loads the same provider and cache path
  as the CLI and MCP server.

### Changed

- PyPI classifier moved from Pre-Alpha to Beta, matching a published
  1.7.0.
- README tests badge is the GitHub Actions workflow, not a static
  "passing" image. Host compatibility splits first-class adapters
  (four) from generic MCP clients.
- `DrawerStore.wing_exists` answers the unknown-wing notice with
  SQL `EXISTS` instead of materialising a row (`list_by(limit=1)`).
  Jarvis's P3 on the 1.7.0 review: existence-only call sites should
  not load objects. `handoff`'s recency `_SCAN_LIMIT` is still a
  window, not "all" — left alone on purpose.
- Root `HARNESS_AUDIT.md` is a pointer to the BrainStormer lineage
  copy, not a second drifted audit. `plans/README.md` names live
  vs dated plans without moving files (moving would break
  commitment discovery). Issue template version placeholder is
  1.7.1. Integration-guide embedder example no longer implies
  MiniLM/384 is production. `setup` names the optional daemon and
  that recipes are CLI-only. Coverage omit on `mcp/server.py` now
  says what it hides.

## [1.7.0] — 2026-08-13

Eight findings from an external upgrade review against a live 3,586-drawer
store — 8.7x the corpus this project develops against. Seven were real. The
1.5.0 embedder diagnosis replicated and worsened at that scale: 78.2% of
drawers exceeded the old 128-token window and 80.5% of stored text was never
vectorised.

A MINOR rather than a patch, by this project's own tiebreak: the model cache
moves, so the model downloads once more, and `cairntir reindex` can now
refuse where it previously succeeded. Both are things a user must read the
changelog to know.

### Fixed

- **The 1.5.0 upgrade could strand a store in a state its own error message
  could not clear.** `cairntir reindex` runs from a shell that carries none
  of the MCP server's environment, and fastembed's `define_cache_dir` falls
  back to `tempfile.gettempdir()/fastembed_cache` when `FASTEMBED_CACHE_PATH`
  is unset. So reindex downloaded the model to a temp directory, rebuilt
  every vector, and stamped the store to the jina 512-dimension space — after
  which the server resolved a *different* cache, found no model, and
  `HF_HUB_OFFLINE=1` forbade fetching it. `_require_embedding_space` gates
  both `add()` and `search()`, so reads and writes failed closed, **and the
  error told the user to run `cairntir reindex` — the command that had just
  done this.**

  The cache is now anchored to `cairntir_home()`, the same root that already
  makes the CLI and the server agree about the database path: if a client can
  find the store, it can find the model beside it. `reindex` also preflights
  the model *before* touching the store and echoes the cache it resolved, so
  a stamp is never written for a vector space that cannot be loaded back.
  **One-time effect: the model downloads again into the new location.**

- **The reindex concurrency guard could not fire on a WAL-mode store,** which
  is the only mode this store runs in. It compared `(st_size, st_mtime_ns)`
  on the main database file before and after the rebuild; a committing writer
  in WAL mode appends to `<db>-wal` and leaves the main file untouched until
  checkpoint. Measured on the reviewer's store, the main file's mtime was 34
  hours older than the `-wal` beside it, with 2.1 MB accumulated. Now uses
  `PRAGMA data_version` read from a connection held open across the window —
  the documented, WAL-aware detector for "another connection committed."

- **Stale `-wal`/`-shm` files survived the atomic swap.** A write-ahead log
  carries no identity binding to its database, so frames belonging to the
  *old* file could be recovered onto the rebuilt one — replaying old page
  images over a store whose vec table may not share their vector dimension.
  Removing them is now part of the swap.

- **`reindex` had no per-drawer window check.** `cost.py` has reported the
  over-window ratio since 1.3.0, but nothing on the write path compared
  content length to the window, so a rebuild would silently re-truncate any
  drawer wider than it — reintroducing the exact partial-vector defect 1.5.0
  existed to remove, and reporting success. It now refuses, naming the worst
  offender. Both sites read one constant, `PRODUCTION_CHAR_WINDOW`.

- **`_unknown_wing_notice` built a wing→count dict by materialising
  `list_by(limit=10_000)`** — a `GROUP BY` written as a Python loop, on an
  error path, inside a stdio call — then summed that *capped* result to
  report a total. Past ten thousand drawers it under-reported with complete
  confidence, which is the same "confidently wrong about what is here"
  failure the notice exists to prevent. Now `DrawerStore.wing_counts()`.

- **The same silent cap was in seven other places, and `10_000` was standing
  in for "all" in every one of them.** It was one instance of a shape, not a
  one-off. `list_by` and `list_discoveries` now accept `limit=None`, so a
  caller that needs completeness has to say so instead of guessing a number
  large enough to feel safe:

  - `cairntir status` counted the newest ten thousand drawers and printed the
    result as the store's total — wrong on precisely the stores big enough to
    warrant running it. Now a `GROUP BY`.
  - `cairntir cost` read drawer sizes off a capped scan and reported
    percentages over that truncated sample as corpus-wide. New
    `DrawerStore.content_lengths()` measures every drawer with `LENGTH()` in
    SQL, which also stops it materialising ten thousand full drawers to read
    their sizes.
  - `transition_discovery` validated a drawer id against a capped set and
    would have rejected a legitimate discovery past the cap; the discovery
    scanner, the CodeGlass retention lookup and the Obsidian projection could
    each miss existing records and duplicate them. All unbounded now.
  - `handoff`'s `_SCAN_LIMIT = 500` is deliberately left alone: it is a
    recency window for a budgeted brief, not a stand-in for "everything".

- **The update notifier went silent during a release.** `_is_newer` compared
  plain numeric tuples, and `_parse_version_tuple` discards everything after
  the first non-digit, so an in-prep `1.7.0.dev0` rated *equal* to the
  published `1.7.0`: anyone installed from git during the prep window was
  never told the real release landed, and `pip install -U` would not move
  them. A suffixed version now ranks below its own final release.

### Changed

- **`tests/eval/test_embedder_window.py` no longer asserts against a frozen
  literal.** `test_the_window_covers_the_whole_live_corpus` compared
  `PRODUCTION_TOKEN_WINDOW` to `LONGEST_LIVE_DRAWER_TOKENS * 2` — two module
  constants, `8192 > 4754`. It opened no store, loaded no model, and could
  not fail for any reason other than someone editing a literal, despite
  carrying `eval` and `slow` markers for work it never did. Its ground truth
  was a snapshot of a corpus 8.7x smaller than the reviewer's, where the real
  longest drawer is 6,414 tokens and the true headroom is 1.28x, not 3.4x.
  It now measures the store under test with the real tokenizer and fails
  loudly when the recorded floor is stale.

### Documentation

- **`FastEmbedProvider`'s docstring described the wrong model.** It still
  advertised itself as a drop-in replacement "using the same
  `all-MiniLM-L6-v2` model under the hood" with "the same output dimension"
  — both untrue since 2026-08-10, when the model became jina and the
  dimension went 384 → 512. `cairntir setup` likewise still promised "the
  ONNX MiniLM model (~25 MB)" cached under `~/.cache/fastembed`.

- **The module docstring carried the same stale model claim as the class.**
  `embeddings.py` still introduced `FastEmbedProvider` as loading
  "`all-MiniLM-L6-v2`" and described `SentenceTransformerProvider` as using
  "the same model and dimension". They write incompatible vector spaces;
  switching between them requires a full reindex.

- **Model provenance is now written down.** `PRODUCTION_MODEL` reads
  `jinaai/jina-embeddings-v2-small-en`, but fastembed's registry resolves it
  to `ModelSource(hf="xenova/jina-embeddings-v2-small-en")` — a third-party
  ONNX re-conversion. `ModelSource` carries no revision field, so a download
  takes that repository's `HEAD` and integrity checking is size-only: two
  machines provisioned a month apart can hold different weights under the
  same name. Pinning needs a fastembed API that does not exist yet, so the
  exposure is recorded rather than implied — the same "read the tokenizer,
  never the description" rule applied to where the bytes come from.

```cairntir-commitments
# The cache both processes must agree on, or a reindex strands the store.
file   tests/unit/test_model_cache.py
symbol src/cairntir/config.py model_cache_dir
# One window constant, read by the report *and* the write path.
symbol src/cairntir/memory/embeddings.py PRODUCTION_CHAR_WINDOW
symbol src/cairntir/memory/store.py _drawers_over_window
# WAL correctness: the guard, and the sidecars the swap must not leave behind.
symbol src/cairntir/memory/store.py _discard_sidecars
symbol src/cairntir/memory/store.py wing_counts
symbol src/cairntir/update.py _release_key
# "all" is a thing a caller asks for, never a big number they hope covers it.
symbol src/cairntir/memory/store.py content_lengths
test   tests/unit/test_store.py test_list_by_limit_none_returns_everything
test   tests/unit/test_store.py test_content_lengths_counts_the_whole_corpus
test   tests/unit/test_store.py test_reindex_refuses_to_replace_a_database_written_during_the_rebuild
test   tests/unit/test_store.py test_reindex_discards_stale_write_ahead_sidecars
test   tests/unit/test_store.py test_reindex_refuses_drawers_wider_than_the_embedder_window
test   tests/unit/test_update.py test_a_published_release_is_newer_than_its_own_prep_version
test   tests/integration/test_mcp_backend.py test_unknown_wing_total_is_not_capped_by_a_scan_limit
```

## [1.6.2] — 2026-08-11

### Fixed

- **`cairntir_session_start` reported an unknown wing as an empty store.**
  IDENTITY is cross-wing by design, so asking for a wing that does not exist
  returned a stack of *other* projects' identity drawers with Essential,
  On-demand and Deep all at zero — and nothing anywhere saying the wing was
  never real. A Cursor session asked for wing `'workspace'`, a name that has
  never existed, and told the user *"store is empty (no
  identity/essential/on-demand/deep drawers)."* **The store held 424 drawers
  across 24 wings at that moment.**

  Falsely reporting emptiness is the worst failure this product has: it is
  indistinguishable from data loss to whoever reads it, and it teaches them
  not to trust the tool that is supposed to be their backbone. `handoff` has
  warned on an unknown wing since 1.3.0; `session_start` never did — the same
  asymmetry between the two entry points that hid the `on_demand` blind spot
  in 1.5.0.

  `session_start` now leads with `WING '<name>' DOES NOT EXIST`, states
  plainly that the store is not empty, gives the drawer and wing totals, and
  **names the wings that actually exist** — because "no such wing" alone still
  leaves the caller guessing, and a guessing caller invents a new wing and
  splits a project's memory in two. When the store is genuinely empty it still
  says so, and still says not to substitute model memory.

## [1.6.1] — 2026-08-11

Closes the 2026-08-10 arc. Both items were the last things reported open, and
nothing is open behind them.

### Fixed

- **The recall receipt's `truncated` flag is now `snippet_shortened`.** It only
  ever described the preview line being cut for display — the drawer is stored
  whole and the `sha256` beside it is over the complete content. But the old
  name was actively dangerous in the one place it mattered: proving the
  128-token embedder fix meant retrieving a drawer by text from its tail, and
  the receipt on that exact hit read `truncated=true`, which reads as "the
  defect is still here." A field name that invites the wrong conclusion about
  the defect sitting next to it is a bug in the receipt, not a nitpick.

### Changed

- **This repository now wires Qwen Code at project scope**, via `QWEN.md` and
  `.qwen/settings.json`, written by Cairntir's own `configure_host` rather than
  by hand. Qwen support shipped in 1.4.0 and `cairntir doctor` had reported
  `project qwen MCP=missing policy=missing` ever since — the project did not
  dogfood its own fourth host. `QWEN.md` is a thin pointer to `CLAUDE.md`, the
  same shape as `AGENTS.md`, so it cannot drift into a stale second brief.

## [1.6.0] — 2026-08-10

Closes the last of the "assurance mechanism that lies" defects found this day.
`cairntir_settle` was scoring correct predictions as misses.

**A MINOR, not the 1.5.1 that was asked for.** `cairntir_settle` gains a `held`
parameter, and by `docs/release-cadence.md`'s tiebreak a change an agent must
read the changelog to use is a MINOR. Drawer #342 — written 2026-08-06, before
the fix existed — reached the same conclusion independently: *"This is new MCP
surface, so it is a MINOR."*

### Added

- **`cairntir_settle(held=...)` — the verdict, stated rather than inferred.**
  `held` answers "did the prediction come true?"; `delta` answers "what
  surprised me?". They are different questions.

### Fixed

- **`cairntir_settle` recorded a correct prediction as a miss whenever a delta
  was written.** The verdict was derived from delta presence alone
  (`held = not delta`) and persisted to `metadata["success"]`, which is what
  `cairntir_calibration` counts. So an honest note about a *surprising route to
  a correct outcome* silently scored as a failure. **The incentive ran exactly
  backwards**: an agent wanting good calibration numbers was pushed to omit the
  surprise signal `delta` exists to capture — the thing the v0.4 design calls
  "the gradient when there are no weights." It did this to real settlements;
  see drawers #341 and #414.

  Resolution order, and none of it reads a verdict out of prose:
  `held` given is authoritative; `held` omitted with no delta still means it
  held; `held` omitted **with** a delta leaves `metadata["success"]` off
  entirely, so calibration skips the settlement rather than scoring a guess.
  Not counting beats counting wrong.

- **A seam guard now ties `settle`'s verdict to what `calibration` scores.**
  Each side was individually correct and individually tested for months while
  together they punished the one signal the store was built to collect.
  Verified to fail when the fix is removed: under the old logic three
  settlements score 0 confirmed and 3 failed.

## [1.5.0] — 2026-08-10

The session that started with *"i think cairntir is beyond broke."* It was,
in two independent ways, and neither was visible to any gate the project had.
Both are the same shape — **an assurance mechanism reporting success without
doing its job** — which is now five of the last six defects here.

**A MINOR, not a patch**, by this project's own tiebreak: a user has to read
this entry to know they need `cairntir reindex`. A patch number would tell
them there is nothing to learn, which is false.

**Upgrading from 1.4.x: run `cairntir reindex` once.** It backs up first. The
store detects the dimension change and refuses to serve a mismatched index
rather than returning wrong results.

### Changed

- **The production embedder is now `jinaai/jina-embeddings-v2-small-en`
  (8,192-token window, 512 dimensions), replacing `all-MiniLM-L6-v2`.**
  MiniLM's configured truncation is **128 tokens — about 500 characters** —
  read directly off the live model as
  `truncation: {'max_length': 128, ...}` and confirmed twice by binary search.
  On a 407-drawer corpus that left **73.4% of all stored text invisible to
  semantic recall**: only 66 of 407 drawers were fully searchable, 244 were
  more than half invisible, and `cosine(full_content, first_1500_chars)` was
  exactly `1.000000` for the five longest drawers. Every drawer was being
  compared on its opening boilerplate, which is why recall clustered every hit
  between distance 1.03 and 1.15.

  The longest drawer in the live store is 2,377 tokens, so the new window
  covers the entire corpus in a single vector — **no chunking, no multi-vector
  schema, one row per drawer preserved.** Existing stores need one
  `cairntir reindex`, which backs up first and is refused automatically if the
  dimension does not match.

  **Existing installs must run `cairntir reindex`.** The store detects the
  dimension change and refuses to serve a mismatched index rather than
  returning wrong results.

### Fixed

- **`cairntir cost` reported an embedder window 4x too generous.**
  `EMBEDDER_TOKEN_LIMIT` was a hardcoded `512` while the real embedder
  truncated at 128, so the one module built to measure this exact risk
  under-reported it fourfold. It now derives from
  `PRODUCTION_TOKEN_WINDOW`, which a seam test checks against the live
  tokenizer.

- **The LongMemEval R@5 gate never tested the shipping embedder.** It pinned
  `SentenceTransformerProvider("all-MiniLM-L6-v2")` — a different model *and* a
  different runtime from production's ONNX `FastEmbedProvider`. That is why the
  truncation defect passed the quality gate at full strength. A second gate now
  runs the same bar against `production_embedding_provider()`.

- **`handoff` could not see the layer `cairntir_remember` writes by default.**
  The tool declares `"default": "on_demand"` in its MCP schema; the composer
  gathered only `IDENTITY` and `ESSENTIAL`. A user who followed the documented
  policy and took the defaults stored memory perfectly and got an empty brief
  back next session — the cross-chat amnesia Cairntir exists to kill,
  reproduced by its own defaults. Found by rehearsing a stranger's first two
  days on a clean `pip install cairntir` from PyPI: three decisions written on
  day 1, and on day 2 `handoff` answered *"none are identity, essential, an
  open question, or anchored to the files given. Nothing here is broken."*

  `on_demand` drawers now fill a **`Recent activity`** section with a zero
  reserve — skipped entirely in the first budgeting pass, fillable only from
  budget no higher-priority section wanted, so it can never outbid identity or
  essential material. `DEEP` stays excluded: *"skipped unless explicitly
  requested"* is a real decision, whereas `on_demand`'s exclusion was an
  accident of running no query. The default was deliberately **not** flipped to
  `essential` — that starves the budget every drawer competes for.

- **The empty-brief message claimed health while returning nothing.** It said
  "Nothing here is broken" at the exact moment the caller got nothing back.
  It now reports how many drawers sit in the deep layer and states plainly
  that the brief is not evidence the wing is empty.

- **`scripts/check_landed_commitments.py` did not count module constants as
  symbols**, so a truthful commitment naming one reported as UNLANDED. Its
  sibling `check_seams.py` had always counted them; the two read the same
  plans and disagreed about what a symbol is. They now agree.

### Added

- **Seam guard: the default write layer is a layer `handoff` loads.** The
  previous behaviour was not merely untested — it was *asserted* as correct by
  a unit test reasoning from the layer taxonomy, which is why it survived from
  v1.3.0. The new test reads the declared default off the live tool schema
  rather than hardcoding it, so changing either side alone fails the build. It
  was verified to fail when the fix is removed.

## [1.4.1] — 2026-08-06

A hardening patch. Both fixes are the same defect in different clothes: a guard
that reports success without doing its job. One of them was guarding the oldest
governance principle in the project, and had been unreachable for four minor
releases.

### Fixed

- **The silent-exception gate was close to a no-op.**
  `scripts/check_no_silent_except.py` is the check written against
  BrainStormer's 224 `except: pass` blocks. Three of its four regexes required
  `pass` on the *same line* as `except` — a one-liner `ruff format` never emits
  — so they could not fire on this repository's own formatted source, and the
  fourth only caught a bare `except:`, which ruff's E722 already rejects. The
  gate was blind to the form the pattern actually takes: a **typed** handler
  swallowing on the next line. Three live violations sat in `src/` while it
  exited 0. It is now an AST check with no type list to maintain — a handler is
  silent when its body does nothing at all, whatever it catches — and a file it
  cannot read or parse is a violation rather than a skip. It was the only gate
  script in the repository with no test, which is precisely why nothing noticed;
  `tests/unit/test_silent_except.py` closes that.
- **Three swallowed exceptions, now surfaced.** Two failed-checkpoint writes and
  a failed unlink in `cairntir/register.py` reported nothing at all; an
  unwritable checkpoint silently disables the registration fast path forever,
  and a failed unlink silently skips the re-registration the caller just asked
  for. Both now say so on stderr. In `cairntir/memory/store.py` the write
  guard's JSON probe became `_parses_as_json`, turning the exception into the
  value it always meant.
- **`cairntir_recall(full_content=N)` could blow the context budget it claimed
  to respect.** The size test ran per drawer against a shared 12,000-character
  constant with no accumulator, so ten 11,900-character drawers each "fit" and
  `full_content=10` delivered roughly 119,000 characters — about 30,000 tokens.
  The budget is now cumulative across everything delivered whole, the same
  contract `cairntir_handoff` has kept since 1.3.0: once it is spent the
  remaining hits fall back to named snippets, whole drawers or none. Budget
  exhaustion is reported distinctly from a genuinely oversize drawer, and the
  call states what it spent. The tool schema is unchanged.

## [1.4.0] — 2026-08-05

The honesty release. Cairntir's oldest defect is infrastructure built correctly
and never wired: commitments that quietly vanish, checks that run where their
subject does not exist, loops that open but nobody closes. This release wires
the enforcement layer. Settled predictions now actually close in the handoff
and count in calibration. The store-integrity gate runs where the data lives —
pre-commit, beside the bank — instead of on a CI runner that has no store. The
release gate verifies PyPI presence, not just the tag. The write path asks for
a prediction when you assert a claim. And a fourth host — Qwen Code — reads and
writes the same store with full provenance.

### Added

- `cairntir doctor --gate` — the store-integrity and vault-drift gates, run
  where the data actually lives. The five health rules moved into
  `src/cairntir/health.py`, one shared implementation behind both
  `scripts/check_store_health.py` and the gate, so the two cannot drift apart.
  Without a store the gate skips loudly and passes; with one, it exits 1 on
  damage or drift. Wired into `.pre-commit-config.yaml`, because a check that
  runs where its subject does not exist is worse than no check.
- `scripts/check_release_tags.py` now verifies PyPI presence, not just the tag.
  A tag is a claim, not a fact — `v1.1.1` was tagged, released on GitHub, and
  never reached PyPI, unnoticed. Fails closed when pypi.org cannot be reached;
  `0.1.0` and `1.1.1` are recorded as historical fact, not swept away.
- `cairntir_recall(..., full_content=N)` — deliver the top N hits with their
  COMPLETE content instead of snippets, so one good drawer answers the
  question without a `cairntir_get` round trip. Hits too large for whole
  delivery are named, never truncated. Default 0 keeps the old stub-only
  output byte-identical.
- `cairntir_remember` now nudges when a drawer carries a `claim` but no
  `predicted_outcome`. A claim nothing can prove wrong is not a prediction,
  and `delta` was still 0/292 eight days after `cairntir_settle` landed
  because nothing ever asked. Advisory only — the write succeeds either way.
  This is the anchor lesson applied to the epistemic core: publish a contract
  is not the same as asking for compliance.
- **Qwen Code is the fourth supported host.** `cairntir init --host qwen` and
  the doctor/host adapters wire `~/.qwen/settings.json` + `QWEN.md`, and the
  four-host continuity fixture now covers Claude, Codex, Cursor, and Qwen
  writing to one store with per-write provenance.

### Fixed

- Settled predictions close in `cairntir_handoff`, and `cairntir_calibration`
  counts settlements made through the MCP surface. Previously a prediction
  settled via `cairntir_settle` stayed listed as open forever, and calibration
  never saw it. Every declared seam now keeps a paired both-sides test,
  registered in `scripts/check_seams.py`.

## [1.3.0] — 2026-08-02

The context-budget release. Cairntir's oldest inherited idea is **controlled
context** — BabyTIEROS separated material into always-load / load-when-relevant
/ never-load before any vector store existed. The 2026-07-27 evolution audit
found that the policy survived into Cairntir and the *budget* did not, and wrote
the fix into the v1.2 core list. v1.2 shipped without it. This release lands it,
and adds the CI gate that makes that class of miss fail the build instead of
going unnoticed for five days.

### Added

- `cairntir_handoff(wing)` and `cairntir handoff <wing>` — one call returning one
  composed brief, under a hard character budget, to replace keeping a
  `HANDOFF.md` file by hand. Composes the operating protocol, the most recent
  session deltas, open questions, and — when you pass `files` — the drawers
  structurally anchored to the code you are about to touch.

  **Drawers come back whole or not at all.** Truncation is the anti-pattern this
  is built against: it pays the full token cost *and* destroys the information.
  Anything that does not fit the budget is listed with its id, room and size, so
  the caller spends one targeted `cairntir_get` instead of a blind `recall`.

  Measured against `session_start` on a copy of the live store: **7,737 → 4,261
  estimated tokens for the `cairntir` wing (-44%)** and **8,201 → 3,880 for
  `detroit-clone` (-52%)**. The saving is the less interesting half —
  `session_start` spent its tokens on 51 truncated stubs that could not answer
  anything, and `handoff` spends fewer on 9 whole drawers that can.

  No ranking, no embedder, pure SQL, and verified byte-identical across repeat
  calls, so it does not disturb a host's prompt cache. `budget_chars` bounds
  drawer content; the evidence envelope adds provenance on top, which is stated
  in the response rather than quietly excluded from the number.

  Identity is scoped to the wing, unlike `session_start` — a `cairntir` session
  was paying for identity drawers belonging to `larder` and `quietpdf`.
- `cairntir cost <wing>` and `cairntir.cost` — report what Cairntir's own read
  path costs the context window it exists to protect. Measures the tool catalog
  (paid in every session in every host, called or not), `session_start`,
  `handoff`, and the drawer-size distribution against the embedder's ~2,048
  character input window.

  This closes **P5**, the only one of the twelve primitives BrainStormer's
  2026-04-03 harness audit scored MISSING, at risk HIGH, deferred with the words
  *"until cost becomes a real concern."* That condition is now met three ways,
  and every figure in the 2026-08-02 research had to be produced by hand because
  nothing reported it.

  Deliberately narrow: it measures Cairntir's payload and must not grow into a
  general token dashboard — Tokalator already does live budget monitoring and
  Headroom already does reversible compression, both better. It is a CLI command
  rather than an MCP tool because a twentieth tool definition would enlarge the
  very catalog the report holds accountable.

  The comparison is honest in both directions. `handoff` is **not** universally
  cheaper than `session_start`: on a wing holding a few large drawers, stubs
  genuinely cost less than whole content, and the report says so. The saving on
  the live store comes from `session_start` also loading every *other* wing's
  identity drawers.
- Determinism tests on `session_start` and `handoff`
  (`tests/unit/test_determinism.py`). Anthropic's prompt caching reads cached
  tokens at 10% of normal input cost, but any change to a block invalidates that
  block and everything after it. Both surfaces were measured as deterministic on
  2026-08-02 and nothing guaranteed they would stay that way; the realistic
  regressions — a wall-clock timestamp, an unsorted `set`, insertion-ordered
  keys — would fail no other test in the suite. Also pins the boundary that
  determinism holds *within* a store and deliberately **not** across two, since
  each drawer carries a unique per-session write receipt.
- `scripts/check_landed_commitments.py` and `docs/landed-commitments.md` — fail
  the build when a plan document promises something the code does not have. A
  plan may carry a fenced `cairntir-commitments` block asserting that a file,
  symbol, function parameter, or test exists; CI verifies every one.

  This closes the oldest defect in the lineage and the only one present in all
  four generations — *infrastructure without the enforcement layer*, named in
  BrainStormer's 2026-04-03 harness audit. It recurred at the level of the
  recovery plan itself: the 2026-07-27 evolution audit diagnosed the lost
  context budget, wrote "restore explicit context budgets" into the v1.2 core
  list, and v1.2 then shipped, was verified across three hosts, published and
  attested **without it**. The pattern is not "we build badly," it is "we do not
  verify that a commitment landed."

  The `param` assertion is the one that earns its place: `session_start` existed
  the whole time, so a symbol-level check would have passed. Only a
  parameter-level assertion catches an argument that was promised and never
  added. A malformed block fails the run rather than being skipped, because a
  silently skipped assertion is how `## [1.2.0.0]` would have defeated
  `check_release_tags.py`.
- `scripts/check_release_tags.py` — fails when a released `## [x.y.z]` changelog
  header has no matching `vx.y.z` git tag. The version in `pyproject.toml` is
  exempt while a release is in flight, and the two historically untagged
  versions (1.0.1, 1.1.3) are recorded explicitly rather than hidden. Wired into
  the CI lint job and the release verification gate, both of which now check out
  with `fetch-depth: 0` so tags are visible.
- `docs/release-cadence.md` — the release cadence and versioning policy. Defines
  commit vs. merge vs. tag, when a release is warranted, the rule that anything
  breaking install or first run ships immediately as a patch, and how the
  version number is chosen.
- `docs/lineage/mattpocock-skills.md` — attribution for
  [mattpocock/skills](https://github.com/mattpocock/skills) by
  [@mattpocock](https://github.com/mattpocock), whose `CONTEXT.md` demonstrated
  that a shared project vocabulary is worth treating as a first-class artifact.
  Written before any glossary-drawer code, per the project's attribution
  contract. Says plainly that his skills are the better tool for most people and
  that Cairntir is not building an equivalent.
- `docs/lineage/code-review-graph.md` — attribution for
  [code-review-graph](https://github.com/tirth8205/code-review-graph) by Tirth
  Kanani ([@tirth8205](https://github.com/tirth8205)), for the idea that recall
  should be triggerable by what you are touching rather than only by what you
  thought to ask. Written before any `recall_for_change` code, per the
  attribution contract. Records what Cairntir is *not* taking — tree-sitter and
  its grammars, and 27 of its 30 MCP tools — and says plainly that his tool is
  the better fit for any question about the code itself.

- `cairntir_recall_for_change(files)` and `cairntir.memory.anchors` — structural
  recall. Given the files a change touches, surface the drawers anchored to
  them: the question the caller did not think to ask. Anchors are optional
  `metadata.anchors` entries of `{path, symbol, symbol_source_hash}`, so there
  is **no schema change, no migration, no parser, and no new dependency** — the
  store already carries arbitrary JSON. Paths match across separator styles and
  absolute-vs-relative, at segment boundaries so `cli.py` cannot match
  `fastcli.py`. Drawers with no anchors never match, which is the opt-in
  mechanism: anchorability splits per-room (gate A1), and rooms that shouldn't
  anchor simply don't. Malformed anchors are reported on the result and in the
  MCP reply rather than aborting the recall or being silently skipped.
  **Deliberately does not flag staleness** — `symbol_source_hash` is stored and
  never compared, held until rename survival is tested (gate A2).
- `DrawerStore.add_anchors` plus `cairntir anchor` and `cairntir
  recall-for-change` CLI commands — the retroactive path. New drawers can carry
  anchors at write time via `cairntir_remember`, but a corpus written before
  anchors existed could not participate at all. `add_anchors` is append-only
  within metadata: existing anchors are kept, duplicates collapse, unrelated
  metadata is preserved, and the drawer's verbatim content, layer, and belief
  mass are never touched — the same controlled mutation `update_layer` already
  performs. A batch containing a malformed entry is rejected before any write,
  so a partial anchor set is impossible. Backfill is a one-time job and agents
  can already anchor at write time, so this is CLI-only and the MCP surface
  stays at 18.

### Changed

- MCP tool surface is now **18** (was 17), and `TOOL_SURFACE_VERSION` moves to
  `"18"` so new writes stamp the surface that produced them. The single added
  tool is `cairntir_recall_for_change`; 27 of code-review-graph's 30 tools were
  deliberately not taken.
- Stated the versioning policy honestly. `2.0.0` is reserved for a
  revolutionary change in what Cairntir is; a deprecated public surface may be
  removed in a MINOR release after the existing two-minor warning window. This
  is a documented deviation from strict SemVer, not a new rule — the
  deprecation policy already permitted minor-release removal.
- `docs/publish-checklist.md` now reads as a reusable per-release checklist
  rather than a frozen v1.2.0 worksheet. The v1.2.0 evidence record stays in
  `docs/release/v1.2.0-rc.md`.

### Fixed

- **The anchor repair tool could not repair the damage it existed for.**
  `DrawerStore.add_anchors` is append-only and validates the *merged* list, so
  on a drawer whose existing `metadata.anchors` are the legacy string form it
  raised `anchor entries must be objects, got str` and refused before it could
  append. The retroactive-anchoring procedure shipped in 1.2.0 worked only
  because the drawers it targeted had no anchors at all. New
  `DrawerStore.repair_anchors(drawer_id)` and `cairntir anchor <id> --repair`
  coerce the legacy form in place. Coercion is limited to the one case that is
  not a guess — a bare string could only ever have meant a path; an object with
  no recoverable `path` is refused loudly rather than invented. Idempotent,
  metadata-only, duplicate-collapsing, and nothing is written unless every
  entry validates first.
- **`metadata.anchors` was accepted at write and rejected at read, silently
  disabling structural recall.** `cairntir_remember` declared `metadata` as a
  bare `{"type": "object"}` with no description, so a writing agent never saw
  the anchor contract and guessed a list of path strings —
  `["a.rs", "b.toml"]` — where `parse_anchors` requires a list of objects. The
  store accepted it, and the failure surfaced weeks later as a "malformed
  metadata.anchors" warning in `cairntir_recall_for_change`, in a different
  session, about drawers nobody could reconstruct. Found in live use: every
  anchored drawer in the `detroit-clone` wing (#199, #204-#207) was unreadable
  by the feature the anchors were written for. Two changes close it:
  `cairntir_remember` now publishes the full anchor schema in its tool
  description, and it validates anchors on write, raising `MCPError` with the
  correct shape instead of storing a bad row. The reader stays strict — rows
  written before this guard remain visibly malformed rather than being
  silently reinterpreted — so existing bad drawers still need a
  `cairntir anchor` backfill. See `plans/field-report-2026-08-02.md`.
- Marked 1.0.1 and 1.1.3 in this changelog as never released. Both were
  committed and changelogged but never tagged, so neither reached PyPI.
- Resolved a self-contradiction in `docs/deprecation-policy.md`. Its versioning
  section guaranteed `1.x.y` protocol compatibility with `1.0.0` while its own
  warning-window rule permitted removing a deprecated surface in a minor
  release. The guarantee is now stated as what it actually is: a guarantee of
  process, not of permanent surface stability.
- Corrected an unfair characterization of `mattpocock/skills` in
  `plans/next-map.md`. It claimed his `CONTEXT.md` approach "has no provenance";
  the file's `## Flagged ambiguities` section records resolved terminology
  conflicts and their resolutions, which is exactly that. Corrected in the plan
  and in the lineage doc rather than quietly edited away.
- Corrected an unfairly harsh characterization of `code-review-graph` in
  `plans/next-map.md` and drawer #173, which called its token-reduction
  benchmark "inflated by a strawman." He names his baseline plainly, publicly
  corrects people who over-quote his best number in his favor, states the
  impact-analysis circularity in his own README, and publishes results that make
  his tool look worse. The surviving point is a disagreement about which baseline
  is representative, not an accusation of bad faith.

## [1.2.0] — 2026-07-28

### Added — Foundation hardening, multi-host continuity, and visible learning

- Added a single production embedding-provider factory and persisted
  embedding-space identity. Semantic reads and writes now fail closed when the
  database was built by an unknown, mismatched, or structurally incomplete
  embedding index.
- Added read-only `cairntir doctor` diagnostics plus backup-first, sidecar-based
  `cairntir reindex`. Dimension/schema changes are rebuilt outside the live
  database and atomically swapped only after verification.
- Moved wing, room, and layer filters inside sqlite-vec's KNN query so crowded
  global neighbors cannot hide the requested scoped results.
- Added exact `cairntir get` / `cairntir_get` retrieval with stable
  `cairntir://drawer/<id>` references, content length, SHA-256 receipts, and
  explicit truncation markers on summaries.
- Added safe host adapters for Claude Code, Codex, and Cursor:
  `cairntir init --host <host|all> [--user]`. One canonical startup policy is
  rendered into each host's supported instruction surface without overwriting
  unrelated content.
- Added the append-only Discovery Ledger and Human Learning Log. Evidence-backed
  discoveries have explicit novelty scope and lifecycle state; active learning
  is surfaced at session start and through learning MCP/CLI operations.
- Added schema-v6 immutable write provenance: host, model, session, capture
  path, trust, visibility, sensitivity, validity, client version, and tool
  surface version. Legacy memories migrate as explicitly untrusted evidence,
  with a timestamped backup created before schema changes.
- Added crash-safe nested transactions, savepoints, durable workflow receipts,
  and idempotency-key conflict detection. Reason, recipes, replay, portable
  import, daemon capture, and CodeGlass now commit all-or-nothing and replay
  exact retries without duplicate drawers.
- Added prompt-safe evidence rendering. Retrieved memories carry explicit
  `instruction_authority=none`, provenance, trust, and suspicious-pattern
  signals so stored prompt injection cannot masquerade as agent policy.
- Added automatic multi-episode discovery proposals and a read-only
  calibration report. Automation may create or refresh candidates after
  repeated evidence, but cannot corroborate or promote itself.
- Recovered CodeGlass as an evidence-cited teaching recipe with
  novice/intermediate/expert modes, immediate and delayed teach-back,
  retention tracking, and Human Learning Log integration.
- Added one-way `cairntir obsidian-project` projection for Anthropicer/Obsidian.
  Generated learning and CodeGlass notes preserve human annotations, exclude
  secret memories, and leave SQLite authoritative.
- Expanded the MCP surface to 17 tools and added automated Codex ↔ Cursor ↔
  Claude continuity coverage over one canonical store with immutable
  host/model/session provenance.
- Hardened release automation with immutable GitHub Action SHAs,
  least-privilege job permissions, a full pre-publish verification job, OIDC
  Trusted Publishing, build-provenance attestations, and tag-only publish /
  GitHub Release guards.
- Bundled recipe contracts in wheels and made discovery host-neutral. The
  legacy sentence-transformers provider moved to an optional extra; FastEmbed
  remains the production default.

### Fixed — Release-candidate closure

- Fixed Windows CLI help/status output crashing with `UnicodeEncodeError` when
  redirected through a cp1252 process. The console-script boundary now emits
  UTF-8 safely before Typer renders help.
- Fixed the Claude plugin MCP launcher omitting `--host claude`, which made
  immutable write provenance fall back to a generic MCP host.
- Prevented a manually dispatched release workflow from publishing to PyPI or
  creating a GitHub Release; only a `v*.*.*` tag can cross that gate.

### Added — Cairntir Blender add-on (horizon thesis demonstrator)

The first non-code Cairntir client. A Blender add-on that captures
decisions and 3D-print iteration outcomes into Cairntir's memory
layer, demonstrating that **Cairntir doesn't care what is being
remembered** — the same machinery that records code decisions in
the cairntir wing records 3D-print iteration outcomes in a
blender wing. Same shape, same retrieval, same prediction-bound
semantics.

This is the first concrete bridge toward the path described in
the roadmap's Horizon section: AI + grand-scale 3D printing +
post-scarcity tooling. Today it remembers code decisions.
Tomorrow it remembers which printed structure worked, what the
parameters were, what the next iteration should try.

#### Architecture: spool drop, not import

The add-on never imports the `cairntir` Python package. Instead it
writes drawer-shaped JSON envelopes to `$CAIRNTIR_HOME/spool/` —
the same format `cairntir.daemon.spool.parse_capture` already
understands. Cairntir's daemon picks them up on its next poll
cycle. **Stdlib-only** by design (`json`, `pathlib`, `os`, `time`,
`uuid`), so installation in Blender's bundled Python is zero-touch.

Atomic writes (`.tmp` then `os.replace`) mean the daemon never
sees a half-written file.

#### What's in the add-on

`addons/cairntir_blender/`:
- `spool_writer.py` — pure stdlib writer with `write_capture`
  (free-form drawer) and `write_print_outcome` (structured 3D-print
  iteration with parameters + verdict). Auto-lowercases wing/room
  to satisfy Cairntir's identifier convention so users can naturally
  type "PLA" in the dialog.
- `__init__.py` — Blender add-on entry. `bl_info` block, four
  classes (`CAIRNTIR_PG_settings`, `CAIRNTIR_OT_capture_decision`,
  `CAIRNTIR_OT_capture_print_outcome`, `CAIRNTIR_PT_panel`), and
  the standard `register` / `unregister` pair. Lazy-imports `bpy`
  so the spool_writer module remains importable from pytest
  without Blender installed.
- `README.md` — install (zip the directory + Blender preferences),
  configure (per-scene wing / material / cairntir_home), and use
  (panel in the 3D Viewport's N-panel).

#### What gets captured

The Blender panel exposes two operators in the 3D Viewport's
**Cairntir** N-panel tab:

- **Capture Decision** — free-form drawer with content the user
  types. Use for design choices, mid-iteration notes, anything
  that isn't strictly a print outcome.
- **Capture Print Outcome** — structured drawer with nozzle temp,
  bed temp, infill %, layer height, outcome text, success/fail
  verdict, and free-form notes. The drawer's content is
  human-readable markdown; metadata carries the structured fields
  (`source: "blender"`, `kind: "print_outcome"`, `parameters`,
  `success`) so future Decision Replay or consolidation can
  recover the prediction-bound semantics.

#### Tests — 14 new

`tests/unit/test_blender_addon.py` loads `spool_writer.py` directly
via `importlib.util` (sidestepping the bpy import in `__init__.py`).
Covers happy paths, validation rejection (empty wing/room,
whitespace content, unknown layer), the print-outcome helper, the
lowercase normalization, atomic-write behavior, and — the
load-bearing test — **round-trip with the actual Cairntir daemon**:
a file written by the Blender writer parses cleanly through
`cairntir.daemon.spool.parse_capture` and produces a Drawer with
the right wing / room / layer / metadata. If that test ever
breaks, the horizon thesis becomes aspiration instead of fact.

#### Per-file ruff carve-out

Blender's `bpy` API uses `UPPER_PG_thing` class naming and class
attribute idioms (e.g. `bl_options = {"REGISTER"}`) that conflict
with PEP-8 / pep8-naming. `pyproject.toml` adds a per-file ignore
for `addons/cairntir_blender/**` covering N801, N815, RUF012, D102
— the add-on is opt-in code that runs inside Blender, not in
Cairntir's main distribution.

### Status

297 tests passing (14 new), 84% coverage, ruff + mypy --strict
clean, silent-except scanner clean. Zero new runtime dependencies
in Cairntir's main distribution; the add-on is self-contained.

### Added — Agent Memory (per-skill self-memory wings)

Cairntir's three skills (crucible, quality, reason) now keep their
own *self-memory* in reserved wings under the `agent:` prefix —
`agent:crucible`, `agent:quality`, `agent:reason`. Every invocation
through the recipe runner leaves a self-memory drawer in the
appropriate agent wing recording the case, with a pointer back to
the marker drawer in the project wing. The next invocation in the
same originating wing surfaces prior cases as context.

**The compounding effect.** After Crucible has been invoked
several times against the cairntir wing, those prior stress-tests
appear as a "Prior cases" section inside the next Crucible marker
drawer's content. Quality remembers patterns that earned ship-it
verdicts. Reason remembers rabbit holes it has already gone down.
The skills get *better at their own work* without any new
primitives — pure convention-as-code on top of the v1.0 memory
surface.

#### Schema relaxation: `:` allowed in wing identifiers

`_IDENT_RE` in `cairntir.memory.taxonomy` now accepts `:` inside
identifiers (the first and last characters must still be
alphanumeric). This unlocks `agent:crucible` etc. without a database
migration — `wing` is a normal `TEXT` column; only the validator
needed loosening. Existing wing names continue to validate
unchanged.

#### `cairntir.skills.memory` — new module

Five public helpers:
- `agent_wing_for(skill_name)` — returns `"agent:<name>"` for the
  three reserved skills; raises for any other name.
- `is_agent_skill(skill_name)` — predicate used by the recipe runner
  to decide whether to write a self-memory drawer.
- `record_skill_invocation(memory, *, skill_name, originating_wing,
  originating_room, skill_marker_id, summary, metadata)` — writes
  the self-memory drawer with the right metadata shape so future
  recall is structured.
- `recall_skill_history(memory, *, skill_name, originating_wing,
  limit=3)` — pulls recent prior cases. Returns `[]` for non-agent
  skills so callers can invoke unconditionally.
- `format_history_for_prompt(history)` — renders prior cases as
  markdown for inclusion in a skill's marker drawer.

#### `MemoryGateway.list_by` — new protocol method

The `MemoryGateway` Protocol gains a third method:
`list_by(*, wing, room, limit)` — non-semantic listing,
most-recent-first. Required for Agent Memory's recall path (skill
history is recency-ordered, not relevance-ordered). Implemented on
`StoreBackedMemory` by delegating to `Store.list_by`. The fake
`MemoryGateway` in `test_reason_loop.py` was updated to match.

This is a non-breaking addition for `StoreBackedMemory` users; any
custom `MemoryGateway` implementer must add the new method to
satisfy the protocol.

#### `RecipeRunner` integration

`RecipeRunner._run_skill_marker` and `RecipeRunner._run_reason` now:
1. Recall prior cases from the agent wing for the originating wing
   before writing the marker drawer.
2. Embed those cases under a "Prior cases" section in the marker
   content.
3. After the marker (or prediction) lands, write a parallel
   self-memory drawer to the agent wing pointing back at the
   marker.

A guard skips the agent-memory write when the recipe's `output_wing`
is itself an agent wing — the agent prefix is not a fractal.

### Tests — 14 new

- `test_agent_memory.py` (13 tests): pure helper smoke tests,
  taxonomy regex relaxation, record/recall round-trip, originating
  wing scoping, non-agent skill rejection, empty originating wing
  rejection, recipe runner writes agent drawer for crucible/reason,
  recipe runner includes prior cases in subsequent marker, no
  recursion when recipe targets agent wing.
- `test_reason_loop.py` (1 update): `FakeMemoryGateway` now
  implements `list_by`.

### Status

283 tests passing, 84% coverage, ruff + mypy --strict clean,
silent-except scanner clean. No new runtime dependencies.

### Added — Local-AI proposer (Ollama)

The Reason loop's `HypothesisProposer` port has shipped only a manual
adapter (`ManualProposer`, where you type the claim + predicted
yourself) since v0.6. This release adds the first inference-backed
implementation: `OllamaProposer`, which calls a locally-running
[Ollama](https://ollama.com) daemon to draft both fields. Cairntir
still does not call cloud LLMs — Ollama is local-first by design,
the daemon runs on the user's machine, and the adapter is stdlib-only
(`urllib.request` + `json`).

#### `cairntir reason --proposer ollama` and `cairntir replay --proposer ollama`

Both commands accept a new `--proposer {manual,ollama}` flag.
Defaults to `manual` (existing behavior). With `--proposer ollama`:

- A single round-trip to `http://localhost:11434/api/generate` (configurable
  via `--ollama-endpoint`) drafts the `claim` + `predicted_outcome`.
- The draft is **surfaced in the terminal** before the loop commits —
  every load-bearing piece of generated text gets confirmed by the
  user. Cairntir is a memory layer, not a black box.
- Empty input at the prompt accepts the draft; typed input overrides
  it. The observed outcome and verdict still always come from the
  user (you saw what happened, not the model).

```
cairntir reason "did the proposer wiring land?" --wing cairntir \
  --proposer ollama --ollama-model gemma2:2b
```

For `cairntir replay`, `--proposer ollama` reframes the original
chain leaf's claim + predicted given the new evidence — the
"original framing was off, the replay is also a re-statement" case
the recipe README anticipated. Without the flag, replay still
auto-fills from the chain leaf verbatim (the right default for
closing a prediction window).

#### `cairntir.production.OllamaProposer`

New public class on the `cairntir.production` surface. Implements
`HypothesisProposer` (runtime-checkable). Constructor takes `model`,
`endpoint` (default `http://localhost:11434`), and `timeout` (default
120s). Typed exceptions: `OllamaError` (base), `OllamaUnavailableError`
(daemon unreachable), `OllamaModelMissingError` (model not pulled),
`OllamaInvalidResponseError` (malformed body). Every error carries a
recovery hint in its message — never a silent fallback.

#### What this unlocks

The Reason loop now has a path to autonomous invocation that doesn't
involve cloud APIs or billed tokens. Recipes like Signal Reader and
Decision Replay can be invoked with the model drafting the
prediction-bound fields, surfaced for human review. The "memory that
thinks back" loop closes — locally.

The Whisper.cpp + Gemma pattern Patrick already proved in Transcript
Capture is the same shape: local model server, Python client over
HTTP, no telemetry. Reusing it here means no new architectural
surprises.

### Tests — 18 new

- `test_ollama_proposer.py` (14 tests): protocol conformance, happy
  path, custom endpoint, all error paths (unreachable, timeout, model
  missing, internal error, non-JSON envelope, missing response field,
  non-JSON inner payload, non-object payload, missing/empty claim,
  missing predicted_outcome).
- `test_cli.py` (4 tests): `--proposer ollama` happy path with
  mocked HTTP, daemon-unavailable error path, unknown-proposer
  rejection, replay reframe.

### Status

268 tests passing, 84% coverage, ruff + mypy --strict clean,
silent-except scanner clean. Zero new runtime dependencies — Ollama
is an external daemon, not a Python package Cairntir installs.

### Added — Decision Replay recipe (synergy stack completion)

The v1.1 synergy stack — production reason loop, cross-wing recall,
recipe runtime — landed 2026-04-18 but only one recipe (Signal
Reader) ever exercised them together. The cold-start fire (1.1.0 →
1.1.3) ate four days of attention, then the stack sat. Decision
Replay is the second recipe and the first one that uses *all three*
synergy components at once: it loads a past decision drawer through
`cairntir.memory.temporal.walk_supersedes`, runs the production
reason loop with the chain leaf's claim + predicted_outcome
auto-filled, and writes the new prediction-bound drawer with
`supersedes_id` pointing at the leaf — so the chain extends instead
of restarting.

#### `cairntir replay <id>` — new CLI command

The seamless invocation. Walks the supersedes chain from
`<id>`, pre-fills the proposer's claim + predicted_outcome from the
leaf, prompts for the observed outcome and a verdict, runs the
Decision Replay recipe with `supersedes_id` set to the leaf id,
prints the new prediction drawer id and the chain extension. Zero
network calls — Cairntir still never runs LLMs itself.

```
cairntir replay 95 --evidence "fastembed default has held for four days,
no cold-start regressions" --observed "cold start steady at ~1.4s" --success
```

The generic `cairntir recipe-run decision-replay` path also works
when the caller wants to override the auto-filled claim.

#### `docs/recipes/decision-replay/`

Bundled recipe — `recipe.toml` with three inputs
(`decision_drawer_id`, `current_evidence`, `horizon_months`) and the
two-skill chain `["reason", "crucible"]`. Discoverable via
`cairntir recipe-list` alongside Signal Reader. README documents the
full protocol, anti-patterns, and how Decision Replay closes the
loop on Signal Reader's outputs.

#### `ReasonLoop.step(supersedes_id=…)` — non-breaking extension

The reason loop now accepts an optional `supersedes_id` keyword. When
supplied, the prediction drawer that step writes carries that
pointer, so a new prediction can extend an existing chain instead of
starting a fresh one. The default (`None`) preserves v0.6 semantics:
the prediction is rootless, the observation supersedes the
prediction. Existing callers are unaffected.

`RecipeRunner.run(contract, inputs, supersedes_id=…)` is the matching
extension at the recipe layer — the runner threads the pointer into
the reason step when the recipe chains the reason skill.

### Tests

- `test_step_with_supersedes_id_chains_new_prediction_onto_existing_chain`
  / `test_step_without_supersedes_id_starts_fresh_chain` confirm the
  loop's two modes.
- `test_runner_threads_supersedes_id_into_reason_step` /
  `test_runner_default_no_supersedes_id_starts_fresh_chain` confirm
  the runner threads the pointer correctly.
- `test_discover_recipes_finds_decision_replay` asserts the bundled
  recipe loads cleanly with the right inputs and skill chain.
- `test_replay_extends_supersedes_chain` is the load-bearing
  end-to-end: seeds a prediction-bound drawer, invokes
  `cairntir replay`, reopens the store, walks the chain, asserts the
  new prediction's `supersedes_id` points at the original.
- `test_replay_refuses_drawer_without_claim` /
  `test_replay_errors_on_missing_drawer` /
  `test_replay_no_store` cover the error paths.

### Status

250 tests passing, 83% coverage, ruff + mypy --strict clean,
silent-except scanner clean.

## [1.1.3] — 2026-05-03

> **Never released.** This version was committed and changelogged but never
> tagged, so the release workflow — which fires only on a pushed `v*.*.*` tag —
> never ran. It never reached PyPI. The cold-start fix described below finally
> shipped inside **1.2.0** on 2026-08-01, three months later; until then every
> `pip install cairntir` resolved to 1.1.2 and hung on first run. Guarded
> against recurrence by `scripts/check_release_tags.py`.

**The cold-start fix that should have happened four commits ago.**

Five prior commits chased variants of the same symptom — the MCP
server hangs for 1-12 minutes on the first `cairntir_remember`
or `cairntir_recall` after a fresh boot — by patching around the
slow path: lazy load, background warmup, stdout silencing,
default-disable warmup, removing query from session_start.
Every one was a workaround. None killed the root cause.

### Fixed — root cause: torch is slow to import

`import sentence_transformers` triggers `import torch`, which
initializes CUDA detection, threading, and a wall of C++
extensions every Cairntir startup pays for and never uses.
Measured on a CPU-only Windows desktop on 2026-05-03: 2 minutes 7
seconds for the import alone, up to 12 minutes wall-clock when
Hugging Face Hub I/O is slow. Subsequent calls in the same
process were fast, but every fresh MCP server pid paid the full
cold start with zero feedback to the user.

### Added — `FastEmbedProvider`

New production embedder backed by `fastembed` (ONNX Runtime).
Drop-in replacement for `SentenceTransformerProvider`: same
`all-MiniLM-L6-v2` model under the hood, same 384-dim output,
same vector space. Import + load + first embed measured
end-to-end at **1.4 seconds** with the model cached on disk
(versus 2-12 minutes for sentence-transformers). Existing drawers
remain searchable across the swap; both backends embed into the
same model's space.

### Changed — production default flipped

`src/cairntir/mcp/server.py` and `src/cairntir/daemon/__main__.py`
now construct `FastEmbedProvider()` instead of
`SentenceTransformerProvider()`. The legacy provider is kept on
the public surface (`cairntir.impl.SentenceTransformerProvider`)
for opt-in fallback and the eval suite.

### Added — `cairntir setup` step 7: pre-warm the embedder

Setup now downloads and caches the ONNX model
(~25 MB to `~/.cache/fastembed/`) during the wizard, so the first
user-facing `cairntir_remember` after install is never the slow
one. Failure to warm is logged but non-fatal — the model
auto-downloads on demand if setup couldn't fetch it.

### Dependencies

- Added: `fastembed >= 0.4.0` (transitively brings `onnxruntime`
  and `huggingface_hub`)
- Kept: `sentence-transformers >= 3.0.0` for the legacy provider
  and the eval suite. Future major version may move it to an
  optional extras group.

## [1.1.2] — 2026-05-03

**Architectural follow-up to 1.1.1.** 1.1.1 silenced the stdout
corruption that was wedging `cairntir_session_start`; 1.1.2 makes
sure the call can never trigger the slow path in the first place.

### Fixed — `cairntir_session_start` is now pure SQL

Removed the `query` parameter from the `cairntir_session_start` MCP
tool spec. The retriever's optional `query` argument was the only
path through `session_start` that triggered the embedder, and on
cold MCP servers the sentence-transformers cold load took up to
~2.5 minutes — long enough that Claude Code's MCP-call timeout
fired well before the response arrived, even when the server
ultimately produced a valid 3,625-char answer (observed
2026-05-03).

With `query` removed from the tool spec, Claude Code stops passing
it. `session_start` becomes two `list_by` SQL queries plus a string
format — sub-second on every cold MCP server boot, no embedder
cold-load on the critical path. Semantic search has its own home:
`cairntir_recall`.

The backend method `CairntirBackend.session_start(wing, query)`
still accepts `query` for direct library callers; only the
MCP-advertised tool surface drops it.

Diagnostic plumbing added during the chase stays in place:
- `cairntir_home() / mcp.log` — per-process timestamped log of
  server startup, every tool dispatch, every embedder load step
- `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` are set as
  defaults at MCP startup so the embedder never tries to phone
  home

### Process

- New regression test pins the `cairntir_session_start` tool spec
  to never advertise a `query` parameter
- 240 → 241 tests passing, ruff/format/mypy --strict/silent-except
  all clean
- Bumped 1.1.1 → 1.1.2 in pyproject.toml, __init__.py, plugin.json

## [1.1.1] — 2026-04-25

**Critical hotfix.** `cairntir_session_start` was wedging Claude Code
sessions for 20+ minutes (sometimes indefinitely) on real user
machines. Two independent bugs were stacked on top of each other; both
are fixed in this release.

### Fixed — MCP stdio stream corruption

`sentence-transformers`, `transformers`, and `torch` write progress
bars (`Loading weights: ...`) and architecture-mismatch tables
(`BertModel LOAD REPORT`) directly to **stdout** during model
construction. When `SentenceTransformerProvider` runs inside the MCP
stdio server, those bytes interleave with the JSON-RPC responses
Claude Code is reading. The JSON parse breaks, Claude Code waits
forever for a valid response that never comes, and the user sees
"Pontificating..." for hours.

`SentenceTransformerProvider._load()` and `.embed()` now wrap their
work in a `_silence_io()` context manager that:

- Dups fds 1 and 2 to `/dev/null` at the OS level (so even direct C
  extension writes vanish).
- Swaps `sys.stdout` and `sys.stderr` for `io.StringIO()` instances
  (so Python-level writes also vanish).
- Restores both via `try/finally` so a load failure can't silence
  the rest of the process.

### Fixed — Warmup race

The `warm_embedder_in_background` daemon thread (added in 91a8350)
loaded the sentence-transformers model in parallel with the asyncio
stdio loop. When a `cairntir_session_start` call arrived with a
query, the main thread also tried to load the model — both went
through `SentenceTransformer.__init__` simultaneously, and on real
user boxes this combination of (race + stdout corruption) is what
produced the 20-minute hangs.

The warmup is now **opt-in** via `CAIRNTIR_ENABLE_EMBEDDER_WARMUP=1`.
Default behavior is the pre-91a8350 lazy first-call load on the main
thread. The ~25s first-write latency is the price; reliability comes
first. Re-enable the warmup once a process-wide model-load mutex is
in place to serialize the warmup and synchronous paths.

### Process

- `_WARMUP_DISABLE_ENV_VAR` → `_WARMUP_ENABLE_ENV_VAR`. Same
  vocabulary (`1`/`true`/`yes`/`on`), inverted semantics.
- `tests/unit/test_mcp_warmup.py` rewritten for the opt-in shape.
- 240 tests passing, ruff/mypy/silent-except all clean.

### Diagnostics that surfaced this

Three orphaned Python processes (250 MB each, sentence-transformers
fully loaded) were sitting in `tasklist` after multiple Claude Code
sessions had spawned and wedged their MCP servers. The user's
"Pontificating..." Claude Code session showed `cairntir [cairntir_session_start]`
at the top of the active tool stack, blocked indefinitely. Reproducing
the cold load against the real `SentenceTransformerProvider` showed
`Loading weights: 100%|##########|` and a `BertModel LOAD REPORT`
table on stdout — the smoking gun.

## [1.1.0] — 2026-04-18

v1.1 Synergy Stack — the three-upgrade bundle. Pulls forward v1.2
(Production Reason Loop), v1.3-partial (Cross-Wing Recall + Temporal),
and v1.5 (Recipe Runtime) from the Road to 2.0, and ships them
together because the value compounds when they land in the same
release. Plus the cold-start handshake fix and the embedder warmup
from the unreleased hotfix branch; 1.1.0 is the first PyPI release
that carries both halves of the install hardening *and* the synergy
stack.

### Added — Cross-Wing Recall + Temporal Walk

- **`cairntir_cross_recall` MCP tool.** Where `cairntir_recall` scopes
  to one wing, `cairntir_cross_recall` searches every wing the user
  has ever written to, annotating each hit with its wing-of-origin.
  A question asked in one project now finds its answer in another.
- **`cairntir cross-recall "<query>"` CLI.** Same reach at the
  terminal.
- **`cairntir.memory.temporal` module.** Two pure query functions
  over the existing supersedes chain: `walk_supersedes(store, id)`
  returns the full chain root→leaf, and `as_of(store, id, when)`
  returns the chain member that was the live leaf at `when`. No
  schema change — every relation was already present in v0.2.

### Added — Production Reason Loop (stdlib-only, zero network)

Cairntir does not call LLMs. The Reason loop is a *discipline* for
committing falsifiable predictions; the hypothesis comes from the
caller — a human at a terminal, or the Claude Code session already
driving the CLI. Cairntir stays the memory layer, not a second
inference provider that would double-bill the user.

- **`cairntir.production` package.** Four stdlib-only adapters:
  - `StoreBackedMemory(store)` — `MemoryGateway` over any `Store`.
  - `StoreBackedBeliefs(store)` — `BeliefStore` over any `Store`.
  - `NullRunner` — `ExperimentRunner` that records a caller-supplied
    verdict.
  - `ManualProposer` — `HypothesisProposer` that returns a
    caller-supplied hypothesis. Accepts either a prebuilt
    `Hypothesis` or raw `claim` + `predicted_outcome` strings.
- **`cairntir reason "<question>" --wing X` CLI.** Runs one full
  Reason loop step. `--claim`, `--predicted`, `--observed`, and
  `--success`/`--fail` can be supplied as flags for non-interactive
  use, or collected via `typer.prompt` one by one. Writes the
  prediction + observation drawer pair, adjusts belief mass. Zero
  network calls, zero paid tokens.
- **Future: local-AI proposer.** A Gemma 4 (via llama.cpp or
  similar) proposer can drop in by implementing
  `HypothesisProposer` — no API costs, still local-first. Planned
  as a separate phase once the synergy stack has been exercised in
  the field.

### Added — Recipe Runtime

- **`cairntir.recipes` package.** Declarative protocols that chain
  the three core skills into repeatable disciplines. The three
  skills stay locked — recipes are the escape valve.
  - `RecipeContract` dataclass loaded from `recipe.toml`: `name`,
    `description`, `version`, `output_wing`, ordered `skills` list
    (`crucible` / `quality` / `reason`), typed `input` table.
  - `load_recipe(path)` validates the TOML and rejects malformed
    recipes with a typed `RecipeError`.
  - `discover_recipes()` walks `docs/recipes/**/recipe.toml` in the
    project and `~/.claude/recipes/**/recipe.toml` for the user;
    project recipes shadow user recipes when names collide.
  - `RecipeRunner(memory, beliefs, proposer, runner)` executes a
    contract end-to-end. Writes a seed drawer capturing the
    invocation + inputs, then one drawer per skill step. When the
    chain includes `reason`, runs a full `ReasonLoop.step` with
    the caller-supplied `ManualProposer` — the prediction-bound
    drawer pair is the recipe's load-bearing output.
- **`docs/recipes/signal-reader/recipe.toml`.** Ships the Signal
  Reader protocol as an executable recipe. Input slots: `summary`
  (required), `url` (optional), `horizon_months` (optional).
- **`cairntir recipe-list` + `cairntir recipe-run`.** Discover and
  execute recipes from the terminal. Recipes that chain `reason`
  collect claim / predicted / observed / verdict via `--claim` /
  `--predicted` / `--observed` / `--success`/`--fail` flags or
  interactive prompts — never via a network call.

### Changed

- `src/cairntir/__init__.py` and `pyproject.toml` bumped to
  `1.1.0`. `.claude-plugin/plugin.json` matches.
- `src/cairntir/mcp/server.py` and `src/cairntir/cli.py` gain the
  new tools and commands above. The stable v1.0 public API
  (`cairntir.__init__` re-exports) is unchanged — every new surface
  is under `cairntir.impl` / `cairntir.production` / `cairntir.recipes`
  or the CLI/MCP adapters.

### Fixed (carried over from the unreleased hotfix branch)

- **Cold-start MCP handshake timeout** — `DrawerStore.__init__` no
  longer eagerly touches `embedder.dimension`; the model loads only
  when the `vec_drawers` virtual table must be created (first-time
  DBs). Brought startup from ~28 s to ~1 s on cold cache, so Claude
  Code's ~10 s `initialize` timeout stops firing.
- **Embedder background warmup.** A daemon thread kicks off a
  throwaway `embed()` call after the handshake returns, so the
  first `cairntir_remember` / `cairntir_recall` is also instant
  instead of blocking ~25 s on the model load.
- **Pydantic `ValidationError` in MCP tool calls.** The stdio
  server's `_call` adapter now catches `ValidationError` alongside
  `CairntirError` and surfaces it as a one-line `[cairntir error]
  <field>: <message>` so an invalid wing/room/content argument
  doesn't crash the tool response.

## [1.0.1] — 2026-04-17

> **Never released.** Committed and changelogged but never tagged, so it never
> reached PyPI. The work below is present in every later version. Guarded
> against recurrence by `scripts/check_release_tags.py`.

Install hardening. The 1.0.0 install model pinned the MCP registration
to `sys.executable`, which silently broke whenever a venv moved, was
recreated, or got upgraded. This release switches the registration to
a stable console-script shim, adds silent self-heal on every CLI run,
and surfaces a one-line update banner when a newer Cairntir is on
PyPI. Once installed, Cairntir stays on until the user uninstalls — no
re-running setup, no "tools not loaded" surprises.

### Added — Stable install seam
- **`cairntir-mcp` console script.** New entry point declared in
  `[project.scripts]`. Pip's launcher hard-pins the right interpreter
  on install, so the registered MCP command is one stable name that
  survives venv changes, shell restarts, cwd shifts, and Python
  upgrades. `pip uninstall cairntir` removes the launcher; that
  vanish is the user-visible signal that Cairntir is gone.
- **`cairntir.register` module.** Silent self-heal that runs on every
  CLI invocation: checks `claude mcp list` for the cairntir entry,
  re-registers via `claude mcp add -s user cairntir -- cairntir-mcp`
  if missing, writes a checkpoint to `cairntir_home() / .registered`
  for fast-path no-ops on subsequent runs. Opt-out via the
  `CAIRNTIR_DISABLE_AUTOREGISTER` environment variable.
- **`cairntir.update` module.** Non-blocking update notifier. Hits
  `https://pypi.org/pypi/cairntir/json` once per 24 hours in a daemon
  thread (2s timeout, fail-silent on network errors). When a newer
  release exists, the next CLI command and the next MCP tool response
  prepend a one-line banner: `[cairntir update available: X → Y —
  run \`pip install -U cairntir\`]`. Banner appears at most once per
  process. Opt-out via `CAIRNTIR_DISABLE_UPDATE_CHECK`.
- 22 new tests covering the self-heal helper and the update notifier.

### Changed
- `cairntir.cli._mcp_spec` now returns `{"command": "cairntir-mcp",
  "args": []}` — no more `sys.executable` pinning. Both `cairntir
  init` (project scope) and `cairntir init --user` (user scope) use
  the new shim.
- `.claude-plugin/plugin.json` updated to register the same shim.
- The CLI root callback now triggers the silent self-heal and the
  background PyPI check on every invocation. Both side effects are
  fail-silent and opt-out by env var.
- The MCP server kicks off the PyPI check on startup and prepends
  the update banner to the first tool response per process.

### Fixed
- `cairntir_audit` and `cairntir_crucible` MCP tool descriptions no
  longer claim "(Phase-2 stub)" — both tools fully shipped in 1.0.0
  and the label was a documentation bug.
- Tests: `tests/conftest.py` autouse fixture sets both opt-out env
  vars during test runs so the self-heal and PyPI check never touch
  the developer's real home directory or the network.

### Added — Pre-1.0.1 (the prior "Unreleased" block, now historical)
- **PyPI release (2026-04-15):** `pip install cairntir` now works
  worldwide at https://pypi.org/project/cairntir/1.0.0/. First public
  install path; the git-clone + editable-install route is now the
  contributor path, not the user path.
- README badges for PyPI version and monthly downloads.
- `docs/cairntir-for-dummies.md` Step 1 rewritten around `pip install
  cairntir`; uv / pipx alternatives called out; editable-install path
  moved to a "for contributors" aside.
- `docs/publish-checklist.md` Phase 4 marked complete with the two
  gotchas we hit (PowerShell hiding token prompts, never paste a
  token in a shared context).

## [1.0.0] — 2026-04-08

Library extraction. Cairntir graduates from "a tool" to "the thing other
tools store their memory in". The v1.0 contract is a curated protocol
surface re-exported from the package root; concrete implementations
move to `cairntir.impl.*` and reserve the right to change between
minor releases. Six versioned phases (v0.2 → v0.6) landed in the
pre-v1.0 arc — prediction-bound drawers, consolidation / forgetting /
contradiction, surprise + belief-as-distribution, portable signed
format, and the clean-ports Reason loop — and v1.0 locks the seam.

### Added — Public protocol surface (`cairntir.__init__`)
- `Store` protocol: `add`, `get`, `list_by`, `search`, `update_layer`,
  `reinforce`, `weaken`, `stale_ids`, `close`
- `EmbeddingProvider` protocol (re-export from the memory package)
- Reason-loop ports: `HypothesisProposer`, `ExperimentRunner`,
  `BeliefStore`, `MemoryGateway`
- Frozen value types: `Drawer`, `Layer`, `Hypothesis`, `Experiment`,
  `Outcome`, `BeliefUpdate`
- Typed exceptions: the full set from `cairntir.errors`, plus the new
  `CairntirDeprecationWarning`

### Added — `cairntir.impl` namespace
- `DrawerStore`, `HashEmbeddingProvider`, `SentenceTransformerProvider`,
  `Retriever`, `RetrievalResult`, `ReasonLoop`, `SCHEMA_VERSION`
- All concrete — reserved right to change. The public contract is the
  protocol surface above.

### Added — v1.0 contract test infrastructure
- `tests/contract/test_store_contract.py` — every `Store` impl must
  pass this suite; runs against `DrawerStore` via a parametrized
  factory fixture
- `tests/property/test_taxonomy_properties.py` — Hypothesis-driven
  property tests for taxonomy invariants (valid identifiers round
  trip, whitespace content rejected, belief mass preserved, layer
  preserved)
- `tests/unit/test_public_api.py` — snapshot of `dir(cairntir)` that
  fails on drift; separate assertions for `__all__` and `__version__`
- v1 → v2 → v3 schema migration fixtures exercised against
  `DrawerStore` (hand-built pre-v4 databases reopen and upgrade
  losslessly)

### Added — Deprecation policy
- `CairntirDeprecationWarning` subclass of `DeprecationWarning`. Public
  surfaces must emit this warning for at least two minor releases
  before removal. No silent removals.

### Changed
- `cairntir.__init__` is now a *curated* surface. Importing private
  concrete classes from `cairntir.memory.*` or `cairntir.reason.loop`
  still works for now, but the stable seam is the protocol re-exports.
- `hypothesis` added to dev dependencies.
- Version bumped `0.1.0 → 1.0.0`.

## [0.1.0] — 2026-04-08

The memory-first reasoning layer ships. Five phases from bootstrap to the
one-loop daemon, tying together verbatim memory, three skills, and a
six-tool MCP surface that Claude Code can talk to directly.

### Added — Phase 0 · Bootstrap
- Professional scaffolding: `pyproject.toml`, `ruff`, `mypy --strict`,
  `pytest`, `pre-commit`
- GitHub Actions CI: lint + test matrix
- Core documentation, community files, lineage material from
  BrainStormer preserved read-only
- Ban on silent `except: pass` enforced by CI

### Added — Phase 1 · Memory Spike
- `cairntir.memory.taxonomy` — frozen pydantic `Drawer` + `Layer` enum
  with strict identifier validation
- `cairntir.memory.embeddings` — `EmbeddingProvider` protocol,
  deterministic `HashEmbeddingProvider` for tests, lazy-loading
  `SentenceTransformerProvider` for production
- `cairntir.memory.store` — sqlite-vec backed `DrawerStore` with a
  `vec0` virtual table and typed error surface
- `cairntir.memory.retrieval` — 4-layer `Retriever`
  (identity / essential / on_demand / deep)
- LongMemEval R@5 eval skeleton

### Added — Phase 2 · MCP Server
- `cairntir.config` — `CAIRNTIR_HOME` + platformdirs-based path resolution
- `cairntir.mcp.backend.CairntirBackend` — transport-free implementation
  of `remember`, `recall`, `session_start`, `timeline`, `audit`, `crucible`
- `cairntir.mcp.server` — stdio adapter, runnable as
  `python -m cairntir.mcp.server`

### Added — Phase 3 · Skills
- `src/cairntir/skills/crucible.md` — 4-phase epistemic forge distilled
  from BrainStormer lineage
- `src/cairntir/skills/quality.md` — two-stage ship gate with
  Evidence-Before-Claims and the Cairntir-native T6 Memory Discipline tier
- `src/cairntir/skills/reason.md` — new memory-backed thinking loop
- `cairntir.skills.load_skill` — bundled markdown via
  `importlib.resources`, wired into the Crucible and Quality tools

### Added — Phase 4 · Daemon
- `cairntir.daemon.spool` — atomic `write_capture`, arrival-ordered
  `pending_files`, strict `parse_capture`, quarantine-on-failure
- `cairntir.daemon.capture.CaptureDaemon` — `tick()` for one-shot
  processing, `run()` for the asyncio poll loop, graceful `request_stop`
- `python -m cairntir.daemon` — production entry point
- Retires the init/wrapup ceremony: spool → daemon → store → session_start

### Quality
- 54 tests, 85% coverage
- `ruff check`, `ruff format`, `mypy --strict` clean
- Every exception typed; no silent `except: pass`

[Unreleased]: https://github.com/pnmcguire480/cairntir/compare/v1.7.0...HEAD
[1.7.0]: https://github.com/pnmcguire480/cairntir/compare/v1.6.2...v1.7.0
[1.6.2]: https://github.com/pnmcguire480/cairntir/compare/v1.6.1...v1.6.2
[1.6.1]: https://github.com/pnmcguire480/cairntir/compare/v1.6.0...v1.6.1
[1.6.0]: https://github.com/pnmcguire480/cairntir/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/pnmcguire480/cairntir/compare/v1.4.1...v1.5.0
[1.4.1]: https://github.com/pnmcguire480/cairntir/compare/v1.4.0...v1.4.1
[1.4.0]: https://github.com/pnmcguire480/cairntir/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/pnmcguire480/cairntir/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/pnmcguire480/cairntir/compare/v1.1.2...v1.2.0
[1.1.2]: https://github.com/pnmcguire480/cairntir/compare/v1.1.0...v1.1.2
[1.1.0]: https://github.com/pnmcguire480/cairntir/compare/v1.0.0...v1.1.0
[1.0.1]: https://github.com/pnmcguire480/cairntir/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/pnmcguire480/cairntir/compare/v0.1.0...v1.0.0
[0.1.0]: https://github.com/pnmcguire480/cairntir/releases/tag/v0.1.0
