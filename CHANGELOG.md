# Changelog

All notable changes to Cairntir will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial repository bootstrap (Phase 0)
- Professional scaffolding: `pyproject.toml`, `ruff`, `mypy --strict`, `pytest`, `pre-commit`
- GitHub Actions CI: lint + test matrix (Python 3.11/3.12/3.13 on Linux/macOS/Windows), release, docs, CodeQL
- Issue templates, PR template, CODEOWNERS, Dependabot
- Core documentation: `README.md`, `CLAUDE.md`, `docs/manifesto.md`, `docs/concept.md`, `docs/roadmap.md`, lineage docs
- Community files: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `GOVERNANCE.md`, `ETHOS.md`
- Lineage material from BrainStormer preserved in `lineage/brainstormer/` (read-only)
- Ban on silent `except: pass` enforced by pre-commit hook and CI
- MIT license

### Planned (Phase 1)
- `sqlite-vec` memory backend
- Wing / Room / Drawer taxonomy
- 4-layer retrieval loader
- Local embeddings provider

[Unreleased]: https://github.com/pnmcguire480/cairntir/compare/v0.0.0...HEAD
