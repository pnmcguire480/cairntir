# Publish Checklist — releasing Cairntir

This is the canonical release sequence. Code completion never authorizes
publication. Pushing a `v*.*.*` tag starts the trusted-publishing workflow, so
the tag is an explicit human gate.

## Current release candidate — v1.2.0

Automated acceptance:

- [x] all tests, including the opt-in semantic eval
- [x] Ruff lint and format
- [x] mypy strict
- [x] silent-exception scanner
- [x] public API and Store contract suites
- [x] strict MkDocs build
- [x] sdist and wheel build
- [x] isolated wheel install, redirected Windows help, and bundled-recipe smoke
- [x] workflow YAML parses and all external actions use immutable SHAs

Operational acceptance:

- [x] schema-v6 migration/reindex rehearsed on an online backup of the real
      database; drawer count and full-table SHA-256 preserved
- [x] project-local Claude/Codex/Cursor MCP and policy configuration reports
      ready
- [x] real Claude Code MCP health check connects through
      `cairntir-mcp --host claude`
- [x] live database reindex explicitly approved and verified
- [ ] restart Codex and Claude so they reload v1.2 host provenance
- [ ] run Cursor smoke when Cursor is installed; automated adapter coverage
      remains the release fallback

Release operations:

- [ ] review the release-candidate diff and commit history
- [ ] push the release-candidate branch
- [ ] wait for CI on every supported operating system and Python version
- [ ] merge the reviewed release candidate
- [ ] with Patrick's explicit approval, create and push `v1.2.0`
- [ ] confirm the GitHub Release, PyPI Trusted Publishing, and provenance
      attestations
- [ ] install `cairntir==1.2.0` from PyPI in a fresh environment and run
      `cairntir version`, `cairntir --help`, and `cairntir recipe-list`

Evidence and known limits live in
[`docs/release/v1.2.0-rc.md`](release/v1.2.0-rc.md).

## Local verification

Run every command from the repository root:

```powershell
$env:HF_HUB_OFFLINE = "1"
uv sync --all-extras
uv run ruff format --check .
uv run ruff check .
uv run mypy --strict src
uv run python scripts/check_no_silent_except.py
uv run pytest -q
uv run mkdocs build --strict
uv build
```

Also confirm:

- `pyproject.toml`, `uv.lock`, `src/cairntir/__init__.py`, and
  `.claude-plugin/plugin.json` contain the same version;
- `CHANGELOG.md` has a dated entry and an empty Unreleased section;
- the public API snapshot and Store contract tests have not drifted;
- `.github/workflows/release.yml` verifies before it builds and publishes only
  from a version tag;
- the release artifacts contain the bundled recipes and plugin metadata;
- `git diff --check` is clean and no rehearsal database, virtual environment,
  secret, or local Cairntir home is staged.

## Remote acceptance and publication

1. Push the release-candidate branch and open or update its pull request.
2. Wait for every required CI job. Investigate failures; never bypass them.
3. Merge only the exact commit that passed review and CI.
4. Obtain Patrick's explicit approval to publish.
5. Create an annotated `v1.2.0` tag on that merged commit and push only that
   tag.
6. Watch the release workflow through verification, build, attestation, PyPI,
   and GitHub Release.
7. Compare the published artifact hashes with the workflow artifacts and run
   the fresh-install smoke above.

If any publish job fails after PyPI accepts the version, do not delete or reuse
the version. Diagnose the partial release, preserve the evidence, and ship the
smallest higher patch version if another artifact is required.

## Non-negotiable safeguards

- Never force-push a published branch or delete a released tag.
- Never paste a PyPI token into a task, terminal transcript, issue, or
  repository. Cairntir uses OIDC Trusted Publishing.
- Never tag from a dirty tree or an unreviewed commit.
- Never rewrite or delete a user's live memory database during release work.
  Reindex only after a verified backup and explicit approval.
- Never add telemetry. Cairntir remains local-first and useful offline.
- Never present an unavailable host or account-limited model run as a passing
  real-client test; record the limit and retain the automated fallback.
