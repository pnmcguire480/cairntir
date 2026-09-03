# Publish Checklist — releasing Cairntir

This is the canonical release sequence — *how* to publish, once publishing has
been decided. Whether a release is warranted at all, and which version number it
gets, is [Release Cadence](release-cadence.md).

Code completion never authorizes publication. Pushing a `v*.*.*` tag starts the
trusted-publishing workflow, so the tag is an explicit human gate.

## Per-release acceptance

This is a template. Copy it into the release's own evidence document under
`docs/release/` and check items off *there* — leave the boxes here unchecked so
the next release starts from a clean list.

Automated acceptance:

- [ ] all tests, including the opt-in semantic eval
- [ ] Ruff lint and format
- [ ] mypy strict
- [ ] silent-exception scanner
- [ ] release tag check (`scripts/check_release_tags.py`)
- [ ] public API and Store contract suites
- [ ] strict MkDocs build
- [ ] sdist and wheel build
- [ ] isolated wheel install, redirected Windows help, and bundled-recipe smoke
- [ ] workflow YAML parses and all external actions use immutable SHAs

Operational acceptance:

- [ ] any schema migration/reindex rehearsed on an online backup of the real
      database; drawer count and full-table SHA-256 preserved
- [ ] project-local Claude/Codex/Cursor MCP and policy configuration reports
      ready
- [ ] real Claude Code MCP health check connects through
      `cairntir-mcp --host claude`
- [ ] live database reindex explicitly approved and verified, if one is needed
- [ ] restart Codex and Claude so they reload the new host provenance
- [ ] run Cursor smoke when Cursor is installed; automated adapter coverage
      remains the release fallback

Release operations:

- [ ] create the release-candidate branch and conventional checkpoints
- [ ] review the release-candidate diff, secret patterns, and local-only
      artifacts
- [ ] push the release-candidate branch and open its pull request
- [ ] wait for CI on every supported operating system and Python version
- [ ] merge the reviewed release candidate through the pull request, never by
      pushing directly to `main`
- [ ] with Patrick's explicit approval, create and push the version tag
- [ ] confirm the GitHub Release, PyPI Trusted Publishing, and provenance
      attestations
- [ ] install the published version from PyPI in a fresh environment and run
      `cairntir version`, `cairntir --help`, and `cairntir recipe-list`

## Past release records

Evidence and known limits for each shipped release live under `docs/release/`.
The latest published record is
[`docs/release/v1.9.0.md`](release/v1.9.0.md); the prior release is
[`docs/release/v1.8.0.md`](release/v1.8.0.md).

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
5. Create the candidate's annotated version tag on that merged commit and push
   only that tag.
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
