# 2026-08-06 — Post-1.4.0 hardening sweep

**Status:** landed. Released as `1.4.1`.

Patrick's request, verbatim:

> i did a lot of work and got cairntir 1.4.0 released. can you check for hot
> fixes, bugs, recently committed work and execute a hardening sweep. then
> update and release 1.4.1?

## What the sweep found

The build was already green — ruff, `ruff format`, `mypy --strict` across 51
files, all six gate scripts, `cairntir doctor --gate` against the live 337-drawer
store, and 637 tests at 82.26% coverage, with `1.4.0` confirmed present on PyPI.
Nothing was broken. Two real defects turned up anyway, and they are the same
defect wearing different clothes: **a guard that reports success without doing
its job.**

### 1. The silent-except gate was close to a no-op

`scripts/check_no_silent_except.py` guards Cairntir's oldest governance
principle — the one written against BrainStormer's 224 `except: pass` blocks.
It was four regexes. Three of them required `pass` on the *same line* as
`except`:

```python
re.compile(r"^\s*except\s+Exception\s*:\s*pass\s*$", re.MULTILINE)
```

`ruff format` never emits that one-liner, so on this repository's own formatted
source those three patterns could not fire at all. The fourth caught a bare
`except:`, which ruff's E722 already rejects. Net effect: the gate was blind to
the form the pattern actually takes —

```python
except OSError:
    pass
```

— a *typed* handler swallowing on the next line. **Three live violations sat in
`src/` while the script exited 0**: two in `register.py`, one the rewrite found
in `memory/store.py` that no hand review had spotted.

**Root cause:** it was the only gate script in the repository with no test.
`check_release_tags.py`, `check_landed_commitments.py`, `check_seams.py`,
`vault_sync.py` and `reattest_legacy_trust.py` all have one. The oldest gate had
none, so nothing noticed when `ruff format` quietly made it unreachable.

**Fix:** rewritten as an AST check with no type list to maintain — a handler is
silent when its body does nothing at all (`pass` and/or `...`), whatever it
catches. A file that cannot be read or parsed is a violation rather than a skip,
because a file the gate cannot inspect is one it cannot vouch for. Plus
`tests/unit/test_silent_except.py`, 22 cases pinning what counts as silent, what
counts as surfacing, and that the live tree is clean.

The three violations are fixed by *surfacing*, not by suppressing:

- `register.py` — the two checkpoint writes now report a failed write to stderr.
  A silently unwritable checkpoint turns the fast path off forever and looks like
  nothing from the outside. `clear_checkpoint` got the same treatment: a failed
  unlink means the next invocation takes the fast path and skips the
  re-registration the caller just asked for — the opposite of what was requested.
- `store.py` — `_parses_as_json` turns the exception into a value. The failure
  there genuinely *is* the signal (an unparseable tail is not the swallowed-
  tool-call shape and falls through to the next rule), so converting it to a
  boolean keeps the intent on the page instead of hiding it in a bare handler.

`scripts/` and `tests/` were scanned with the new rule as well and are clean, so
widening the gate's scope is not needed yet.

### 2. `cairntir_recall(full_content=N)` had no cumulative budget

Shipped in 1.4.0. The size test ran **per drawer** against a shared constant:

```python
fits = len(drawer.content) <= DEFAULT_BUDGET_CHARS   # 12,000
```

with no accumulator and no upper bound on `full_content`. Ten 11,900-character
drawers each "fit" a 12,000-character ceiling, so `full_content=10` delivered
~119,000 characters — roughly 30,000 tokens — while claiming to respect the
budget. `handoff` and `session_start` have enforced a real cumulative ceiling
since 1.3.0; recall's full-content path never did.

This is a regression against the point of the 1.3.0 release, and against the
oldest inherited idea in the lineage: **controlled context** predates any vector
store here. It is the fourth time that invariant has had to be re-landed.

**Fix:** the budget accumulates across everything delivered whole. Once spent,
remaining hits fall back to snippets and are named with their ids — whole
drawers or none, the same contract `handoff` keeps. Budget exhaustion is
reported distinctly from a genuinely oversize drawer, because "too large for
full delivery" is a lie about a drawer that would have fit an empty budget. The
call now says what it spent.

The `budget_chars` parameter is deliberately **not** published in the
`cairntir_recall` tool schema. The ceiling is what fixes the defect; the tunable
is new surface, and new surface makes a MINOR under `docs/release-cadence.md`.
1.4.1 is fixes-only. Exposing it in the next MINOR is adding one property and
nothing else.

## Not done, and why

- **The repo does not dogfood its own fourth host.** `cairntir doctor` reports
  `project qwen MCP=missing policy=missing` — 1.4.0 added Qwen Code as a
  supported host, but `C:\Dev\Cairntir` has no `.qwen/settings.json` and no
  `QWEN.md`, while claude, codex and cursor are all wired at project scope. A
  Qwen agent opening this repo gets no policy. Real, but it is repo config
  rather than a defect in the shipped package, and it does not belong in a
  fixes-only patch.
- **Two commits reached `main` without a pull request.** `2829ef3` and `77ee341`
  are direct pushes, which is the admin bypass `docs/release-cadence.md`
  explicitly warns against. Not retroactively fixable; noted so the pattern is
  visible.
- **The embedder bake-off** remains the highest-value open item and still needs
  Patrick awake for the live reindex. Untouched, as before.

## Commitments

```cairntir-commitments
# 1 — the silent-except gate, and the test that was missing for four minor releases.
file   scripts/check_no_silent_except.py
symbol scripts/check_no_silent_except.py check_file
symbol scripts/check_no_silent_except.py _is_noop
file   tests/unit/test_silent_except.py
test   tests/unit/test_silent_except.py test_the_exact_regression_that_shipped
test   tests/unit/test_silent_except.py test_unparseable_file_is_a_violation_not_a_skip
test   tests/unit/test_silent_except.py test_src_tree_has_no_silent_handlers

# 2 — the three swallows, fixed by surfacing rather than suppressing.
symbol src/cairntir/register.py _write_checkpoint
symbol src/cairntir/memory/store.py _parses_as_json

# 3 — the cumulative recall budget. `param` is the assertion that earns its
# place here: `recall` existed the whole time the ceiling did not.
param  src/cairntir/mcp/backend.py recall:budget_chars
test   tests/integration/test_mcp_backend.py test_recall_full_content_budget_is_cumulative
test   tests/integration/test_mcp_backend.py test_recall_budget_exhaustion_is_not_reported_as_oversize
```
