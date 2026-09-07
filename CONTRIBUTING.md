# Contributing

Read [ETHOS.md](ETHOS.md), the [current brief](CLAUDE.md), and the
[plan map](plans/README.md). Keep changes focused on shared project memory.

## Development

Use Python 3.11–3.13 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --locked --all-extras
uv run pre-commit install --install-hooks
uv run pre-commit install --hook-type commit-msg
```

The development environment uses this checkout. An installed `cairntir-mcp`
outside it may use a published package; inspect the launcher before assuming
source changes affect a running host. Tests must use temporary stores, not
your production memory.

## Required checks

```bash
uv run ruff check src tests scripts addons
uv run ruff format --check src tests scripts addons
uv run mypy --strict src
uv run pytest -m "not slow"
uv run pytest -m eval --no-cov
uv run pytest -m "slow and not eval" --no-cov
uv run python scripts/check_no_silent_except.py
uv run python scripts/check_release_tags.py
uv run python scripts/check_landed_commitments.py
uv run python scripts/check_seams.py
uv run python scripts/check_docs_links.py
uv run python scripts/check_dependency_advisories.py
uv run python scripts/check_verification_preservation.py
uv run python scripts/verify_history.py --output .cairntir/verification/history
uv run python scripts/verify_mutations.py --output .cairntir/verification/mutations
uv run mkdocs build --strict
uv build
uv run python scripts/verify_package.py --wheel dist/cairntir-1.12.1-py3-none-any.whl --output .cairntir/verification/package
```

The release-tag and dependency-advisory gates need network access to PyPI. Model-backed evaluation
may download weights. CI covers Linux, macOS, and Windows on Python 3.11–3.13.
The coverage floor is 92% of the configured statement-and-branch surface;
thin transport entrypoints retain their existing exclusions. The
[verification plan](plans/verification-structure.md) records the behavioral
evidence behind this gate. Do not add exclusions to improve the number.
Subprocess coverage includes SQLite helpers; installed CLI/MCP verification also
checks the excluded transport entrypoints directly.

Every fix needs a reproducer that fails against the actual broken behavior and
passes after repair. Preserve both results and the tested source/test identities.
An import error, broken fixture, skipped control or unrelated failure is not
behavioral evidence. Acceptance checks assert required user outcomes; a backup
must restore usable evidence and task history, not merely create a file.

Critical changes need a deliberate mutation in an isolated copy, with a passing
clean control and a specific failing assertion. Use disposable stores for SQLite
contention, interrupted processes and storage failures. Test both the reported
failure and the surviving data, then prove a corrected retry works. Existing
frozen acceptance artifacts remain unchanged. Review coverage afterward to find
missing outcomes and failure paths; execution alone does not prove correctness.

Package verification installs the built wheel into a disposable environment,
checks its installed bytes, and runs actual console scripts and MCP sessions
outside the source checkout. Provision the production model cache first with
`uv run python -c "from cairntir.memory.embeddings import production_embedding_provider; production_embedding_provider().embed(['verification'])"`.
It does not install into a user's production environment or restart host apps.

Local `cairntir doctor --gate` checks store integrity and optional vault drift.
Hosted CI cannot inspect your store and reports that limitation.

## Pull requests

Use a focused branch and Conventional Commits (`fix:`, `feat:`, `docs:`,
`test:`, `refactor:`, `build:`, `ci:`, or `chore:`). Add regression tests
for fixes, update `CHANGELOG.md` under `[Unreleased]`, and run the checks above.
All work reaches `main` through a green pull request.

Use typed, surfaced exceptions, strict type hints, Google-style public
docstrings, and Ruff formatting. Do not add dependencies without discussion.
Never edit `lineage/`; it is attribution and read-only historical evidence.
Keep executable commitments when retiring an old plan.

Report reproducible bugs through GitHub issues. Propose features against the
[roadmap](docs/roadmap.md) before implementing them. Security reports follow
[SECURITY.md](SECURITY.md), not public issues. The
[code of conduct](CODE_OF_CONDUCT.md) applies to all contributions.
