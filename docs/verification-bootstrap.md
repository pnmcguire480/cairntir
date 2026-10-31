# Offline test bootstrap

The unpublished candidate can inspect a pure Python project and prepare its existing pytest tests in a versioned virtual environment. Preparation returns an executable command and an input receipt. It does not run the project tests or claim they passed.

The supported slice uses Python 3.11–3.13, a static `[project]` declaration in `pyproject.toml`, pre-existing `tests/test_*.py` files, and optional `src/` code. Project dependencies, build backends, mixed stacks and additional pytest configuration require a separate bootstrap. Direct execution evidence currently uses Windows and Python 3.11.9; this proof has not exercised other interpreter versions.

Call `inspect_test_infrastructure(project_root)` from `cairntir.paladin_bootstrap` to inspect metadata and bounded source bytes without importing project code. Unsupported inputs return `BLOCKED` with a named blocker. Inspection does not grant permission to install packages.

Call `prepare_test_bootstrap` with an output root separate from the project, explicit Python and uv executables, a caller-approved requirements file and its SHA256, and a local wheelhouse. Each nonblank requirements line must contain one exact `name==version --hash=sha256:...` pin. Include pytest and every transitive package. The wheelhouse must contain exactly those universal wheels. No network fallback or project build is performed. Caller-supplied approval is recorded as such; it does not authenticate a human.

A `PREPARED` result records the snapshot, lock, wheels, tool identities, installed versions and import origins. Its `command` contains `argv`, `cwd`, a clean `env` and `junit_path`. Execute that command only when project test execution is authorized, then inspect its actual exit and JUnit results. A virtual environment isolates dependencies; it is not a security sandbox for project code.

Identical inputs reuse their verified version without reinstalling. Changed inputs receive a different identity, preserving the old snapshot. Modified published bytes are refused. A failed preparation can retain its owned diagnostic directory, but cannot publish a successful receipt. Installed virtual environments stay at their original paths.

The proof uses independently authored decision-log tests. The unchanged tests pass on clean code, fail on a deliberately broken reversal, then pass on corrected source under a new version. This qualifies the bootstrap workflow separately from PALADIN stage results, protected evaluator custody and complete release qualification.
