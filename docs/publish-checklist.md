# Publish Checklist — going public with Cairntir

This is the exact sequence to take Cairntir from "local git repo"
to "public on GitHub, installable from PyPI, indexed by search
engines." Every step is listed; none of them are run automatically.
You decide the timing.

## Phase 0 — Verify the repo is publish-ready

Run these locally. Every one must come back green.

```bash
# Full test suite
uv run pytest -m "not slow and not eval" -q

# LongMemEval R@5 fail-on-regression gate
uv run pytest -m eval --no-cov -q

# Lint + format + type check
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy --strict src

# Silent except scanner
uv run python scripts/check_no_silent_except.py

# Public API snapshot (must not drift)
uv run pytest tests/unit/test_public_api.py -v

# Contract tests (every Store impl passes protocol invariants)
uv run pytest tests/contract/ -v
```

Review this file structure is present and current:

- [ ] `README.md` — hero page, keyword set, compatibility table
- [ ] `LICENSE` — MIT, with the right year and name
- [ ] `CHANGELOG.md` — v1.0.0 entry at the top
- [ ] `CONTRIBUTING.md` — referenced from README, actually exists
- [ ] `CODE_OF_CONDUCT.md` — community baseline
- [ ] `SECURITY.md` — how to report vulnerabilities
- [ ] `ETHOS.md` — the five rules
- [ ] `docs/cairntir-for-dummies.md`
- [ ] `docs/conception.md`
- [ ] `docs/integration-guide.md`
- [ ] `docs/deprecation-policy.md`
- [ ] `docs/manifesto.md`
- [ ] `docs/concept.md`
- [ ] `docs/roadmap.md`
- [ ] `pyproject.toml` — version = "1.0.0", description accurate, URLs point at github.com/pnmcguire480/cairntir
- [ ] `.claude-plugin/plugin.json` — version = "1.0.0"

## Phase 1 — Create the GitHub repository

```bash
# From inside c:/Dev/Cairntir (or wherever the repo lives)

# 1. Log in if you haven't. Opens a browser.
gh auth login

# 2. Create the public repo. Adjust the description and topics to match.
gh repo create pnmcguire480/cairntir \
  --public \
  --description "Memory-first reasoning layer for Claude Code. Kills cross-chat AI amnesia. MCP server, verbatim storage, prediction-bound drawers, belief-as-distribution retrieval." \
  --homepage "https://github.com/pnmcguire480/cairntir" \
  --push \
  --source .

# 3. Set topics for search/discovery. This is the SEO lever.
gh repo edit pnmcguire480/cairntir --add-topic claude-code
gh repo edit pnmcguire480/cairntir --add-topic mcp
gh repo edit pnmcguire480/cairntir --add-topic model-context-protocol
gh repo edit pnmcguire480/cairntir --add-topic ai-memory
gh repo edit pnmcguire480/cairntir --add-topic llm-memory
gh repo edit pnmcguire480/cairntir --add-topic anthropic
gh repo edit pnmcguire480/cairntir --add-topic claude
gh repo edit pnmcguire480/cairntir --add-topic python
gh repo edit pnmcguire480/cairntir --add-topic sqlite
gh repo edit pnmcguire480/cairntir --add-topic sqlite-vec
gh repo edit pnmcguire480/cairntir --add-topic vector-search
gh repo edit pnmcguire480/cairntir --add-topic persistent-memory
gh repo edit pnmcguire480/cairntir --add-topic local-first
gh repo edit pnmcguire480/cairntir --add-topic mcp-server
gh repo edit pnmcguire480/cairntir --add-topic developer-tools
gh repo edit pnmcguire480/cairntir --add-topic productivity
gh repo edit pnmcguire480/cairntir --add-topic open-source
gh repo edit pnmcguire480/cairntir --add-topic agent
gh repo edit pnmcguire480/cairntir --add-topic reasoning
```

After this runs, https://github.com/pnmcguire480/cairntir exists and
has all the code.

## Phase 2 — Cut the v1.0.0 release

```bash
# Tag is already committed locally as v1.0.0 (from an earlier session).
# Confirm it:
git tag | grep v1.0.0

# Push it.
git push origin v1.0.0

# Create the GitHub release from the tag. Paste the CHANGELOG entry
# as the release notes body.
gh release create v1.0.0 \
  --title "v1.0.0 — Library Extraction" \
  --notes-from-tag \
  --latest
```

If `--notes-from-tag` doesn't give you what you want, use
`--notes-file CHANGELOG.md` and edit the release on github.com to
trim it to just the v1.0.0 section.

## Phase 3 — Announce

The goal is one signal in each of five places so the first wave of
search traffic can find it. Skip any that don't feel right; the repo
speaks for itself.

- **r/LocalLLaMA** — "I built the memory layer Claude Code should
  have shipped with. Kills cross-chat amnesia. MIT, MCP-compatible,
  local-first." Link to README. Short, not salesy. Answer questions.
- **r/ClaudeAI** — same post, different framing: emphasize the
  Claude Code experience.
- **Hacker News — Show HN:** title format: *"Show HN: Cairntir —
  verbatim memory for Claude Code (kills cross-chat amnesia)"*.
  Submit in the morning (Pacific) on a Tuesday or Wednesday. Be in
  the thread for the first hour to answer comments.
- **X / Twitter** — one thread from a dev account if you have one.
  Lead with the day-30 pitch, not the feature list.
- **Anthropic Discord / MCP discussion channels** — mention it in
  the MCP-tools channel. Don't spam; one post, link, and a sentence
  about why it's different.

Do not post to all five on the same day. Space them out so you can
respond to each audience without burning out.

## Phase 4 — Publish to PyPI ✅ *(completed 2026-04-15)*

**Live at https://pypi.org/project/cairntir/1.0.0/** —
`pip install cairntir` works worldwide. The process that actually
shipped it, kept below for anyone repeating this on a future project:

> **Gotcha we hit:** a PowerShell token prompt looks like it's
> waiting for input even when it has already accepted the paste.
> Trust the "100% ━━━━" lines — if the upload shows bytes going
> through, the token worked even if the shell looks frozen.
>
> **Gotcha we also hit:** don't post your API token in any shared
> context, ever. A single leaked pypi- prefix is enough to compromise
> the project. Rotate immediately via https://pypi.org/manage/account/token/
> if it ever happens.

```bash
# 1. Confirm pyproject.toml is ready
cat pyproject.toml | grep '^version'
# Should read: version = "1.0.0"

# 2. Build the distribution
uv build
# produces dist/cairntir-1.0.0.tar.gz and dist/cairntir-1.0.0-py3-none-any.whl

# 3. Test-publish to TestPyPI first (requires an account at test.pypi.org)
uv publish --publish-url https://test.pypi.org/legacy/
# Then from a fresh venv:
pip install --index-url https://test.pypi.org/simple/ \
    --extra-index-url https://pypi.org/simple/ cairntir
cairntir setup --yes   # confirm it works end-to-end
# If this works, you're safe to publish for real.

# 4. Publish to real PyPI (requires pypi.org account + API token)
uv publish
# cairntir is now `pip install cairntir`-able worldwide.
```

Subsequent releases: bump version in `pyproject.toml` and
`.claude-plugin/plugin.json`, add a CHANGELOG entry, run
`uv build && uv publish`. Done.

## Phase 5 — Post-launch monitoring

Week 1:

- [ ] Watch GitHub issues — respond within 24h
- [ ] Watch PRs — review within 48h
- [ ] Add a `good-first-issue` label and tag 3-5 small tasks
- [ ] Answer every HN / Reddit / Discord comment

Month 1:

- [ ] Open a v1.1 milestone with whatever the first real users ask
      for (don't plan in a vacuum; let demand drive the roadmap)
- [ ] Write a blog post: *"The Amnesia Problem and What It Cost Me"*
      — the v0.1 roadmap listed this, it's still unwritten, and now
      is when it would land with the most reach
- [ ] Optional: submit to the
      [Awesome MCP](https://github.com/punkpeye/awesome-mcp-servers)
      list

Month 3:

- [ ] Retrospective in CHANGELOG: what shipped, what was cut, what
      users actually asked for vs what the round table predicted
- [ ] Decide: keep iterating solo, or cut a v2.0 that splits the CLI
      / MCP / daemon into separate distributions (the one piece of
      v1.0 that was deferred)

## Don'ts

- **Don't force-push to `main` after publishing.** People are
  cloning it.
- **Don't delete old tags.** Reproducibility matters even for a
  tool this young.
- **Don't rename the package on PyPI** without a two-minor-release
  deprecation window (see [docs/deprecation-policy.md](deprecation-policy.md)).
- **Don't add telemetry.** Cairntir is local-first. A user should
  be able to disconnect their machine from the network forever and
  Cairntir should keep working.
- **Don't promise features the round-table already cut.** Team
  Memory as a feature, Temporal Knowledge Graph as standalone —
  these were deliberately rejected. If users ask, point them at the
  portable signed format and the prediction-bound drawer schema.

## The one-line summary

```
Phase 0: make sure it's green.
Phase 1: gh repo create + topics.
Phase 2: push the tag, cut the release.
Phase 3: one signal per place, spaced out.
Phase 4: PyPI when you're ready.
Phase 5: answer every question for the first month.
```
