# Release prep — v1.3.0

**Status:** prepared, **not cut.** The version has deliberately *not* been
bumped and nothing has been tagged. Publication is an explicit human gate and
stays Patrick's. See [publish-checklist.md](publish-checklist.md).

---

## The number is 1.3.0, not 1.2.1

Patrick asked for "1.2.1". Per the division of labour he set himself
(drawer #177, and `docs/release-cadence.md`): **Patrick decides *when* a
release is worth considering; the agent reads the accumulated changelog and
decides *which number*.** So this is that decision, with its reasoning
exposed for him to overrule.

`docs/release-cadence.md` is unambiguous, and uses these exact examples:

| Segment | When | Its own example |
|---|---|---|
| **PATCH** `1.2.1` | Fixes only. Nothing new to learn. | Cold-start hang; a Windows encoding crash. |
| **MINOR** `1.3.0` | New capability, additive. | **"A new MCP tool"** |

What accumulated is **two new MCP-adjacent capabilities and two new CI
gates**, not fixes:

- `cairntir_handoff(wing)` — a new MCP tool. The literal MINOR example.
- `cairntir cost <wing>` — a new CLI command.
- `cairntir handoff <wing>` — a new CLI command.
- `scripts/check_landed_commitments.py` — a new build gate.

And the tiebreak settles it outright:

> If a user would need to read the changelog to know what changed, it is a
> MINOR, not a PATCH.

A user upgrading would absolutely need the changelog — there is a new tool they
would not otherwise know to call. **1.3.0.**

Nothing here is breaking, nothing is deprecated, and `2.0.0` is untouched — it
remains reserved for a revolutionary change in what Cairntir *is*.

---

## Do not cut it yet, and why

The work sits in **four stacked, unmerged pull requests**:

| PR | Contents |
|---|---|
| #25 | The two research documents (docs only) |
| #26 | `cairntir_handoff` |
| #27 | `check_landed_commitments.py` |
| #28 | `cairntir cost` + determinism suite |

Bumping the version now would put a `## [1.3.0]` header on a branch whose
features may not all land. If only some PRs merge, the changelog would claim
capabilities that are not in the build — which is a more embarrassing version
of the exact defect `check_release_tags.py` and `check_landed_commitments.py`
were both written to prevent.

**The version bump belongs on `main`, after the merges.** That is also the
order `docs/release-cadence.md` describes: the header is written before the
tag, but after the code.

---

## The sequence, once the PRs are merged

Run from `main`, in order. Nothing here publishes; step 6 is the human gate.

1. **Merge #25 → #26 → #27 → #28**, in that order — they are stacked, so
   merging out of order will produce confusing diffs. Each is already green on
   14/14 checks.

2. **Bump the version in three places.** They must agree or the release
   verification gate fails:
   - `pyproject.toml` → `version = "1.3.0"`
   - `.claude-plugin/plugin.json` → `"version": "1.3.0"`
   - `src/cairntir/__init__.py` → `__version__ = "1.3.0"`

3. **Cut the changelog header.** Change `## [Unreleased]` to
   `## [1.3.0] - <date>` and open a fresh empty `## [Unreleased]` above it.
   The entries are already written and ordered.

4. **Verify locally.** All of these must be clean:
   ```bash
   uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run mypy --strict src && uv run python scripts/check_no_silent_except.py && uv run python scripts/check_release_tags.py && uv run python scripts/check_landed_commitments.py && uv run mkdocs build --strict
   ```

5. **Land the bump through a PR**, like everything else. `main` is protected and
   the release workflow builds from `main`, so the full matrix must be green
   before `main` moves.

6. **Tag — the human gate.** `git tag v1.3.0 && git push origin v1.3.0`.
   Only a pushed `v*.*.*` tag publishes. Follow
   [publish-checklist.md](publish-checklist.md) from here.

---

## What is deliberately NOT in this release

**The embedder change.** `cairntir cost` now reports that a meaningful share of
drawers exceed the embedder's ~2,048-character window (29% on the `cairntir`
wing; 43% store-wide when measured across all wings on 2026-08-02). The fix —
chunking long drawers at embed time, or moving to a long-context embedding
model — **requires reindexing the live store.**

That was not done unattended, on purpose. This project's own discipline, set by
drawers #182 and #210, is to rehearse on a read-only snapshot and take a
timestamped backup before touching the live database, with explicit approval.
Doing a live reindex while the maintainer is asleep would violate the rule the
project wrote for itself after the last time this went sideways.

It is now **measured** rather than estimated, which is the prerequisite. The
change itself is Patrick's call. The research doc's practical upgrade 1 (the
embedder bake-off) is the right next step, and the reindex path already exists
and has been exercised on the live store before.

**`session_start` itself is unchanged.** `handoff` is the bounded alternative
beside it, not a fix to it. `session_start` still returns every identity and
essential drawer as a truncated stub; its description now points at `handoff`
for resuming work. Narrowing or budgeting `session_start` is a behaviour change
for existing callers and deserves its own decision.

---

## A correction to the research

`plans/research-2026-08-02-trends-and-practical-upgrades.md`, practical upgrade
4, says model capture "remains unbuilt." **That is wrong, and the research
document was not corrected in place** — it is a dated artifact and this is the
correction.

The capture seam is fully wired and always has been: `cairntir-mcp --model`,
the `CAIRNTIR_MODEL` environment variable, flowing into
`WriteProvenance.create(model=...)` and stored on every drawer's immutable
receipt (`src/cairntir/mcp/server.py`).

What is true is narrower: **no host sets it**, so every receipt honestly records
`unknown`. The remaining work is not building capture — it is having the
launchers populate it where a host exposes the model at all. A user can set
`CAIRNTIR_MODEL` in their MCP config today and it will be recorded.

Read the source before characterising it — drawer #173's standard, applied to
Cairntir's own research.
