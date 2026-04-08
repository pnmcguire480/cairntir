# Contributing to Cairntir

Thank you for considering contributing. Cairntir is a small, opinionated project with a clear mission: kill cross-chat AI amnesia. Contributions that serve that mission are welcome. Contributions that don't will be politely declined.

## Before You Start

1. **Read `docs/manifesto.md`** — understand *why* Cairntir exists.
2. **Read `docs/concept.md`** — understand *what* Cairntir is (three ingredients, nothing more).
3. **Read `ETHOS.md`** — the five principles that guide all decisions.
4. **Read the current plan** at `plans/purrfect-drifting-sparrow.md` — know the roadmap.
5. **Open a discussion or issue first** for anything larger than a typo fix. Silent surprise PRs are difficult to review.

## Ground Rules

- **Cairntir is deliberately minimal.** We say no to most features. Simplicity is the product.
- **Every exception is typed, logged, and surfaced.** CI will fail you if you introduce a bare `except:` or `except: pass`.
- **No hardcoded paths.** Use `platformdirs`, `pathlib.Path.home()`, or config.
- **No summarization of memory.** Verbatim only.
- **No dependencies added without discussion.** The dep list is the surface area.
- **No feature creep.** If you want a new skill beyond crucible / quality / reason, expect a high bar.

## Development Setup

```bash
git clone https://github.com/pnmcguire480/cairntir.git
cd cairntir
pip install uv           # if you don't have it
uv sync --all-extras --dev
uv run pre-commit install
uv run pre-commit install --hook-type commit-msg
```

Verify your setup:

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy --strict src
uv run pytest
```

All four commands should pass with zero warnings, zero errors, zero failures, and ≥80% coverage.

## Commit Messages

Cairntir uses **[Conventional Commits](https://www.conventionalcommits.org/)**. Format:

```
<type>(<optional scope>): <short description>

<optional body>

<optional footer>
```

Allowed types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`.

Examples:
- `feat(memory): add 4-layer retrieval loader`
- `fix(mcp): propagate wing filter to recall tool`
- `docs(lineage): clarify MemPalace AAAK decision`
- `test(store): cover add_drawer rollback path`

The `conventional-pre-commit` hook enforces this at commit time.

## Pull Request Process

1. Fork, branch (`feat/short-name` or `fix/short-name`)
2. Make your changes — small PRs are reviewed faster than large ones
3. Update `CHANGELOG.md` under `[Unreleased]` if user-facing
4. Ensure CI passes locally (ruff, mypy strict, pytest)
5. Open a PR using the template
6. Be patient — one maintainer in v1

## Testing Expectations

- **Unit tests** for every public function in `src/cairntir/`
- **Integration tests** for MCP tools and CLI commands
- **Eval tests** for memory retrieval accuracy (LongMemEval subset)
- Target: **≥80% branch coverage** (CI-enforced)
- Use pytest fixtures (`tests/conftest.py`) for shared setup
- Mark slow tests with `@pytest.mark.slow`

## Code Style

- `ruff format` is the only formatter
- `ruff check` is the only linter (with bandit / bugbear / pydocstyle built in)
- `mypy --strict` is mandatory
- Google-style docstrings for every public function and class
- Type hints for every function signature — no exceptions

## Reporting Bugs

Use the bug report issue template. Include Python version, OS, Cairntir version, and a minimal reproduction.

## Proposing Features

Use the feature request template. You will be asked *how does this serve the north star*. The answer should be specific.

## Security

Do not open a public issue for security reports. See `SECURITY.md`.

## Code of Conduct

All contributors are expected to follow the [Contributor Covenant 2.1](CODE_OF_CONDUCT.md).

---

*Welcome. Let's kill amnesia.*
