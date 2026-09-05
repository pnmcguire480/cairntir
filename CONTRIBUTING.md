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
uv run python scripts/check_no_silent_except.py
uv run python scripts/check_release_tags.py
uv run python scripts/check_landed_commitments.py
uv run python scripts/check_seams.py
uv run python scripts/check_docs_links.py
uv run python scripts/check_dependency_advisories.py
uv run mkdocs build --strict
uv build
```

The release-tag and dependency-advisory gates need network access to PyPI. Model-backed evaluation
may download weights. CI covers Linux, macOS, and Windows on Python 3.11–3.13.
The coverage floor is 80% of the configured surface, including branch
measurement; thin transport entrypoints are explicitly excluded.

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
